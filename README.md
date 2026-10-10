# Introduction

What GameMode is, how to launch games with the optimisations, and what to know before configuring

## What GameMode is

GameMode is a set of Linux optimisations applied temporarily (and then reverted) when you launch a game. When a game requests it, the gamemoded daemon changes system settings on the fly such as the CPU governor, process priority, I/O priority, the scheduler and — on supported hardware — the GPU power state. The goal is to reduce stutter and latency and give the game more resources, returning to normal when it exits.

Github link -> https://github.com/feralinteractive/gamemode

## Why GameMode GUI

GameMode is configured through the /etc/gamemode.ini file: convenient if you know it, but easy to get wrong (comments, sections, allowed values). This GUI lets you manage every option visually and safely: the file is rewritten in full with atomic writes, backup and restore. Every option has a description of what it does, the benefits and the possible issues.

## Launching a game with gamemoderun

The most direct way is to prefix the game's executable with the gamemoderun command. From a terminal, for example:

```bash
gamemoderun ./my-game
```

GameMode enters "game mode" when the process starts and disables it when the game closes. With a wrapper (e.g. DRI_PRIME or optirun) you can combine them: gamemoderun DRI_PRIME=1 ./my-game.

## Steam

In your Steam library: right-click the game → Properties → Launch Options, and write (or replace) with:

```text
gamemoderun %command%
```

%command% is replaced by Steam with the game's executable, which gamemoderun launches in game mode. This also works with Proton/Windows games.

## Lutris

In Lutris, open the game's configuration (right-click → Configure) and in the System options tab enable the "Enable GameMode" option, if available. To do it manually, set a run prefix with gamemoderun, keeping %command% as the game command.

## Disclaimer

Some options (especially the GPU/iGPU ones) may not be supported or may not work correctly on laptops, due to different thermal and power management. In general, changing the governor, platform profiles, GPU power state and system priorities can reduce the machine's stability (crashes, freezes, reboots, overheating). Apply one change at a time, check the result, and keep the "Restore backup" and "Restore original" buttons in the Summary tab within reach. GPU optimisations only take effect if the file is at /etc/gamemode.ini and require the responsibility acceptance switch.

## Building

### Dependencies

- Python 3.10+
- PyGObject (GTK 4 + libadwaita)
- Feral GameMode (the daemon the GUI configures)
- `pkexec` (polkit) or `sudo` for the privileged writes to `/etc`

```bash
# Fedora / RHEL
sudo dnf install python3-gobject gtk4 libadwaita gamemode

# Debian / Ubuntu
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gamemode
```

### Run from source

```bash
cd gamemode-gui
python3 main.py
```

The first write to `/etc/gamemode.ini` asks for the administrator password (via `pkexec`, with `sudo` as fallback). To try it without touching `/etc` (temporary writable path):

```bash
GAMEMODE_CONFIG=/tmp/try/gamemode.ini python3 main.py
```

### Tests

```bash
python3 test/test_engine.py   # engine, no display
python3 test/test_app.py      # application (bootstrap / save / restore), no display
python3 test/smoke_test.py    # interface (needs DISPLAY), uses a temporary folder
```

### Build the packages (`.deb` / `.rpm`)

`packaging/build.sh` builds both packages into `dist/`. There is no compilation: it is a pure Python/GTK package.

```bash
packaging/build.sh
```

Requirements: `dpkg-deb` (package `dpkg-dev`/`dpkg`) for the `.deb`; `rpmbuild` (package `rpm-build`) for the `.rpm`. If `rpmbuild` is not in the `PATH`, point at an alternative binary and its config dir:

```bash
RPMBUILD=/path/usr/bin/rpmbuild RPMCONF=/path/rpmconf packaging/build.sh
```

`VERSION` and `RELEASE` can be overridden from the environment (defaults `1.0.0` and `1`); in CI the version comes from the git tag.

Package metadata:

- **`.deb`** (Debian/Ubuntu): `Depends: python3, python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, gamemode-daemon | gamemode` (plus `pkexec | policykit-1`; `Recommends: sudo`).
- **`.rpm`** (Fedora/RHEL): `Requires: python3, python3-gobject, gtk4, libadwaita, gamemode, polkit` (plus `Recommends: sudo`).

Both install:

```text
/usr/bin/gamemode-gui                                        # launcher
/usr/share/gamemode-gui/main.py                              # entry point
/usr/share/gamemode-gui/*.py                                 # application modules
/usr/share/gamemode-gui/sections/                            # one folder per section
/usr/share/gamemode-gui/data/                                # style, translations
/usr/share/gamemode-gui/data/locale/{it,en}.xml              # translations
/usr/share/applications/io.github.gamemodegui.GameModeGui.desktop
/usr/share/icons/hicolor/scalable/apps/io.github.gamemodegui.GameModeGui.svg
```

> **Configuration reset (temporary):** on every installation or upgrade the
> post-install script **wipes** the configuration managed by the GUI —
> `/etc/gamemode.ini` with its service files (`.orig`, `.bak`, `.tmp`,
> `.session.json`) and the user preferences
> `~/.config/gamemode-gui/settings.json` — so the new version always starts from a
> clean state.

### Automatic releases (GitHub Actions)

`.github/workflows/build-packages.yml` builds the packages for a release:

- **On pushing a tag** `vX.Y.Z` (e.g. `git tag v1.2.3 && git push origin v1.2.3`): it builds the `.deb` and the `.rpm` and **publishes them in the GitHub Releases** section, attached to the tag's release. The package version is taken from the tag (overriding the defaults of `packaging/build.sh` via `VERSION`).
- **Manually** (`workflow_dispatch`, from the "Actions" tab): it builds and uploads the packages as artifacts, without creating a release.

The packages are built on `ubuntu-latest` installing `dpkg-dev` and `rpm` (`rpmbuild`).
