"""CWE-89: SQL Injection.

Deva will flag the f-string interpolation into a raw SQL query.
The fix is parameterized queries.
"""

import sqlite3


def get_user(username: str) -> dict | None:
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    # BAD: user input flows directly into the SQL string.
    query = f"SELECT * FROM users WHERE username = '{username}'"
    cursor.execute(query)
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_safe(username: str) -> dict | None:
    """The fix: parameterized query, separating data from SQL."""
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None
