from setuptools import setup

APP = ["app.py"]
OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "CFBundleName": "SpamBack",
        "CFBundleIdentifier": "com.autoelk.spamback",
        "CFBundleShortVersionString": "0.1.0",
        "NSAppleEventsUsageDescription": "SpamBack needs to send Apple Events to control Messages and Contacts.",
        "NSContactsUsageDescription": "SpamBack may read Contacts (via Apple Events) to match senders.",
        "LSBackgroundOnly": True,  # Run as a background app
    },
}

setup(
    app=APP,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
    packages=["spamback"],
    package_dir={"": "src"},
)
