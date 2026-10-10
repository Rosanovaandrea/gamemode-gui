# Section: general (`[general]`)

Manages the `[general]` keys of `gamemode.ini`: reaper frequency, CPU governor and
platform profile (desired/default), iGPU governor and load threshold, soft-realtime,
renice, ioprio, screensaver inhibition and split-lock mitigation. The full list is
`GENERAL_OPTIONS` in `core.py`.

## Files

- `core.py` — `GENERAL_OPTIONS` (the section's options), `GeneralState` (its values)
  and `GeneralCore`: renders the `[general]` block, reads it back, and exposes a
  speaking getter/setter per option. Also `available_governors()`, which reads the
  CPU governors from the kernel.
- `ui.py` — `GeneralPage`: one editable row per option (with the kernel governors as
  choices where relevant), wired to the core; `TAB_TITLE_ID`/`TITLE_ID`/`SUBTITLE_ID`.
- `initializer.py` — reads the `[general]` keys from the base/override texts and puts
  them into the state (resetting it first).

## Notes

- `desiredgov`, `defaultgov` and `igpu_desiredgov` are **special**: their allowed
  values come from the kernel (`available_governors()`); everything else is static.
- Value types used here: `int`, `float`, `choice`, `bool`. Only **active** options
  (value different from the default) are written.
