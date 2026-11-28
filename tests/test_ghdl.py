"""Exercise generated Bash scripts and real GHDL analysis."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from fpgather import Source, SourcesError, export_sources
from fpgather.cli import main


def source(root, name, library="work", version="2008", content=""):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return Source(path, library, version)


def fake_ghdl(root):
    executable = root / "tool ' $; ghdl"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "with open('calls.jsonl', 'a') as stream:\n"
        "    stream.write(json.dumps({'args': sys.argv[1:], "
        "'cwd': os.getcwd(), 'tmp': os.environ['TMPDIR']}) + '\\n')\n"
        "sys.exit(int(os.environ.get('FAIL_ANALYSIS', '0')))\n"
    )
    executable.chmod(0o755)
    return executable


def export(sources, root, **options):
    return export_sources(
        sources, root / "analyze.sh", tool="ghdl", file_type="sh", **options
    )


def test_order_libraries_quoting_and_options(tmp_path):
    sources = [
        source(tmp_path, "dir '/first $(touch INJECTED);\n.vhd", "common"),
        source(tmp_path, 'second `touch BAD` "*.vhd', "work", "1993"),
    ]
    build = tmp_path / "build '$; directory"
    script = export(
        sources,
        tmp_path,
        build_dir=build,
        ghdl=fake_ghdl(tmp_path),
        analysis_options=["-frelaxed-rules"],
    )
    subprocess.run([str(script)], cwd=tmp_path, check=True)
    calls = [
        json.loads(line)
        for line in (build / "calls.jsonl").read_text().splitlines()
    ]
    assert [c["args"][-1] for c in calls] == [str(s.path) for s in sources]
    for call, lib, std in zip(calls, ["common", "work"], ["08", "93"]):
        assert call["cwd"] == str(build)
        assert Path(call["tmp"]).is_relative_to(build)
        assert call["args"][:2] == ["-a", f"--std={std}"]
        assert f"--work={lib}" in call["args"]
        assert f"--workdir={build / lib}" in call["args"]
        assert f"-P{build / 'common'}" in call["args"]
        assert f"-P{build / 'work'}" in call["args"]
        assert "-frelaxed-rules" in call["args"]
    assert not (tmp_path / "INJECTED").exists()
    assert not (build / "INJECTED").exists()
    assert not (build / "BAD").exists()
    assert not script.with_suffix(".settings.json").exists()
    assert all(s.path.read_text() == "" for s in sources)


@pytest.mark.parametrize(
    "version,standard",
    [
        ("1987", "87"),
        ("87", "87"),
        ("1993", "93"),
        ("93", "93"),
        ("93c", "93c"),
        ("2000", "00"),
        ("00", "00"),
        ("2002", "02"),
        ("02", "02"),
        ("2008", "08"),
        ("08", "08"),
        ("2019", "19"),
        ("19", "19"),
    ],
)
def test_standard_mapping(tmp_path, version, standard):
    script = export([source(tmp_path, "a.vhd", version=version)], tmp_path)
    assert f"--std={standard}" in script.read_text()


def test_failure_stops_analysis_and_preserves_exit_code(tmp_path):
    script = export(
        [source(tmp_path, "a.vhd"), source(tmp_path, "b.vhd")],
        tmp_path,
        build_dir=tmp_path / "build",
        ghdl=fake_ghdl(tmp_path),
    )
    result = subprocess.run(
        [str(script)], env={**os.environ, "FAIL_ANALYSIS": "37"}
    )
    assert result.returncode == 37
    assert len((tmp_path / "build/calls.jsonl").read_text().splitlines()) == 1


@pytest.mark.parametrize(
    "option",
    [
        "--workdir=/tmp/outside",
        "--work=other",
        "--std=93",
        "-e",
        "-o",
        "-P/tmp/lib",
        "@options.txt",
        "-Wc,-o,/tmp/outside",
        "-frelaxed-rules; touch BAD",
    ],
)
def test_unsafe_options_rejected_before_writing(tmp_path, option):
    with pytest.raises(SourcesError, match="analysis option"):
        export([], tmp_path, analysis_options=[option])
    assert not (tmp_path / "analyze.sh").exists()


@pytest.mark.parametrize("version,suffix", [("2023", ".vhd"), ("2008", ".sv")])
def test_invalid_source_rejected(tmp_path, version, suffix):
    with pytest.raises(SourcesError, match="Unsupported GHDL"):
        export([source(tmp_path, "a" + suffix, version=version)], tmp_path)
    assert not (tmp_path / "analyze.sh").exists()


def test_symlink_cannot_redirect_build_writes(tmp_path):
    build = tmp_path / "build"
    build.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (build / "work").symlink_to(outside, target_is_directory=True)
    script = export(
        [source(tmp_path, "a.vhd")],
        tmp_path,
        build_dir=build,
        ghdl=fake_ghdl(tmp_path),
    )
    result = subprocess.run([str(script)], capture_output=True, text=True)
    assert result.returncode != 0
    assert "symlink" in result.stderr.lower()
    assert list(outside.iterdir()) == []


def test_cli_and_relative_paths(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    source(tmp_path, "a.vhd")
    (tmp_path / "sources.yml").write_text(
        'language_defaults: {".vhd": "2008"}\nsources: [a.vhd]\n'
    )
    tool = fake_ghdl(tmp_path)
    assert (
        main(
            [
                "sources.yml",
                "--project-root",
                ".",
                "--tool",
                "ghdl",
                "--file-type",
                "sh",
                "--output",
                "analyze.sh",
                "--build-dir",
                "results",
                "--ghdl",
                "./" + tool.name,
                "--ghdl-option=-frelaxed-rules",
                "--ghdl-standard",
                "highest",
            ]
        )
        == 0
    )
    assert "settings.json" not in capsys.readouterr().out
    subprocess.run([str(tmp_path / "analyze.sh")], cwd="/", check=True)
    assert (tmp_path / "results/calls.jsonl").is_file()


def test_vunit_rejects_ghdl_options(tmp_path):
    with pytest.raises(SourcesError, match="GHDL"):
        export_sources(
            [],
            tmp_path / "a.csv",
            tool="vunit",
            file_type="csv",
            build_dir=tmp_path / "build",
        )


@pytest.mark.skipif(not shutil.which("ghdl"), reason="GHDL is not installed")
def test_real_ghdl_cross_library_analysis(tmp_path):
    sources = [
        source(
            tmp_path,
            "input '/types $;.vhd",
            "common",
            content=(
                "package types is constant width : integer := 8; "
                "end package;\n"
            ),
        ),
        source(
            tmp_path,
            "core.vhd",
            content=(
                "library common; use common.types.all;\n"
                "entity core is end entity;\n"
                "architecture rtl of core is\n"
                "signal value : bit_vector(width - 1 downto 0);\n"
                "begin end architecture;\n"
            ),
        ),
        source(
            tmp_path,
            "legacy.vhd",
            "legacy",
            "1993",
            "entity legacy is end entity;\n",
        ),
    ]
    before = {s.path: s.path.read_bytes() for s in sources}
    build = tmp_path / "build"
    script = export(
        sources,
        tmp_path,
        build_dir=build,
        analysis_options=["-frelaxed-rules"],
    )
    subprocess.run([str(script)], cwd=tmp_path, check=True)
    assert (build / "common/common-obj08.cf").is_file()
    assert (build / "work/work-obj08.cf").is_file()
    assert (build / "legacy/legacy-obj93.cf").is_file()
    assert all(p.read_bytes() == content for p, content in before.items())
    sources[0].path.write_text("this is invalid VHDL;\n")
    result = subprocess.run([str(script)], capture_output=True, text=True)
    assert result.returncode != 0


@pytest.mark.parametrize(
    "setting,expected",
    [
        (None, ["93", "02", "08"]),
        ("highest", ["08", "08", "08"]),
        ("2002", ["02", "02", "02"]),
        ("08", ["08", "08", "08"]),
    ],
)
def test_common_standard_selection(tmp_path, setting, expected):
    sources = [
        source(tmp_path, f"{i}.vhd", version=version)
        for i, version in enumerate(["1993", "2002", "2008"])
    ]
    script = export(
        sources,
        tmp_path,
        build_dir=tmp_path / "build",
        ghdl=fake_ghdl(tmp_path),
        ghdl_standard=setting,
    )
    subprocess.run([str(script)], check=True)
    calls = [
        json.loads(line)["args"]
        for line in (tmp_path / "build/calls.jsonl").read_text().splitlines()
    ]
    assert [args[1] for args in calls] == [f"--std={s}" for s in expected]
    assert [s.language_version for s in sources] == ["1993", "2002", "2008"]


@pytest.mark.parametrize(
    "versions,expected",
    [
        (["87", "93", "00"], "00"),
        (["93", "93c"], "93c"),
        (["2008", "2019"], "19"),
    ],
)
def test_highest_uses_chronology_not_numeric_order(
    tmp_path, versions, expected
):
    sources = [
        source(tmp_path, f"{i}.vhd", version=v) for i, v in enumerate(versions)
    ]
    script = export(sources, tmp_path, ghdl_standard="highest")
    assert script.read_text().count(f"--std={expected}\n") == len(sources)


def test_unknown_standard_rejected_even_with_override(tmp_path):
    with pytest.raises(SourcesError, match="Unsupported GHDL VHDL standard"):
        export(
            [source(tmp_path, "a.vhd", version="2099")],
            tmp_path,
            ghdl_standard="2008",
        )
    with pytest.raises(
        SourcesError, match="Unsupported GHDL standard override"
    ):
        export([], tmp_path, ghdl_standard="2099")


@pytest.mark.skipif(not shutil.which("ghdl"), reason="GHDL is not installed")
def test_real_ghdl_highest_resolves_cross_standard_dependency(tmp_path):
    sources = [
        source(
            tmp_path,
            "types.vhd",
            "common",
            "1993",
            "package types is constant width : integer := 8; end package;\n",
        ),
        source(
            tmp_path,
            "core.vhd",
            "work",
            "2008",
            "library common; use common.types.all;\n"
            "entity core is end entity;\n"
            "architecture rtl of core is\n"
            "signal x : bit_vector(width - 1 downto 0);\n"
            "begin end architecture;\n",
        ),
    ]
    script = export(sources, tmp_path, build_dir=tmp_path / "per-source")
    assert subprocess.run([str(script)], capture_output=True).returncode != 0
    script = export(
        sources,
        tmp_path,
        build_dir=tmp_path / "common-standard",
        ghdl_standard="highest",
    )
    subprocess.run([str(script)], check=True)
    assert (tmp_path / "common-standard/common/common-obj08.cf").is_file()
    assert (tmp_path / "common-standard/work/work-obj08.cf").is_file()
