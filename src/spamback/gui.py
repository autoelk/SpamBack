"""
SpamBack GUI - A Messages-like interface for viewing spam detection and auto-replies.
"""

import tkinter as tk
from tkinter import ttk
import queue
import os
import json
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Callable


@dataclass
class Message:
    """Represents a single message in a conversation."""

    text: str
    sender: str
    timestamp: str
    is_from_me: bool
    is_spam: bool = False
    service: str = "imessage"


@dataclass
class Conversation:
    """Represents a conversation with a contact."""

    sender: str
    messages: list[Message]
    is_spammer: bool = False
    service: str = "imessage"

    @property
    def last_message(self) -> Optional[Message]:
        return self.messages[-1] if self.messages else None

    @property
    def display_name(self) -> str:
        """Format the sender for display."""
        return self.sender or "Unknown"


class MessageBubble(tk.Frame):
    """A chat bubble widget that mimics macOS Messages style."""

    def __init__(self, parent, message: Message, **kwargs):
        super().__init__(parent, **kwargs)
        self.message = message
        self.configure(bg="#1e1e1e")  # Dark background like Messages

        # Determine bubble colors based on message type
        if message.is_from_me:
            bubble_bg = "#0b84fe"  # Blue for sent messages
            text_color = "#ffffff"
            anchor = "e"
            padx = (60, 10)
        else:
            if message.is_spam:
                bubble_bg = "#ff3b30"  # Red for spam
            else:
                bubble_bg = "#3a3a3c"  # Gray for received messages
            text_color = "#ffffff"
            anchor = "w"
            padx = (10, 60)

        # Create bubble frame
        bubble_frame = tk.Frame(self, bg=bubble_bg)
        bubble_frame.pack(anchor=anchor, padx=padx, pady=2)

        # Message text
        msg_label = tk.Label(
            bubble_frame,
            text=message.text,
            bg=bubble_bg,
            fg=text_color,
            font=("SF Pro", 13),
            wraplength=300,
            justify="left" if not message.is_from_me else "right",
            padx=12,
            pady=8,
        )
        msg_label.pack()

        # Timestamp (small, below bubble)
        time_label = tk.Label(
            self,
            text=message.timestamp,
            bg="#1e1e1e",
            fg="#8e8e93",
            font=("SF Pro", 9),
        )
        time_label.pack(anchor=anchor, padx=padx)


