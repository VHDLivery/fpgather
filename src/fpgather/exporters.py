"""Export source lists by target tool and output format."""

import csv
import hashlib
import io
import json
import tempfile
from collections.abc import Iterable
from pathlib import Path

from .manifest import normalize_library_name
from .model import Source, SourcesError

STANDARDS = {
    "93": "1993",
    "1993": "1993",
    "02": "2002",
    "2002": "2002",
    "08": "2008",
    "2008": "2008",
    "19": "2019",
    "2019": "2019",
}


def _write_bytes(path: Path, data: bytes) -> None:
    """Atomically replace a file with new byte content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(data)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _vunit_csv(sources: list[Source], output: Path) -> Path:
    """Write CSV and settings that reference original VHDL files."""
    if output.suffix.lower() != ".csv":
        raise SourcesError("VUnit CSV output must have the .csv suffix")
    rows, metadata = [], []
    for source in sources:
        original = Path(source.path).resolve()
        library = normalize_library_name(source.library)
        if library == "work":
            raise SourcesError(
                "VUnit does not allow a library named work; "
                "use --work-lib-name top_lib"
            )
        if original.suffix.lower() not in {".vhd", ".vhdl", ".hdl"}:
            raise SourcesError(
                f"Unsupported VUnit CSV source suffix: {original.suffix}; "
                "currently VHDL only"
            )
        if source.language_version not in STANDARDS:
            raise SourcesError(
                "Unsupported VUnit VHDL standard "
                f"{source.language_version!r}: {original}"
            )
        if not original.is_file():
            raise SourcesError(f"Source file not found: {original}")
        absolute = original.as_posix()
        if absolute.strip() != absolute:
            raise SourcesError(
                f"VUnit strips surrounding path whitespace: {absolute!r}"
            )
        rows.append([library, absolute])
        metadata.append(
            {
                "library": library,
                "path": absolute,
                "original_path": original.as_posix(),
                "language_version": source.language_version,
                "vhdl_standard": STANDARDS[source.language_version],
            }
        )

    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="\n").writerows(rows)
    content = buffer.getvalue().encode("utf-8")
    settings = {
        "syntax_version": 1,
        "tool": "vunit",
        "file_type": "csv",
        "csv_sha256": hashlib.sha256(content).hexdigest(),
        "sources": metadata,
    }
    # Only metadata is written; original sources stay unchanged.
    settings_path = output.with_suffix(".settings.json")
    settings_content = (json.dumps(settings, indent=2) + "\n").encode("utf-8")
    _write_bytes(settings_path, settings_content)
    _write_bytes(output, content)
    return output


EXPORTERS = {("vunit", "csv"): _vunit_csv}


def export_sources(
    sources: Iterable[Source],
    output: str | Path,
    *,
    tool: str,
    file_type: str,
) -> Path:
    """Export sources for the selected tool and output format."""
    exporter = EXPORTERS.get((tool, file_type))
    if exporter is None:
        raise SourcesError(
            f"Unsupported export: tool={tool!r}, file_type={file_type!r}"
        )
    try:
        return exporter(list(sources), Path(output).resolve())
    except OSError as exc:
        raise SourcesError(f"Cannot write export {output}: {exc}") from exc
