"""Verify the three-level sources.yml fixture through VUnit."""

from pathlib import Path
from tempfile import TemporaryDirectory

from vunit import VUnit

from fpgather import export_sources, resolve
from fpgather.vunit import import_vunit_csv


def main():
    root = Path(__file__).resolve().parent
    sources = resolve(
        root / "src/rtl/scripts/sources.yml",
        project_root=root,
        library="top_lib",
    )
    expected = [
        ("lib_b", "module_b.vhd", "2008"),
        ("lib_b", "wide_datapath.vhd", "2008"),
        ("lib_b", "legacy.vhd", "93"),
        ("lib_a", "module_a.vhd", "2008"),
        ("lib_a", "debug.vhd", "2008"),
        ("top_lib", "top.vhd", "2008"),
    ]
    assert [
        (s.library, s.path.name, s.language_version) for s in sources
    ] == expected
    output = export_sources(
        sources,
        root / "build/vunit/sources.csv",
        tool="vunit",
        file_type="csv",
    )

    with TemporaryDirectory(prefix="fpgather-vunit-") as temporary:
        vu = VUnit.from_argv(
            ["--output-path", str(Path(temporary) / "native")],
            compile_builtins=False,
        )
        native_files = vu.add_source_files_from_csv(
            output, vhdl_standard="2008"
        )
        assert [Path(f.name).resolve() for f in native_files] == [
            source.path for source in sources
        ]

        vu = VUnit.from_argv(
            ["--output-path", str(Path(temporary) / "settings")],
            compile_builtins=False,
        )
        files = import_vunit_csv(vu, output)
        assert [Path(f.name).resolve() for f in files] == [
            source.path for source in sources
        ]
        assert all(source.path.is_relative_to(root) for source in sources)
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

    print(
        "PASS: 3 YAML levels; inherited bool/string/number definitions; "
        "6 selected sources."
    )
    print(
        "PASS: native VUnit CSV import and original .vhd paths "
        "with individual VHDL standards."
    )
    print(f"CSV: {output}")
    print(output.read_text(encoding="utf-8"), end="")


if __name__ == "__main__":
    main()
