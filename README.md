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
rm -rf build dist && python3 setup.py py2app -A
```

To run the app in development mode, use:
```
./dist/SpamBack.app/Contents/MacOS/SpamBack
```

The bundled app launches in GUI mode by default. Add `--terminal` flag to the above command for terminal mode.
