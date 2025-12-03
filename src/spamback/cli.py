import argparse
import threading
from . import watcher


def main():
    parser = argparse.ArgumentParser(
        description="SpamBack - Automatically respond to spam messages"
    )
    parser.add_argument(
        "--gui", "-g",
        action="store_true",
        help="Launch the graphical user interface"
    )
    parser.add_argument(
        "--terminal", "-t",
        action="store_true",
        help="Run in terminal mode (default)"
    )
    
    args = parser.parse_args()
    
    if args.gui:
        # Launch GUI mode
        from .gui import create_gui
        
        gui = create_gui()
        
        # Start watcher in background thread
        watcher_thread = threading.Thread(
            target=watcher.main,
            args=(gui,),
            daemon=True
        )
        watcher_thread.start()
        
        # Run the GUI main loop (blocks until window closed)
        gui.run()
    else:
        # Terminal mode (default)
        watcher.main()
