"""Import original sources into VUnit with per-file standards."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

from .exporters import STANDARDS
from .model import SourcesError

if TYPE_CHECKING:
    from vunit import VUnit
    from vunit.ui.source import SourceFile


def import_vunit_csv(vu: VUnit, csv_path: str | Path) -> list[SourceFile]:
    """Import our CSV + .settings.json using only public VUnit APIs.

    Native CSV import supports known suffixes and a common standard.
    This helper sets explicit file types and individual standards, so it
    also supports original .hdl paths.
    This helper must be used instead of, not after, the native import.
    """
    csv_path = Path(csv_path).resolve()
    try:
        content = csv_path.read_bytes()
        settings_path = csv_path.with_suffix(".settings.json")
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        with csv_path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.reader(stream))
        if (
            settings["syntax_version"] != 1
            or settings["tool"] != "vunit"
            or settings["file_type"] != "csv"
        ):
            raise SourcesError("Unsupported VUnit settings format")
        if hashlib.sha256(content).hexdigest() != settings["csv_sha256"]:
            raise SourcesError(
                "Mismatch between CSV and settings; regenerate the export"
            )
        records = settings["sources"]
        expected_rows = [
            [record["library"], record["path"]] for record in records
        ]
        if rows != expected_rows:
            raise SourcesError("Mismatch between CSV rows and settings")
        for record in records:
            if record["vhdl_standard"] not in STANDARDS.values():
                raise SourcesError(
                    f"Unsupported VHDL standard: {record['vhdl_standard']}"
                )
            if not (csv_path.parent / record["path"]).is_file():
                raise SourcesError(
                    f"Exported source file not found: {record['path']}"
                )
    except (
        OSError,
        UnicodeError,
        ValueError,
        KeyError,
        TypeError,
        csv.Error,
    ) as exc:
        raise SourcesError(f"{csv_path}: {exc}") from exc

    files, libraries = [], {}
    for record in records:
        name = record["library"]
        if name not in libraries:
            libraries[name] = vu.add_library(name, allow_duplicate=True)
        source = libraries[name].add_source_file(
            csv_path.parent / record["path"],
            file_type="vhdl",
            vhdl_standard=record["vhdl_standard"],
        )
        if files:
            source.add_dependency_on(files[-1])
        files.append(source)
    return files
