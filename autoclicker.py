"""Auto Clicker - click tuần tự nhiều vị trí trên màn hình.

Chạy được trên Windows và macOS.
macOS cần cấp quyền: System Settings > Privacy & Security > Accessibility
và Input Monitoring cho app này.
"""

import ctypes
import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from tkinter import font as tkfont
from tkinter import messagebox, ttk

from pynput import keyboard, mouse

# Phải khớp với tag git khi phát hành. Workflow build có bước kiểm tra,
# tag v1.2.0 mà quên sửa dòng này là build đỏ ngay.
APP_VERSION = "1.3.2"

RELEASES_API = "https://api.github.com/repos/HThanh209/autoclick/releases/latest"
RELEASES_PAGE = "https://github.com/HThanh209/autoclick/releases/latest"

HOTKEY_TOGGLE = "<f8>"
HOTKEY_STOP = "<esc>"
MIN_INTERVAL_MS = 10
MOVE_SETTLE = 0.02  # chờ con trỏ ổn định trước khi click
PICK_DELAY_MS = 350  # chờ cửa sổ thu nhỏ xong rồi mới bắt click

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"


def config_dir():
    """Thư mục lưu cấu hình theo chuẩn từng hệ điều hành.

    Không lưu cạnh file .exe vì bản onefile giải nén vào thư mục tạm, ghi
    vào đó thì mỗi lần chạy là mất sạch.
    """
    if IS_WIN:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return Path(base) / "AutoClicker"
    if IS_MAC:
        return Path.home() / "Library" / "Application Support" / "AutoClicker"
    return Path.home() / ".config" / "autoclicker"


PROFILES_PATH = config_dir() / "profiles.json"


def parse_version(text):
    """'v1.2.0' -> (1, 2, 0). Phần không phải số coi như 0 để không nổ."""
    parts = []
    for chunk in str(text).strip().lstrip("vV").split("."):
        digits = ""
        for ch in chunk:
            if not ch.isdigit():
                break
            digits += ch
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def fetch_latest_version(timeout=6):
    """Hỏi GitHub xem bản mới nhất là gì. Lỗi mạng thì trả None."""
    req = urllib.request.Request(
        RELEASES_API,
        headers={
            "User-Agent": f"AutoClicker/{APP_VERSION}",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    tag = data.get("tag_name")
    return str(tag) if tag else None


def _fmt_secs(ms):
    """1000 -> '1s', 4500 -> '4.5s'. Người dùng nghĩ bằng giây, không phải ms."""
    s = ms / 1000.0
    return f"{s:g}s"


def _parse_point(item):
    """Một điểm trong file là [x, y] hoặc [x, y, delay_ms].

    delay_ms = None nghĩa là điểm dùng giãn cách chung. Giữ dạng [x, y] cho
    file cũ (chưa có tính năng chờ riêng) để không phải nâng cấp thủ công.
    """
    x = int(item[0])
    y = int(item[1])
    delay = None
    if len(item) >= 3 and item[2] is not None:
        delay = float(item[2])
        if delay < 0:
            delay = None
    return (x, y, delay)


def load_profiles():
    """Đọc các bộ vị trí đã lưu. File hỏng thì trả về rỗng chứ không làm
    sập app — mất cấu hình còn hơn không mở lên được."""
    try:
        with open(PROFILES_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}

    profiles = {}
    for name, entry in (data.get("profiles") or {}).items():
        try:
            points = [_parse_point(item) for item in entry["points"]]
        except (KeyError, TypeError, ValueError):
            continue
        if not points:
            continue
        try:
            interval = float(entry.get("interval_ms", 1000))
        except (TypeError, ValueError):
            interval = 1000.0
        profiles[str(name)] = {"points": points, "interval_ms": interval}
    return profiles


def save_profiles(profiles):
    """Ghi ra file. Ghi vào file tạm rồi mới đổi tên, để nếu app bị tắt
    giữa chừng thì file cũ vẫn nguyên vẹn thay vì cụt nửa chừng."""
    PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "version": 1,
        "profiles": {
            name: {
                "points": [
                    ([x, y] if d is None else [x, y, d]) for (x, y, d) in p["points"]
                ],
                "interval_ms": p["interval_ms"],
            }
            for name, p in profiles.items()
        },
    }
    tmp = PROFILES_PATH.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PROFILES_PATH)


