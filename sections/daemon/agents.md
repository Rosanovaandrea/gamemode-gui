# Section: daemon (stateless)

Daemon utilities and a simulated console: run the diagnostics, show the version,
restart the daemon and manage the `gamemode` group. It holds no state and has no
initializer.

## Files

- `core.py` — the daemon actions and their command constants (`test_daemon`,
  `daemon_version`, `restart_daemon`, the group helpers). It uses the shared
  `services.commands` helpers (`find_executable`, `run_command`,
  `CommandResult`).
- `ui.py` — `DaemonPage`: the action cards, the group card and the console. The
  window connects its buttons to `core.py` and displays the raw output.

## Notes

- Binaries (`gamemoded`, `systemctl`, `usermod`, `pkill`, `pkexec`, `sudo`) are
  resolved to **absolute paths** (`shutil.which` + known fallbacks), so the section
  works with a minimal PATH (e.g. under `pkexec`) and on merged-usr systems.
- Restart order: `systemctl --user restart gamemoded`, then the system unit, then
  `pkill -TERM gamemoded`.
- Adding the user to the `gamemode` group runs `usermod -aG gamemode $USER` via
  pkexec/sudo; the logout reminder is shown only on success.
