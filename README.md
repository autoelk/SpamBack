# SpamBack

Utilities for iMessage on macOS: read recent messages, watch for new ones, send messages, and check Contacts.

## Install (editable dev)

```bash
# from project root
python3 -m pip install -e .
```

## Usage

After install, a `spamback` command is available:

```bash
# Read last 10 messages
spamback read --limit 10

# Watch for new incoming messages (Ctrl+C to stop)
spamback watch --interval 2.0

# Send a message
spamback send "+15551234567" "Hello from spamback!"

# Check if a phone/email is in Contacts
spamback check-contact "+15551234567"
spamback check-contact "alice@example.com"
```

Alternatively, without installing, you can run via module:

```bash
python3 -m spamback read --limit 5
python3 -m spamback watch
```

## Packaging to an executable/app

- Standalone binary (quickest):

  - Use PyInstaller: `pyinstaller -F -n spamback src/spamback/cli.py`
  - Or for module entrypoint: `pyinstaller -F -n spamback -m spamback`
  - Note: Automation (AppleScript) and Full Disk Access permissions still need to be granted to the built binary.

- macOS .app bundle:
  - Use `py2app` or `briefcase` to produce a proper app bundle with icon and Info.plist.
  - Add an app icon and configure bundle identifiers.

## Permissions you’ll need on macOS

- Reading Messages DB: grant Full Disk Access to your terminal or the built app.
- Sending messages / Contacts lookup: allow Automation for controlling “Messages” / “Contacts”.

## Notes

- This project uses only the system SQLite DB and AppleScript. No private APIs.
- For production-grade Contacts access without AppleScript prompts, consider `pyobjc` and the Contacts framework.
