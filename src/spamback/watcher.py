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
from .utils import normalize_address
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
    # Default history window for contextual prompts
    try:
        hw = int(payload.get("history_window", 12))
        if hw <= 0:
            hw = 12
        payload["history_window"] = hw
    except Exception:
        payload["history_window"] = 12

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
        SELECT m.ROWID,
               m.text,
               m.date,
               h.id AS sender,
               COALESCE(m.service, '') AS service,
               cmj.chat_id AS chat_id
        FROM message m
        LEFT JOIN handle h ON m.handle_id = h.ROWID
        LEFT JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
        WHERE m.ROWID > ? AND m.text IS NOT NULL AND m.is_from_me = 0
        ORDER BY m.date ASC
        """,
        (since,),
    )
    return c.fetchall()


def write_json(path: str, data):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# Load spammers list from json config
def load_spammers() -> list[str]:
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


# Add a sender from the spammers list
def add_spammer(sender: str):
    normalized = normalize_address(sender)
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


# Remove a sender from the spammers list
def remove_spammer(sender: str):
    normalized = normalize_address(sender)
    if not normalized:
        return False

    spammers = load_spammers()
    if normalized not in spammers:
        return False

    spammers.remove(normalized)

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


# Check if a sender is in the spammers list
def is_spammer(sender: str) -> bool:
    normalized = normalize_address(sender)
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


def get_history_window() -> int:
    """Read history_window from config; default to 12."""
    try:
        payload = load_config_payload()
        hw = int(payload.get("history_window", 12))
        return hw if hw > 0 else 12
    except Exception:
        return 12


def fetch_thread_history(
    conn, chat_id: Optional[int], sender: Optional[str], limit: int = 12
):
    """
    Fetch last `limit` messages for a thread as chronological history.

    Prefer chat-based lookup via chat_message_join; fallback to handle.id for 1:1.
    Returns a list of dicts: {"is_from_me": bool, "sender": str|None, "text": str, "date": int, "service": str}
    """
    c = conn.cursor()
    rows = []
    try:
        if chat_id is not None:
            c.execute(
                """
                SELECT m.is_from_me,
                       h.id AS sender,
                       m.text,
                       m.date,
                       COALESCE(m.service, '') AS service
                FROM chat_message_join cmj
                INNER JOIN message m ON cmj.message_id = m.ROWID
                LEFT JOIN handle h ON m.handle_id = h.ROWID
                WHERE cmj.chat_id = ? AND m.text IS NOT NULL
                ORDER BY m.date DESC
                LIMIT ?
                """,
                (chat_id, limit),
            )
            rows = c.fetchall()
        elif sender:
            c.execute(
                """
                SELECT m.is_from_me,
                       h.id AS sender,
                       m.text,
                       m.date,
                       COALESCE(m.service, '') AS service
                FROM message m
                LEFT JOIN handle h ON m.handle_id = h.ROWID
                WHERE h.id = ? AND m.text IS NOT NULL
                ORDER BY m.date DESC
                LIMIT ?
                """,
                (sender, limit),
            )
            rows = c.fetchall()
    except sqlite3.DatabaseError:
        return []

    # Reverse to chronological order (oldest -> newest)
    history = [
        {
            "is_from_me": bool(r[0]),
            "sender": r[1],
            "text": r[2],
            "date": r[3],
            "service": r[4],
        }
        for r in reversed(rows)
        if r and r[2]
    ]
    return history


def build_reply_prompt(history: list, latest_text: str) -> str:
    """
    Build a compact transcript followed by a clear reply instruction.

    Example:
    Them: Hi there
    Me: Hey
    Them: Are you available?

    Instruction: Reply as Me in 1–2 sentences, consistent with context.
    """
    lines = []
    for h in history:
        label = "Me" if h.get("is_from_me") else "Them"
        sender = h.get("sender") or "Unknown"
        # For group chats, include sender name on 'Them'
        if label == "Them" and sender:
            line = f"Them ({sender}): {h.get('text','').strip()}"
        else:
            line = f"{label}: {h.get('text','').strip()}"
        lines.append(line)

    # Ensure the latest incoming text is present at the end (deduplicate if necessary)
    if latest_text and (
        not lines or latest_text.strip() != history[-1].get("text", "").strip()
    ):
        lines.append(f"Them: {latest_text.strip()}")

    instruction = (
        "\n\n"  # spacer
        "Reply as Me in 1–2 sentences, staying consistent with the conversation. "
        "Avoid personal details. Keep the tone natural and continue the thread."
    )
    return "\n".join(lines) + instruction


def _handle_spam_reply(
    sender: str,
    transport: str,
    text: str,
    client,
    spammer: bool,
    conn,
    chat_id: Optional[int],
):
    """Generate and send spam reply; update GUI and counters."""
    global _reply_count

    if client is None:
        print("Cannot send reply: API key not configured")
        _notify_gui_status("Spam detected (no API key for reply)", running=True)
        return

    _notify_gui_status(f"Generating reply to {sender}...", running=True)

    try:
        # Build contextual prompt
        history_window = get_history_window()
        history = fetch_thread_history(conn, chat_id, sender, limit=history_window)
        prompt = build_reply_prompt(history, latest_text=text)

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            config=types.GenerateContentConfig(
                system_instruction="You are pretending to answer messages from a spammer. "
                "Output a short 1-2 sentence reply that engages with the scammer "
                "as if you were a regular person responding in response to their messages:",
            ),
            contents=prompt,
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


def _process_record(record, client, conn):
    """Process a single DB record and return the latest ROWID consumed."""
    from .contacts import is_contact

    rid, text, date, sender, service, chat_id = record
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
        _handle_spam_reply(sender, transport, text, client, spammer, conn, chat_id)

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
                rid = _process_record(record, client, conn)
                last = max(last, rid)

            time.sleep(POLL_INTERVAL)
    finally:
        conn.close()
        _notify_gui_status("Stopped", running=False)


if __name__ == "__main__":
    main()
