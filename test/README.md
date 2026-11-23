# sources.yml example

This fixture has three inclusion levels: root project → module_a → module_b.
All dependencies are centrally located at `target/dependency/<library>/<module>`.
Source paths inside each manifest are relative to that YAML file.

The root defines `debug: true` (boolean), `target: xilinx` (string) and
`data_width: 32` (number). These definitions are inherited by child manifests.
Module A checks `debug` and `target`; module B checks `data_width`.
`optional_feature` is undefined, so `optional.vhd` is skipped.

All seven original `.vhd` files are intentionally empty. They remain in
`src/rtl/hdl/`, next to `src/rtl/scripts/`, within their respective modules.
The default language version for `.vhd` is `"2008"`; `legacy.vhd` uses `"93"`.

Expected dependency-first order:

1. `lib_b`: `module_b.vhd`, `wide_datapath.vhd`, `legacy.vhd`
2. `lib_a`: `module_a.vhd`, `debug.vhd`
3. Root library: `top.vhd`

## Run the testbench

After installing the package with its test dependencies, run from the package root:

```sh
.venv/bin/python test/run.py
```

The script resolves the manifests, checks selection and order, generates
`build/vunit/sources.csv`, and verifies an actual VUnit import. CSV and settings
contain absolute paths to the **original `.vhd` files under this `test/` tree**.
No source files are copied, moved or renamed.

The script explicitly uses `top_lib`, equivalent to `--work-lib-name top_lib`.
The tool-independent default is `work`, which VUnit does not accept as a
concrete library name.

`sources.settings.json` retains individual language versions. The
`fpgather.vunit.import_vunit_csv` helper passes original paths to VUnit
with explicit `file_type="vhdl"` and applies the VHDL-1993 override.
Native `add_source_files_from_csv` imports all six selected `.vhd` files with
one common standard. The testbench verifies this direct import as well as
the helper import, which preserves the per-file standards.

The Python testbench needs no simulator and does not run an HDL simulation.
