# Section: cpu (`[cpu]`)

Manages the `[cpu]` keys: core pinning and core parking. The options live in
`CPU_OPTIONS` in `options.py`.

## Files

- `options.py` — `CPU_OPTIONS`, the option descriptors (the `[cpu]` keys).
- `core.py` — `CpuCore` (extends `SectionCore`), plus `available_cores()` and
  `expand_cpu_list()` which read/parse the online CPU list from the kernel.
- `ui.py` — `CpuPage`: the pinning row (checkboxes) and the parking switch.
- `initializer.py` — reads the `[cpu]` keys from the base/override texts; it
  delegates to `sections/initializer.py`.

## Notes

- `pin_cores` is a **special** `cores` option: the choices are the online cores
  (`available_cores()`); the value is a list of ints, written as a comma-separated
  list and parsed back with `expand_cpu_list()` (supports ranges like `0-3`).
- `park_cores` is a plain `bool`. Both are written only when active (a non-empty core
  list / a set switch).
