# Section: presentation (stateless)

The tab shown by default: a **guide** that introduces GameMode, explains how to
launch a game with `gamemoderun` (Steam/Lutris hints) and how to use each section
of the GUI, and ends with a disclaimer. It holds no state and has no initializer.

## Files

- `core.py` — loads `presentation.json` (next to it) into `Presentation` /
  `PresentationBlock` objects: which blocks exist, in what order, and which are
  warnings. A missing/broken file yields an empty presentation.
- `ui.py` — `PresentationPage` renders the blocks; a warning block becomes a card
  with a warning icon.
- `presentation.json` — the block **structure** (introduction + per-section guide);
  the **texts** live in the language files.

## Notes

- Adding or editing content is data-driven: a JSON entry plus its i18n keys, no code.
- It is a view-only section: the general initializer does not touch it.
