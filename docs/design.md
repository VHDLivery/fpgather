# sources.yml → build inputs

## Manifest contract

`syntax_version` is optional and defaults to version 1, even after upgrades.
Explicit values must be supported integer versions. `language_defaults` maps suffixes to language
versions expressed as strings. `sources` is an ordered list of paths or entries
such as `{path: {language_version: "93", if: debug}}`.
Source paths are relative to their YAML file. `dependencies` maps libraries
to lists of YAML paths, resolved at every level against the central
`<libraries_root>/<library>/` directory. `libraries_root` defaults to
`target/dependency`, relative to `project_root`; absolute paths are supported.
The same configured root applies throughout the dependency graph.

`defines` contains user-defined booleans, strings or finite numbers. A manifest
inherits its parent's definitions and can override them within its own subtree.
`if: debug` checks for boolean true; `if: {target: xilinx}` checks equality.
Multiple comparison keys are combined with AND. Missing definitions or false
conditions exclude the entry without requiring its file to exist.
Boolean true is distinct from numeric 1.

## Resolver

Iterative depth-first traversal processes dependencies before local sources
without Python's recursion limit. Manifest visits are distinguished by path,
library and effective definitions. Active paths detect cycles. Each source
appears once per library; conflicting versions are errors. Relative dependency
paths cannot escape their central library directory. No repositories are fetched.

## Export

CLI: `fpgather ENTRY --project-root ROOT --work-lib-name LIB --tool vunit
--file-type csv --output FILE`. Optional `--libraries-root DIR` selects the
central library directory. Relative values are resolved against
`--project-root`. The Python API accepts the same `libraries_root` option.
Tool and output format select an exporter.
`--work-lib-name` defaults to `work`, independently of the selected tool;
`--library` is an alias. For VUnit, callers explicitly select a concrete library
such as `top_lib`, since VUnit rejects the reserved name `work`.
The Python API likewise defaults to `library="work"`.
Dependency libraries retain their declared names.

The initial exporter supports VHDL (`.vhd`, `.vhdl` and `.hdl`). It explicitly
rejects unsupported languages and standards rather than silently losing settings.

The CSV has no header and exactly two columns: `library,path`.
Every path is absolute and points to the original source file. The exporter
does not copy, move, rename or modify sources. All selected files in the
example remain under `test/`, in their original `src/rtl/hdl/` directories.
Only CSV and JSON metadata are regenerated for each build.

## VUnit integration

The CSV cannot store individual language versions or explicit file types.
A JSON companion preserves versions and absolute source paths, with a CSV hash
to detect mismatched exports. The helper reads both files and uses public VUnit
APIs to set per-file standards and explicit compile dependencies. It passes
`file_type="vhdl"` and imports sources at their original paths.
No private VUnit attributes are modified.

Native `add_source_files_from_csv` can import recognized suffixes such as `.vhd`
and `.vhdl` with a common standard, including the supplied `.vhd` fixture.
The helper is required to preserve its per-file standards.

## Verification

The Python test suite uses isolated copies of the existing three-level fixture.
It checks recursive selection, inherited definitions, original absolute paths,
native import of recognized suffixes and helper import of original `.vhd` paths.
`test/run.py` regenerates the example CSV and validates it against actual VUnit
objects without a simulator. Empty HDL files are not a runnable hardware testbench.

Reference: [VUnit CSV import](https://vunit.github.io/py/vunit.html#vunit.ui.VUnit.add_source_files_from_csv).

## GHDL integration

The `ghdl`/`sh` exporter produces executable Bash for analysis only. It preserves
resolved order and original absolute paths, with one build subdirectory per
library and `-P` search paths for all selected libraries. Bash arrays preserve
literal arguments; allowed extra flags cannot override compiler output paths.

Per-source standards are retained by default. `ghdl_standard="highest"` selects
the newest declared standard for every selected source; an explicit standard
applies that version to all sources. Neither changes the source objects.
Unknown standards are rejected. GHDL reports language incompatibilities and
unsupported compiler features at execution time.

See [GHDL usage](ghdl.md) for CLI/API examples, flags and execution boundaries.
