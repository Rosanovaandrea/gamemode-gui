"""Integration tests for the Daemon section (stateless).

Happy path: run a command and combine its output. Failure paths: a non-zero exit,
a missing binary and a timeout, none of which must raise.
"""

import _testkit
_testkit.isolate()

from services.commands import (  # noqa: E402
    CommandResult, find_executable, privileged_prefixes, run_command,
)


def main():
    # --- CommandResult.output joins the streams, falling back to the error text
    _testkit.equal("output joins stdout and stderr",
                   CommandResult(True, 0, stdout="out\n", stderr="err\n").output,
                   "out\nerr")
    _testkit.equal("output falls back to the error",
                   CommandResult(False, -1, error="boom").output, "boom")

    # --- find_executable: a PATH hit and a clear miss
    _testkit.check("finds a binary in PATH", find_executable("sh") is not None)
    _testkit.check("returns None for a missing binary",
                   find_executable("definitely-not-a-real-binary-xyz") is None)

    # --- run_command: success, non-zero exit, missing binary and timeout
    ok = run_command(["sh", "-c", "echo hello"])
    _testkit.check("successful command", ok.success and ok.stdout.strip() == "hello")
    failed = run_command(["false"])
    _testkit.check("non-zero exit is not a success",
                   not failed.success and failed.returncode != 0)
    missing = run_command(["definitely-not-a-real-binary-xyz"])
    _testkit.check("missing binary is reported, not raised",
                   not missing.success and bool(missing.error))
    timed_out = run_command(["sleep", "5"], timeout=1)
    _testkit.check("timeout is reported", not timed_out.success and bool(timed_out.error))

    # --- privileged prefixes is always a list (possibly empty)
    _testkit.check("privileged prefixes is a list",
                   isinstance(privileged_prefixes(), list))

    _testkit.finish()


if __name__ == "__main__":
    main()
