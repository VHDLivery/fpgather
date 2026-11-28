"""Command-line entry point."""

import argparse
from collections.abc import Sequence

from .exporters import export_sources
from .model import SourcesError
from .resolver import resolve


def main(argv: Sequence[str] | None = None) -> int:
    """Resolve a manifest and export its selected sources."""
    parser = argparse.ArgumentParser(
        description="Resolve sources.yml and export an HDL build file list."
    )
    parser.add_argument("entry", help="Entry sources.yml")
    parser.add_argument(
        "--project-root",
        required=True,
        help="Project root for resolving a relative libraries root",
    )
    parser.add_argument(
        "--libraries-root",
        default="target/dependency",
        help=(
            "Directory containing library folders; absolute or relative "
            "to --project-root (default: target/dependency)"
        ),
    )
    parser.add_argument(
        "--work-lib-name",
        "--library",
        dest="work_lib_name",
        default="work",
        help=(
            "Library for entry sources "
            "(default: work; use e.g. top_lib for VUnit)"
        ),
    )
    parser.add_argument(
        "--tool", required=True, help="Target tool (vunit or ghdl)"
    )
    parser.add_argument(
        "--file-type", required=True, help="Output format (csv or sh)"
    )
    parser.add_argument(
        "--output", required=True, help="Output CSV or Bash script path"
    )
    parser.add_argument(
        "--build-dir", help="GHDL build directory (default: build/ghdl)"
    )
    parser.add_argument("--ghdl", help="GHDL executable (default: ghdl)")
    parser.add_argument(
        "--ghdl-option",
        action="append",
        dest="analysis_options",
        help="Repeatable analysis flag, e.g. --ghdl-option=-frelaxed-rules",
    )
    parser.add_argument(
        "--ghdl-standard",
        help="Common GHDL standard: highest or a version such as 2008",
    )
    args = parser.parse_args(argv)
    try:
        sources = resolve(
            args.entry,
            project_root=args.project_root,
            libraries_root=args.libraries_root,
            library=args.work_lib_name,
        )
        output = export_sources(
            sources,
            args.output,
            tool=args.tool,
            file_type=args.file_type,
            build_dir=args.build_dir,
            ghdl=args.ghdl,
            analysis_options=args.analysis_options,
            ghdl_standard=args.ghdl_standard,
        )
    except SourcesError as exc:
        parser.exit(2, f"error: {exc}\n")
    print(f"Exported {len(sources)} sources: {output}")
    if args.tool != "vunit":
        return 0
    print(
        f"Per-file language settings: {output.with_suffix('.settings.json')}"
    )
    if any(source.path.suffix.lower() == ".hdl" for source in sources):
        print(
            "Original .hdl paths retained: use "
            "fpgather.vunit.import_vunit_csv for explicit VHDL typing."
        )
    if len({source.language_version for source in sources}) > 1:
        print(
            "Mixed language versions: use "
            "fpgather.vunit.import_vunit_csv to preserve them."
        )
    return 0
