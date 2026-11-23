"""Test original-path exports, the CLI and actual VUnit imports."""

import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from vunit import VUnit

from fpgather import Source, SourcesError, export_sources, resolve
from fpgather.vunit import import_vunit_csv


@pytest.fixture
def exported(tmp_path):
    root = tmp_path / "project with spaces"
    shutil.copytree(
        Path(__file__).parents[1] / "test",
        root,
        ignore=shutil.ignore_patterns("build", "__pycache__", ".DS_Store"),
    )
    sources = resolve(
        root / "src/rtl/scripts/sources.yml",
        project_root=root,
        library="top_lib",
    )
    output = root / "build/vunit/sources.csv"
    export_sources(sources, output, tool="vunit", file_type="csv")
    return root, sources, output


def test_csv_is_headerless_absolute_and_preserves_originals(exported):
    root, sources, output = exported
    with output.open(newline="") as stream:
        rows = list(csv.reader(stream))
    assert [row[0] for row in rows] == [
        "lib_b",
        "lib_b",
        "lib_b",
        "lib_a",
        "lib_a",
        "top_lib",
    ]
    assert all(len(row) == 2 and Path(row[1]).is_absolute() for row in rows)
    assert [Path(row[1]) for row in rows] == [
        source.path for source in sources
    ]
    assert all(Path(row[1]).is_relative_to(root) for row in rows)
    assert not (output.parent / "sources_files").exists()
    assert all((output.parent / row[1]).read_bytes() == b"" for row in rows)
    assert all(
        source.path.exists() and source.path.read_bytes() == b""
        for source in sources
    )
    assert len(list(root.rglob("*.vhd"))) == 7
    metadata = json.loads(output.with_suffix(".settings.json").read_text())
    assert all(
        Path(row["path"]).is_absolute()
        and Path(row["original_path"]).is_absolute()
        for row in metadata["sources"]
    )
    assert [row["vhdl_standard"] for row in metadata["sources"]] == [
        "2008",
        "2008",
        "1993",
        "2008",
        "2008",
        "2008",
    ]


def test_actual_vunit_native_csv_import_for_recognized_suffixes(
    tmp_path, monkeypatch
):
    sources = []
    for library, name in [("lib_a", "module_a.vhd"), ("top_lib", "top.vhdl")]:
        path = tmp_path / name
        path.touch()
        sources.append(Source(path, library, "2008"))
    output = export_sources(
        sources, tmp_path / "native.csv", tool="vunit", file_type="csv"
    )
    monkeypatch.chdir(tmp_path)
    vu = VUnit.from_argv(
        ["--output-path", str(tmp_path / "native_vunit")],
        compile_builtins=False,
    )
    files = vu.add_source_files_from_csv(output, vhdl_standard="2008")
    assert [Path(source.name).resolve() for source in files] == [
        source.path for source in sources
    ]
    assert sorted({source.library.name for source in files}) == [
        "lib_a",
        "top_lib",
    ]


def test_vunit_helper_applies_per_file_versions_and_order(exported, tmp_path):
    _, sources, output = exported
    vu = VUnit.from_argv(
        ["--output-path", str(tmp_path / "settings_vunit")],
        compile_builtins=False,
    )
    files = import_vunit_csv(vu, output)
    assert [Path(f.name).resolve() for f in files] == [
        source.path for source in sources
    ]
    assert [f.vhdl_standard for f in files] == [
        "2008",
        "2008",
        "93",
        "2008",
        "2008",
        "2008",
    ]
    assert [Path(f.name).name for f in vu.get_compile_order()] == [
        "module_b.vhd",
        "wide_datapath.vhd",
        "legacy.vhd",
        "module_a.vhd",
        "debug.vhd",
        "top.vhd",
    ]


def test_cli_accepts_tool_and_file_type_from_another_working_directory(
    tmp_path,
):
    root = Path(__file__).parents[1] / "test"
    output = tmp_path / "cli.csv"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fpgather",
            str(root / "src/rtl/scripts/sources.yml"),
            "--project-root",
            str(root),
            "--work-lib-name",
            "top_lib",
            "--tool",
            "vunit",
            "--file-type",
            "csv",
            "--output",
            str(output),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert len(list(csv.reader(output.open()))) == 6


@pytest.mark.parametrize(
    "tool,file_type", [("unknown", "csv"), ("vunit", "xml")]
)
def test_unsupported_export_does_not_create_output(tmp_path, tool, file_type):
    output = tmp_path / "no.csv"
    with pytest.raises(SourcesError, match="[Uu]nsupported"):
        export_sources([], output, tool=tool, file_type=file_type)
    assert not output.exists()


