# fpgather

Gather your FPGA sources. Build in order.

A Python package that recursively resolves `sources.yml` files and exports an
HDL build list. An external tool supplies module repositories at
`target/dependency/<library>/<module>` by default; the library root is
configurable. This package does not fetch repositories.

## Installation

Requires Python 3.10 or newer:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
```

For the resolver and exporter alone, use `pip install .`. Their only runtime
dependency is PyYAML. The test extra installs pytest and VUnit.

## Run the example

From the package directory:

```sh
.venv/bin/fpgather test/src/rtl/scripts/sources.yml \
  --project-root test \
  --work-lib-name top_lib \
  --tool vunit \
  --file-type csv \
  --output test/build/vunit/sources.csv
```

Alternatively, use `.venv/bin/python -m fpgather` with the same arguments.

- `--project-root` locates the project directory.
- `--libraries-root` selects the directory containing the library folders.
  It defaults to `target/dependency` and accepts an absolute path or a path
  relative to `--project-root`. The same root applies at every inclusion depth.
- `--work-lib-name` sets the entry manifest's library. Its tool-independent
  default is `work`. VUnit rejects that reserved name, so select a concrete
  name such as `top_lib` for VUnit. `--library` remains an alias.
- `--tool` selects the target tool; currently `vunit` is supported.
- `--file-type` selects the **output format**, not a source suffix filter.
  Currently `csv` is supported.
- `--output` selects the CSV location. Each run regenerates the CSV and its
  `.settings.json` companion file.

The Python resolver has the corresponding default:
`resolve(entry, project_root=root, library="work")`.
Pass `libraries_root="vendor"` to use `<project-root>/vendor/<library>/`,
or supply an absolute path to a shared library directory. The CLI equivalent
is `--libraries-root vendor`; source paths remain relative to their YAML file.
Additional tool/format combinations can be added to the registry in
`src/fpgather/exporters.py` without changing dependency resolution.

## Manifest format

```yaml
syntax_version: 1

language_defaults:
  ".vhd": "2008"
  ".vhdl": "2008"

defines:
  debug: true
  target: xilinx
  data_width: 32

sources:
  - ../hdl/core.vhd
  - ../hdl/debug.vhd:
      if: debug
  - ../hdl/legacy.vhd:
      language_version: "93"
      if:
        data_width: 32

dependencies:
  lib_a:
    - module_a/src/rtl/scripts/sources.yml
    - module_d/src/rtl/scripts/sources.yml:
        if:
          target: xilinx
```

- `syntax_version` is optional. Omitting it always means version 1, including
  after future upgrades. Explicit unsupported versions are rejected.
- Source paths are relative to the YAML file containing them.
- Dependency paths are relative to `<libraries-root>/<library>/` at every
  inclusion depth. The default is `<project-root>/target/dependency/<library>/`.
- Each library can reference multiple manifests.
- Definitions are inherited by child manifests. Local definitions override
  inherited values only within that subtree; siblings are unaffected.
- `if: debug` requires boolean `true`. A comparison mapping checks equality;
  multiple entries in that mapping are combined with AND.
- Missing definitions and false conditions skip the entry. A skipped source
  or dependency file does not need to exist. Conditions do not execute code.
- Strings and numbers are not coerced, and `true` is distinct from `1`.
- Language defaults apply only to sources in the declaring manifest.
  A file's `language_version` overrides its suffix default. Versions are strings.
- Dependencies are processed first; list order is preserved. A shared source
  appears once per library. Conflicting versions, cycles, missing active files
  and invalid YAML produce errors with file context.
- Library names are normalized to lowercase; their directory names must match.
- An explicit stack supports deep inclusion graphs without Python recursion.

## Original source paths

The CSV contains **absolute paths to the original files**, including their
original suffixes. The exporter never copies, moves or renames HDL files.
Only the CSV and its settings file are written.

In the supplied example, all six selected files remain under `test/`:

```text
test/target/dependency/lib_b/module_b/src/rtl/hdl/module_b.vhd
test/target/dependency/lib_b/module_b/src/rtl/hdl/wide_datapath.vhd
test/target/dependency/lib_b/module_b/src/rtl/hdl/legacy.vhd
test/target/dependency/lib_a/module_a/src/rtl/hdl/module_a.vhd
test/target/dependency/lib_a/module_a/src/rtl/hdl/debug.vhd
test/src/rtl/hdl/top.vhd
```

The CSV prefixes these paths with the absolute package directory.
`optional.vhd` remains in its original directory but is excluded because
`optional_feature` is undefined. No source path points into `test/build/`.

CSV and settings can be stored in a temporary directory or moved together
without rebasing source paths. Original sources must exist when imported.

## Import into VUnit

The CSV has **no header** and exactly two columns: `library,path`.
It cannot represent per-file language versions or explicit source types.

For the supplied `.vhd` example, use the provided helper:

```python
from vunit import VUnit
from fpgather.vunit import import_vunit_csv

