import sqlite3
import os
import time
import json
from pathlib import Path
from google import genai
from google.genai import types
from datetime import datetime
from .spam_filter import is_spam
from .sender import send_message
from .contacts import is_contact
from typing import Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .gui import SpamBackGUI

DB_PATH = os.path.expanduser("~/Library/Messages/chat.db")
POLL_INTERVAL = 2.0

# Global GUI reference for callbacks
_gui: Optional["SpamBackGUI"] = None
_reply_count: int = 0


def get_config_path() -> Path:
    """Get the config file path in app support directory."""
    config_dir = Path.home() / "Library" / "Application Support" / "SpamBack"
    return config_dir / "config.json"


def load_config_payload() -> dict:
    """Load config JSON as dict, or return empty dict on failure."""
    config_path = get_config_path()
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def ensure_config_baseline() -> dict:
    """Ensure config file exists with required keys; return payload."""
    config_path = get_config_path()
    payload = load_config_payload()
    if not isinstance(payload.get("spammers"), list):
        payload["spammers"] = []

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        pass

    return payload


def init_client_from_config(payload: dict):
    """Return a genai client if API key exists; otherwise None."""
    api_key = payload.get("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        return genai.Client(api_key=str(api_key))
    except Exception:
        return None


def get_whitelist_contacts() -> bool:
    """Return whether contacts should be whitelisted (default True)."""
    payload = load_config_payload()
    val = payload.get("whitelist_contacts")
    if isinstance(val, bool):
        return val
    return True


def ts_to_str(apple_ts):
    """
    Convert apple timestamp to a human-readable string.

    :param apple_ts: Apple timestamp
    """
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
    """Load spammers list from app-support config.json."""
    config_path = get_config_path()
    try:
        if config_path.exists():
            data = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "spammers" in data:
                spammers = data["spammers"]
                if isinstance(spammers, list):
                    return spammers
        return []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def add_spammer(sender: str):
    """Add a sender to the spammers list in app-support config.json."""
    normalized = normalize_sender(sender)
    if not normalized:
        return False

    spammers = load_spammers()
    if normalized in spammers:
        return False

    spammers.append(normalized)

    # Ensure directory exists
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing config, update spammers, write back
    payload = {}
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                payload.update(existing)
        except Exception:
            pass

    payload["spammers"] = spammers
    config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return True


def is_spammer(sender: str) -> bool:
    """Check if a sender is in the spammers list."""
    normalized = normalize_sender(sender)
    if not normalized:
        return False
    spammers = load_spammers()
    return normalized in spammers


def _notify_gui_message(
    sender: str,
    text: str,
    timestamp: str,
    is_from_me: bool = False,
    is_spam_msg: bool = False,
    is_spammer_status: bool = False,
    service: str = "imessage",
):
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


def _handle_spam_reply(sender: str, transport: str, text: str, client, spammer: bool):
    """Generate and send spam reply; update GUI and counters."""
    global _reply_count

    if client is None:
        print("Cannot send reply: API key not configured")
        _notify_gui_status("Spam detected (no API key for reply)", running=True)
        return

    _notify_gui_status(f"Generating reply to {sender}...", running=True)

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            config=types.GenerateContentConfig(
                system_instruction="You are pretending to answer messages from a spammer. "
                "Output a short 1-2 sentence reply that engages with the scammer "
                "as if you were a regular person responding in response to their messages:",
            ),
            contents=text,
        )
        if sender and response.text:
            send_message(sender, response.text, transport=transport)
            _reply_count += 1

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
    except Exception as e:
        print(f"Error generating/sending reply: {e}")
        _notify_gui_status(f"Error: {str(e)}", running=True)


def _process_record(record, client):
    """Process a single DB record and return the latest ROWID consumed."""
    from .contacts import is_contact

    rid, text, date, sender, service = record
    transport = (service or "").strip().lower()
    timestamp_str = ts_to_str(date)
    print(f"[{timestamp_str}] {sender or 'Unknown'} ({service or 'unknown'}): {text}")

    whitelist_contacts = get_whitelist_contacts()
    contact_match, contact_name = is_contact(sender)
    spammer = False if (whitelist_contacts and contact_match) else is_spammer(sender)
    is_spam_msg = False if (whitelist_contacts and contact_match) else is_spam(text)

    if is_spam_msg and not spammer:
        if add_spammer(sender):
            print(f"Added {sender} to spammers list.")
            spammer = True

    _notify_gui_message(
        sender=sender or "Unknown",
        text=text,
        timestamp=timestamp_str,
        is_from_me=False,
        is_spam_msg=is_spam_msg,
        is_spammer_status=spammer,
        service=transport,
    )
    _notify_gui_stats()

    if whitelist_contacts and contact_match:
        print(
            f"Sender {sender or 'Unknown'} is in Contacts"
            + (f" as {contact_name}" if contact_name else "")
            + "; skipping spam handling."
        )
        return rid

    if spammer or is_spam_msg:
        print(f"Spam detected from {sender}. Sending auto-reply through {transport}.")
        _handle_spam_reply(sender, transport, text, client, spammer)

    return rid


def main(gui: Optional["SpamBackGUI"] = None):
    global _gui, _reply_count
    _gui = gui
    _reply_count = 0

    try:
        payload = ensure_config_baseline()
        client = init_client_from_config(payload)

        if not os.path.exists(DB_PATH):
            print(f"DB not found: {DB_PATH}")
            _notify_gui_status("Error: Messages database not found", running=False)
            return
    except Exception as e:
        print(f"Initialization error: {e}")
        _notify_gui_status(f"Error: {str(e)}", running=False)
        return

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

            for record in new:
                rid = _process_record(record, client)
                last = max(last, rid)

            time.sleep(POLL_INTERVAL)
    finally:
        conn.close()
        _notify_gui_status("Stopped", running=False)


if __name__ == "__main__":
    main()
