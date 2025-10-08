import sqlite3
import os
from datetime import datetime


def convert_apple_timestamp(apple_timestamp):
    # apple uses epoch which starts at Jan 1, 2001
    if not apple_timestamp:
        return "Unknown date"
    unix_timestamp = apple_timestamp / 1000000000 + 978307200
    readable_date = datetime.fromtimestamp(unix_timestamp)
    return readable_date.strftime("%Y-%m-%d %H:%M:%S")


def read_recent_messages(limit):
    home = os.path.expanduser("~")
    db_path = os.path.join(home, "Library", "Messages", "chat.db")

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.cursor()

        query = """
        SELECT 
            message.text,
            message.date,
            message.is_from_me,
            handle.id as sender
        FROM message
        LEFT JOIN handle ON message.handle_id = handle.ROWID
        WHERE message.text IS NOT NULL
        ORDER BY message.date DESC
        LIMIT ?
        """

        cursor.execute(query, (limit,))
        messages = cursor.fetchall()

        for text, date, is_from_me, sender in messages:
            date_str = convert_apple_timestamp(date)
            speaker = "You" if is_from_me else (sender or "Unknown")
            print(f"[{date_str}] {speaker}: {text}")

        conn.close()
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    read_recent_messages(10)
