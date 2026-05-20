"""CWE-78: OS Command Injection.

Deva will flag passing user input to shell=True or os.system.
The fix is to use a list-form subprocess call without a shell.
"""

import subprocess


def ping_vulnerable(host: str) -> str:
    # BAD: shell=True with interpolated input — `host=";rm -rf ~"` runs.
    output = subprocess.check_output(f"ping -c 1 {host}", shell=True)
    return output.decode()


def ping_safe(host: str) -> str:
    """The fix: list-form, no shell, host is just an argv argument."""
    output = subprocess.check_output(["ping", "-c", "1", host])
    return output.decode()
