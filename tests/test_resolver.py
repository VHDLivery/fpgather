"""Test manifest validation, source selection and traversal."""

import shutil
from pathlib import Path

import pytest
import yaml

from fpgather import SourcesError, resolve


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    shutil.copytree(
        Path(__file__).parents[1] / "test",
        root,
        ignore=shutil.ignore_patterns("build", "__pycache__", ".DS_Store"),
    )
    return root


def write_manifest(
    path, *, sources=(), dependencies=None, defines=None, **extra
):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "syntax_version": 1,
        "language_defaults": {".vhd": "2008"},
        "sources": list(sources),
        "dependencies": dependencies or {},
        "defines": defines or {},
        **extra,
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


def test_three_levels_inherit_types_order_sources_and_override_version(
    project,
):
    result = resolve(
        project / "src/rtl/scripts/sources.yml",
        project_root=project,
        library="top_lib",
    )
    assert [(s.library, s.path.name, s.language_version) for s in result] == [
        ("lib_b", "module_b.vhd", "2008"),
        ("lib_b", "wide_datapath.vhd", "2008"),
        ("lib_b", "legacy.vhd", "93"),
        ("lib_a", "module_a.vhd", "2008"),
        ("lib_a", "debug.vhd", "2008"),
        ("top_lib", "top.vhd", "2008"),
    ]
    assert all(
        s.path.is_absolute() and s.path.stat().st_size == 0 for s in result
    )


def test_work_library_defaults_to_work(project):
    result = resolve(
        project / "src/rtl/scripts/sources.yml", project_root=project
    )
    assert [(s.library, s.path.name) for s in result][-1] == (
        "work",
        "top.vhd",
    )
    assert {s.library for s in result[:-1]} == {"lib_a", "lib_b"}


@pytest.mark.parametrize(
    "defines, condition, included",
    [
        ({}, "debug", False),
        ({"debug": False}, "debug", False),
        ({"debug": True}, "debug", True),
        ({"debug": 1}, "debug", False),
        ({"debug": "true"}, "debug", False),
        ({"target": "xilinx"}, {"target": "xilinx"}, True),
        ({"target": "intel"}, {"target": "xilinx"}, False),
        ({}, {"target": "xilinx"}, False),
        ({"width": 32}, {"width": 32}, True),
        ({"width": "32"}, {"width": 32}, False),
        ({"width": True}, {"width": 1}, False),
        ({"width": 32.0}, {"width": 32}, True),
        (
            {"target": "xilinx", "debug": False},
            {"target": "xilinx", "debug": True},
            False,
        ),
    ],
)
def test_conditions_do_not_use_truthiness_or_bool_number_coercion(
    tmp_path, defines, condition, included
):
    entry = write_manifest(
        tmp_path / "sources.yml",
        defines=defines,
        sources=[{"selected.vhd": {"if": condition}}],
    )
    if included:
        touch(tmp_path / "selected.vhd")
    result = resolve(entry, project_root=tmp_path, library="top_lib")
    assert [s.path.name for s in result] == (
        ["selected.vhd"] if included else []
    )


def test_multiple_manifests_local_defines_do_not_leak_and_context_is_revisited(
    tmp_path,
):
    base = tmp_path / "target/dependency/lib_a"
    for name in ("enabled.vhd", "disabled.vhd"):
        touch(base / name)
    write_manifest(
        base / "shared.yml",
        sources=[
            {"enabled.vhd": {"if": "debug"}},
            {"disabled.vhd": {"if": {"debug": False}}},
        ],
    )
    write_manifest(
        base / "a.yml",
        defines={"debug": False},
        dependencies={"lib_a": ["shared.yml"]},
    )
    write_manifest(base / "b.yml", dependencies={"lib_a": ["shared.yml"]})
    entry = write_manifest(
        tmp_path / "sources.yml",
        defines={"debug": True},
        dependencies={"lib_a": ["a.yml", "b.yml", "shared.yml"]},
    )
    result = resolve(entry, project_root=tmp_path, library="top_lib")
    assert [s.path.name for s in result] == ["disabled.vhd", "enabled.vhd"]


def test_missing_conditional_dependency_is_not_opened(tmp_path):
    entry = write_manifest(
        tmp_path / "sources.yml",
        dependencies={"lib_a": [{"missing.yml": {"if": "undefined"}}]},
    )
    assert resolve(entry, project_root=tmp_path, library="top_lib") == []


def test_cycle_reports_manifest_chain(tmp_path):
    base = tmp_path / "target/dependency/lib_a"
    a = write_manifest(base / "a.yml", dependencies={"lib_a": ["b.yml"]})
    write_manifest(base / "b.yml", dependencies={"lib_a": ["a.yml"]})
    with pytest.raises(SourcesError, match=r"[Cc]ycle.*a.yml.*b.yml.*a.yml"):
        resolve(a, project_root=tmp_path, library="lib_a")


