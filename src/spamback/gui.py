"""
SpamBack GUI - A Messages-like interface for viewing spam detection and auto-replies.
"""

import tkinter as tk
from tkinter import ttk, font
import threading
import queue
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, Callable
import os


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
    
    def __init__(self, parent, conversation: Conversation, on_click: Callable, selected: bool = False, **kwargs):
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
            spam_dot = tk.Canvas(content, width=8, height=8, bg=bg_color, highlightthickness=0)
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
                text=conversation.last_message.timestamp.split()[0] if conversation.last_message else "",
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
        
        self._setup_ui()
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
        header_label.pack(pady=15)
        
        # Status indicator
        status_frame = tk.Frame(self.sidebar, bg="#1e1e1e")
        status_frame.pack(fill="x", padx=12, pady=8)
        
        self.status_dot = tk.Canvas(status_frame, width=8, height=8, bg="#1e1e1e", highlightthickness=0)
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
        self.conv_scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=self.conv_canvas.yview)
        self.conv_list_frame = tk.Frame(self.conv_canvas, bg="#1e1e1e")
        
        self.conv_canvas.configure(yscrollcommand=self.conv_scrollbar.set)
        
        self.conv_scrollbar.pack(side="right", fill="y")
        self.conv_canvas.pack(side="left", fill="both", expand=True)
        
        self.conv_canvas_window = self.conv_canvas.create_window((0, 0), window=self.conv_list_frame, anchor="nw")
        
        self.conv_list_frame.bind("<Configure>", lambda e: self.conv_canvas.configure(scrollregion=self.conv_canvas.bbox("all")))
        self.conv_canvas.bind("<Configure>", lambda e: self.conv_canvas.itemconfig(self.conv_canvas_window, width=e.width))
        
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
        self.message_header_label.pack(pady=18)
        
        # Message list container
        message_container = tk.Frame(self.content, bg="#1e1e1e")
        message_container.pack(fill="both", expand=True)
        
        # Canvas for scrollable messages
        self.msg_canvas = tk.Canvas(message_container, bg="#1e1e1e", highlightthickness=0)
        self.msg_scrollbar = ttk.Scrollbar(message_container, orient="vertical", command=self.msg_canvas.yview)
        self.msg_list_frame = tk.Frame(self.msg_canvas, bg="#1e1e1e")
        
        self.msg_canvas.configure(yscrollcommand=self.msg_scrollbar.set)
        
        self.msg_scrollbar.pack(side="right", fill="y")
        self.msg_canvas.pack(side="left", fill="both", expand=True)
        
        self.msg_canvas_window = self.msg_canvas.create_window((0, 0), window=self.msg_list_frame, anchor="nw")
        
        self.msg_list_frame.bind("<Configure>", lambda e: self.msg_canvas.configure(scrollregion=self.msg_canvas.bbox("all")))
        self.msg_canvas.bind("<Configure>", lambda e: self.msg_canvas.itemconfig(self.msg_canvas_window, width=e.width))
        
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
    
    def add_message(self, sender: str, text: str, timestamp: str, is_from_me: bool = False, 
                    is_spam: bool = False, is_spammer: bool = False, service: str = "imessage"):
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
        
        # Scroll to bottom
        self.msg_canvas.update_idletasks()
        self.msg_canvas.yview_moveto(1.0)
    
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
        self.message_queue.put({
            "action": "stats",
            "spammer_count": spammer_count,
            "reply_count": reply_count,
        })
    
    def run(self):
        """Start the GUI main loop."""
        self.root.mainloop()


def create_gui() -> SpamBackGUI:
    """Create and return a new GUI instance."""
    return SpamBackGUI()


if __name__ == "__main__":
    # Test the GUI standalone
    gui = create_gui()
    gui.set_status("Watching for messages...", running=True)
    
    # Add some test messages
    gui.add_message(
        sender="+1234567890",
        text="Congratulations! You've won a free iPhone! Click here to claim.",
        timestamp="2024-01-15 10:30:00",
        is_from_me=False,
        is_spam=True,
        is_spammer=True,
    )
    
    gui.add_message(
        sender="+1234567890",
        text="Oh wow, that's amazing! How do I claim my prize?",
        timestamp="2024-01-15 10:30:15",
        is_from_me=True,
        is_spam=False,
    )
    
    gui.add_message(
        sender="+0987654321",
        text="Hey, just checking in!",
        timestamp="2024-01-15 09:00:00",
        is_from_me=False,
        is_spam=False,
    )
    
    gui.update_stats(spammer_count=1, reply_count=1)
    
    gui.run()
