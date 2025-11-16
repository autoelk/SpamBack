import sqlite3
import os
import time
import json
from google import genai
from google.genai import types
from datetime import datetime
from .spam_filter import is_spam
from .sender import send_message
from dotenv import load_dotenv

DB_PATH = os.path.expanduser("~/Library/Messages/chat.db")
POLL_INTERVAL = 2.0

SPAMMERS_FILE = os.path.join(os.path.dirname(__file__), "spammers.json")

# contents : list[dict[str, str]] = []

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

def normalize_sender(sender: str) -> str:
    """Normalize a sender (phone number or email) for comparison."""
    if not sender:
        return ""
    
    sender = sender.strip().lower()

    if "@" in sender:
        # Email
        return sender

    # Phone number
    if sender.startswith("+"):
        # Remove leading +1
        sender = sender[2:]
    sender = sender.replace("-", "").replace(" ", "").replace("(", "").replace(")", "")
    return sender

def write_json(path: str, data):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

def load_spammers() -> list[str]:
    try:
        with open(SPAMMERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
        return []
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def add_spammer(sender: str):
    normalized = normalize_sender(sender)
    if not normalized:
        return False
    
    handles = load_spammers()
    if normalized in handles:
        return False
    handles.append(normalized)
    write_json(SPAMMERS_FILE, handles)
    return True


def is_spammer(sender: str) -> bool:
    normalize = normalize_sender(sender)
    if not normalize:
        return False
    normalized = normalize_sender(sender)
    handles = load_spammers()
    return normalized in handles

def main():
    load_dotenv()
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    if not os.path.exists(DB_PATH):
        print(f"DB not found: {DB_PATH}")
        return

    dirpath = os.path.dirname(SPAMMERS_FILE)
    if dirpath:
        os.makedirs(dirpath, exist_ok=True)
    if not os.path.exists(SPAMMERS_FILE):
        write_json(SPAMMERS_FILE, [])

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
                normalized = normalize_sender(sender)
                spammer = is_spammer(sender)
                spam = is_spam(text)
                if spam and not spammer:
                    if add_spammer(sender):
                        print(f"Added {sender} to spammers list.")
                        spammer = True
                    # if spammer already in list, add_spammer returns False but this theoretically shouldn't happen

                if spammer or spam:
                    # content = contents.get(normalized, []).copy()
                    # content.append(text)
                    print(
                        f"Spam detected from {sender}. Sending auto-reply through {transport}."
                    )
                    response = client.models.generate_content(
                        model="gemini-2.5-flash",
                        config=types.GenerateContentConfig(
                            system_instruction="You are pretending to answer messages from a spammer. "
                            "Output a short 1-2 sentence reply that engages with the scammer "
                            "as if you were a regular person responding in response to their messages:",
                        ),
                        contents=text
                    )
                    if sender and response.text:
                        # content.append(response.text)
                        # contents[normalized] = content
                        send_message(sender, response.text, transport=transport)
                    else:
                        print("No sender or message available, cannot send reply.")
                last = max(last, rid)

            time.sleep(POLL_INTERVAL)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
