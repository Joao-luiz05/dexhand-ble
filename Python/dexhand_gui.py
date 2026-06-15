"""
DexHand GUI Controller
======================
Top-down hand schematic with clickable servo regions, sidebar gesture buttons,
and serial (USB) control. A "Switch to BLE" button launches the external BLE script.

Requirements:
    pip install pyserial

Usage:
    python dexhand_gui.py
    python dexhand_gui.py --port COM3          # specify port directly
    python dexhand_gui.py --ble-script path/to/ble_script.py
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import serial
import serial.tools.list_ports
import threading
import subprocess
import sys
import argparse
import time

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WINDOW_TITLE  = "DexHand Controller"
BG_DARK       = "#1e1e2e"
BG_PANEL      = "#2a2a3e"
BG_CARD       = "#313145"
ACCENT        = "#7c6af7"
ACCENT_HOVER  = "#9d8fff"
ACCENT_ACTIVE = "#5a4ecc"
TEXT_LIGHT    = "#e0e0f0"
TEXT_DIM      = "#888aaa"
SUCCESS       = "#50fa7b"
WARNING       = "#ffb86c"
DANGER        = "#ff5555"
SERVO_IDLE    = "#3d3d5c"
SERVO_HOVER   = "#7c6af7"
SERVO_ACTIVE  = "#9d8fff"
SERVO_OUTLINE = "#555577"

BAUD_RATE = 9600

# Servo definitions  (index matches the Arduino #defines)
SERVOS = [
    {"id": 0,  "name": "Index Lower",   "group": "index"},
    {"id": 1,  "name": "Index Upper",   "group": "index"},
    {"id": 2,  "name": "Middle Lower",  "group": "middle"},
    {"id": 3,  "name": "Middle Upper",  "group": "middle"},
    {"id": 4,  "name": "Ring Lower",    "group": "ring"},
    {"id": 5,  "name": "Ring Upper",    "group": "ring"},
    {"id": 6,  "name": "Pinky Lower",   "group": "pinky"},
    {"id": 7,  "name": "Pinky Upper",   "group": "pinky"},
    {"id": 8,  "name": "Index Tip",     "group": "index"},
    {"id": 9,  "name": "Middle Tip",    "group": "middle"},
    {"id": 10, "name": "Ring Tip",      "group": "ring"},
    {"id": 11, "name": "Pinky Tip",     "group": "pinky"},
    {"id": 12, "name": "Thumb Tip",     "group": "thumb"},
    {"id": 13, "name": "Thumb Right",   "group": "thumb"},
    {"id": 14, "name": "Thumb Left",    "group": "thumb"},
    {"id": 15, "name": "Thumb Rotate",  "group": "thumb"},
    {"id": 16, "name": "Wrist Left",    "group": "wrist"},
    {"id": 17, "name": "Wrist Right",   "group": "wrist"},
]

SERVO_RANGES = {
    0:  (30, 110), 1:  (30, 140), 2:  (30, 120), 3:  (30, 150),
    4:  (30, 150), 5:  (30, 100), 6:  (30, 140), 7:  (30, 100),
    8:  (30, 100), 9:  (30, 90),  10: (30, 120), 11: (30, 130),
    12: (30, 130), 13: (30, 150), 14: (20, 120), 15: (30, 90),
    16: (30, 160), 17: (30, 160),
}

CANNED_GESTURES = [
    ("Default",    "default"),
    ("Count",      "count"),
    ("Wave",       "wave"),
    ("Shaka",      "shaka"),
    ("Fist (0)",   "zero"),
    ("One",        "one"),
    ("Two",        "two"),
    ("Three",      "three"),
    ("Four",       "four"),
    ("Finger Test","fingertest"),
    ("Thumb Test", "thumbtest"),
]

GESTURE_DESCRIPTIONS = {
    "Default":    "Return the hand to the neutral resting pose.",
    "Count":      "Curl fingers in sequence from index through pinky.",
    "Wave":       "Open and close the hand in a wave-style motion.",
    "Shaka":      "Extend thumb and pinky while curling the middle fingers.",
    "Fist (0)":   "Close all fingers into a basic fist.",
    "One":        "Raise only the index finger.",
    "Two":        "Raise the index and middle fingers.",
    "Three":      "Raise the index, middle, and ring fingers.",
    "Four":       "Raise all fingers except the thumb.",
    "Finger Test": "Sweep each finger through its range for calibration.",
    "Thumb Test":  "Exercise the thumb through its full range of motion.",
}

FINGER_COMMANDS = [
    ("Index Max",    "fingermax:0"),
    ("Index Min",    "fingermin:0"),
    ("Middle Max",   "fingermax:1"),
    ("Middle Min",   "fingermin:1"),
    ("Ring Max",     "fingermax:2"),
    ("Ring Min",     "fingermin:2"),
    ("Pinky Max",    "fingermax:3"),
    ("Pinky Min",    "fingermin:3"),
]

GROUP_COLORS = {
    "index":  "#6ec6f5",
    "middle": "#74f5b8",
    "ring":   "#f5c46e",
    "pinky":  "#f57bb0",
    "thumb":  "#c97bf5",
    "wrist":  "#f5f574",
}

# ---------------------------------------------------------------------------
# Hand schematic layout  (canvas is 460 × 560)
# Each servo is described as an ellipse: (cx, cy, rx, ry, label_dy)
# Coordinates are in a 460×560 space; we scale at draw time.
# ---------------------------------------------------------------------------

CANVAS_W = 460
CANVAS_H = 560

# (servo_id, cx, cy, rx, ry)
SERVO_SHAPES = {
    # ── Wrist (bottom) ──────────────────────────────────────────────────────
    16: (168, 530, 42, 18),   # Wrist Left
    17: (292, 530, 42, 18),   # Wrist Right

    # ── Thumb (left side, angled) ────────────────────────────────────────────
    14: ( 62, 390, 26, 16),   # Thumb Left
    13: ( 48, 340, 26, 16),   # Thumb Right
    15: ( 70, 295, 22, 14),   # Thumb Rotate
    12: ( 52, 248, 22, 14),   # Thumb Tip

    # ── Index finger ─────────────────────────────────────────────────────────
    0:  (168, 390, 26, 16),   # Index Lower
    1:  (168, 340, 26, 16),   # Index Upper
    8:  (168, 295, 22, 14),   # Index Tip

    # ── Middle finger ────────────────────────────────────────────────────────
    2:  (230, 390, 26, 16),   # Middle Lower
    3:  (230, 335, 26, 16),   # Middle Upper
    9:  (230, 280, 22, 14),   # Middle Tip

    # ── Ring finger ──────────────────────────────────────────────────────────
    4:  (292, 390, 26, 16),   # Ring Lower
    5:  (292, 340, 26, 16),   # Ring Upper
    10: (292, 295, 22, 14),   # Ring Tip

    # ── Pinky finger ─────────────────────────────────────────────────────────
    6:  (354, 390, 26, 16),   # Pinky Lower
    7:  (354, 345, 26, 16),   # Pinky Upper
    11: (354, 305, 22, 14),   # Pinky Tip
}


# ---------------------------------------------------------------------------
# Serial helper
# ---------------------------------------------------------------------------

class SerialManager:
    def __init__(self):
        self.ser = None
        self.port = None
        self.lock = threading.Lock()

    def connect(self, port, baud=BAUD_RATE):
        try:
            self.ser = serial.Serial(port, baud, timeout=1)
            self.port = port
            time.sleep(2)   # let Arduino reset
            return True
        except Exception as e:
            return str(e)

    def disconnect(self):
        with self.lock:
            if self.ser and self.ser.is_open:
                self.ser.close()
            self.ser = None
            self.port = None

    def send(self, cmd):
        with self.lock:
            if self.ser and self.ser.is_open:
                try:
                    self.ser.write((cmd.strip() + "\n").encode())
                    return True
                except Exception as e:
                    return str(e)
        return "Not connected"

    @staticmethod
    def list_ports():
        return [p.device for p in serial.tools.list_ports.comports()]

    @property
    def connected(self):
        return self.ser is not None and self.ser.is_open


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class DexHandApp(tk.Tk):
    def __init__(self, initial_port=None, ble_script=None):
        super().__init__()
        self.ble_script = ble_script or "ble_controller.py"
        self.serial_mgr = SerialManager()
        self.selected_servo = None
        self.hover_servo    = None
        self.servo_canvas_items = {}   # servo_id → canvas oval id
        self.servo_values   = {s["id"]: SERVO_RANGES[s["id"]][0] for s in SERVOS}

        self.title(WINDOW_TITLE)
        self.configure(bg=BG_DARK)
        self.resizable(False, False)

        self._build_ui()
        self._refresh_ports()

        if initial_port:
            self.port_var.set(initial_port)
            self._connect()

    # ── UI construction ─────────────────────────────────────────────────────

    def _build_ui(self):
        # Top bar
        topbar = tk.Frame(self, bg=BG_PANEL, height=52)
        topbar.pack(fill="x", side="top")
        topbar.pack_propagate(False)

        tk.Label(topbar, text="✦  DexHand Controller", font=("Segoe UI", 14, "bold"),
                 bg=BG_PANEL, fg=TEXT_LIGHT).pack(side="left", padx=18, pady=12)

        # BLE switch button (top-right)
        ble_btn = tk.Button(topbar, text="⇄  Switch to BLE",
                            font=("Segoe UI", 10, "bold"),
                            bg=ACCENT, fg="white", relief="flat",
                            activebackground=ACCENT_HOVER, activeforeground="white",
                            padx=12, pady=4, cursor="hand2",
                            command=self._launch_ble)
        ble_btn.pack(side="right", padx=14, pady=10)

        # Connection bar
        connbar = tk.Frame(self, bg=BG_CARD, height=44)
        connbar.pack(fill="x", side="top")
        connbar.pack_propagate(False)

        tk.Label(connbar, text="Port:", bg=BG_CARD, fg=TEXT_DIM,
                 font=("Segoe UI", 10)).pack(side="left", padx=(14, 4), pady=10)

        self.port_var = tk.StringVar()
        self.port_menu = ttk.Combobox(connbar, textvariable=self.port_var,
                                      width=12, state="readonly",
                                      font=("Segoe UI", 10))
        self.port_menu.pack(side="left", pady=10)

        self._styled_btn(connbar, "↻", self._refresh_ports, small=True).pack(side="left", padx=4)
        self.conn_btn = self._styled_btn(connbar, "Connect", self._connect)
        self.conn_btn.pack(side="left", padx=6)

        self.status_lbl = tk.Label(connbar, text="● Disconnected",
                                   bg=BG_CARD, fg=DANGER,
                                   font=("Segoe UI", 10))
        self.status_lbl.pack(side="left", padx=10)

        # Main body
        body = tk.Frame(self, bg=BG_DARK)
        body.pack(fill="both", expand=True)

        # Left sidebar
        sidebar = tk.Frame(body, bg=BG_PANEL, width=200)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        self._build_sidebar(sidebar)

        # Center canvas area
        center = tk.Frame(body, bg=BG_DARK)
        center.pack(side="left", fill="both", expand=True, padx=16, pady=16)
        self._build_canvas(center)

        # Right panel: servo detail
        right = tk.Frame(body, bg=BG_PANEL, width=220)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        self._build_detail_panel(right)

        # Bottom log
        logbar = tk.Frame(self, bg=BG_CARD, height=100)
        logbar.pack(fill="x", side="bottom")
        logbar.pack_propagate(False)
        tk.Label(logbar, text="Serial Log", bg=BG_CARD, fg=TEXT_DIM,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(6, 0))
        self.log_text = tk.Text(logbar, bg=BG_CARD, fg=TEXT_DIM,
                                font=("Consolas", 9), height=4,
                                relief="flat", state="disabled",
                                insertbackground=TEXT_LIGHT)
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(0, 6))

    def _build_sidebar(self, parent):
        tk.Label(parent, text="GESTURES", bg=BG_PANEL, fg=TEXT_DIM,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=14, pady=(14, 4))

        for label, cmd in CANNED_GESTURES:
            b = self._styled_btn(parent, label, lambda c=cmd: self._send(c), wide=True)
            b.pack(fill="x", padx=10, pady=2)
            desc = GESTURE_DESCRIPTIONS.get(label)
            if desc:
                b.bind("<Enter>", lambda e, d=desc: self._show_tooltip(d, e))
                b.bind("<Leave>", lambda e: self._hide_tooltip())
                b.bind("<Motion>", lambda e: self._move_tooltip(e))

        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=10, pady=10)

        tk.Label(parent, text="FINGER CONTROLS", bg=BG_PANEL, fg=TEXT_DIM,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=14, pady=(0, 4))

        finger_frame = tk.Frame(parent, bg=BG_PANEL)
        finger_frame.pack(fill="x", padx=10)
        finger_frame.columnconfigure(0, weight=1)
        finger_frame.columnconfigure(1, weight=1)

        for idx, (label, cmd) in enumerate(FINGER_COMMANDS):
            col = idx % 2
            row = idx // 2
            b = self._styled_btn(finger_frame, label, lambda c=cmd: self._send(c), wide=False)
            b.grid(row=row, column=col, sticky="ew", padx=4, pady=2)

        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=10, pady=10)

        tk.Label(parent, text="WRIST", bg=BG_PANEL, fg=TEXT_DIM,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=14, pady=(0, 4))

        wrist_cmds = [
            ("Pitch +20",  "wrist:pitch:20"),
            ("Pitch -20",  "wrist:pitch:-20"),
            ("Yaw +20",    "wrist:yaw:20"),
            ("Yaw -20",    "wrist:yaw:-20"),
        ]
        for label, cmd in wrist_cmds:
            b = self._styled_btn(parent, label, lambda c=cmd: self._send(c), wide=True)
            b.pack(fill="x", padx=10, pady=2)

    def _build_canvas(self, parent):
        tk.Label(parent, text="Hand Schematic  —  click a servo to control it",
                 bg=BG_DARK, fg=TEXT_DIM,
                 font=("Segoe UI", 10)).pack(anchor="w")

        self.canvas = tk.Canvas(parent, width=CANVAS_W, height=CANVAS_H,
                                bg=BG_DARK, highlightthickness=0)
        self.canvas.pack(pady=(6, 0))

        self._draw_hand()

        self.canvas.bind("<Motion>",   self._on_canvas_motion)
        self.canvas.bind("<Leave>",    self._on_canvas_leave)
        self.canvas.bind("<Button-1>", self._on_canvas_click)

    def _build_detail_panel(self, parent):
        tk.Label(parent, text="SERVO DETAIL", bg=BG_PANEL, fg=TEXT_DIM,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=14, pady=(14, 4))

        self.detail_name = tk.Label(parent, text="—", bg=BG_PANEL, fg=TEXT_LIGHT,
                                    font=("Segoe UI", 13, "bold"), wraplength=180)
        self.detail_name.pack(anchor="w", padx=14, pady=(4, 0))

        self.detail_id = tk.Label(parent, text="", bg=BG_PANEL, fg=TEXT_DIM,
                                  font=("Segoe UI", 9))
        self.detail_id.pack(anchor="w", padx=14)

        self.detail_range = tk.Label(parent, text="", bg=BG_PANEL, fg=TEXT_DIM,
                                     font=("Segoe UI", 9))
        self.detail_range.pack(anchor="w", padx=14, pady=(0, 10))

        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=10, pady=4)

        tk.Label(parent, text="Position", bg=BG_PANEL, fg=TEXT_DIM,
                 font=("Segoe UI", 9)).pack(anchor="w", padx=14, pady=(8, 0))

        self.slider_var = tk.IntVar(value=30)
        self.slider = tk.Scale(parent, from_=0, to=180,
                               orient="horizontal",
                               variable=self.slider_var,
                               bg=BG_PANEL, fg=TEXT_LIGHT,
                               troughcolor=BG_CARD,
                               highlightthickness=0,
                               activebackground=ACCENT,
                               length=190,
                               command=self._on_slider_move)
        self.slider.pack(padx=10)
        self.slider.config(state="disabled")

        self.pos_label = tk.Label(parent, text="—°", bg=BG_PANEL, fg=ACCENT,
                                  font=("Segoe UI", 22, "bold"))
        self.pos_label.pack(pady=(0, 8))

        self.send_btn = self._styled_btn(parent, "Send to Hand",
                                         self._send_servo_position, wide=True)
        self.send_btn.pack(fill="x", padx=10, pady=2)
        self.send_btn.config(state="disabled")

        self.max_btn = self._styled_btn(parent, "Move to Max",
                                        self._send_servo_max, wide=True)
        self.max_btn.pack(fill="x", padx=10, pady=2)
        self.max_btn.config(state="disabled")

        self.min_btn = self._styled_btn(parent, "Move to Min",
                                        self._send_servo_min, wide=True)
        self.min_btn.pack(fill="x", padx=10, pady=2)
        self.min_btn.config(state="disabled")

        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=10, pady=10)

        tk.Label(parent, text="Set Max Limit", bg=BG_PANEL, fg=TEXT_DIM,
                 font=("Segoe UI", 9)).pack(anchor="w", padx=14)

        self.max_limit_var = tk.IntVar(value=180)
        self.max_limit_entry = tk.Spinbox(parent, from_=0, to=180,
                                          textvariable=self.max_limit_var,
                                          width=6, font=("Segoe UI", 10),
                                          bg=BG_CARD, fg=TEXT_LIGHT,
                                          buttonbackground=BG_CARD,
                                          insertbackground=TEXT_LIGHT,
                                          relief="flat", state="disabled")
        self.max_limit_entry.pack(anchor="w", padx=14, pady=(2, 6))

        self.set_max_btn = self._styled_btn(parent, "Set as New Max",
                                            self._send_set_max, wide=True)
        self.set_max_btn.pack(fill="x", padx=10, pady=2)
        self.set_max_btn.config(state="disabled")

        # Group legend
        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=10, pady=10)
        tk.Label(parent, text="COLOUR LEGEND", bg=BG_PANEL, fg=TEXT_DIM,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=14, pady=(0, 4))

        legend_frame = tk.Frame(parent, bg=BG_PANEL)
        legend_frame.pack(fill="x", padx=14, pady=1)
        legend_frame.columnconfigure(0, weight=1)
        legend_frame.columnconfigure(1, weight=1)

        items = list(GROUP_COLORS.items())
        for idx, (group, color) in enumerate(items):
            row_num = idx // 2
            col_num = (idx % 2)
            item_frame = tk.Frame(legend_frame, bg=BG_PANEL)
            item_frame.grid(row=row_num, column=col_num, sticky="w", padx=(0, 20), pady=2)
            tk.Label(item_frame, bg=color, width=2, height=1).pack(side="left", padx=(0, 6))
            tk.Label(item_frame, text=group.capitalize(), bg=BG_PANEL, fg=TEXT_LIGHT,
                     font=("Segoe UI", 9)).pack(side="left")

    # ── Canvas drawing ───────────────────────────────────────────────────────

    def _draw_hand(self):
        c = self.canvas
        c.delete("all")
        self.servo_canvas_items.clear()

        # Palm background
        c.create_rectangle(110, 400, 390, 520, fill="#252538", outline="#333355", width=1)

        # Finger columns — just subtle guide lines
        for fx in [168, 230, 292, 354]:
            c.create_line(fx, 270, fx, 400, fill="#2e2e48", width=2)

        # Thumb guide
        c.create_line(60, 240, 80, 410, fill="#2e2e48", width=2)

        # Draw knuckle connectors between lower servos and palm
        for sid, (cx, cy, rx, ry) in SERVO_SHAPES.items():
            if sid in (0, 2, 4, 6):   # lower knuckles
                c.create_line(cx, cy + ry, cx, 400, fill="#2a2a45", width=6)

        # Draw each servo
        for servo in SERVOS:
            sid = servo["id"]
            if sid not in SERVO_SHAPES:
                continue
            cx, cy, rx, ry = SERVO_SHAPES[sid]
            color = GROUP_COLORS[servo["group"]]
            item = c.create_oval(cx - rx, cy - ry, cx + rx, cy + ry,
                                 fill=SERVO_IDLE, outline=color,
                                 width=2, tags=(f"servo_{sid}", "servo"))
            # Short label
            short = servo["name"].replace("Lower", "Lo").replace("Upper", "Up")
            short_parts = short.split()
            label = short_parts[-1] if len(short_parts) > 1 else short
            c.create_text(cx, cy, text=label, fill=TEXT_DIM,
                          font=("Segoe UI", 7, "bold"),
                          tags=(f"label_{sid}", "servo_label"))
            self.servo_canvas_items[sid] = item

    def _set_servo_color(self, sid, fill):
        if sid in self.servo_canvas_items:
            self.canvas.itemconfig(self.servo_canvas_items[sid], fill=fill)

    def _servo_at(self, x, y):
        for sid, (cx, cy, rx, ry) in SERVO_SHAPES.items():
            if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0:
                return sid
        return None

    # ── Canvas events ────────────────────────────────────────────────────────

    def _on_canvas_motion(self, event):
        sid = self._servo_at(event.x, event.y)
        if sid == self.hover_servo:
            return
        # Un-hover previous
        if self.hover_servo is not None and self.hover_servo != self.selected_servo:
            self._set_servo_color(self.hover_servo, SERVO_IDLE)
        self.hover_servo = sid
        if sid is not None and sid != self.selected_servo:
            self._set_servo_color(sid, SERVO_HOVER)
            servo = SERVOS[sid]
            self.canvas.config(cursor="hand2")
            self._show_hover_tip(sid)
        else:
            self.canvas.config(cursor="")
            self._hide_hover_tip()

    def _on_canvas_leave(self, event):
        if self.hover_servo is not None and self.hover_servo != self.selected_servo:
            self._set_servo_color(self.hover_servo, SERVO_IDLE)
        self.hover_servo = None
        self._hide_hover_tip()

    def _on_canvas_click(self, event):
        sid = self._servo_at(event.x, event.y)
        if sid is None:
            return
        # Deselect old
        if self.selected_servo is not None and self.selected_servo != sid:
            self._set_servo_color(self.selected_servo, SERVO_IDLE)
        self.selected_servo = sid
        self._set_servo_color(sid, SERVO_ACTIVE)
        self._populate_detail(sid)

    # ── Hover tooltip ────────────────────────────────────────────────────────

    def _show_hover_tip(self, sid):
        self._hide_hover_tip()
        cx, cy, rx, ry = SERVO_SHAPES[sid]
        servo = SERVOS[sid]
        lo, hi = SERVO_RANGES[sid]
        tip_text = f"{servo['name']}\nID {sid}  •  {lo}°–{hi}°"
        self._tip = self.canvas.create_text(cx, cy - ry - 16,
                                            text=tip_text, fill=TEXT_LIGHT,
                                            font=("Segoe UI", 8),
                                            anchor="s",
                                            tags="tooltip")
        self._tip_bg = self.canvas.create_rectangle(
            self.canvas.bbox(self._tip),
            fill=BG_CARD, outline=SERVO_OUTLINE, tags="tooltip")
        self.canvas.tag_raise(self._tip)

    def _show_tooltip(self, text, event):
        self._hide_tooltip()
        self._tooltip = tk.Toplevel(self)
        self._tooltip.wm_overrideredirect(True)
        self._tooltip.wm_attributes("-topmost", True)
        label = tk.Label(self._tooltip, text=text, bg=BG_CARD, fg=TEXT_LIGHT,
                         font=("Segoe UI", 8), bd=1, relief="solid",
                         padx=6, pady=4, wraplength=220, justify="left")
        label.pack()
        self._position_tooltip(event.x_root, event.y_root)

    def _move_tooltip(self, event):
        if getattr(self, "_tooltip", None):
            self._position_tooltip(event.x_root, event.y_root)

    def _position_tooltip(self, x, y):
        if getattr(self, "_tooltip", None):
            self._tooltip.wm_geometry(f"+{x + 14}+{y + 18}")

    def _hide_tooltip(self):
        if getattr(self, "_tooltip", None):
            try:
                self._tooltip.destroy()
            except Exception:
                pass
            self._tooltip = None

    def _hide_hover_tip(self):
        self.canvas.delete("tooltip")

    # ── Detail panel ─────────────────────────────────────────────────────────

    def _populate_detail(self, sid):
        servo = SERVOS[sid]
        lo, hi = SERVO_RANGES[sid]
        self.detail_name.config(text=servo["name"])
        self.detail_id.config(text=f"Servo ID: {sid}  •  Group: {servo['group'].capitalize()}")
        self.detail_range.config(text=f"Range: {lo}° – {hi}°")

        self.slider.config(from_=lo, to=hi, state="normal")
        cur = self.servo_values.get(sid, lo)
        self.slider_var.set(cur)
        self.pos_label.config(text=f"{cur}°")

        self.max_limit_var.set(hi)
        self.max_limit_entry.config(state="normal")

        for btn in (self.send_btn, self.max_btn, self.min_btn, self.set_max_btn):
            btn.config(state="normal")

    def _on_slider_move(self, val):
        self.pos_label.config(text=f"{int(float(val))}°")

    # ── Serial commands ──────────────────────────────────────────────────────

    def _send(self, cmd):
        result = self.serial_mgr.send(cmd)
        if result is True:
            self._log(f"→ {cmd}")
        else:
            self._log(f"✗ {result}")

    def _send_servo_position(self):
        if self.selected_servo is None:
            return
        pos = self.slider_var.get()
        self.servo_values[self.selected_servo] = pos
        self._send(f"set:{self.selected_servo}:{pos}")

    def _send_servo_max(self):
        if self.selected_servo is None:
            return
        self._send(f"max:{self.selected_servo}")

    def _send_servo_min(self):
        if self.selected_servo is None:
            return
        self._send(f"min:{self.selected_servo}")

    def _send_set_max(self):
        if self.selected_servo is None:
            return
        new_max = self.max_limit_var.get()
        self._send(f"max:{self.selected_servo}:{new_max}")

    # ── Connection ───────────────────────────────────────────────────────────

    def _refresh_ports(self):
        ports = SerialManager.list_ports()
        self.port_menu["values"] = ports
        if ports and not self.port_var.get():
            self.port_var.set(ports[0])

    def _connect(self):
        if self.serial_mgr.connected:
            self.serial_mgr.disconnect()
            self.conn_btn.config(text="Connect")
            self.status_lbl.config(text="● Disconnected", fg=DANGER)
            self._log("Disconnected.")
            return

        port = self.port_var.get()
        if not port:
            messagebox.showwarning("No Port", "Please select a serial port.")
            return

        self.status_lbl.config(text="○ Connecting…", fg=WARNING)
        self.update_idletasks()

        result = self.serial_mgr.connect(port)
        if result is True:
            self.conn_btn.config(text="Disconnect")
            self.status_lbl.config(text=f"● {port}", fg=SUCCESS)
            self._log(f"Connected to {port} @ {BAUD_RATE} baud")
        else:
            self.status_lbl.config(text="● Disconnected", fg=DANGER)
            messagebox.showerror("Connection Failed", str(result))

    # ── BLE launch ───────────────────────────────────────────────────────────

    def _launch_ble(self):
        ans = messagebox.askyesno(
            "Switch to BLE",
            f"This will close the serial connection and launch:\n\n  {self.ble_script}\n\nContinue?")
        if not ans:
            return
        self.serial_mgr.disconnect()
        try:
            subprocess.Popen([sys.executable, self.ble_script])
            self._log(f"Launched BLE script: {self.ble_script}")
        except FileNotFoundError:
            messagebox.showerror("Not Found",
                f"Could not find:\n{self.ble_script}\n\nUpdate the --ble-script argument.")

    # ── Log ──────────────────────────────────────────────────────────────────

    def _log(self, msg):
        self.log_text.config(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    # ── Button factory ───────────────────────────────────────────────────────

    def _styled_btn(self, parent, text, command, wide=False, small=False):
        font = ("Segoe UI", 8) if small else ("Segoe UI", 10)
        px = 6 if small else 10
        py = 2 if small else 5
        btn = tk.Button(parent, text=text, command=command,
                        bg=BG_CARD, fg=TEXT_LIGHT,
                        activebackground=ACCENT_HOVER, activeforeground="white",
                        relief="flat", font=font,
                        padx=px, pady=py, cursor="hand2",
                        bd=0, highlightthickness=0)
        def on_enter(e): btn.config(bg=ACCENT)
        def on_leave(e): btn.config(bg=BG_CARD)
        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
        return btn


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="DexHand GUI Controller")
    parser.add_argument("--port",       default=None, help="Serial port (e.g. COM3)")
    parser.add_argument("--ble-script", default="ble_controller.py",
                        help="Path to the BLE Python script")
    args = parser.parse_args()

    app = DexHandApp(initial_port=args.port, ble_script=args.ble_script)
    app.mainloop()


if __name__ == "__main__":
    main()
