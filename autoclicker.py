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
from tkinter import messagebox, simpledialog, ttk

from pynput import keyboard, mouse

# Phải khớp với tag git khi phát hành. Workflow build có bước kiểm tra,
# tag v1.2.0 mà quên sửa dòng này là build đỏ ngay.
APP_VERSION = "1.2.0"

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
            points = [(int(x), int(y)) for x, y in entry["points"]]
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
                "points": [[x, y] for x, y in p["points"]],
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


class AutoClicker:
    def __init__(self, root):
        self.root = root
        self.points = []
        self.running = threading.Event()
        self.worker = None
        self.picking = False
        self.pick_listener = None
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
            width=30,
            activestyle="none",
            font=self.mono_font,
            borderwidth=1,
            relief="solid",
            highlightthickness=0,
        )
        self.listbox.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(4, 8))

        self.pick_btn = ttk.Button(frm, text="+ Chọn vị trí", command=self.pick_position)
        self.pick_btn.grid(row=5, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(frm, text="Xóa dòng chọn", command=self.remove_point).grid(
            row=5, column=1, sticky="ew", padx=4
        )
        ttk.Button(frm, text="Xóa hết", command=self.clear_points).grid(
            row=5, column=2, sticky="ew", padx=(4, 0)
        )

        ttk.Separator(frm, orient="horizontal").grid(
            row=6, column=0, columnspan=3, sticky="ew", pady=10
        )

        ttk.Label(frm, text="Giãn cách mỗi click (ms)").grid(row=7, column=0, sticky="w")
        self.interval_var = tk.StringVar(value="1000")
        ttk.Entry(frm, textvariable=self.interval_var, width=8, justify="center").grid(
            row=7, column=1, sticky="w", padx=(10, 0)
        )

        self.toggle_btn = ttk.Button(frm, text="BẮT ĐẦU  (F8)", command=self.toggle)
        self.toggle_btn.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(12, 4))

        self.status_var = tk.StringVar(value="Đã dừng")
        ttk.Label(frm, textvariable=self.status_var, foreground="#555").grid(
            row=9, column=0, columnspan=3, sticky="w"
        )

        ttk.Label(
            frm,
            text="F8 = bật/tắt   •   ESC = dừng khẩn cấp",
            foreground="#888",
        ).grid(row=10, column=0, columnspan=3, sticky="w", pady=(8, 0))

        # Ẩn cho tới khi biết chắc có bản mới, để không chiếm chỗ vô ích.
        self.update_label = ttk.Label(
            frm, text="", foreground="#1a6dd4", cursor="hand2"
        )
        self.update_label.grid(row=11, column=0, columnspan=3, sticky="w")
        self.update_label.grid_remove()
        self.update_label.bind("<Button-1>", lambda _e: webbrowser.open(RELEASES_PAGE))

        for i in range(3):
            frm.columnconfigure(i, weight=1)

    def _refresh_list(self):
        self.listbox.delete(0, tk.END)
        for i, (x, y) in enumerate(self.points, 1):
            self.listbox.insert(tk.END, f"  {i}.   X = {x}     Y = {y}")

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

        name = simpledialog.askstring(
            "Lưu bộ vị trí",
            "Đặt tên cho bộ này:\n(ví dụ: Trang chủ, Menu sản phẩm)",
            initialvalue=self.current_profile or "",
            parent=self.root,
        )
        if name is None:
            return
        name = name.strip()
        if not name:
            messagebox.showwarning("Thiếu tên", "Tên không được để trống.")
            return
        if name in self.profiles and not messagebox.askyesno(
            "Ghi đè?", f"Đã có bộ tên \"{name}\". Ghi đè lên bộ cũ?"
        ):
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
        if self.picking or self.running.is_set():
            return
        self.picking = True
        self.pick_btn.config(state="disabled")
        self.status_var.set("Click chuột trái vào vị trí cần chọn...")
        self.root.iconify()
        self.root.after(PICK_DELAY_MS, self._start_pick_listener)

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

    def clear_points(self):
        if self.running.is_set():
            return
        self.points.clear()
        self._refresh_list()

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
        self.status_var.set("Đang chạy...")

    def stop(self):
        if not self.running.is_set():
            return
        self.running.clear()
        self.toggle_btn.config(text="BẮT ĐẦU  (F8)")

    def _click_loop(self, points, interval):
        idx = 0
        count = 0
        while self.running.is_set():
            x, y = points[idx]
            self.mouse_ctl.position = (x, y)
            time.sleep(MOVE_SETTLE)
            if not self.running.is_set():
                break
            self.mouse_ctl.click(mouse.Button.left, 1)
            count += 1
            self.events.put(("count", count, idx + 1))
            idx = (idx + 1) % len(points)
            self._interruptible_sleep(interval)

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
                    self.points.append((msg[1], msg[2]))
                    self._refresh_list()
                    self.picking = False
                    self.pick_listener = None
                    self.pick_btn.config(state="normal")
                    self.status_var.set(f"Đã lưu vị trí #{len(self.points)}")
                    self.root.deiconify()
                    self.root.lift()
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
