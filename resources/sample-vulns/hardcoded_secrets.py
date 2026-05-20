"""CWE-798: Use of Hard-coded Credentials.

Deva will flag both the API key string and the password literal.
The fix is to read from environment variables or a secret manager.
"""

import os


# BAD: an API key checked into source code is permanent — even removing
# it from HEAD doesn't help; git history retains it forever.
API_KEY = "sk-proj-abcdef1234567890ghijklmnop1234567890qrstuvwxyz1234"

# BAD: hardcoded password.
DATABASE_PASSWORD = "admin1234"


def auth_header_vulnerable() -> dict[str, str]:
    return {"Authorization": f"Bearer {API_KEY}"}


def auth_header_safe() -> dict[str, str]:
    """The fix: read from the environment at runtime."""
    key = os.environ["DEVA_API_KEY"]
    return {"Authorization": f"Bearer {key}"}
