# Section: cpu (`[cpu]`)

Manages the `[cpu]` keys: core pinning and core parking. The options live in
`CPU_OPTIONS` in `core.py`.

## Files

- `core.py` — `CPU_OPTIONS`, `CpuState` and `CpuCore`, plus `available_cores()` and
  `expand_cpu_list()` which read/parse the online CPU list from the kernel.
- `ui.py` — `CpuPage`: the pinning row (checkboxes) and the parking switch.
- `initializer.py` — reads the `[cpu]` keys from the base/override texts.

## Notes

- `pin_cores` is a **special** `cores` option: the choices are the online cores
  (`available_cores()`); the value is a list of ints, written as a comma-separated
  list and parsed back with `expand_cpu_list()` (supports ranges like `0-3`).
- `park_cores` is a plain `bool`. Both are written only when active (a non-empty core
  list / a set switch).
