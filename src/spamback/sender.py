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


def send_imessage(phone_number: str, message: str, transport: str = "imessage"):
    """Send a message via Messages.app.

    Args:
        phone_number: Phone number or email (use +1... format for best results)
        message: Text to send
        transport: 'imessage' or 'sms' (default: 'sms')
    """
    phone_number = (phone_number or "").strip()
    message = (message or "").strip()

    if not phone_number or not message:
        print("Error: phone_number and message are required")
        return

    try:
        t = transport.strip().lower()
        if t not in {"imessage", "sms"}:
            raise ValueError("Invalid transport type")

        script = APPLE_SCRIPT_SEND_IMESSAGE
        if t == "sms":
            script = APPLE_SCRIPT_SEND_SMS

        result = subprocess.run(
            ["osascript", "-e", script, phone_number, message],
            capture_output=True,
            text=True,
            timeout=15,
        )

        if result.returncode == 0:
            out = (result.stdout or "").strip()
            if out.startswith("SENT_VIA:"):
                via = out.split(":", 1)[1]
                print(f'Sent "{message}" to {phone_number} via {via}')
            elif out.startswith("ERROR:"):
                print(
                    "Failed to send message: "
                    + out
                    + "\nTip: To send SMS to Android, enable Text Message Forwarding in iPhone Settings > Messages."
                )
            else:
                print(f"Send result: {out}")
        else:
            err = (result.stderr or "").strip()
            print(f"Failed to send message (osascript exit {result.returncode}): {err}")
    except FileNotFoundError:
        print("Error: 'osascript' not found. This only works on macOS.")
    except Exception as e:
        print(f"Error sending message: {e}")


if __name__ == "__main__":
    if len(sys.argv) == 3:
        recipient = sys.argv[1]
        message = sys.argv[2]
        send_imessage(recipient, message)
    else:
        print("Usage: python send_imessage.py <phone_number> <message>")
