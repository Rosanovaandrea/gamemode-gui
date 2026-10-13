# Tests

Everything under `test/`. Every test is a plain script run with `python3` (no
test framework), so the same command works locally and in CI.

## Layout

- `sections/` — **integration tests, one per section**: the happy path plus the
  paths that can go wrong.
  - `test_general.py` — override precedence, round-trip, invalid values, `:` and
    comments, session fallback, kernel governors.
  - `test_gpu.py` — master switch and dependent-option gating, invalid values.
  - `test_cpu.py` — core pinning (ranges), parking, invalid tokens.
  - `test_custom.py` — repeated-key lists, notification toggles, base+override
    merge, invalid timeout, value escaping.
  - `test_presentation.py` — the shipped JSON, plus a missing and a broken file.
  - `test_daemon.py` — output joining, command success, non-zero exit, missing
    binary, timeout.
  - `_testkit.py` — shared helpers: isolation plus `check`/`equal`/`finish`.
  - `run_all.py` — runs every section test, each in its own process.
- `test_engine.py` — each section's options and INI (de)serialisation, i18n and the
  privileged helper.
- `test_app.py` — bootstrap, atomic save, `.orig`/`.bak`, restore and reload.
- `smoke_test.py` — builds the real GTK window (needs a display).

## Run

```bash
python3 test/sections/run_all.py   # per-section integration tests
python3 test/test_engine.py        # engine
python3 test/test_app.py           # application
python3 test/smoke_test.py         # interface (needs DISPLAY)
```

Each test prints one line per check and exits non-zero if any check failed.
