# GHDL analysis export

`--tool ghdl --file-type sh` exports an executable Bash script. Exporting does
not invoke GHDL; run the generated script to analyze the original sources in
resolved dependency order. Bash and GHDL must be installed on the execution
machine. No elaboration, simulation or synthesis is performed.

## Copyable example

From a directory where `fpgather` is installed, create two files with a
cross-library dependency:

```bash
mkdir -p demo/libraries/common demo/rtl

cat > demo/libraries/common/types.vhd <<'VHDL'
package types is
  constant width : positive := 8;
end package;
VHDL

cat > demo/libraries/common/sources.yml <<'YAML'
language_defaults:
  '.vhd': '1993'
sources:
  - types.vhd
YAML

cat > demo/rtl/core.vhd <<'VHDL'
library common;
use common.types.all;

entity core is
end entity;

architecture rtl of core is
  signal value : bit_vector(width - 1 downto 0);
begin
end architecture;
VHDL

cat > demo/sources.yml <<'YAML'
language_defaults:
  '.vhd': '2008'
dependencies:
  common:
    - sources.yml
sources:
  - rtl/core.vhd
YAML

fpgather demo/sources.yml \
  --project-root demo \
  --libraries-root libraries \
  --tool ghdl --file-type sh \
  --output demo/build/analyze.sh \
  --build-dir demo/build/ghdl \
  --ghdl ghdl \
  --ghdl-standard highest \
  --ghdl-option=-frelaxed-rules

./demo/build/analyze.sh
```

Both sources are analyzed with `--std=08`. The `common` library is analyzed
first, then the entry file in `work`. GHDL's library databases are stored in
`demo/build/ghdl/common/` and `demo/build/ghdl/work/`; both directories are
passed with `-P`. Original source files are not copied or modified.

The equivalent Python API, using the files created above:

```python
import subprocess
from fpgather import export_sources, resolve

sources = resolve(
    "demo/sources.yml",
    project_root="demo",
    libraries_root="libraries",
    library="work",
)
script = export_sources(
    sources,
    "demo/build/analyze.sh",
    tool="ghdl",
    file_type="sh",
    build_dir="demo/build/ghdl",
    ghdl="ghdl",
    analysis_options=["-frelaxed-rules"],
    ghdl_standard="highest",
)
subprocess.run([str(script)], check=True)
```

## Configuration

| CLI | Python keyword | Default |
| --- | --- | --- |
| `--build-dir DIR` | `build_dir` | `build/ghdl` |
| `--ghdl EXECUTABLE` | `ghdl` | `ghdl` from PATH |
| `--ghdl-option=FLAG` (repeatable) | `analysis_options` | No extra flags |
| `--ghdl-standard VERSION` | `ghdl_standard` | Each source's own standard |

Relative output, build and executable paths are resolved against the current
working directory **at export time**, not against `--project-root` or the
script directory. A bare executable name is looked up in PATH when the script
runs. A path such as `./tools/ghdl` is fixed at export time. The script can be
started from another working directory; it references absolute original paths.

All sources are validated before the script is written. GHDL-only arguments
are rejected for VUnit exports. VUnit CSV and settings exports are unchanged.

### VHDL standards

Supported mappings are `1987`/`87` → `87`, `1993`/`93` → `93`, `93c` → `93c`,
`2000`/`00` → `00`, `2002`/`02` → `02`, `2008`/`08` → `08`, and
`2019`/`19` → `19`. Other values are rejected, even with a common override.
The installed GHDL version must support the requested standard; in particular,
older releases may reject `19`. Language implementation can be partial.

- Omit `--ghdl-standard` to retain each source's declared version.
- Use `--ghdl-standard highest` to choose the newest version among all selected
  sources and apply it to every source. Excluded sources do not participate.
- Use `--ghdl-standard 2008` (or another supported value) to explicitly select
  one standard for all sources, even if it is older than a declared version.

`93c` is treated as the relaxed variant of 1993: it wins over `93` but is older
than `00`. Neither mode changes source objects, YAML files or VUnit settings.
An empty source list produces no analysis commands.

GHDL separates the 87, 93/93c/00/02, 08 and 19 standard groups. Dependent units
must belong to compatible groups, including across libraries. `highest` can
resolve this mismatch but does not make old code automatically compatible with
a newer language version. Compilation errors are reported without fallback.
Use a clean, dedicated build directory when changing standards or source sets;
the script does not remove old compilation results.

### Additional options and output boundaries

Accepted flags are `-frelaxed`, `-frelaxed-rules`, `-fexplicit`, `-fsynopsys`,
`-fpsl`, `-fcolor-diagnostics`, `-fno-color-diagnostics`,
`-fdiagnostics-show-option`, `-fno-diagnostics-show-option`,
`-fcaret-diagnostics` and `-fno-caret-diagnostics`. Pass one flag per list item
or CLI occurrence. Use the equals form for CLI flags beginning with `-`.
`--std` is emitted before extra flags so it does not reset `-frelaxed-rules`.

The exporter controls `-a`, `--work`, `--workdir`, `--std` and `-P`. Other
options, response files and compiler forwarding are rejected to prevent output
redirection or replacing analysis with a different action. Bash arrays and
shell quoting preserve spaces, quotes and shell metacharacters as literal
arguments; no `eval` or shell command string is used.

The generated script uses `set -euo pipefail` and stops at the first failed
analysis with GHDL's exit status. It works inside the configured build directory,
sets temporary directories there, and creates a subdirectory per library.
Symlinks within the build tree are rejected to prevent redirected writes.
The export operation itself writes the requested `.sh` file; executing it
writes compiler output only inside the build directory. The configured GHDL
executable is trusted: the script is not an OS sandbox for arbitrary programs.
Top-level selection, generics, elaboration, simulation and synthesis remain
with the consuming project.

See the [GHDL invocation documentation](https://ghdl.github.io/ghdl/using/InvokingGHDL.html)
and [VHDL standard compatibility](https://ghdl.github.io/ghdl/using/ImplementationOfVHDL.html).

## CI integration tests

The dedicated GHDL CI job uses `ghcr.io/vhdlivery/docker-ghdl:6.0.0-1`
(GHDL 6.0.0, LLVM backend). It mounts the checkout read-only, copies it into
container-local temporary storage, and installs that copy into a fresh Python
environment. This tests the current package, not the fpgather version bundled
in the image. All tests in `tests/test_ghdl.py` run there, including actual
cross-library analysis and common-standard selection. Package builds and
publishing depend on this job passing.