def enable_dpi_awareness():
    """Báo Windows rằng app tự lo việc scale.

    Không gọi cái này thì Windows phóng to cửa sổ bằng cách kéo giãn ảnh
    bitmap 96 DPI -> chữ mờ, vỡ nét trên màn hình có scale 125%/150%.
    PHẢI gọi trước khi tạo tk.Tk().
    """
    if not IS_WIN:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # per-monitor aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()  # Windows cũ
        except Exception:
            pass


def apply_scaling_and_fonts(root):
    """Tk vẫn vẽ theo 96 DPI kể cả khi đã DPI-aware, nên phải tự đặt tỉ lệ."""
    if IS_WIN:
        try:
            hdc = ctypes.windll.user32.GetDC(0)
            dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
            ctypes.windll.user32.ReleaseDC(0, hdc)
            if dpi > 0:
                root.tk.call("tk", "scaling", dpi / 72.0)
        except Exception:
            pass

    ui_family = "Segoe UI" if IS_WIN else ("SF Pro Text" if IS_MAC else "TkDefaultFont")
    mono_family = "Consolas" if IS_WIN else ("Menlo" if IS_MAC else "TkFixedFont")
    available = set(tkfont.families(root))
    if ui_family not in available:
        ui_family = "TkDefaultFont"
    if mono_family not in available:
        mono_family = "TkFixedFont"

    base_size = 10 if IS_WIN else 13
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        try:
            tkfont.nametofont(name).configure(family=ui_family, size=base_size)
        except tk.TclError:
            pass

    return (mono_family, base_size)


class NameDialog(tk.Toplevel):
    """Hộp thoại đặt tên bộ: chọn tên có sẵn trong danh sách để ghi đè,
    hoặc gõ tên mới. Ô nhập cho gõ tự do nên làm được cả hai việc."""

    def __init__(self, parent, names, initial=""):
        super().__init__(parent)
        self.result = None
        self.names = list(names)

        self.title("Lưu bộ vị trí")
        self.resizable(False, False)
        self.transient(parent)

        frm = ttk.Frame(self, padding=14)
        frm.grid(sticky="nsew")

        ttk.Label(frm, text="Chọn bộ có sẵn để ghi đè, hoặc gõ tên mới:").grid(
            row=0, column=0, columnspan=2, sticky="w"
        )

        self.var = tk.StringVar(value=initial)
        self.combo = ttk.Combobox(frm, textvariable=self.var, values=self.names, width=32)
        self.combo.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 2))

        # Nói trước sẽ ghi đè hay tạo mới, để khỏi phải hỏi lại lần nữa.
        self.hint_var = tk.StringVar()
        self.hint = ttk.Label(frm, textvariable=self.hint_var, foreground="#8a8a8a")
        self.hint.grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 12))
        self.var.trace_add("write", lambda *_: self._update_hint())
        self._update_hint()

        ttk.Button(frm, text="Lưu", command=self._ok).grid(
            row=3, column=0, sticky="ew", padx=(0, 4)
        )
        ttk.Button(frm, text="Hủy", command=self._cancel).grid(
            row=3, column=1, sticky="ew", padx=(4, 0)
        )
        frm.columnconfigure(0, weight=1)
        frm.columnconfigure(1, weight=1)

        self.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self.combo.focus_set()
        self._center_on(parent)
        self.grab_set()
        self.wait_window(self)

    def _update_hint(self):
        name = self.var.get().strip()
        if not name:
            self.hint_var.set(" ")
        elif name in self.names:
            self.hint_var.set(f"Sẽ ghi đè bộ \"{name}\" đang có")
        else:
            self.hint_var.set("Sẽ tạo bộ mới")

    def _center_on(self, parent):
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _ok(self):
        name = self.var.get().strip()
        if not name:
            self.hint_var.set("Chưa nhập tên")
            return
        self.result = name
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


