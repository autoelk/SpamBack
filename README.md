# SpamBack

Automatically respond to spammers with LLM to waste their time.

## Features

- **Spam Detection**: Uses RoBERTa model to automatically detect spam messages
- **Auto-Reply**: Generates engaging responses using Gemini AI to waste spammers' time
- **Messages-like GUI**: Beautiful dark-themed interface that mimics the macOS Messages app
- **Real-time Monitoring**: Watches your Messages database for incoming spam

## Usage

## Development Build and Run Instructions:

To build the .app file, use:

```
rm -rf build dist && pyinstaller ./SpamBack.spec
```

To run the app directly from source, use:

```
python3 -m spamback --gui
```
