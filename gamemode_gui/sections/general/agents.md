# Section: general (`[general]`)

Manages the `[general]` keys of `gamemode.ini`: reaper frequency, CPU governor
(desired/default), iGPU governor and load threshold, soft-realtime, renice, ioprio,
screensaver inhibition and split-lock mitigation. The full list is `GENERAL_OPTIONS`
in `options.py`.

## Files

- `options.py` — `GENERAL_OPTIONS`, the option descriptors (the `[general]` keys).
- `core.py` — `GeneralCore` (extends `SectionCore`): renders the `[general]` block,
  reads it back, gates the dependent options and resolves the kernel governors
  (`available_governors()`). The shared state/accessor machinery is in
  `gamemode_gui/sections/core.py`.
- `ui.py` — `GeneralPage`: one editable row per option (with the kernel governors as
  choices where relevant), wired to the core; `TAB_TITLE_ID`/`TITLE_ID`/`SUBTITLE_ID`.
- `initializer.py` — reads the `[general]` keys from the base/override texts and puts
  them into the state (resetting it first); it delegates to `gamemode_gui/sections/initializer.py`.

## Notes

- `desiredgov`, `defaultgov` and `igpu_desiredgov` are **special**: their allowed
  values come from the kernel (`available_governors()`); everything else is static.
- Value types used here: `int`, `float`, `choice`, `bool`. Only **active** options
  (value different from the default) are written.
