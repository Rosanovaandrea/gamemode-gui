"""Integration tests for the Custom section (``[custom]``).

Happy path: the script lists and the timeout. Failure paths: the notification
toggles extracted from a list, the base+override merge and an invalid timeout.
"""

import _testkit
_testkit.isolate()

from sections.custom import initializer as custom_initializer  # noqa: E402
from sections.custom.core import CustomCore, escape_value  # noqa: E402

NOTIFY_START = 'start=notify-send "GameMode started"'


def main():
    # --- happy path: lists are repeated keys, the timeout is a scalar
    core = CustomCore()
    custom_initializer.initialize(
        core, "[custom]\nstart=echo one\nstart=echo two\nscript_timeout=30\n", "")
    _testkit.equal("list items parsed", core.get_start(), ["echo one", "echo two"])
    _testkit.equal("timeout parsed", core.get_script_timeout(), 30)
    rendered = core.render_ini_section()
    _testkit.check("list rendered as repeated keys", rendered.count("start=") == 2)
    _testkit.check("timeout rendered", "script_timeout=30" in rendered)

    # --- the notification toggle is extracted from the list on read...
    managed = CustomCore()
    custom_initializer.initialize(
        managed, f"[custom]\n{NOTIFY_START}\nstart=echo hi\n", "")
    _testkit.equal("managed string turns the switch on", managed.get_notify_start(), True)
    _testkit.equal("managed string removed from the list", managed.get_start(), ["echo hi"])
    # ...and re-added above the list at render time.
    text = managed.render_ini_section()
    notify_at = text.find(NOTIFY_START)
    plain_at = text.find("start=echo hi")
    _testkit.check("switch re-adds the string first",
                   notify_at != -1 and plain_at != -1 and notify_at < plain_at)

    # --- the override lists are appended to the base, not replaced
    merged = CustomCore()
    custom_initializer.initialize(merged, "[custom]\nstart=base\n",
                                  "[custom]\nstart=override\n")
    _testkit.equal("override lists appended", merged.get_start(), ["base", "override"])

    # --- failure paths
    broken = CustomCore()
    custom_initializer.initialize(broken, "[custom]\nscript_timeout=abc\n", "")
    _testkit.equal("invalid timeout keeps the default", broken.get_script_timeout(), 10)

    _testkit.equal("empty section renders nothing", CustomCore().render_ini_section(), "")

    # A script that spans lines or starts with ';' must stay on one safe INI line.
    _testkit.equal("newlines collapsed", escape_value("a\nb"), "a b")
    _testkit.equal("leading ';' escaped", escape_value("; harmful"), "\\; harmful")

    _testkit.finish()


if __name__ == "__main__":
    main()
