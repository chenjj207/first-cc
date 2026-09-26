# -*- coding: utf-8 -*-
"""番茄钟 - 桌面专注计时软件

功能：
- 专注 / 短休息 / 长休息 自动循环（经典番茄工作法）
- 到点声音提醒 + 桌面置顶弹窗 + 任务栏闪烁
- 记录每日完成的番茄数，自动保存、跨天清零
- 所有时长与提醒方式均可在设置中自定义
- 仅使用 Python 自带模块，无第三方依赖
"""

import ctypes
import json
import math
import os
import time
import tkinter as tk
from tkinter import messagebox
import winsound

APP_NAME = "番茄钟"
WINDOW_W, WINDOW_H = 360, 600

# 数据存放位置：系统用户配置目录（Windows 下即 %APPDATA%\Pomodoro）
DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Pomodoro")
DATA_FILE = os.path.join(DATA_DIR, "data.json")

# ---------- 配色方案：专注模式番茄红，休息模式薄荷绿 ----------
WORK_COLOR = "#E8553B"        # 番茄红（专注主色）
WORK_DARK = "#D64A2F"         # 番茄红（悬停加深）
WORK_LIGHT = "#FBE5DE"        # 番茄红（浅色环）
WORK_BG = "#FBF6F1"           # 专注模式窗口背景
BREAK_COLOR = "#3FA37C"       # 薄荷绿（休息主色）
BREAK_DARK = "#2F8B66"        # 薄荷绿（悬停加深）
BREAK_LIGHT = "#E2F2EB"       # 薄荷绿（浅色环）
BREAK_BG = "#F3FAF6"          # 休息模式窗口背景
TEXT_DARK = "#2D2A26"
TEXT_GRAY = "#8C8680"
WHITE = "#FFFFFF"

DEFAULT_SETTINGS = {
    "work_min": 25,             # 专注时长（分钟）
    "short_break_min": 5,       # 短休息时长（分钟）
    "long_break_min": 15,       # 长休息时长（分钟）
    "long_break_interval": 4,   # 每完成几个番茄进入一次长休息
    "auto_start": True,         # 阶段结束后自动开始下一阶段
    "sound": True,              # 到点响铃提醒
}


# ---------- 数据读写 ----------
def load_data():
    """读取本地数据文件（不存在或损坏时返回空）"""
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_data(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def today_str():
    return time.strftime("%Y-%m-%d")


# ---------- 任务栏闪烁（Windows 专用） ----------
class FLASHWINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint),
                ("hwnd", ctypes.c_void_p),
                ("dwFlags", ctypes.c_uint),
                ("uCount", ctypes.c_uint),
                ("dwTimeout", ctypes.c_uint)]


def flash_taskbar(root):
    """让任务栏图标闪烁，吸引用户注意"""
    try:
        hwnd = root.winfo_id()
        info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd,
                          0xF, 6, 0)  # FLASHW_ALL | FLASHW_TIMERNOFG，闪 6 次
        ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
    except Exception:
        pass