class ConversationListItem(tk.Frame):
    """A conversation list item widget."""

    def __init__(
        self,
        parent,
        conversation: Conversation,
        on_click: Callable,
        selected: bool = False,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self.conversation = conversation
        self.on_click = on_click

        bg_color = "#2c2c2e" if selected else "#1e1e1e"
        hover_color = "#3a3a3c"

        self.configure(bg=bg_color, cursor="hand2")

        # Bind click events
        self.bind("<Button-1>", lambda e: on_click(conversation))

        # Hover effects
        def on_enter(e):
            if not selected:
                self.configure(bg=hover_color)
                for child in self.winfo_children():
                    try:
                        child.configure(bg=hover_color)
                    except tk.TclError:
                        pass

        def on_leave(e):
            if not selected:
                self.configure(bg=bg_color)
                for child in self.winfo_children():
                    try:
                        child.configure(bg=bg_color)
                    except tk.TclError:
                        pass

        self.bind("<Enter>", on_enter)
        self.bind("<Leave>", on_leave)

        # Container for content
        content = tk.Frame(self, bg=bg_color)
        content.pack(fill="x", padx=12, pady=8)
        content.bind("<Button-1>", lambda e: on_click(conversation))

        # Spam indicator (red dot)
        if conversation.is_spammer:
            spam_dot = tk.Canvas(
                content, width=8, height=8, bg=bg_color, highlightthickness=0
            )
            spam_dot.create_oval(0, 0, 8, 8, fill="#ff3b30", outline="")
            spam_dot.pack(side="left", padx=(0, 8))
            spam_dot.bind("<Button-1>", lambda e: on_click(conversation))

        # Name and preview container
        text_container = tk.Frame(content, bg=bg_color)
        text_container.pack(side="left", fill="x", expand=True)
        text_container.bind("<Button-1>", lambda e: on_click(conversation))

        # Sender name
        name_color = "#ff3b30" if conversation.is_spammer else "#ffffff"
        name_label = tk.Label(
            text_container,
            text=conversation.display_name,
            bg=bg_color,
            fg=name_color,
            font=("SF Pro", 13, "bold"),
            anchor="w",
        )
        name_label.pack(anchor="w")
        name_label.bind("<Button-1>", lambda e: on_click(conversation))

        # Last message preview
        preview_text = ""
        if conversation.last_message:
            prefix = "You: " if conversation.last_message.is_from_me else ""
            preview_text = prefix + conversation.last_message.text[:40]
            if len(conversation.last_message.text) > 40:
                preview_text += "..."

        preview_label = tk.Label(
            text_container,
            text=preview_text,
            bg=bg_color,
            fg="#8e8e93",
            font=("SF Pro", 11),
            anchor="w",
        )
        preview_label.pack(anchor="w")
        preview_label.bind("<Button-1>", lambda e: on_click(conversation))

        # Timestamp on right
        if conversation.last_message:
            time_label = tk.Label(
                content,
                text=(
                    conversation.last_message.timestamp.split()[0]
                    if conversation.last_message
                    else ""
                ),
                bg=bg_color,
                fg="#8e8e93",
                font=("SF Pro", 10),
            )
            time_label.pack(side="right")
            time_label.bind("<Button-1>", lambda e: on_click(conversation))


class SpamBackGUI:
    """Main GUI application mimicking macOS Messages."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SpamBack")
        self.root.geometry("900x600")
        self.root.minsize(700, 400)

        # Set dark appearance
        self.root.configure(bg="#1e1e1e")

        # Conversations storage
        self.conversations: dict[str, Conversation] = {}
        self.selected_conversation: Optional[str] = None

        # Message queue for thread-safe updates
        self.message_queue = queue.Queue()

        # Status
        self.status_text = tk.StringVar(value="Initializing...")
        self.is_running = False

        # Paths
        self.env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        self.config_dir = Path.home() / "Library" / "Application Support" / "SpamBack"
        self.config_path = self.config_dir / "config.json"

        self._setup_ui()
        self._check_permissions()  # Make sure we have full disk access
        self._poll_queue()

    def _setup_ui(self):
        """Set up the main UI components."""
        # Main container
        main_container = tk.Frame(self.root, bg="#1e1e1e")
        main_container.pack(fill="both", expand=True)

        # Left sidebar (conversation list)
        self.sidebar = tk.Frame(main_container, bg="#1e1e1e", width=280)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Sidebar header
        sidebar_header = tk.Frame(self.sidebar, bg="#2c2c2e", height=60)
        sidebar_header.pack(fill="x")
        sidebar_header.pack_propagate(False)

        header_label = tk.Label(
            sidebar_header,
            text="SpamBack",
            bg="#2c2c2e",
            fg="#ffffff",
            font=("SF Pro", 18, "bold"),
        )
        header_label.pack(side="left", padx=12, pady=15)

        # Status indicator
        status_frame = tk.Frame(self.sidebar, bg="#1e1e1e")
        status_frame.pack(fill="x", padx=12, pady=8)

        self.status_dot = tk.Canvas(
            status_frame, width=8, height=8, bg="#1e1e1e", highlightthickness=0
        )
        self.status_dot.create_oval(0, 0, 8, 8, fill="#8e8e93", outline="", tags="dot")
        self.status_dot.pack(side="left", padx=(0, 6))

        status_label = tk.Label(
            status_frame,
            textvariable=self.status_text,
            bg="#1e1e1e",
            fg="#8e8e93",
            font=("SF Pro", 11),
        )
        status_label.pack(side="left")

        # Conversation list container with scrollbar
        list_container = tk.Frame(self.sidebar, bg="#1e1e1e")
        list_container.pack(fill="both", expand=True)

        # Canvas for scrollable conversation list
        self.conv_canvas = tk.Canvas(list_container, bg="#1e1e1e", highlightthickness=0)
        self.conv_scrollbar = ttk.Scrollbar(
            list_container, orient="vertical", command=self.conv_canvas.yview
        )
        self.conv_list_frame = tk.Frame(self.conv_canvas, bg="#1e1e1e")

        self.conv_canvas.configure(yscrollcommand=self.conv_scrollbar.set)

        self.conv_scrollbar.pack(side="right", fill="y")
        self.conv_canvas.pack(side="left", fill="both", expand=True)

        self.conv_canvas_window = self.conv_canvas.create_window(
            (0, 0), window=self.conv_list_frame, anchor="nw"
        )

        self.conv_list_frame.bind(
            "<Configure>",
            lambda e: self.conv_canvas.configure(
                scrollregion=self.conv_canvas.bbox("all")
            ),
        )
        self.conv_canvas.bind(
            "<Configure>",
            lambda e: self.conv_canvas.itemconfig(
                self.conv_canvas_window, width=e.width
            ),
        )

        # Separator
        separator = tk.Frame(main_container, bg="#3a3a3c", width=1)
        separator.pack(side="left", fill="y")

        # Right content area (message view)
        self.content = tk.Frame(main_container, bg="#1e1e1e")
        self.content.pack(side="right", fill="both", expand=True)

        # Message area header
        self.message_header = tk.Frame(self.content, bg="#2c2c2e", height=60)
        self.message_header.pack(fill="x")
        self.message_header.pack_propagate(False)

        self.message_header_label = tk.Label(
            self.message_header,
            text="Select a conversation",
            bg="#2c2c2e",
            fg="#ffffff",
            font=("SF Pro", 15, "bold"),
        )
        self.message_header_label.pack(side="left", padx=12, pady=18)

        # Settings (gear) button on the right
        self.settings_btn = tk.Label(
            self.message_header,
            text="⚙",
            bg="#2c2c2e",
            fg="#ffffff",
            font=("SF Pro", 16, "bold"),
            padx=10,
            pady=6,
            cursor="hand2",
        )

        def _gear_enter(_):
            self.settings_btn.configure(bg="#3a3a3c")

        def _gear_leave(_):
            self.settings_btn.configure(bg="#2c2c2e")

        self.settings_btn.bind("<Enter>", _gear_enter)
        self.settings_btn.bind("<Leave>", _gear_leave)
        self.settings_btn.bind("<Button-1>", lambda _: self._open_settings_dialog())
        self.settings_btn.pack(side="right", padx=12, pady=12)

        # Message list container
        message_container = tk.Frame(self.content, bg="#1e1e1e")
        message_container.pack(fill="both", expand=True)

        # Canvas for scrollable messages
        self.msg_canvas = tk.Canvas(
            message_container, bg="#1e1e1e", highlightthickness=0
        )
        self.msg_scrollbar = ttk.Scrollbar(
            message_container, orient="vertical", command=self.msg_canvas.yview
        )
        self.msg_list_frame = tk.Frame(self.msg_canvas, bg="#1e1e1e")

        self.msg_canvas.configure(yscrollcommand=self.msg_scrollbar.set)

        self.msg_scrollbar.pack(side="right", fill="y")
        self.msg_canvas.pack(side="left", fill="both", expand=True)

        self.msg_canvas_window = self.msg_canvas.create_window(
            (0, 0), window=self.msg_list_frame, anchor="nw"
        )

        self.msg_list_frame.bind(
            "<Configure>",
            lambda e: self.msg_canvas.configure(
                scrollregion=self.msg_canvas.bbox("all")
            ),
        )
        self.msg_canvas.bind(
            "<Configure>",
            lambda e: self.msg_canvas.itemconfig(self.msg_canvas_window, width=e.width),
        )

        # Empty state message
        self.empty_label = tk.Label(
            self.content,
            text="No messages yet.\nSpamBack is watching for incoming spam...",
            bg="#1e1e1e",
            fg="#8e8e93",
            font=("SF Pro", 14),
            justify="center",
        )
        self.empty_label.place(relx=0.5, rely=0.5, anchor="center")

        # Stats bar at bottom
        stats_bar = tk.Frame(self.content, bg="#2c2c2e", height=40)
        stats_bar.pack(side="bottom", fill="x")
        stats_bar.pack_propagate(False)

        self.stats_label = tk.Label(
            stats_bar,
            text="0 spammers detected | 0 auto-replies sent",
            bg="#2c2c2e",
            fg="#8e8e93",
            font=("SF Pro", 11),
        )
        self.stats_label.pack(pady=10)

    def _check_permissions(self):
        """Check if Full Disk Access is granted and show permission screen if not."""
        from .permissions import has_full_disk_access, open_system_preferences_privacy

        if not has_full_disk_access():
            # Hide the main UI and show permission screen
            self._show_permission_screen(open_system_preferences_privacy)

    def _show_permission_screen(self, open_settings_callback):
        """Show a full-screen permission request overlay."""
        # Create overlay frame
        self.permission_overlay = tk.Frame(self.root, bg="#1e1e1e")
        self.permission_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)

        # Center content container
        content = tk.Frame(self.permission_overlay, bg="#1e1e1e")
        content.place(relx=0.5, rely=0.5, anchor="center")

        # Warning icon (red circle with !)
        icon_canvas = tk.Canvas(
            content, width=80, height=80, bg="#1e1e1e", highlightthickness=0
        )
        icon_canvas.create_oval(10, 10, 70, 70, fill="#ff3b30", outline="")
        icon_canvas.create_text(
            40, 40, text="!", fill="#ffffff", font=("SF Pro", 40, "bold")
        )
        icon_canvas.pack(pady=(0, 20))

        # Title
        title = tk.Label(
            content,
            text="Full Disk Access Required",
            bg="#1e1e1e",
            fg="#ffffff",
            font=("SF Pro", 24, "bold"),
        )
        title.pack(pady=(0, 20))

        # Instructions
        instructions = tk.Label(
            content,
            text=(
                "SpamBack needs Full Disk Access to read your Messages database.\n"
                "Without this permission, SpamBack cannot detect spam messages.\n\n"
                "Steps to grant access:\n"
                "1. Click Open System Settings\n"
                "2. Find the SpamBack app in the list\n"
                "3. Click the toggle to enable Full Disk Access\n"
                "4. Reopen SpamBack"
            ),
            bg="#1e1e1e",
            fg="#8e8e93",
            font=("SF Pro", 14),
            justify="center",
        )
        instructions.pack(pady=(0, 30))

        # Buttons frame
        buttons = tk.Frame(content, bg="#1e1e1e")
        buttons.pack()

        def make_button(parent, text, bg, hover_bg, command):
            btn = tk.Label(
                parent,
                text=text,
                bg=bg,
                fg="#ffffff",
                padx=18,
                pady=10,
                font=("SF Pro", 14, "bold"),
                cursor="hand2",
                bd=0,
                relief="flat",
                highlightthickness=0,
            )

            def on_enter(_):
                btn.configure(bg=hover_bg)

            def on_leave(_):
                btn.configure(bg=bg)

            def on_click(_):
                command()

            btn.bind("<Enter>", on_enter)
            btn.bind("<Leave>", on_leave)
            btn.bind("<Button-1>", on_click)
            btn.pack(side="left", padx=5)
            return btn

        make_button(
            buttons,
            "Open System Settings",
            "#0b84fe",
            "#0a74dd",
            lambda: [open_settings_callback(), self.root.quit()],
        )

        make_button(
            buttons,
            "Quit",
            "#3a3a3c",
            "#2c2c2e",
            self.root.quit,
        )

    def _open_settings_dialog(self):
        """Open Settings screen (hosts API key and preferences)."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Settings")
        dlg.configure(bg="#1e1e1e")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        container = tk.Frame(dlg, bg="#1e1e1e", padx=24, pady=20)
        container.pack(fill="both", expand=True)

        # Preferences section
        tk.Label(
            container,
            text="Preferences",
            bg="#1e1e1e",
            fg="#ffffff",
            font=("SF Pro", 14, "bold"),
            anchor="w",
        ).pack(anchor="w")

        # Whitelist contacts toggle
        toggle_frame = tk.Frame(container, bg="#1e1e1e")
        toggle_frame.pack(fill="x", pady=(8, 16))

        tk.Label(
            toggle_frame,
            text="Whitelist numbers in Contacts",
            bg="#1e1e1e",
            fg="#ffffff",
            font=("SF Pro", 13),
        ).pack(side="left")

        whitelist_var = tk.BooleanVar(value=self._load_whitelist_contacts())
        chk = ttk.Checkbutton(toggle_frame, variable=whitelist_var)
        chk.pack(side="right")

        # Separator
        sep = tk.Frame(container, bg="#3a3a3c", height=1)
        sep.pack(fill="x", pady=(0, 16))

        # API Key section
        tk.Label(
            container,
            text="API Key",
            bg="#1e1e1e",
            fg="#ffffff",
            font=("SF Pro", 14, "bold"),
            anchor="w",
        ).pack(anchor="w")

        tk.Label(
            container,
            text="You can get one from the Google AI Studio website.",
            bg="#1e1e1e",
            fg="#8e8e93",
            font=("SF Pro", 11),
            anchor="w",
        ).pack(anchor="w", pady=(6, 10))

        # Current API key display
        current_key = self._load_api_key()
        if current_key:
            suffix = current_key[-6:] if len(current_key) > 6 else current_key
            current_text = f"Current key: ...{suffix}"
            current_color = "#30d158"
        else:
            current_text = "No API key set"
            current_color = "#8e8e93"

        tk.Label(
            container,
            text=current_text,
            bg="#1e1e1e",
            fg=current_color,
            font=("SF Pro", 11),
            anchor="w",
        ).pack(anchor="w", pady=(0, 12))

        key_var = tk.StringVar(value=current_key)
        entry = tk.Entry(
            container,
            textvariable=key_var,
            show="*",
            bg="#2c2c2e",
            fg="#ffffff",
            insertbackground="#ffffff",
            relief="flat",
            width=46,
            font=("SF Pro", 12),
        )
        entry.pack(fill="x", pady=(0, 14))
        entry.focus_set()

        btn_row = tk.Frame(container, bg="#1e1e1e")
        btn_row.pack(anchor="e")

        def save_and_close():
            key = key_var.get().strip()
            if key:
                self._save_api_key(key)
            self._save_whitelist_contacts(bool(whitelist_var.get()))
            dlg.destroy()

        def cancel():
            dlg.destroy()

        def make_btn(parent, text, bg, hover_bg, cmd):
            btn = tk.Label(
                parent,
                text=text,
                bg=bg,
                fg="#ffffff",
                padx=14,
                pady=8,
                font=("SF Pro", 12, "bold"),
                cursor="hand2",
            )
            btn.bind("<Enter>", lambda _: btn.configure(bg=hover_bg))
            btn.bind("<Leave>", lambda _: btn.configure(bg=bg))
            btn.bind("<Button-1>", lambda _: cmd())
            btn.pack(side="right", padx=(8, 0))
            return btn

        make_btn(btn_row, "Save", "#0b84fe", "#0a74dd", save_and_close)
        make_btn(btn_row, "Cancel", "#3a3a3c", "#2c2c2e", cancel)

        dlg.update_idletasks()
        w, h = dlg.winfo_width(), dlg.winfo_height()
        sw, sh = dlg.winfo_screenwidth(), dlg.winfo_screenheight()
        x, y = int((sw - w) / 2), int((sh - h) / 3)
        dlg.geometry(f"{w}x{h}+{x}+{y}")

        dlg.protocol("WM_DELETE_WINDOW", cancel)
        self.root.wait_window(dlg)

    def _poll_queue(self):
        """Poll the message queue for updates from the watcher thread."""
        try:
            while True:
                item = self.message_queue.get_nowait()
                self._process_queue_item(item)
        except queue.Empty:
            pass

        # Schedule next poll
        self.root.after(100, self._poll_queue)

    def _process_queue_item(self, item: dict):
        """Process an item from the message queue."""
        action = item.get("action")

        if action == "status":
            self.set_status(item.get("text", ""), item.get("running", False))
        elif action == "message":
            self.add_message(
                sender=item.get("sender", "Unknown"),
                text=item.get("text", ""),
                timestamp=item.get("timestamp", ""),
                is_from_me=item.get("is_from_me", False),
                is_spam=item.get("is_spam", False),
                is_spammer=item.get("is_spammer", False),
                service=item.get("service", "imessage"),
            )
        elif action == "stats":
            self.update_stats(
                spammer_count=item.get("spammer_count", 0),
                reply_count=item.get("reply_count", 0),
            )

    def set_status(self, text: str, running: bool = False):
        """Update the status indicator."""
        self.status_text.set(text)
        self.is_running = running
        color = "#30d158" if running else "#8e8e93"  # Green when running
        self.status_dot.itemconfig("dot", fill=color)

    def add_message(
        self,
        sender: str,
        text: str,
        timestamp: str,
        is_from_me: bool = False,
        is_spam: bool = False,
        is_spammer: bool = False,
        service: str = "imessage",
    ):
        """Add a message to a conversation."""
        # Normalize sender for storage key
        sender_key = sender.lower().strip()

        # Create message object
        message = Message(
            text=text,
            sender=sender,
            timestamp=timestamp,
            is_from_me=is_from_me,
            is_spam=is_spam,
            service=service,
        )

        # Get or create conversation
        if sender_key not in self.conversations:
            self.conversations[sender_key] = Conversation(
                sender=sender,
                messages=[],
                is_spammer=is_spammer,
                service=service,
            )

        conversation = self.conversations[sender_key]
        conversation.messages.append(message)

        if is_spammer:
            conversation.is_spammer = True

        # Hide empty state
        self.empty_label.place_forget()

        # Refresh the conversation list
        self._refresh_conversation_list()

        # If this conversation is selected, refresh the message view
        if self.selected_conversation == sender_key:
            self._refresh_message_view()

    def _select_conversation(self, conversation: Conversation):
        """Select a conversation to view."""
        sender_key = conversation.sender.lower().strip()
        self.selected_conversation = sender_key

        # Update header
        title = conversation.display_name
        if conversation.is_spammer:
            title += " ⚠️ SPAMMER"
        self.message_header_label.config(text=title)

        # Refresh both views
        self._refresh_conversation_list()
        self._refresh_message_view()

    def _refresh_conversation_list(self):
        """Refresh the conversation list display."""
        # Clear existing items
        for widget in self.conv_list_frame.winfo_children():
            widget.destroy()

        # Sort conversations by last message time (most recent first)
        sorted_convs = sorted(
            self.conversations.values(),
            key=lambda c: c.last_message.timestamp if c.last_message else "",
            reverse=True,
        )

        # Add conversation items
        for conv in sorted_convs:
            sender_key = conv.sender.lower().strip()
            is_selected = sender_key == self.selected_conversation

            item = ConversationListItem(
                self.conv_list_frame,
                conv,
                on_click=self._select_conversation,
                selected=is_selected,
            )
            item.pack(fill="x")

            # Separator line
            sep = tk.Frame(self.conv_list_frame, bg="#3a3a3c", height=1)
            sep.pack(fill="x")

    def _refresh_message_view(self):
        """Refresh the message view for the selected conversation."""
        # Clear existing messages
        for widget in self.msg_list_frame.winfo_children():
            widget.destroy()

        if not self.selected_conversation:
            return

        conversation = self.conversations.get(self.selected_conversation)
        if not conversation:
            return

        # Add message bubbles
        for message in conversation.messages:
            bubble = MessageBubble(self.msg_list_frame, message)
            bubble.pack(fill="x", pady=2)

        # Ensure scrollregion is updated, then scroll to bottom after layout
        def _schedule_scroll_bottom():
            self.msg_canvas.update_idletasks()
            bbox = self.msg_canvas.bbox("all")
            if bbox:
                self.msg_canvas.configure(scrollregion=bbox)
            self.msg_canvas.yview_moveto(1.0)

        self.root.after(0, _schedule_scroll_bottom)

    def update_stats(self, spammer_count: int, reply_count: int):
        """Update the stats bar."""
        self.stats_label.config(
            text=f"{spammer_count} spammer{'s' if spammer_count != 1 else ''} detected | "
            f"{reply_count} auto-repl{'ies' if reply_count != 1 else 'y'} sent"
        )

    def queue_message(self, **kwargs):
        """Thread-safe method to queue a message for display."""
        kwargs["action"] = "message"
        self.message_queue.put(kwargs)

    def queue_status(self, text: str, running: bool = False):
        """Thread-safe method to update status."""
        self.message_queue.put({"action": "status", "text": text, "running": running})

    def queue_stats(self, spammer_count: int, reply_count: int):
        """Thread-safe method to update stats."""
        self.message_queue.put(
            {
                "action": "stats",
                "spammer_count": spammer_count,
                "reply_count": reply_count,
            }
        )

    def run(self):
        """Start the GUI main loop."""
        self.root.mainloop()

    # ------------------------------------------------------------------
    # Config helpers
    def _load_api_key(self) -> str:
        """Load API key from app-support config.json"""
        if self.config_path.exists():
            try:
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("GEMINI_API_KEY"):
                    return str(data["GEMINI_API_KEY"])
            except Exception:
                pass
        return ""

    def _save_api_key(self, key: str):
        """Persist API key to app-support config only."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            payload = {}
            if self.config_path.exists():
                try:
                    existing = json.loads(self.config_path.read_text(encoding="utf-8"))
                    if isinstance(existing, dict):
                        payload.update(existing)
                except Exception:
                    pass
            payload["GEMINI_API_KEY"] = key
            self.config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _load_whitelist_contacts(self) -> bool:
        """Load whitelist_contacts setting (default True)."""
        if self.config_path.exists():
            try:
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
                val = data.get("whitelist_contacts")
                if isinstance(val, bool):
                    return val
            except Exception:
                pass
        return True

    def _save_whitelist_contacts(self, enabled: bool):
        """Persist whitelist_contacts setting."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            payload = {}
            if self.config_path.exists():
                try:
                    existing = json.loads(self.config_path.read_text(encoding="utf-8"))
                    if isinstance(existing, dict):
                        payload.update(existing)
                except Exception:
                    pass
            payload["whitelist_contacts"] = bool(enabled)
            self.config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            pass


def create_gui() -> SpamBackGUI:
    """Create and return a new GUI instance."""
    return SpamBackGUI()


if __name__ == "__main__":
    # Test the GUI standalone
    gui = create_gui()
    gui.set_status("Watching for messages...", running=True)

    gui.update_stats(spammer_count=1, reply_count=1)

    gui.run()