vu = VUnit.from_argv(compile_builtins=False)
files = import_vunit_csv(vu, "test/build/vunit/sources.csv")
vu.main()
```

The helper reads `sources.settings.json`, passes each original path directly
to VUnit with `file_type="vhdl"` and its individual `vhdl_standard`, and adds
explicit dependencies to preserve the resolved order. A hash detects mismatched
CSV/settings. Original files are imported without changing their name or location.

VUnit's native `add_source_files_from_csv(csv_path, vhdl_standard="2008")`
works directly for recognized suffixes such as `.vhd` and `.vhdl` when one
common standard is sufficient. **It does not infer VHDL from `.hdl`** and
cannot apply individual language versions. The supplied `.vhd` fixture can be
imported directly with the native method. Use the helper to retain its mixed
VHDL-2008 and VHDL-1993 standards.

The VUnit exporter supports VHDL-1993, -2002, -2008 and -2019, including aliases
`93`, `02`, `08` and `19`. It treats `.hdl` as VHDL. Unsupported languages or
standards are rejected explicitly; the resolver itself is tool-independent.

Reference: [VUnit CSV import](https://vunit.github.io/py/vunit.html#vunit.ui.VUnit.add_source_files_from_csv).

## Code style

Python code uses four-space indentation, a 79-character code line limit,
72-character comment and docstring lines,
`snake_case` functions and variables, `PascalCase` classes, grouped imports,
and type hints on public functions. Ruff formats the code and checks PEP 8
style, import ordering and common Python errors. Configuration lives in
`pyproject.toml`.

```sh
.venv/bin/python -m pip install -e '.[test,dev]'
.venv/bin/ruff format --check .
.venv/bin/ruff check .
```

To apply formatting, run `.venv/bin/ruff format .`.

## Python testbench

```sh
.venv/bin/python -m pytest -q
.venv/bin/python test/run.py
```

Tests use isolated copies of the three-level fixture under `test/` and check
typed conditions, inheritance, shared dependencies, language versions, errors,
more than 1,000 levels, CLI behavior, original absolute paths and actual VUnit
imports. Native CSV import is tested with recognized suffixes; the helper is
tested with original `.vhd` files and mixed standards.

`test/run.py` regenerates the example CSV, verifies selection and compile order,
checks native CSV import, imports the original paths with individual standards
and prints the final CSV.

This is a Python testbench for the resolver. The seven original HDL files are
intentionally empty, so no HDL simulation is performed or required.

## Continuous integration

GitHub Actions runs on pushes, pull requests and manual dispatches. CI checks
Ruff lint and formatting, runs the tests and VUnit import testbench on Python
3.10–3.14, and builds the wheel and source distribution. No HDL simulator is
required.

The build job validates package metadata with Twine and checks the installed
wheel's CLI in a fresh environment. Successful builds are available as the
`distributions` workflow artifact for seven days. CI requires no repository
secrets and does not publish to PyPI. Publishing is handled separately below.

## Publishing to PyPI

The `release.yml` workflow publishes when a GitHub release is published. It
checks that the release tag equals `v` followed by the version in
`pyproject.toml`, reruns the complete CI workflow on the release commit, and
uploads those validated distributions using PyPI Trusted Publishing.
Ordinary pushes and pull requests never publish packages.

One-time setup:

1. Create a GitHub environment named `pypi` in this repository's settings.
2. Sign in to PyPI and open
   [account publishing settings](https://pypi.org/manage/account/publishing/).
   Add a pending GitHub publisher with these exact values:
   - PyPI project: `fpgather`
   - Owner: `VHDLivery`
   - Repository: `fpgather`
   - Workflow filename: `release.yml`
   - Environment: `pypi`
   For an existing project you own, add it under that project's publishing
   settings instead. No API token or GitHub secret is required.

To release:

1. Set the new version in `pyproject.toml`, commit and push the release changes.
2. Publish a GitHub release with the matching tag, initially `v0.1.0`, targeting
   that commit. Publishing the release triggers the PyPI upload.
3. Check the `Publish to PyPI` workflow, then verify the release with
   `python -m pip install fpgather==0.1.0` in a fresh environment.

A pending publisher does not reserve the project name. PyPI distribution
filenames cannot be reused; subsequent releases need a new version.

## License

Copyright (c) 2026 VHDLivery. Released under the [MIT License](LICENSE).

Author: VHDLivery — vhdlivery@gmail.com.