class DelayDialog(tk.Toplevel):
    """Đặt thời gian chờ riêng cho một điểm, tính bằng giây.

    result là một trong ba: giá trị ms (float) nếu đặt số cụ thể,
    chuỗi "clear" nếu chọn dùng giãn cách chung, hoặc None nếu bấm Hủy.
    """

    def __init__(self, parent, row_no, current_ms):
        super().__init__(parent)
        self.result = None

        self.title("Thời gian chờ")
        self.resizable(False, False)
        self.transient(parent)

        frm = ttk.Frame(self, padding=14)
        frm.grid(sticky="nsew")

        ttk.Label(
            frm,
            text=f"Chờ bao lâu sau khi click điểm số {row_no},\ntrước khi sang điểm tiếp theo?",
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w")

        self.var = tk.StringVar(
            value="" if current_ms is None else f"{current_ms / 1000:g}"
        )
        entry = ttk.Entry(frm, textvariable=self.var, width=12, justify="center")
        entry.grid(row=1, column=0, sticky="w", pady=(10, 2))
        ttk.Label(frm, text="giây").grid(row=1, column=1, sticky="w", padx=(6, 0))

        ttk.Label(
            frm,
            text="Để trống = dùng giãn cách chung của cả bộ.",
            foreground="#8a8a8a",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 12))

        ttk.Button(frm, text="Lưu", command=self._ok).grid(
            row=3, column=0, sticky="ew", padx=(0, 4)
        )
        ttk.Button(frm, text="Dùng chung", command=self._clear).grid(
            row=3, column=1, sticky="ew", padx=(4, 0)
        )

        self.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self.destroy())

        entry.focus_set()
        entry.select_range(0, tk.END)
        self._center_on(parent)
        self.grab_set()
        self.wait_window(self)

    def _center_on(self, parent):
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _ok(self):
        text = self.var.get().strip().replace(",", ".")
        if not text:
            self.result = "clear"
            self.destroy()
            return
        try:
            secs = float(text)
        except ValueError:
            messagebox.showwarning("Sai giá trị", "Nhập một con số, ví dụ 4 hoặc 4.5.", parent=self)
            return
        ms = secs * 1000.0
        if ms < MIN_INTERVAL_MS:
            messagebox.showwarning(
                "Quá nhanh", f"Thời gian chờ tối thiểu là {MIN_INTERVAL_MS} ms.", parent=self
            )
            return
        self.result = ms
        self.destroy()

    def _clear(self):
        self.result = "clear"
        self.destroy()


