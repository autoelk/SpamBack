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
from typing import Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .gui import SpamBackGUI

DB_PATH = os.path.expanduser("~/Library/Messages/chat.db")
POLL_INTERVAL = 2.0

SPAMMERS_FILE = os.path.join(os.path.dirname(__file__), "spammers.json")

# Global GUI reference for callbacks
_gui: Optional["SpamBackGUI"] = None
_reply_count: int = 0

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


def _notify_gui_message(sender: str, text: str, timestamp: str, is_from_me: bool = False,
                        is_spam_msg: bool = False, is_spammer_status: bool = False, service: str = "imessage"):
    """Send message update to GUI if available."""
    global _gui
    if _gui is not None:
        _gui.queue_message(
            sender=sender,
            text=text,
            timestamp=timestamp,
            is_from_me=is_from_me,
            is_spam=is_spam_msg,
            is_spammer=is_spammer_status,
            service=service,
        )


def _notify_gui_status(text: str, running: bool = False):
    """Send status update to GUI if available."""
    global _gui
    if _gui is not None:
        _gui.queue_status(text, running)


def _notify_gui_stats():
    """Send stats update to GUI if available."""
    global _gui, _reply_count
    if _gui is not None:
        spammer_count = len(load_spammers())
        _gui.queue_stats(spammer_count, _reply_count)


def main(gui: Optional["SpamBackGUI"] = None):
    global _gui, _reply_count
    _gui = gui
    _reply_count = 0
    
    load_dotenv()
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    if not os.path.exists(DB_PATH):
        print(f"DB not found: {DB_PATH}")
        _notify_gui_status("Error: Messages database not found", running=False)
        return

    dirpath = os.path.dirname(SPAMMERS_FILE)
    if dirpath:
        os.makedirs(dirpath, exist_ok=True)
    if not os.path.exists(SPAMMERS_FILE):
        write_json(SPAMMERS_FILE, [])

    conn = open_conn()
    last = get_last_rowid(conn)
    print(f"Watching incoming messages (starting ROWID={last})")
    _notify_gui_status("Watching for messages...", running=True)
    _notify_gui_stats()

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
                _notify_gui_status("Reconnecting to database...", running=True)
                continue

            for rid, text, date, sender, service in new:
                transport = (service or "").strip().lower()
                timestamp_str = ts_to_str(date)
                print(
                    f"[{timestamp_str}] {sender or 'Unknown'} ({service or 'unknown'}): {text}"
                )
                normalized = normalize_sender(sender)
                spammer = is_spammer(sender)
                spam = is_spam(text)
                
                if spam and not spammer:
                    if add_spammer(sender):
                        print(f"Added {sender} to spammers list.")
                        spammer = True
                    # if spammer already in list, add_spammer returns False but this theoretically shouldn't happen

                # Notify GUI about the incoming message
                _notify_gui_message(
                    sender=sender or "Unknown",
                    text=text,
                    timestamp=timestamp_str,
                    is_from_me=False,
                    is_spam_msg=spam,
                    is_spammer_status=spammer,
                    service=transport,
                )
                _notify_gui_stats()

                if spammer or spam:
                    print(
                        f"Spam detected from {sender}. Sending auto-reply through {transport}."
                    )
                    _notify_gui_status(f"Generating reply to {sender}...", running=True)
                    
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
                        send_message(sender, response.text, transport=transport)
                        _reply_count += 1
                        
                        # Notify GUI about the sent reply
                        reply_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        _notify_gui_message(
                            sender=sender,
                            text=response.text,
                            timestamp=reply_timestamp,
                            is_from_me=True,
                            is_spam_msg=False,
                            is_spammer_status=spammer,
                            service=transport,
                        )
                        _notify_gui_stats()
                        _notify_gui_status("Watching for messages...", running=True)
                    else:
                        print("No sender or message available, cannot send reply.")
                        _notify_gui_status("Failed to send reply", running=True)
                        
                last = max(last, rid)

            time.sleep(POLL_INTERVAL)
    finally:
        conn.close()
        _notify_gui_status("Stopped", running=False)


if __name__ == "__main__":
    main()
