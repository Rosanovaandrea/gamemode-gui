"""Core logic for the GameMode GUI.

This package contains all the *pure* logic of the application: the
declarative options table, the INI renderer, the activation flags, the
config/backup managers and the wrapper around gamemode utilities.

None of these modules depend on GTK, so they can be unit tested without a
display.
"""