# ---------- 圆角按钮（画布绘制，支持悬停变色） ----------
class RoundedButton(tk.Canvas):
    """现代风格的圆角按钮"""

    def __init__(self, parent, text, command, width, bg, fg, fill, height=44,
                 radius=12, font=None, outline=None, hover_fill=None):
        super().__init__(parent, width=width, height=height, bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.command = command
        self.fg = fg
        self.fill = fill
        self.hover_fill = hover_fill or fill
        self.outline = outline or fill
        self.font = font or ("Microsoft YaHei UI", 11)
        self.radius = radius
        self._enabled = True

        self._rect = self._draw_rect(self.fill)
        self._text = self.create_text(width // 2, height // 2, text=text,
                                      fill=fg, font=self.font)
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", lambda e: self._set_fill(self.hover_fill))
        self.bind("<Leave>", lambda e: self._set_fill(self.fill))

    def _draw_rect(self, color):
        r = self.radius
        w = int(self["width"])
        h = int(self["height"])
        pts = [1 + r, 1, w - 1 - r, 1, w - 1, 1, w - 1, 1 + r,
               w - 1, h - 1 - r, w - 1, h - 1, w - 1 - r, h - 1,
               1 + r, h - 1, 1, h - 1, 1, h - 1 - r, 1, 1 + r, 1, 1]
        return self.create_polygon(pts, smooth=True, fill=color, outline=self.outline)

    def _set_fill(self, color):
        if self._enabled:
            self.itemconfig(self._rect, fill=color)

    def _on_click(self, event):
        if self._enabled and self.command:
            self.command()

    def set_text(self, text):
        self.itemconfig(self._text, text=text)

    def set_colors(self, fill, hover_fill):
        """切换模式时更换按钮主色"""
        self.fill = fill
        self.hover_fill = hover_fill
        self._set_fill(fill)


# ---------- 主程序 ----------
class PomodoroApp:
    def __init__(self, root):
        self.root = root
        root.title(APP_NAME)
        root.resizable(False, False)
        root.configure(bg=WORK_BG)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 读取设置与历史数据
        self.data = load_data()
        self.settings = dict(DEFAULT_SETTINGS)
        if "settings" in self.data:
            for k in DEFAULT_SETTINGS:
                if k in self.data["settings"]:
                    self.settings[k] = self.data["settings"][k]
        self.today_count = self.data.get("history", {}).get(today_str(), 0)

        # 计时状态
        self.mode = "work"           # work / short_break / long_break
        self.total = 0               # 当前阶段总秒数
        self.remaining = 0           # 当前阶段剩余秒数
        self.running = False
        self.round_in_cycle = 0      # 本轮循环内已完成的番茄数（判断长休息）
        self._last_tick = 0.0

        self._build_ui()
        self._center_window()
        self._apply_mode("work")
        self._render()

    # ----- 界面构建 -----
    def _build_ui(self):
        bg = WORK_BG

        # 顶部栏：标题 + 设置按钮
        top = tk.Frame(self.root, bg=bg)
        top.pack(fill="x", padx=20, pady=(18, 0))
        tk.Label(top, text=APP_NAME, font=("Microsoft YaHei UI", 15, "bold"),
                 fg=TEXT_DARK, bg=bg).pack(side="left")
        self.settings_btn = RoundedButton(
            top, text="设置", command=self.open_settings,
            width=64, height=32, radius=16, bg=bg, fg=TEXT_GRAY, fill=WHITE,
            outline="#E5DFD8", hover_fill="#F3EEE8",
            font=("Microsoft YaHei UI", 10))
        self.settings_btn.pack(side="right")

        # 进度圆环 + 倒计时
        self.ring = tk.Canvas(self.root, width=300, height=300, bg=bg,
                              highlightthickness=0)
        self.ring.pack(pady=(24, 0))
        self.bg_arc = self.ring.create_arc(20, 20, 280, 280, start=0,
                                           extent=359.9, style="arc",
                                           outline=WORK_LIGHT, width=14)
        self.progress_arc = self.ring.create_arc(20, 20, 280, 280, start=90,
                                                 extent=-359.9, style="arc",
                                                 outline=WORK_COLOR, width=14)
        self.time_text = self.ring.create_text(150, 136, text="25:00",
                                               font=("Segoe UI", 48, "bold"),
                                               fill=TEXT_DARK)
        self.mode_text = self.ring.create_text(150, 188, text="专注中",
                                               font=("Microsoft YaHei UI", 12),
                                               fill=WORK_COLOR)

        # 今日统计：小番茄图标 + 数字
        stats = tk.Frame(self.root, bg=bg)
        stats.pack(pady=(18, 0))
        self.tomato_cv = tk.Canvas(stats, width=22, height=22, bg=bg,
                                   highlightthickness=0)
        self.tomato_cv.pack(side="left")
        self._draw_tomato()
        self.stats_text = tk.Label(stats, text="", font=("Microsoft YaHei UI", 12),
                                   fg=TEXT_GRAY, bg=bg)
        self.stats_text.pack(side="left", padx=(8, 0))

        # 按钮行：重置 / 开始暂停 / 跳过
        btns = tk.Frame(self.root, bg=bg)
        btns.pack(pady=(22, 8))
        self.reset_btn = RoundedButton(
            btns, text="重置", command=self.reset, width=76, height=44, radius=22,
            bg=bg, fg=TEXT_GRAY, fill=WHITE, outline="#E5DFD8", hover_fill="#F3EEE8")
        self.reset_btn.pack(side="left", padx=(0, 12))
        self.start_btn = RoundedButton(
            btns, text="开始", command=self.toggle, width=148, height=48, radius=24,
            bg=bg, fg=WHITE, fill=WORK_COLOR, hover_fill=WORK_DARK)
        self.start_btn.pack(side="left", padx=(0, 12))
        self.skip_btn = RoundedButton(
            btns, text="跳过", command=self.skip, width=76, height=44, radius=22,
            bg=bg, fg=TEXT_GRAY, fill=WHITE, outline="#E5DFD8", hover_fill="#F3EEE8")
        self.skip_btn.pack(side="left")

        # 底部提示
        self.hint = tk.Label(self.root, text="在「设置」中可调整时长与提醒方式",
                             font=("Microsoft YaHei UI", 9), fg="#B8B0A8", bg=bg)
        self.hint.pack()

        # 模式切换时需要同步换背景色的组件
        self._bg_widgets = [top, stats, btns, self.hint, self.ring,
                            self.tomato_cv, self.stats_text,
                            self.settings_btn, self.reset_btn,
                            self.start_btn, self.skip_btn]

    def _draw_tomato(self):
        """在统计栏画一个小番茄图标"""
        c = self.tomato_cv
        c.delete("all")
        c.create_oval(4, 7, 20, 21, fill=WORK_COLOR, outline="")
        c.create_oval(5, 8, 19, 20, fill="#F0745C", outline="")   # 高光
        c.create_oval(9, 2, 14, 9, fill="#4E9B5F", outline="")    # 叶子

    def _center_window(self):
        self.root.geometry(f"{WINDOW_W}x{WINDOW_H}")
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - WINDOW_W) // 2
        y = (self.root.winfo_screenheight() - WINDOW_H) // 3
        self.root.geometry(f"{WINDOW_W}x{WINDOW_H}+{x}+{y}")

    # ----- 模式与计时 -----
    def _phase_duration(self, mode):
        """返回指定阶段的时长（秒）"""
        if mode == "work":
            return self.settings["work_min"] * 60
        if mode == "short_break":
            return self.settings["short_break_min"] * 60
        return self.settings["long_break_min"] * 60

    def _apply_mode(self, mode):
        """切换到指定模式：更新配色、圆环、文案"""
        self.mode = mode
        if mode == "work":
            color, dark, light, bg = WORK_COLOR, WORK_DARK, WORK_LIGHT, WORK_BG
            mode_label = "专注中"
        elif mode == "short_break":
            color, dark, light, bg = BREAK_COLOR, BREAK_DARK, BREAK_LIGHT, BREAK_BG
            mode_label = "短休息"
        else:
            color, dark, light, bg = BREAK_COLOR, BREAK_DARK, BREAK_LIGHT, BREAK_BG
            mode_label = "长休息"

        self.root.configure(bg=bg)
        for w in self._bg_widgets:
            w.configure(bg=bg)
        self.ring.itemconfig(self.bg_arc, outline=light)
        self.ring.itemconfig(self.progress_arc, outline=color)
        self.ring.itemconfig(self.mode_text, text=mode_label, fill=color)
        self.start_btn.set_colors(color, dark)

        self.total = self._phase_duration(mode)
        self.remaining = self.total
        self.running = False
        self.start_btn.set_text("开始")

    def start(self):
        if self.remaining <= 0:
            self.remaining = self.total
        self.running = True
        self._last_tick = time.monotonic()
        self.start_btn.set_text("暂停")
        self.root.after(200, self._tick)

    def pause(self):
        self.running = False
        self.start_btn.set_text("继续")

    def toggle(self):
        if self.running:
            self.pause()
        else:
            self.start()

    def reset(self):
        """重置当前阶段"""
        self.running = False
        self.remaining = self.total
        self.start_btn.set_text("开始")
        self._render()

    def skip(self):
        """跳过当前阶段（跳过的专注不计入番茄数）"""
        self._finish_phase(count=False)

    def _tick(self):
        """每 200 毫秒刷新一次倒计时"""
        if not self.running:
            return
        now = time.monotonic()
        self.remaining -= (now - self._last_tick)
        self._last_tick = now
        if self.remaining <= 0:
            self._finish_phase(count=True)
            return
        self._render()
        self.root.after(200, self._tick)

    def _finish_phase(self, count):
        """当前阶段结束：结算、切换下一阶段、提醒"""
        self.running = False
        finished = self.mode

        if finished == "work":
            if count:
                self.today_count += 1
                self.round_in_cycle += 1
                self._save_count()
            if self.round_in_cycle >= self.settings["long_break_interval"]:
                next_mode = "long_break"
                self.round_in_cycle = 0
            else:
                next_mode = "short_break"
            title, message = "专注完成！", "干得漂亮！休息一下，给大脑充个电。"
        else:
            next_mode = "work"
            title, message = "休息结束！", "准备开始下一个番茄吧。"

        self._apply_mode(next_mode)
        self._render()

        if self.settings["sound"]:
            self._play_alarm()
        self._show_notice(title, message)

        if self.settings["auto_start"]:
            self.start()

    def _render(self):
        """刷新倒计时数字、进度圆环与统计文案"""
        mm, ss = divmod(math.ceil(self.remaining), 60)
        self.ring.itemconfig(self.time_text, text=f"{mm:02d}:{ss:02d}")
        frac = max(0.0, min(1.0, self.remaining / self.total)) if self.total else 0
        self.ring.itemconfig(self.progress_arc, extent=-359.9 * frac)
        n = self.today_count
        self.stats_text.config(text=f"今日完成 {n} 个番茄")

    # ----- 提醒 -----
    def _play_alarm(self):
        """连响三声系统提示音（非阻塞）"""
        for i in range(3):
            self.root.after(i * 350, lambda: winsound.MessageBeep(0x40))

    def _show_notice(self, title, message):
        """桌面置顶弹窗，6 秒后自动关闭"""
        win = tk.Toplevel(self.root)
        win.title(title)
        win.configure(bg=WHITE)
        win.resizable(False, False)
        win.attributes("-topmost", True)
        w, h = 300, 190
        x = self.root.winfo_rootx() + (WINDOW_W - w) // 2
        y = self.root.winfo_rooty() + (WINDOW_H - h) // 2
        win.geometry(f"{w}x{h}+{x}+{y}")

        color = WORK_COLOR if self.mode == "work" else BREAK_COLOR
        banner = tk.Frame(win, bg=color, height=64)
        banner.pack(fill="x")
        banner.pack_propagate(False)
        tk.Label(banner, text=title, font=("Microsoft YaHei UI", 14, "bold"),
                 fg=WHITE, bg=color).place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(win, text=message, font=("Microsoft YaHei UI", 11),
                 fg=TEXT_DARK, bg=WHITE).pack(pady=(20, 4))
        RoundedButton(win, text="好的", command=win.destroy,
                      width=120, height=38, radius=19, bg=WHITE, fg=WHITE,
                      fill=color, hover_fill=color).pack(pady=(8, 0))

        def close():
            if win.winfo_exists():
                win.destroy()

        win.after(6000, close)
        self._flash_and_raise()

    def _flash_and_raise(self):
        """唤起主窗口并闪烁任务栏"""
        self.root.deiconify()
        self.root.lift()
        flash_taskbar(self.root)

    # ----- 设置窗口 -----
    def open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("设置")
        win.configure(bg=WHITE)
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()
        self._center_over(win, 340, 380)

        rows = [
            ("专注时长（分钟）", "work_min", 1, 120),
            ("短休息（分钟）", "short_break_min", 1, 60),
            ("长休息（分钟）", "long_break_min", 1, 60),
            ("每几个番茄进入长休息", "long_break_interval", 2, 10),
        ]
        vars_ = {}
        for i, (label, key, lo, hi) in enumerate(rows):
            tk.Label(win, text=label, font=("Microsoft YaHei UI", 11),
                     fg=TEXT_DARK, bg=WHITE).grid(row=i, column=0, sticky="w",
                                                  padx=(24, 0), pady=8)
            var = tk.IntVar(value=self.settings[key])
            tk.Spinbox(win, from_=lo, to=hi, textvariable=var, width=7,
                       font=("Segoe UI", 11), justify="center",
                       buttonbackground="#EFEAE3", relief="flat",
                       highlightthickness=1, highlightbackground="#E5DFD8",
                       highlightcolor=WORK_COLOR).grid(row=i, column=1,
                                                       sticky="e", padx=(0, 24))
            vars_[key] = var

        auto_var = tk.BooleanVar(value=self.settings["auto_start"])
        sound_var = tk.BooleanVar(value=self.settings["sound"])
        tk.Checkbutton(win, text="阶段结束后自动开始下一阶段", variable=auto_var,
                       font=("Microsoft YaHei UI", 11), fg=TEXT_DARK, bg=WHITE,
                       activebackground=WHITE).grid(row=4, column=0, columnspan=2,
                                                    sticky="w", padx=(24, 0),
                                                    pady=(10, 0))
        tk.Checkbutton(win, text="到点声音提醒", variable=sound_var,
                       font=("Microsoft YaHei UI", 11), fg=TEXT_DARK, bg=WHITE,
                       activebackground=WHITE).grid(row=5, column=0, columnspan=2,
                                                    sticky="w", padx=(24, 0))

        btns = tk.Frame(win, bg=WHITE)
        btns.grid(row=6, column=0, columnspan=2, pady=16)
        RoundedButton(btns, text="取消", command=win.destroy,
                      width=110, height=40, radius=20, bg=WHITE, fg=TEXT_GRAY,
                      fill="#F5F1EB", outline="#F5F1EB", hover_fill="#EEE8E0").pack(
            side="left", padx=(0, 12))
        RoundedButton(btns, text="保存",
                      command=lambda: self._save_settings(win, vars_, auto_var, sound_var),
                      width=110, height=40, radius=20, bg=WHITE, fg=WHITE,
                      fill=WORK_COLOR, hover_fill=WORK_DARK).pack(side="left")

    def _save_settings(self, win, vars_, auto_var, sound_var):
        for key, var in vars_.items():
            self.settings[key] = int(var.get())
        self.settings["auto_start"] = bool(auto_var.get())
        self.settings["sound"] = bool(sound_var.get())
        self.data["settings"] = self.settings
        save_data(self.data)
        # 若当前未在计时，立即按新时长重置当前阶段
        if not self.running:
            self.remaining = self._phase_duration(self.mode)
            self.total = self.remaining
            self.start_btn.set_text("开始")
            self._render()
        win.destroy()

    def _center_over(self, win, w, h):
        """把弹窗定位在主窗口正上方"""
        self.root.update_idletasks()
        x = self.root.winfo_rootx() + (WINDOW_W - w) // 2
        y = self.root.winfo_rooty() + (WINDOW_H - h) // 2
        win.geometry(f"{w}x{h}+{x}+{y}")

    # ----- 数据与退出 -----
    def _save_count(self):
        self.data.setdefault("history", {})[today_str()] = self.today_count
        save_data(self.data)

    def _on_close(self):
        if self.running:
            if not messagebox.askyesno(APP_NAME, "计时正在进行中，确定要退出吗？"):
                return
        self.root.destroy()


def main():
    # 高分屏下启用 DPI 感知，避免界面模糊
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    PomodoroApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
