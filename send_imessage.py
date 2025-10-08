import subprocess
import sys


def send_imessage(phone_number, message):
    applescript = """
    on run {targetNumber, messageText}
        tell application "Messages"
            set targetService to 1st service whose service type = iMessage
            set targetBuddy to buddy targetNumber of targetService
            send messageText to targetBuddy
        end tell
    end run
    """

    try:
        result = subprocess.run(
            ["osascript", "-e", applescript, phone_number, message],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            print(f'Successfully sent "{message}" to {phone_number}')
        else:
            print(f"Failed to send message: {result.stderr}")
    except Exception as e:
        print(f"Error sending message: {e}")


if __name__ == "__main__":
    if len(sys.argv) == 3:
        recipient = sys.argv[1]
        message = sys.argv[2]
        send_imessage(recipient, message)
    else:
        print("Usage: python send_imessage.py <phone_number> <message>")