class AutoClicker:
    def __init__(self, root):
        self.root = root
        self.points = []
        self.running = threading.Event()
        self.worker = None
        self.picking = False
        self.pick_listener = None
        self.replace_index = None  # dòng sắp bị thay vị trí, None = thêm mới
        self.events = queue.Queue()
        self.mouse_ctl = mouse.Controller()
        self.mono_font = apply_scaling_and_fonts(root)

        self.profiles = load_profiles()
        self.current_profile = None

        self._build_ui()
        self._refresh_profile_list()
        self._start_update_check()
        self._start_hotkeys()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(50, self._drain_events)

    # ---------- UI ----------

    def _build_ui(self):
        self.root.title(f"Auto Clicker  v{APP_VERSION}")
        self.root.resizable(False, False)

        frm = ttk.Frame(self.root, padding=12)
        frm.grid(sticky="nsew")

        ttk.Label(frm, text="Bộ vị trí đã lưu").grid(
            row=0, column=0, columnspan=3, sticky="w"
        )

        self.profile_var = tk.StringVar()
        self.profile_combo = ttk.Combobox(
            frm, textvariable=self.profile_var, state="readonly", width=18
        )
        self.profile_combo.grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=(4, 0))
        self.profile_combo.bind("<<ComboboxSelected>>", self.on_profile_selected)

        ttk.Button(frm, text="Lưu bộ này", command=self.save_current_profile).grid(
            row=1, column=1, sticky="ew", padx=4, pady=(4, 0)
        )
        ttk.Button(frm, text="Xóa bộ", command=self.delete_profile).grid(
            row=1, column=2, sticky="ew", padx=(4, 0), pady=(4, 0)
        )

        ttk.Separator(frm, orient="horizontal").grid(
            row=2, column=0, columnspan=3, sticky="ew", pady=10
        )

        ttk.Label(frm, text="Danh sách vị trí (click theo thứ tự từ trên xuống)").grid(
            row=3, column=0, columnspan=3, sticky="w"
        )

        self.listbox = tk.Listbox(
            frm,
            height=8,
            width=38,
            activestyle="none",
            font=self.mono_font,
            borderwidth=1,
            relief="solid",
            highlightthickness=0,
        )
        self.listbox.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(4, 2))
        self.listbox.bind("<<ListboxSelect>>", self.on_list_select)
        self.listbox.bind("<Double-Button-1>", self.edit_delay)

        ttk.Label(
            frm,
            text="Bấm đúp vào một dòng để đặt thời gian chờ riêng cho điểm đó.",
            foreground="#8a8a8a",
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(0, 8))

        # Nút này LUÔN thêm điểm mới, không đổi chữ. Việc thay vị trí tách sang
        # nút riêng bên dưới, để thêm điểm đầu tiên không nuốt mất nút thêm.
        self.pick_btn = ttk.Button(frm, text="+ Chọn vị trí", command=self.pick_position)
        self.pick_btn.grid(row=6, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(frm, text="Xóa dòng chọn", command=self.remove_point).grid(
            row=6, column=1, sticky="ew", padx=4
        )
        ttk.Button(frm, text="Xóa hết", command=self.clear_points).grid(
            row=6, column=2, sticky="ew", padx=(4, 0)
        )

        # Chỉ bật khi có dòng đang chọn. Bấm rồi click lại để đổi tọa độ dòng đó.
        self.replace_btn = ttk.Button(
            frm, text="Thay vị trí dòng đang chọn", command=self.replace_position,
            state="disabled",
        )
        self.replace_btn.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(4, 0))

        ttk.Separator(frm, orient="horizontal").grid(
            row=8, column=0, columnspan=3, sticky="ew", pady=10
        )

        ttk.Label(frm, text="Giãn cách chung mỗi click (ms)").grid(row=9, column=0, columnspan=2, sticky="w")
        self.interval_var = tk.StringVar(value="1000")
        ttk.Entry(frm, textvariable=self.interval_var, width=8, justify="center").grid(
            row=9, column=2, sticky="e"
        )

        self.toggle_btn = ttk.Button(frm, text="BẮT ĐẦU  (F8)", command=self.toggle)
        self.toggle_btn.grid(row=10, column=0, columnspan=3, sticky="ew", pady=(12, 4))

        self.status_var = tk.StringVar(value="Đã dừng")
        ttk.Label(frm, textvariable=self.status_var, foreground="#555").grid(
            row=11, column=0, columnspan=3, sticky="w"
        )

        ttk.Label(
            frm,
            text="F8 = bật/tắt   •   ESC = dừng khẩn cấp",
            foreground="#888",
        ).grid(row=12, column=0, columnspan=3, sticky="w", pady=(8, 0))

        # Ẩn cho tới khi biết chắc có bản mới, để không chiếm chỗ vô ích.
        self.update_label = ttk.Label(
            frm, text="", foreground="#1a6dd4", cursor="hand2"
        )
        self.update_label.grid(row=13, column=0, columnspan=3, sticky="w")
        self.update_label.grid_remove()
        self.update_label.bind("<Button-1>", lambda _e: webbrowser.open(RELEASES_PAGE))

        for i in range(3):
            frm.columnconfigure(i, weight=1)

    def _refresh_list(self):
        self.listbox.delete(0, tk.END)
        for i, (x, y, d) in enumerate(self.points, 1):
            wait = "chung" if d is None else _fmt_secs(d)
            self.listbox.insert(
                tk.END, f" {i:>2}.  X ={x:>6}   Y ={y:>6}   chờ {wait:>6}"
            )

    # ---------- Kiểm tra bản mới ----------

    def _start_update_check(self):
        """Chạy nền để không làm app khựng lúc mở khi mạng chậm hoặc không có
        mạng. Chỉ đọc số phiên bản, không tải và không tự cài gì."""

        def worker():
            tag = fetch_latest_version()
            if tag and parse_version(tag) > parse_version(APP_VERSION):
                self.events.put(("update", tag))

        threading.Thread(target=worker, daemon=True).start()

    # ---------- Bộ vị trí đã lưu ----------

    def _refresh_profile_list(self):
        names = list(self.profiles)
        self.profile_combo["values"] = names
        if self.current_profile in self.profiles:
            self.profile_var.set(self.current_profile)
        else:
            self.current_profile = None
            self.profile_var.set("")

    def on_profile_selected(self, _event=None):
        name = self.profile_var.get()
        if self.running.is_set():
            # Đang chạy mà đổi bộ thì vòng lặp vẫn dùng danh sách cũ,
            # người dùng sẽ tưởng đã đổi. Chặn luôn cho khỏi hiểu nhầm.
            messagebox.showinfo("Đang chạy", "Dừng lại trước khi đổi bộ vị trí.")
            self._refresh_profile_list()
            return
        profile = self.profiles.get(name)
        if not profile:
            return
        self.points = list(profile["points"])
        self.interval_var.set(str(int(profile["interval_ms"])))
        self.current_profile = name
        self._refresh_list()
        self.listbox.selection_clear(0, tk.END)
        self.on_list_select()
        self.status_var.set(f"Đã nạp \"{name}\" — {len(self.points)} vị trí")

    def save_current_profile(self):
        if self.running.is_set():
            return
        if not self.points:
            messagebox.showwarning(
                "Chưa có vị trí", "Chọn ít nhất 1 vị trí rồi mới lưu được."
            )
            return
        try:
            interval = float(self.interval_var.get())
        except ValueError:
            messagebox.showwarning("Sai giá trị", "Giãn cách phải là một con số.")
            return

        # Hộp thoại đã báo trước "ghi đè" hay "tạo mới" nên không hỏi lại nữa.
        name = NameDialog(self.root, list(self.profiles), self.current_profile or "").result
        if not name:
            return

        self.profiles[name] = {
            "points": list(self.points),
            "interval_ms": interval,
        }
        if not self._persist():
            return
        self.current_profile = name
        self._refresh_profile_list()
        self.status_var.set(f"Đã lưu \"{name}\" — {len(self.points)} vị trí")

    def delete_profile(self):
        if self.running.is_set():
            return
        name = self.profile_var.get()
        if not name or name not in self.profiles:
            messagebox.showinfo("Chưa chọn bộ", "Chọn một bộ trong danh sách để xóa.")
            return
        if not messagebox.askyesno("Xóa bộ", f"Xóa bộ \"{name}\"?"):
            return
        removed = self.profiles.pop(name)
        if not self._persist():
            self.profiles[name] = removed  # ghi hỏng thì trả lại như cũ
            return
        self.current_profile = None
        self._refresh_profile_list()
        self.status_var.set(f"Đã xóa \"{name}\"")

    def _persist(self):
        try:
            save_profiles(self.profiles)
            return True
        except OSError as exc:
            messagebox.showerror(
                "Không lưu được",
                f"Không ghi được file cấu hình:\n{PROFILES_PATH}\n\n{exc}",
            )
            return False

    # ---------- Chọn vị trí ----------

    def pick_position(self):
        """Luôn thêm một điểm mới vào cuối danh sách."""
        self._begin_pick(None)

    def replace_position(self):
        """Đổi tọa độ của đúng dòng đang chọn, không thêm dòng mới."""
        sel = self.listbox.curselection()
        if not sel:
            return
        self._begin_pick(sel[0])

    def _begin_pick(self, replace_index):
        if self.picking or self.running.is_set():
            return
        self.replace_index = replace_index
        self.picking = True
        self.pick_btn.config(state="disabled")
        self.replace_btn.config(state="disabled")
        if replace_index is None:
            self.status_var.set("Click chuột trái vào vị trí cần thêm...")
        else:
            self.status_var.set(
                f"Click để thay vị trí cho dòng {replace_index + 1}..."
            )
        self.root.iconify()
        self.root.after(PICK_DELAY_MS, self._start_pick_listener)

    def on_list_select(self, _event=None):
        """Bật nút thay vị trí khi có dòng đang chọn."""
        if self.picking or self.running.is_set():
            return
        has = bool(self.listbox.curselection())
        self.replace_btn.config(state="normal" if has else "disabled")

    def edit_delay(self, event=None):
        """Bấm đúp vào một dòng để đặt thời gian chờ riêng cho điểm đó."""
        if self.picking or self.running.is_set():
            return
        # Bấm đúp thì lấy dòng ngay dưới con trỏ cho chắc, không dựa vào ô đang chọn.
        if event is not None:
            idx = self.listbox.nearest(event.y)
        else:
            sel = self.listbox.curselection()
            idx = sel[0] if sel else None
        if idx is None or not (0 <= idx < len(self.points)):
            return

        x, y, delay = self.points[idx]
        result = DelayDialog(self.root, idx + 1, delay).result
        if result is None:  # bấm Hủy / đóng
            return
        new_delay = None if result == "clear" else float(result)
        self.points[idx] = (x, y, new_delay)
        self._refresh_list()
        self.listbox.selection_set(idx)
        self.listbox.see(idx)
        self.on_list_select()
        if new_delay is None:
            self.status_var.set(f"Dòng {idx + 1} dùng giãn cách chung")
        else:
            self.status_var.set(f"Dòng {idx + 1} chờ {_fmt_secs(new_delay)}")

    def _restore_window(self):
        """Đưa cửa sổ trở lại trước mặt sau khi chọn xong vị trí.

        Windows có khóa tiêu điểm: cửa sổ đang ở nền không được tự nhảy lên trên,
        nên deiconify + lift thôi là chưa đủ (nó khôi phục nhưng nằm dưới, hoặc
        chỉ nhấp nháy taskbar). Bật -topmost chớp nhoáng rồi tắt để ép nổi lên,
        không để dính topmost vĩnh viễn che mất cửa sổ khác.
        """
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.focus_force()
        self.root.after(400, lambda: self.root.attributes("-topmost", False))

    def _start_pick_listener(self):
        self.pick_listener = mouse.Listener(on_click=self._on_pick_click)
        self.pick_listener.start()

    def _on_pick_click(self, x, y, button, pressed):
        if pressed and button == mouse.Button.left:
            self.events.put(("point", int(x), int(y)))
            return False  # dừng listener

    def remove_point(self):
        sel = self.listbox.curselection()
        if not sel or self.running.is_set():
            return
        del self.points[sel[0]]
        self._refresh_list()
        self.on_list_select()

    def clear_points(self):
        if self.running.is_set():
            return
        self.points.clear()
        self._refresh_list()
        self.on_list_select()

    # ---------- Chạy / dừng ----------

    def toggle(self):
        if self.running.is_set():
            self.stop()
        else:
            self.start()

    def start(self):
        if self.picking or self.running.is_set():
            return
        if not self.points:
            messagebox.showwarning("Chưa có vị trí", "Bấm '+ Chọn vị trí' để thêm ít nhất 1 điểm.")
            return
        try:
            interval_ms = float(self.interval_var.get())
        except ValueError:
            messagebox.showwarning("Sai giá trị", "Giãn cách phải là một con số.")
            return
        if interval_ms < MIN_INTERVAL_MS:
            messagebox.showwarning(
                "Quá nhanh", f"Giãn cách tối thiểu là {MIN_INTERVAL_MS} ms."
            )
            return

        self.running.set()
        self.worker = threading.Thread(
            target=self._click_loop,
            args=(list(self.points), interval_ms / 1000.0),
            daemon=True,
        )
        self.worker.start()
        self.toggle_btn.config(text="DỪNG  (F8)")
        self.replace_btn.config(state="disabled")
        self.status_var.set("Đang chạy...")

    def stop(self):
        if not self.running.is_set():
            return
        self.running.clear()
        self.toggle_btn.config(text="BẮT ĐẦU  (F8)")
        self.on_list_select()  # bật lại nút thay vị trí nếu đang chọn dòng

    def _click_loop(self, points, interval):
        idx = 0
        count = 0
        while self.running.is_set():
            x, y, delay = points[idx]
            self.mouse_ctl.position = (x, y)
            time.sleep(MOVE_SETTLE)
            if not self.running.is_set():
                break
            self.mouse_ctl.click(mouse.Button.left, 1)
            count += 1
            self.events.put(("count", count, idx + 1))
            idx = (idx + 1) % len(points)
            # Điểm có đặt thời gian chờ riêng thì dùng nó, không thì giãn cách chung.
            wait = (delay / 1000.0) if delay is not None else interval
            self._interruptible_sleep(wait)

    def _interruptible_sleep(self, seconds):
        """Ngủ theo từng lát 20ms để bấm dừng là dừng ngay."""
        deadline = time.monotonic() + seconds
        while self.running.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(0.02, remaining))

    # ---------- Hotkey toàn cục ----------

    def _start_hotkeys(self):
        try:
            self.hotkeys = keyboard.GlobalHotKeys(
                {
                    HOTKEY_TOGGLE: lambda: self.events.put(("toggle",)),
                    HOTKEY_STOP: lambda: self.events.put(("stop",)),
                }
            )
            self.hotkeys.daemon = True
            self.hotkeys.start()
        except Exception as exc:  # macOS thiếu quyền Input Monitoring
            self.hotkeys = None
            print(f"Không bật được hotkey toàn cục: {exc}")

    # ---------- Cầu nối thread -> tkinter ----------

    def _drain_events(self):
        """Mọi thao tác lên tkinter phải nằm ở main thread, nên các thread
        khác chỉ đẩy message vào queue và xử lý ở đây."""
        try:
            while True:
                msg = self.events.get_nowait()
                kind = msg[0]
                if kind == "point":
                    idx = self.replace_index
                    if idx is not None and 0 <= idx < len(self.points):
                        # Thay tọa độ nhưng giữ nguyên thời gian chờ đã đặt.
                        old_delay = self.points[idx][2]
                        self.points[idx] = (msg[1], msg[2], old_delay)
                        note = f"Đã thay vị trí dòng {idx + 1}"
                    else:
                        self.points.append((msg[1], msg[2], None))
                        idx = len(self.points) - 1
                        note = f"Đã lưu vị trí #{len(self.points)}"
                    self.replace_index = None
                    self._refresh_list()
                    # Giữ nguyên dòng vừa đụng tới để dễ nhìn và sửa tiếp.
                    self.listbox.selection_set(idx)
                    self.listbox.see(idx)
                    self.picking = False
                    self.pick_listener = None
                    self.pick_btn.config(state="normal")
                    self.on_list_select()
                    self.status_var.set(note)
                    self._restore_window()
                elif kind == "count":
                    self.status_var.set(f"Đang chạy — {msg[1]} click (điểm #{msg[2]})")
                elif kind == "toggle":
                    self.toggle()
                elif kind == "stop":
                    if self.running.is_set():
                        self.stop()
                        self.status_var.set("Đã dừng bằng ESC")
                elif kind == "update":
                    self.update_label.config(
                        text=f"Đã có bản mới {msg[1]} — bấm vào đây để tải"
                    )
                    self.update_label.grid()
        except queue.Empty:
            pass
        self.root.after(50, self._drain_events)

    def on_close(self):
        self.running.clear()
        if self.pick_listener is not None:
            self.pick_listener.stop()
        if self.hotkeys is not None:
            self.hotkeys.stop()
        self.root.destroy()


def main():
    enable_dpi_awareness()  # phải gọi trước tk.Tk()
    root = tk.Tk()
    try:
        ttk.Style(root).theme_use("vista" if IS_WIN else "aqua")
    except tk.TclError:
        pass
    AutoClicker(root)
    root.mainloop()


if __name__ == "__main__":
    main()
