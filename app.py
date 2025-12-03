#!/usr/bin/env python3
"""
Launcher for the SpamBack app bundle. Launches GUI by default.
"""
import sys
import threading
from spamback.gui import create_gui
from spamback import watcher


def main():
    # Check for --terminal flag to run in terminal mode
    if "--terminal" in sys.argv or "-t" in sys.argv:
        from spamback.cli import main as cli_main
        cli_main()
        return
    
    # GUI mode (default for app bundle)
    gui = create_gui()
    
    # Start watcher in background thread
    watcher_thread = threading.Thread(
        target=watcher.main,
        args=(gui,),
        daemon=True
    )
    watcher_thread.start()
    
    # Run the GUI main loop
    gui.run()


if __name__ == "__main__":
    main()
