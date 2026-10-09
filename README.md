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
