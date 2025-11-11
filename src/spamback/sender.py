import subprocess
import sys

APPLE_SCRIPT_SEND_IMESSAGE = r"""
on run {targetNumber, messageText}
    tell application "Messages"
        try
            set imService to first service whose service type = iMessage
            set targetBuddy to buddy targetNumber of imService
            send messageText to targetBuddy
            return "SENT_VIA:iMessage"
        on error errMsg
            return "ERROR: " & errMsg
        end try
    end tell
end run
"""


APPLE_SCRIPT_SEND_SMS = r"""
on run {targetNumber, messageText}
    tell application "Messages"
        try
            set smsService to first service whose service type = SMS
            set targetBuddy to buddy targetNumber of smsService
            send messageText to targetBuddy
            return "SENT_VIA:SMS"
        on error errMsg
            return "ERROR: " & errMsg
        end try
    end tell
end run
"""


def send_message(phone_number: str, message: str, transport: str = "imessage") -> bool:
    """Send a message via Messages.app.

    Args:
        phone_number: Phone number or email (use +1... format for best results)
        message: Text to send
        transport: 'imessage' or 'sms' (default: 'imessage')
    """

    # Clean inputs
    phone_number = (phone_number or "").strip()
    message = (message or "").strip()
    transport = transport.strip().lower()

    if not phone_number or not message:
        raise ValueError("Error: phone_number and message are required")
    if transport not in {"imessage", "sms", "rcs"}:
        raise ValueError("Invalid transport type")

    try:
        script = APPLE_SCRIPT_SEND_IMESSAGE
        if transport == "sms" or transport == "rcs":
            script = APPLE_SCRIPT_SEND_SMS

        result = subprocess.run(
            ["osascript", "-e", script, phone_number, message],
            capture_output=True,
            text=True,
            timeout=15,
        )

        if result.returncode == 0:
            out = (result.stdout or "").strip()
            if out.startswith("ERROR:"):
                error_msg = out
                print(f"Failed to send message via {transport}: {error_msg}")
                return False
            elif out.startswith("SENT_VIA:"):
                via = out.split(":", 1)[1]
                print(f'Sent "{message}" to {phone_number} via {via}')
                return True
            else:
                print(f"Send result: {out}")
                return True
        else:
            raise RuntimeError(f"(osascript exit {result.returncode}): {result.stderr}")
    except FileNotFoundError:
        print("Error: 'osascript' not found. This only works on macOS.")
        return False
    except Exception as e:
        print(f"Error sending message: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) == 3:
        recipient = sys.argv[1]
        message = sys.argv[2]
        send_message(recipient, message, transport="imessage")
    else:
        print("Usage: python sender.py <phone_number> <message>")