def test_more_than_python_recursion_limit(tmp_path):
    base = tmp_path / "target/dependency/lib_a"
    for index in range(1050):
        write_manifest(
            base / f"{index}.yml", dependencies={"lib_a": [f"{index + 1}.yml"]}
        )
    write_manifest(base / "1050.yml", sources=["leaf.vhd"])
    touch(base / "leaf.vhd")
    result = resolve(base / "0.yml", project_root=tmp_path, library="lib_a")
    assert [s.path.name for s in result] == ["leaf.vhd"]


def test_conflicting_standards_for_shared_source_are_not_silently_dropped(
    tmp_path,
):
    touch(tmp_path / "same.vhd")
    entry = write_manifest(
        tmp_path / "sources.yml",
        sources=["same.vhd", {"same.vhd": {"language_version": "93"}}],
    )
    with pytest.raises(SourcesError, match="[Cc]onflicting"):
        resolve(entry, project_root=tmp_path, library="top_lib")


@pytest.mark.parametrize(
    "content",
    [
        "syntax_version: 2\n",
        "syntax_version: true\n",
        "syntax_version: null\n",
        'syntax_version: "1"\n',
        "syntax_version: 1\nsyntax_version: 1\n",
        "syntax_version: 1\nsources: bad\n",
        "syntax_version: 1\ndefines: {debug: [true]}\n",
        "syntax_version: 1\nlanguage_defaults: {'.vhd': 2008}\n",
        "syntax_version: 1\nsources: [{file.vhd: {iff: debug}}]\n",
        "syntax_version: 1\nsources: [{file.vhd: {if: []}}]\n",
        "syntax_version: 1\nsources: [{file.vhd: {if: {}}}]\n",
    ],
)
def test_invalid_manifest_is_reported_with_its_filename(tmp_path, content):
    entry = tmp_path / "bad.yml"
    entry.write_text(content)
    with pytest.raises(SourcesError, match="bad.yml"):
        resolve(entry, project_root=tmp_path, library="top_lib")


def test_missing_active_source_and_default_report_context(tmp_path):
    entry = write_manifest(tmp_path / "sources.yml", sources=["missing.vhd"])
    with pytest.raises(SourcesError, match="missing.vhd"):
        resolve(entry, project_root=tmp_path, library="top_lib")
    touch(tmp_path / "file.vhdl")
    write_manifest(entry, sources=["file.vhdl"])
    with pytest.raises(SourcesError, match="language"):
        resolve(entry, project_root=tmp_path, library="top_lib")


def test_dependency_cannot_escape_its_library(tmp_path):
    entry = write_manifest(
        tmp_path / "sources.yml", dependencies={"lib_a": ["../outside.yml"]}
    )
    with pytest.raises(SourcesError, match="[Oo]utside"):
        resolve(entry, project_root=tmp_path, library="top_lib")


@pytest.mark.parametrize("relative", [True, False])
def test_custom_libraries_root_at_every_depth(project, relative):
    destination = project / "vendor"
    shutil.move(project / "target/dependency", destination)
    result = resolve(
        project / "src/rtl/scripts/sources.yml",
        project_root=project,
        libraries_root="vendor" if relative else destination,
    )
    assert len(result) == 6
    assert all(s.path.is_relative_to(destination) for s in result[:-1])
    assert result[-1].library == "work"


def test_omitted_syntax_version_defaults_to_one(project):
    for manifest in project.rglob("sources.yml"):
        data = yaml.safe_load(manifest.read_text())
        data.pop("syntax_version")
        manifest.write_text(yaml.safe_dump(data))
    result = resolve(
        project / "src/rtl/scripts/sources.yml", project_root=project
    )
    assert len(result) == 6


def test_custom_libraries_root_rejects_escape(tmp_path):
    entry = write_manifest(
        tmp_path / "sources.yml", dependencies={"lib_a": ["../outside.yml"]}
    )
    with pytest.raises(SourcesError, match="[Oo]utside"):
        resolve(entry, project_root=tmp_path, libraries_root="vendor")


def test_cli_custom_libraries_root(project, tmp_path):
    from fpgather.cli import main

    shutil.move(project / "target/dependency", project / "vendor")
    output = tmp_path / "sources.csv"
    assert (
        main(
            [
                str(project / "src/rtl/scripts/sources.yml"),
                "--project-root",
                str(project),
                "--libraries-root",
                "vendor",
                "--work-lib-name",
                "top_lib",
                "--tool",
                "vunit",
                "--file-type",
                "csv",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert len(output.read_text().splitlines()) == 6
    assert str(project / "vendor") in output.read_text()