def test_supported_extensions_are_not_copied_and_csv_quotes_commas(tmp_path):
    source = tmp_path / "name, with spaces.vhd"
    source.write_text("-- original VHDL\n")
    output = tmp_path / "out/files.csv"
    export_sources(
        [Source(source, "lib_a", "2008")],
        output,
        tool="vunit",
        file_type="csv",
    )
    with output.open(newline="") as stream:
        assert list(csv.reader(stream)) == [["lib_a", str(source.resolve())]]


def test_absolute_csv_can_move_without_rebasing_paths(exported, tmp_path):
    _, _, output = exported
    moved = tmp_path / "moved/sources.csv"
    moved.parent.mkdir()
    shutil.copyfile(output, moved)
    shutil.copyfile(
        output.with_suffix(".settings.json"),
        moved.with_suffix(".settings.json"),
    )
    vu = VUnit.from_argv(
        ["--output-path", str(tmp_path / "moved_vunit")],
        compile_builtins=False,
    )
    files = import_vunit_csv(vu, moved)
    assert [Path(f.name).name for f in files] == [
        "module_b.vhd",
        "wide_datapath.vhd",
        "legacy.vhd",
        "module_a.vhd",
        "debug.vhd",
        "top.vhd",
    ]


def test_cli_default_work_explains_vunit_override(tmp_path):
    root = Path(__file__).parents[1] / "test"
    output = tmp_path / "default.csv"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fpgather",
            str(root / "src/rtl/scripts/sources.yml"),
            "--project-root",
            str(root),
            "--tool",
            "vunit",
            "--file-type",
            "csv",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "--work-lib-name" in result.stderr
    assert not output.exists()


def test_same_hdl_basename_keeps_both_original_paths(tmp_path):
    sources = []
    for folder, content in [("one", "-- one"), ("two", "-- two")]:
        path = tmp_path / folder / "unit.vhd"
        path.parent.mkdir()
        path.write_text(content)
        sources.append(Source(path, "lib_a", "2008"))
    output = tmp_path / "files.csv"
    export_sources(sources, output, tool="vunit", file_type="csv")
    with output.open(newline="") as stream:
        paths = [Path(row[1]) for row in csv.reader(stream)]
    assert paths == [source.path for source in sources]
    contents = [path.read_text() for path in paths]
    assert contents == ["-- one", "-- two"]


def test_backend_rejects_unsupported_standard_without_partial_csv(tmp_path):
    source = tmp_path / "file.vhd"
    source.touch()
    with pytest.raises(SourcesError, match="standard"):
        export_sources(
            [Source(source, "lib_a", "2099")],
            tmp_path / "bad.csv",
            tool="vunit",
            file_type="csv",
        )
    assert not (tmp_path / "bad.csv").exists()


@pytest.mark.parametrize("symlink_parent", [False, True])
def test_export_preserves_inputs_in_former_copy_directory(
    tmp_path, symlink_parent
):
    hdl = tmp_path / "unit.vhd"
    hdl.write_text("-- HDL input")
    destination = tmp_path / "sources_files/0001_lib_a"
    destination.mkdir(parents=True)
    if symlink_parent:
        original_folder = tmp_path / "original"
        original_folder.mkdir()
        destination.rmdir()
        destination.symlink_to(original_folder, target_is_directory=True)
        original = original_folder / "unit.vhd"
    else:
        original = destination / "unit.vhd"
    original.write_text("-- VHDL original must survive")
    output = tmp_path / "sources.csv"
    export_sources(
        [Source(hdl, "lib_a", "2008"), Source(original, "lib_a", "2008")],
        output,
        tool="vunit",
        file_type="csv",
    )
    assert original.read_text() == "-- VHDL original must survive"
    assert hdl.read_text() == "-- HDL input"
    with output.open(newline="") as stream:
        assert list(csv.reader(stream)) == [
            ["lib_a", str(hdl.resolve())],
            ["lib_a", str(original.resolve())],
        ]


def test_helper_rejects_stale_sidecar(exported, tmp_path):
    _, _, output = exported
    output.write_text(output.read_text().replace("lib_b", "other", 1))
    vu = VUnit.from_argv(
        ["--output-path", str(tmp_path / "stale_vunit")],
        compile_builtins=False,
    )
    with pytest.raises(SourcesError, match="[Mm]ismatch"):
        import_vunit_csv(vu, output)
