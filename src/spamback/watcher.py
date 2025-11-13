import sqlite3
import os
import time
from google import genai
from datetime import datetime
from .spam_filter import is_spam
from .sender import send_message
from dotenv import load_dotenv

DB_PATH = os.path.expanduser("~/Library/Messages/chat.db")
POLL_INTERVAL = 2.0


def ts_to_str(apple_ts):
    if not apple_ts:
        return "Unknown date"
    unix_ts = apple_ts / 1_000_000_000 + 978307200
    return datetime.fromtimestamp(unix_ts).strftime("%Y-%m-%d %H:%M:%S")


def open_conn():
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=5)


def get_last_rowid(conn):
    c = conn.cursor()
    c.execute("SELECT ROWID FROM message ORDER BY ROWID DESC LIMIT 1")
    r = c.fetchone()
    return r[0] if r else 0


def fetch_new(conn, since):
    c = conn.cursor()
    c.execute(
        """
        SELECT message.ROWID, message.text, message.date, handle.id, COALESCE(message.service, '') as service
        FROM message
        LEFT JOIN handle ON message.handle_id = handle.ROWID
        WHERE message.ROWID > ? AND message.text IS NOT NULL AND message.is_from_me = 0
        ORDER BY message.date ASC
        """,
        (since,),
    )
    return c.fetchall()


def main():
    load_dotenv()
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    if not os.path.exists(DB_PATH):
        print(f"DB not found: {DB_PATH}")
        return

    conn = open_conn()
    last = get_last_rowid(conn)
    print(f"Watching incoming messages (starting ROWID={last})")

    try:
        while True:
            try:
                new = fetch_new(conn, last)
            except sqlite3.DatabaseError:
                try:
                    conn.close()
                except Exception:
                    pass
                time.sleep(0.5)
                conn = open_conn()
                continue

            for rid, text, date, sender, service in new:
                transport = (service or "").strip().lower()
                print(
                    f"[{ts_to_str(date)}] {sender or 'Unknown'} ({service or 'unknown'}): {text}"
                )
                if is_spam(text):
                    print(
                        f"Spam detected from {sender}. Sending auto-reply through {transport}."
                    )
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=f"You are pretending to answer messages from a spammer. "
                        "Output a short 1-2 sentence reply that engages with the scammer " \
                        "as if you were a regular person responding "
                        "in response to this message: {text}",
                    )
                    if sender and response.text:
                        send_message(sender, response.text, transport=transport)
                    else:
                        print("No sender or message available, cannot send reply.")
                last = max(last, rid)

            time.sleep(POLL_INTERVAL)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
