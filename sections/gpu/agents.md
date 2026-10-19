# Section: gpu (`[gpu]`)

Manages the `[gpu]` keys: the master switch to edit the GPU power plan plus the
NVIDIA and AMD power-state options. The options live in `GPU_OPTIONS` in
`options.py`.

## Files

- `options.py` — `GPU_OPTIONS`, the option descriptors (the `[gpu]` keys).
- `core.py` — `GpuCore` (extends `SectionCore`). The master switch
  (`apply_gpu_optimisations`, type `enable`) **gates** the other options
  (`depends_on`): while it is off they are not rendered and `is_option_active()` is
  False.
- `ui.py` — `GpuPage`: a warning banner at the top, then the rows; dependent rows are
  enabled/disabled according to the master switch. Defines `BANNER_ID`.
- `initializer.py` — reads the `[gpu]` keys from the base/override texts; it
  delegates to `sections/initializer.py`.

## Notes

- The master switch maps off → `apply_gpu_optimisations=0` and on →
  `apply_gpu_optimisations=accept-responsibility`; the other options are written only
  when it is on.
- The `[gpu]` options only take effect when the file is in `/etc` (or
  `/usr/share/gamemode`), a GameMode requirement.
