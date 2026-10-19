"""Compatibility shim: the window lives in :mod:`gamemode_gui.ui.window`."""

from gamemode_gui.ui.window import *  # noqa: F401,F403
from gamemode_gui.ui.window import Application, MainWindow, run  # noqa: F401
