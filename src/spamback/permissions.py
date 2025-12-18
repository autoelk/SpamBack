"""
Helper functions for checking macOS permissions.
"""

import os
import sqlite3
import subprocess


def has_full_disk_access() -> bool:
    """Check if the app has Full Disk Access by attempting to read the Messages database."""
    db_path = os.path.expanduser("~/Library/Messages/chat.db")

    if not os.path.exists(db_path):
        return False

    try:
        # Try to open and query the database
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=1)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM message LIMIT 1")
        cursor.fetchone()
        conn.close()
        return True
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return False


def open_system_preferences_privacy():
    """Open System Settings to the Privacy & Security > Full Disk Access pane."""
    try:
        # macOS Ventura and later
        subprocess.run(
            [
                "open",
                "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles",
            ]
        )
    except Exception:
        pass
