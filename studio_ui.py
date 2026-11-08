"""Studio presentation and direct manipulation, with the existing local runner."""
from __future__ import annotations

import math
import time
import tkinter as tk
from pathlib import Path

import customtkinter as ctk
from PIL import Image

import backend as service
from studio_widgets import AnimatedNumber, OrbitDial, PulseButton

BG = "#F5F4EF"
PANEL = "#FFFEFA"
RAISED = "#ECEFE8"
INK = "#3E4944"
MUTED = "#818880"
FAINT = "#A4ABA0"
BORDER = "#E0E5DA"
ACCENT = "#7E9481"
SAGE = "#7E9481"
LAVENDER = "#A297B6"
RED = "#BA7D7A"
DARK_INK = "#FFFFFF"
FONT = "Microsoft YaHei UI"


class StudioInterface:
    def __init__(self, project, demo=False):
        ctk.set_appearance_mode("light")
        self.avatar_cache = {}
        self.quick_goal = None
        self.goal_dirty = False
        self.execution_state = "idle"
        self.page_transition_id = None
        self.transition_frame = None
        self.toast_clear_id = None
        self.palette = None
        self.tasks_dirty = False
        self.task_revision = 0
        self.pending_task_revision = None
        self.suppress_task_trace = False
        self.selected_log_name = None
        super().__init__(project, demo)
        self.title("move" + (" · 离线演示" if demo else ""))
        self.geometry("1280x860")
        self.minsize(1120, 760)
        self.bind("<Control-k>", self.open_command_palette)
        self.bind("<Control-K>", self.open_command_palette)
        self.bind("<Configure>", self.resize_overview, add="+")

    @staticmethod
    def font(size=13, bold=False):
        return ctk.CTkFont(family=FONT, size=size, weight="bold" if bold else "normal")

    def label(self, parent, text, size=13, color=INK, bold=False, **kwargs):
        return ctk.CTkLabel(parent, text=text, font=self.font(size, bold), text_color=color, **kwargs)

    def button(self, parent, text, command, primary=False, **kwargs):
        return PulseButton(parent, text=text, command=command, height=40, corner_radius=12,
                           font=self.font(12, primary), fg_color=ACCENT if primary else RAISED,
                           hover_color="#6F8673" if primary else "#E4EBDD",
                           text_color=DARK_INK if primary else INK,
                           border_color=ACCENT if primary else BORDER, border_width=0,
                           **kwargs)

    def card(self, parent, **kwargs):
        return ctk.CTkFrame(parent, fg_color=PANEL, corner_radius=16,
                           border_color=BORDER, border_width=1, **kwargs)

    def avatar(self, size):
        if size not in self.avatar_cache:
            with Image.open(Path(__file__).parent / "assets" / "mimotion.png") as source:
                portrait = source.convert("RGBA")
            self.avatar_cache[size] = ctk.CTkImage(light_image=portrait, dark_image=portrait, size=(size, size))
        return self.avatar_cache[size]

    def _sidebar(self):
        side = ctk.CTkFrame(self, width=208, corner_radius=0, fg_color="#EFF2EA")
        side.grid(row=0, column=0, sticky="nsew")
        side.grid_propagate(False)
        side.grid_columnconfigure(0, weight=1)
        side.grid_rowconfigure(8, weight=1)
        brand = ctk.CTkFrame(side, fg_color="transparent")
        brand.grid(row=0, column=0, padx=23, pady=(30, 0), sticky="ew")
        ctk.CTkLabel(brand, text="", image=self.avatar(43)).pack(side="left", padx=(0, 9))
        ctk.CTkLabel(brand, text="move", text_color=INK,
                     font=ctk.CTkFont(family="Georgia", size=29, slant="italic")).pack(side="left")
        self.label(side, "每天一点，慢慢来。", 10, MUTED).grid(row=1, column=0, pady=(8, 29))
        for row, (key, number, title) in enumerate([
            ("overview", "01", "今日目标"), ("settings", "02", "账号设置"),
            ("logs", "03", "运行记录"), ("tasks", "04", "自动计划"),
            ("sport", "05", "运动路线"),
        ], 2):
            button = PulseButton(side, text=title, anchor="w", height=44,
                                 corner_radius=12, fg_color="transparent", hover_color="#E9EEE4",
                                 text_color=MUTED, font=self.font(13), border_width=0,
                                 command=lambda page=key: self.show_page(page))
            button.grid(row=row, column=0, sticky="ew", padx=17, pady=4)
            self.nav[key] = button
        quick = ctk.CTkFrame(side, fg_color="transparent", corner_radius=0)
        quick.grid(row=9, column=0, sticky="ew", padx=18, pady=(15, 15))
        self.label(quick, "不用着急。", 11, SAGE).pack(anchor="w", padx=14, pady=(16, 12))
        self.button(quick, "快速跳转   Ctrl K", self.open_command_palette, width=142).pack(padx=11, pady=(0, 12))
        self.button(side, f"帮助  ·  {service.VERSION}", self.show_help).grid(
            row=10, column=0, sticky="ew", padx=18, pady=(0, 24))

    def _topbar(self):
        top = ctk.CTkFrame(self.main, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=30, pady=(23, 19))
        top.grid_columnconfigure(0, weight=1)
        self.heading = self.label(top, "今日目标", 25, bold=True, anchor="w")
        self.heading.grid(row=0, column=0, sticky="w", pady=(3, 0))
        self.subheading = self.label(top, "目标、账号与运行结果，一眼掌握。", 12, MUTED, anchor="w")
        self.subheading.grid(row=1, column=0, sticky="w", pady=(3, 0))
        self.project_badge = self.label(top, "", 10, SAGE, anchor="e")
        self.project_badge.grid(row=0, column=1, sticky="e", padx=(10, 0))
        self.button(top, "切换项目", self.choose_project, width=100).grid(row=1, column=1, sticky="e", pady=(6, 0))

    def show_page(self, name):
        if self.page_transition_id:
            self.after_cancel(self.page_transition_id)
            self.page_transition_id = None
            if self.transition_frame and self.transition_frame.winfo_exists():
                self.transition_frame.grid_configure(pady=0)
        super().show_page(name)
        self.heading.configure(text={"overview": "今日目标", "settings": "账号与目标", "logs": "运行记录",
                                     "tasks": "自动计划", "sport": "运动路线"}[name])
        for key, button in self.nav.items():
            button.configure(fg_color="#DFE7DC" if key == name else "transparent",
                             text_color=ACCENT if key == name else MUTED)
        subtitles = {"overview": "今天也，慢慢前进。", "settings": "把常用设置留在这里。",
                     "logs": "查看和搜索每一次结果。", "tasks": "安排好时间，就轻松一点。",
                     "sport": "画一条路线，去走走吧。"}
        self.subheading.configure(text=subtitles[name])
        frame = self.pages[name]
        if name != "sport":
            self.transition_frame = frame
            started = time.monotonic()

            def move():
                if self.closing or self.current_page != name or not frame.winfo_exists():
                    return
                rate = min(1, (time.monotonic() - started) / .16)
                frame.grid_configure(pady=(round(9 * (1 - rate) ** 3), 0))
                if rate < 1:
                    self.page_transition_id = self.after(16, move)
                else:
                    self.page_transition_id = None
            move()

    def notify(self, text, error=False):
        self.last_error = text if error else ""
        if self.toast_clear_id:
            self.after_cancel(self.toast_clear_id)
            self.toast_clear_id = None
        self.toast.configure(text=("●  " + text) if text else "", text_color=RED if error else SAGE,
                             font=self.font(11))
        if text == "自动任务已保存。" and self.pending_task_revision == self.task_revision:
            self.tasks_dirty = False
            self.update_task_view()
        if text and not error:
            self.toast_clear_id = self.after(6500, lambda: self.toast.configure(text="") if not self.closing else None)

    def choose_project(self):
        old = self.project
        super().choose_project()
        if self.project != old:
            self.goal_dirty = False
            self.quick_goal = None
            self.tasks_dirty = False
            self.task_revision = 0
            self.update_overview()

    def build_overview(self, frame):
        frame.grid_rowconfigure(2, weight=1)
        hero = self.card(frame)
        hero.grid(row=0, column=0, sticky="ew")
        hero.grid_columnconfigure(0, weight=3)
        hero.grid_columnconfigure(1, weight=2)
        left = ctk.CTkFrame(hero, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(25, 5), pady=(20, 14))
        left.grid_columnconfigure(0, weight=1)
        eyebrow = ctk.CTkFrame(left, fg_color="transparent")
        eyebrow.grid(row=0, column=0, sticky="ew")
        self.label(eyebrow, "设定目标", 11, MUTED).pack(side="left")
        self.run_status = self.label(eyebrow, "准备就绪", 10, SAGE)
        self.run_status.pack(side="right", padx=(12, 0))
        self.label(left, "给今天，一个小小的目标。", 19, INK).grid(row=1, column=0, sticky="w", pady=(12, 0))
        number_line = ctk.CTkFrame(left, fg_color="transparent")
        number_line.grid(row=2, column=0, sticky="ew", pady=(0, 0))
        self.goal_label = AnimatedNumber(number_line, value=0, text_color=INK,
                                         font=ctk.CTkFont(family="Bahnschrift", size=56, weight="bold"), anchor="w")
        self.goal_label.pack(side="left")
        self.goal_unit = self.label(number_line, "步 · 设定目标", 11, MUTED)
        self.goal_unit.pack(side="left", padx=(10, 0), pady=(22, 0))
        self.goal_note = self.label(left, "", 11, MUTED, anchor="w")
        self.goal_note.grid(row=3, column=0, sticky="w", pady=(0, 8))
        self.goal_slider = ctk.CTkSlider(left, from_=0, to=100000, number_of_steps=200,
                                         command=self.on_goal_change, fg_color="#E0E5DA",
                                         progress_color=ACCENT, button_color=INK, button_hover_color=ACCENT,
                                         height=18, button_length=15)
        self.goal_slider.grid(row=4, column=0, sticky="ew", pady=(2, 8))
        presets = ctk.CTkFrame(left, fg_color="transparent")
        presets.grid(row=5, column=0, sticky="w", pady=(0, 11))
        self.goal_presets = {}
        for value in (8000, 12000, 18000, 25000):
            button = self.button(presets, f"{value // 1000}k", lambda goal=value: self.on_goal_change(goal), width=58)
            button.configure(height=28, corner_radius=9, font=self.font(11))
            button.pack(side="left", padx=(0, 7))
            self.goal_presets[value] = button
        actions = ctk.CTkFrame(left, fg_color="transparent")
        actions.grid(row=6, column=0, sticky="ew")
        self.run_button = self.button(actions, "立即运行  ↗", self.start_run, primary=True, width=143)
        self.run_button.pack(side="left")
        self.save_goal_button = self.button(actions, "目标已保存", self.save_quick_goal, width=108, state="disabled")
        self.save_goal_button.pack(side="left", padx=9)
        self.stop_button = self.button(actions, "停止", self.stop_run, width=65, state="disabled")
        self.stop_button.pack(side="left")
        art = ctk.CTkFrame(hero, fg_color=PANEL, corner_radius=18, width=310, height=300)
        art.grid(row=0, column=1, sticky="nsew", padx=(10, 18), pady=(11, 8))
        art.grid_columnconfigure(0, weight=1)
        art.grid_rowconfigure(0, weight=1)
        self.dial = OrbitDial(art, value=0, on_change=self.on_goal_change, bg=PANEL, size=300, show_value=False)
        self.dial.grid(row=0, column=0, sticky="nsew")
        self.hero_portrait = ctk.CTkLabel(art, text="", image=self.avatar(139), fg_color=PANEL)
        self.hero_portrait.place(relx=.5, rely=.455, anchor="center")
        self.run_progress = ctk.CTkProgressBar(hero, height=3, corner_radius=2, mode="determinate",
                                              fg_color="#E5E9E1", progress_color=ACCENT, indeterminate_speed=.7)
        self.run_progress.grid(row=1, column=0, columnspan=2, sticky="ew", padx=25, pady=(0, 13))
        self.run_progress.set(0)

        metrics = ctk.CTkFrame(frame, fg_color="transparent")
        metrics.grid(row=1, column=0, sticky="ew", pady=14)
        metrics.grid_columnconfigure((0, 1, 2), weight=1, uniform="studio-metrics")
        self.metric_values, self.metric_details = [], []
        for column, (title, target) in enumerate([("已配置账号", "settings"), ("最近运行", "logs"), ("自动任务", "tasks")]):
            card = self.card(metrics, height=104)
            card.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 5, 0 if column == 2 else 5))
            card.grid_propagate(False)
            self.label(card, title, 10, MUTED).place(x=18, y=12)
            value = self.label(card, "—", 22, bold=True)
            value.place(x=18, y=33)
            detail = self.label(card, "", 10, MUTED)
            detail.place(x=18, y=70)
            arrow = self.button(card, "↗", lambda page=target: self.show_page(page), width=30)
            arrow.configure(height=28, corner_radius=9, text_color=ACCENT)
            arrow.place(relx=1, x=-47, y=13)
            self.metric_values.append(value)
            self.metric_details.append(detail)

        lower = ctk.CTkFrame(frame, fg_color="transparent")
        self.overview_lower = lower
        lower.grid(row=2, column=0, sticky="nsew")
        lower.grid_columnconfigure(0, weight=3)
        lower.grid_columnconfigure(1, weight=2)
        lower.grid_rowconfigure(0, weight=1)
        recent = self.card(lower)
        recent.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        recent.grid_columnconfigure(0, weight=1)
        header = ctk.CTkFrame(recent, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(11, 2))
        self.label(header, "最近记录", 13, bold=True).pack(side="left")
        more = self.button(header, "查看全部 ↗", lambda: self.show_page("logs"), width=105)
        more.configure(height=27, fg_color="transparent", font=self.font(10), text_color=MUTED)
        more.pack(side="right")
        self.recent_list = ctk.CTkFrame(recent, fg_color="transparent")
        self.recent_list.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 13))
        self.recent_list.grid_columnconfigure(1, weight=1)
        link = self.card(lower)
        link.grid(row=0, column=1, sticky="nsew")
        self.label(link, "运动路线", 12, LAVENDER).pack(anchor="w", padx=21, pady=(16, 4))
        self.label(link, "画条路线，去走走。", 18, INK, justify="left").pack(anchor="w", padx=21)
        self.label(link, "地图与运动文件导出", 10, MUTED).pack(anchor="w", padx=21, pady=(3, 9))
        open_map = self.button(link, "打开运动轨迹  ↗", lambda: self.show_page("sport"), width=170)
        open_map.configure(height=31, fg_color="#EEE8F3", text_color="#7E738F", hover_color="#E5DCEE")
        open_map.pack(anchor="w", padx=21, pady=(0, 16))

    def resize_overview(self, event=None):
        if event is not None and event.widget is not self:
            return
        if not hasattr(self, "overview_lower") or not self.overview_lower.winfo_exists():
            return
        logical_height = self.winfo_height() / self._get_window_scaling()
        if logical_height < 825:
            self.overview_lower.grid_remove()
        else:
            self.overview_lower.grid()

    def _config_goal(self):
        try:
            return max(0, min(999999, int(self.config_data.get("MAX_STEP", 25000))))
        except (TypeError, ValueError):
            return 25000

    def _sync_step_fields(self):
        if "settings" in self.pages and self.quick_goal is not None:
            self.mode.set("固定步数")
            self.min_value.set(str(self.quick_goal))
            self.max_value.set(str(self.quick_goal))
            self.change_mode("固定步数")

    def on_goal_change(self, value):
        if self.process:
            self.dial.set_value(self.quick_goal, animate=False)
            return
        goal = max(0, min(999999, int(round(float(value) / 100) * 100)))
        self.quick_goal = goal
        self.execution_state = "idle"
        self.goal_dirty = str(goal) != str(self.config_data.get("MIN_STEP")) or str(goal) != str(self.config_data.get("MAX_STEP"))
        self._sync_step_fields()
        self.update_overview()

    def save_quick_goal(self):
        if self.process or self.quick_goal is None:
            return False
        if not self.goal_dirty:
            self.notify("目标已是最新设定。")
            return True
        try:
            self.store.save({"MIN_STEP": str(self.quick_goal), "MAX_STEP": str(self.quick_goal)})
            self.goal_dirty = False
            self.reload_data()
            self.quick_goal = self._config_goal()
            self._sync_step_fields()
            self.update_overview()
            self.notify("目标已保存，下次运行将使用这个设定。")
            return True
        except (OSError, ValueError) as exc:
            self.notify(str(exc), True)
            if not self.config_data.get("USER"):
                self.show_page("settings")
            return False

    def update_overview(self):
        if "overview" not in self.pages:
            return
        if self.quick_goal is None or not self.goal_dirty:
            self.quick_goal = self._config_goal()
        running = self.process is not None
        minimum, maximum = str(self.config_data.get("MIN_STEP")), str(self.config_data.get("MAX_STEP"))
        random_mode = minimum != maximum and not self.goal_dirty
        self.goal_label.set_value(self.quick_goal)
        self.goal_unit.configure(text="步 · 目标上限" if random_mode else "步")
        ramp = str(self.config_data.get("NO_TIME_RATE", "True")).lower() not in ("true", "1", "yes")
        note = f"随机范围 {minimum}–{maximum}" if random_mode else "固定目标"
        note += "  ·  22:00 达到目标" if ramp else "  ·  直接使用设定值"
        if self.goal_dirty:
            note = "目标预览  ·  尚未保存"
        self.goal_note.configure(text=note, text_color=ACCENT if self.goal_dirty else MUTED)
        self.dial.set_value(self.quick_goal)
        state = "running" if running else self.execution_state
        self.dial.set_state(state)
        self.run_status.configure(text="●  运行中" if running else ("●  离线演示" if self.demo else "●  准备就绪"),
                                  text_color=ACCENT if running else SAGE)
        self.run_button.configure(state="disabled" if running else "normal",
                                  text="正在运行…" if running else ("保存并运行" if self.goal_dirty else "立即运行"))
        self.stop_button.configure(state="normal" if running else "disabled")
        self.save_goal_button.configure(state="normal" if self.goal_dirty and not running else "disabled",
                                        text="保存目标" if self.goal_dirty else "目标已保存")
        self.goal_slider.configure(state="disabled" if running else "normal")
        self.goal_slider.set(min(self.quick_goal, 100000))
        for goal, button in self.goal_presets.items():
            button.configure(state="disabled" if running else "normal",
                             fg_color="#DFE7DC" if goal == self.quick_goal else RAISED,
                             text_color=ACCENT if goal == self.quick_goal else MUTED)
        if running:
            self.run_progress.configure(mode="indeterminate")
            self.run_progress.start()
        else:
            self.run_progress.stop()
            self.run_progress.configure(mode="determinate")
            self.run_progress.set(0)
        self.resize_overview()
        users = [item for item in str(self.config_data.get("USER", "")).split("#") if item]
        self.metric_values[0].configure(text=f"{len(users):02d}", text_color=INK)
        self.metric_details[0].configure(text=service.mask_account(users[0]) if len(users) == 1 else ("多个账号，统一管理" if users else "添加你的第一个账号"))
        latest = self.logs[0] if self.logs else None
        states = {"success": "模拟完成" if self.demo else "执行成功", "failed": "需要检查", "stopped": "已停止", "unknown": "查看记录"}
        self.metric_values[1].configure(text=states.get(latest["state"], "查看记录") if latest else "等待开始",
                                        text_color=(SAGE if latest["state"] == "success" else RED if latest["state"] == "failed" else INK) if latest else INK)
        self.metric_details[1].configure(text=latest["time"] if latest else "每一次执行，都会留有记录")
        self.metric_values[2].configure(text=("已开启" if self.task.get("enabled") else "已暂停") if self.task.get("found") else "待检查" if self.task.get("unavailable") else "未设置",
                                        text_color=SAGE if self.task.get("enabled") else INK)
        self.metric_details[2].configure(text=f"每天 {len(self.task.get('times', []))} 个运行时间" if self.task.get("found") else "在自动任务中安排时间")
        for child in self.recent_list.winfo_children():
            child.destroy()
        if not self.logs:
            self.label(self.recent_list, "还没有记录，先设定一个目标吧。", 11, MUTED).grid(row=0, column=0, sticky="w", pady=18)
        for row, item in enumerate(self.logs[:2]):
            color = SAGE if item["state"] == "success" else RED if item["state"] == "failed" else LAVENDER
            self.label(self.recent_list, "●", 12, color).grid(row=row, column=0, padx=(0, 9), pady=5)
            self.label(self.recent_list, item["summary"], 11).grid(row=row, column=1, sticky="w")
            self.label(self.recent_list, item["time"], 10, MUTED).grid(row=row, column=2, sticky="e")

    def build_settings(self, frame):
        super().build_settings(frame)
        if self.goal_dirty:
            self._sync_step_fields()

    def add_account(self, user="", password=""):
        if len(self.account_rows) >= 50:
            self.notify("最多可添加 50 个账号。", True)
            return
        row = ctk.CTkFrame(self.accounts_host, fg_color=RAISED, corner_radius=12)
        row.pack(fill="x", pady=(0, 10))
        row.grid_columnconfigure((0, 1), weight=1)
        self.label(row, "手机号 / 邮箱", 10, MUTED).grid(row=0, column=0, sticky="w", padx=12, pady=(8, 1))
        hint = self.label(row, "密码 · 已保存" if password else "登录密码", 10, SAGE if password else MUTED)
        hint.grid(row=0, column=1, sticky="w", padx=(0, 8), pady=(8, 1))
        user_var, pass_var = ctk.StringVar(value=user), ctk.StringVar(value="")
        ctk.CTkEntry(row, textvariable=user_var, height=38, fg_color=BG, border_color=BORDER,
                      text_color=INK, font=self.font(12)).grid(row=1, column=0, sticky="ew", padx=(12, 10), pady=(1, 11))
        password_entry = ctk.CTkEntry(row, textvariable=pass_var, show="●", height=38,
                                     fg_color=BG, border_color=BORDER, text_color=INK, font=self.font(12))
        password_entry.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=(1, 11))
        entry = {"frame": row, "user": user_var, "password": pass_var, "original_user": user,
                 "original_password": password, "password_entry": password_entry, "password_hint": hint}
        toggle = self.button(row, "显示", lambda: None, width=48)
        toggle.configure(height=34, font=self.font(10))

        def reveal():
            showing = password_entry.cget("show") == ""
            password_entry.configure(show="●" if showing else "")
            toggle.configure(text="显示" if showing else "隐藏")
        toggle.configure(command=reveal)
        toggle.grid(row=1, column=2, padx=(0, 5), pady=(1, 11))
        remove = self.button(row, "×", lambda: self.remove_account(entry), width=31)
        remove.configure(height=34, fg_color="#F3E8E5", hover_color="#ECD8D5", text_color=RED)
        remove.grid(row=1, column=3, padx=(0, 10), pady=(1, 11))
        self.account_rows.append(entry)

    def save_settings(self):
        saved = super().save_settings()
        if saved:
            self.goal_dirty = False
            self.quick_goal = self._config_goal()
            for row in self.account_rows:
                if row.get("password_hint"):
                    saved_password = bool(row["original_password"]) and row["user"].get().strip() == row["original_user"]
                    row["password_hint"].configure(text="密码 · 已保存" if saved_password else "登录密码",
                                                   text_color=SAGE if saved_password else MUTED)
            self.update_overview()
        return saved

    def reset_settings(self):
        self.goal_dirty = False
        self.quick_goal = None
        super().reset_settings()
        self.update_overview()

    def build_logs(self, frame):
        frame.grid_rowconfigure(2, weight=1)
        toolbar = ctk.CTkFrame(frame, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        toolbar.grid_columnconfigure(1, weight=1)
        self.log_search = ctk.StringVar(value="")
        self.log_filter = ctk.StringVar(value="全部")
        search = ctk.CTkEntry(toolbar, textvariable=self.log_search, height=42, fg_color=PANEL,
                              border_color=BORDER, corner_radius=12, text_color=INK, font=self.font(12))
        self.label(toolbar, "搜索日志", 11, MUTED).grid(row=0, column=0, padx=(0, 12))
        search.grid(row=0, column=1, sticky="ew", padx=(0, 12))
        self.button(toolbar, "刷新", self.refresh_logs, width=78).grid(row=0, column=2, padx=(0, 8))
        self.button(toolbar, "日志文件夹 ↗", self.open_logs_folder, width=128).grid(row=0, column=3)
        filters = ctk.CTkFrame(frame, fg_color="transparent")
        filters.grid(row=1, column=0, sticky="ew", pady=(0, 13))
        ctk.CTkSegmentedButton(filters, values=["全部", "成功", "失败", "停止"], variable=self.log_filter,
                               command=lambda _: self.render_logs(), selected_color="#DDE7D9",
                               selected_hover_color="#D3E0CE", unselected_color=RAISED,
                               unselected_hover_color="#E4EBDD", text_color=INK, font=self.font(11), height=32).pack(side="left")
        self.log_count = self.label(filters, "按文件名、结果或日志内容搜索", 10, MUTED)
        self.log_count.pack(side="right")
        split = ctk.CTkFrame(frame, fg_color="transparent")
        split.grid(row=2, column=0, sticky="nsew")
        split.grid_rowconfigure(0, weight=1)
        split.grid_columnconfigure(1, weight=1)
        self.log_list = ctk.CTkScrollableFrame(split, width=230, fg_color=PANEL, border_width=1,
                                             border_color=BORDER, corner_radius=16,
                                             scrollbar_button_color="#D6DCD0", scrollbar_button_hover_color=MUTED)
        self.log_list.grid(row=0, column=0, sticky="nsew", padx=(0, 13))
        self.log_list.grid_columnconfigure(0, weight=1)
        reader = self.card(split)
        reader.grid(row=0, column=1, sticky="nsew")
        reader.grid_columnconfigure(0, weight=1)
        reader.grid_rowconfigure(1, weight=1)
        self.log_title = self.label(reader, "选择一条记录", 12, bold=True, anchor="w")
        self.log_title.grid(row=0, column=0, sticky="ew", padx=19, pady=(18, 10))
        self.log_text = ctk.CTkTextbox(reader, fg_color=PANEL, text_color="#3E4944", wrap="word",
                                      font=self.font(12), corner_radius=0)
        self.log_text.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 13))
        self.log_text.configure(state="disabled")
        self.log_search.trace_add("write", lambda *_: self.render_logs())

    def refresh_logs(self):
        self.logs = service.log_entries(self.project, self.config_data)
        self.update_overview()
        if "logs" in self.pages:
            self.render_logs()

    def filtered_logs(self):
        query = self.log_search.get().strip().casefold()
        desired = {"成功": "success", "失败": "failed", "停止": "stopped"}.get(self.log_filter.get())
        return [item for item in self.logs if (not desired or item["state"] == desired)
                and (not query or query in (item["name"] + item["summary"] + item["text"]).casefold())]

    def render_logs(self):
        if "logs" not in self.pages or not hasattr(self, "log_list"):
            return
        rows = self.filtered_logs()
        for child in self.log_list.winfo_children():
            child.destroy()
        self.log_count.configure(text=f"{len(rows)} 条匹配  /  共 {len(self.logs)} 条")
        for index, item in enumerate(rows):
            color = SAGE if item["state"] == "success" else RED if item["state"] == "failed" else MUTED
            button = self.button(self.log_list, f"{item['time']}\n{item['summary']}", lambda value=item: self.select_log(value))
            button.configure(height=67, corner_radius=11, anchor="w", text_color=color,
                             font=self.font(11), fg_color=RAISED)
            button.grid(row=index, column=0, sticky="ew", padx=4, pady=4)
        selected = next((item for item in rows if item["name"] == self.selected_log_name), None)
        if rows:
            self.select_log(selected or rows[0])
        else:
            self.log_title.configure(text="没有匹配的记录" if self.logs else "等待第一条记录")
            self.log_text.configure(state="normal")
            self.log_text.delete("1.0", "end")
            self.log_text.insert("1.0", "试试其他关键词，或切换筛选条件。" if self.logs else "运行后的结果和排查信息，会出现在这里。")
            self.log_text.configure(state="disabled")

    def select_log(self, item):
        self.selected_log_name = item["name"]
        super().select_log(item)

    def build_tasks(self, frame):
        card = self.card(frame)
        card.grid(row=0, column=0, sticky="ew")
        card.grid_columnconfigure(0, weight=1)
        self.label(card, "运行时间", 11, LAVENDER).grid(row=0, column=0, sticky="w", padx=24, pady=(20, 1))
        self.label(card, "把日常，安排得轻一点。", 21).grid(row=1, column=0, sticky="w", padx=24, pady=(0, 7))
        self.task_status = self.label(card, "正在检查自动任务…", 12, SAGE, anchor="w")
        self.task_status.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 12))
        self.times_var = ctk.StringVar(value="08:00, 11:30, 15:00, 18:30, 21:00, 22:40")
        self.tasks_dirty = False
        self.time_chips = ctk.CTkFrame(card, fg_color="transparent")
        self.time_chips.grid(row=3, column=0, sticky="ew", padx=24, pady=(0, 8))
        self.times_entry = ctk.CTkEntry(card, textvariable=self.times_var, height=43, font=self.font(14),
                                       fg_color=BG, border_color=BORDER, text_color=INK, corner_radius=11)
        self.times_entry.grid(row=4, column=0, sticky="ew", padx=24)
        add = ctk.CTkFrame(card, fg_color="transparent")
        add.grid(row=5, column=0, sticky="ew", padx=24, pady=(11, 0))
        self.new_time_var = ctk.StringVar(value="07:30")
        ctk.CTkEntry(add, textvariable=self.new_time_var, height=33, width=82, fg_color=BG,
                      border_color=BORDER, text_color=INK, font=self.font(12)).pack(side="left")
        button = self.button(add, "+ 添加时间", self.add_task_time, width=104)
        button.configure(height=33)
        button.pack(side="left", padx=(8, 17))
        self.label(add, "快捷添加", 10, MUTED).pack(side="left", padx=(0, 7))
        for value in ("08:00", "12:30", "21:00"):
            button = self.button(add, value, lambda item=value: self.add_task_time(item), width=64)
            button.configure(height=29, font=self.font(10))
            button.pack(side="left", padx=3)
        self.task_note = self.label(card, "", 11, MUTED, justify="left", anchor="w", wraplength=810)
        self.task_note.grid(row=6, column=0, sticky="ew", padx=24, pady=(14, 14))
        buttons = ctk.CTkFrame(card, fg_color="transparent")
        buttons.grid(row=7, column=0, sticky="ew", padx=24, pady=(0, 21))
        self.task_save_button = self.button(buttons, "保存自动任务", self.save_task_clicked, primary=True, width=150)
        self.task_save_button.pack(side="left")
        self.task_toggle_button = self.button(buttons, "启用自动任务", self.toggle_task_clicked, width=136)
        self.task_toggle_button.pack(side="left", padx=9)
        self.button(buttons, "刷新状态", self.refresh_task, width=105).pack(side="right")
        hint = self.card(frame)
        hint.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        self.label(hint, "电脑开机并登录 Windows 后，计划才能执行。", 13, bold=True).pack(anchor="w", padx=23, pady=(18, 5))
        self.label(hint, "关闭软件窗口后，自动任务仍可运行。新建任务支持错过时间后补跑。\n修改现有任务时，保留原运行程序与启停状态。", 11, MUTED,
                   justify="left").pack(anchor="w", padx=23, pady=(0, 13))
        open_system = self.button(hint, "打开系统任务计划程序 ↗", lambda: __import__("os").startfile("taskschd.msc"), width=220)
        open_system.configure(height=32, font=self.font(11))
        open_system.pack(anchor="w", padx=23, pady=(0, 18))
        self.times_var.trace_add("write", self.task_times_changed)
        self.render_time_chips()

    def task_times_changed(self, *_):
        if not self.suppress_task_trace:
            self.tasks_dirty = True
            self.task_revision += 1
        self.render_time_chips()
        if not self.suppress_task_trace:
            self.update_task_view()

    def render_time_chips(self):
        for child in self.time_chips.winfo_children():
            child.destroy()
        try:
            times = service.validate_times(self.times_var.get())
        except ValueError:
            self.label(self.time_chips, "用 08:00 这样的格式添加时间，多个时间用逗号分隔。", 10, MUTED).grid(row=0, column=0, sticky="w")
            return
        for index, value in enumerate(times):
            button = self.button(self.time_chips, value + "  ×", lambda item=value: self.remove_task_time(item), width=82)
            button.configure(height=29, corner_radius=10, fg_color="#EEE8F3", text_color="#7F748E", font=self.font(10))
            button.grid(row=index // 8, column=index % 8, padx=(0, 7), pady=4, sticky="w")

    def add_task_time(self, value=None):
        try:
            incoming = service.validate_times(value if value is not None else self.new_time_var.get())
            times = service.validate_times(self.times_var.get()) if self.times_var.get().strip() else []
            combined = service.validate_times(", ".join(times + incoming))
            self.times_var.set(", ".join(combined))
            self.notify("这个时间已在列表中。" if combined == times else "时间已添加，保存后生效。")
        except ValueError as exc:
            self.notify(str(exc), True)

    def remove_task_time(self, value):
        try:
            self.times_var.set(", ".join(item for item in service.validate_times(self.times_var.get()) if item != value))
            self.notify("时间已移除，保存后生效。")
        except ValueError as exc:
            self.notify(str(exc), True)

    def update_task_view(self):
        self.update_overview()
        if "tasks" not in self.pages:
            return
        info = self.task
        if info.get("found"):
            self.task_status.configure(text=("● 已开启" if info.get("enabled") else "● 已暂停") + "  ·  " + info["name"],
                                       text_color=SAGE if info.get("enabled") else MUTED)
            if not self.task_busy and info.get("times") and not self.tasks_dirty:
                self.suppress_task_trace = True
                self.times_var.set(", ".join(info["times"]))
                self.suppress_task_trace = False
            self.task_note.configure(text="下次计划运行：" + str(info.get("next", "待定")) + ("  ·  时间修改尚未保存" if self.tasks_dirty else ""))
        else:
            self.task_status.configure(text="暂时无法读取系统任务" if info.get("unavailable") else "尚未设置自动任务", text_color=MUTED)
            note = "可打开系统任务计划程序查看，再刷新状态。" if info.get("unavailable") else "安排好时间，再点击保存。新建任务后请保留软件当前位置。"
            self.task_note.configure(text=note + ("  ·  时间修改尚未保存" if self.tasks_dirty else ""))
        self.task_save_button.configure(state="disabled" if self.task_busy else "normal")
        self.task_toggle_button.configure(text="暂停自动任务" if info.get("enabled") else "启用自动任务",
                                          state="normal" if info.get("found") and not self.task_busy else "disabled")

    def save_task_clicked(self):
        if self.task_busy:
            self.notify("正在读取自动任务，请稍后再保存。")
            return
        self.pending_task_revision = self.task_revision
        super().save_task_clicked()

    def start_run(self):
        if self.process:
            return
        if self.goal_dirty and not self.save_quick_goal():
            return
        self.execution_state = "idle"
        super().start_run()

    def poll_run(self):
        was_running = self.process is not None
        super().poll_run()
        if was_running and self.process is None:
            if self.cancelled:
                self.execution_state = "stopped"
            elif self.last_error:
                self.execution_state = "error"
            else:
                self.execution_state = "success"
            self.update_overview()

    def open_command_palette(self, event=None):
        if self.palette and self.palette.winfo_exists():
            self.palette.lift()
            return "break"
        box = ctk.CTkToplevel(self)
        self.palette = box
        box.title("move · 快速跳转")
        box.geometry("580x440")
        box.resizable(False, False)
        box.configure(fg_color=BG)
        box.transient(self)
        box.grab_set()
        self.label(box, "想去哪里？", 23, bold=True).pack(anchor="w", padx=25, pady=(22, 2))
        self.label(box, "输入关键词，按 Enter 执行第一项；Esc 关闭。", 11, MUTED).pack(anchor="w", padx=25, pady=(0, 12))
        query = ctk.StringVar(value="")
        entry = ctk.CTkEntry(box, textvariable=query, height=42, fg_color=PANEL, border_color=BORDER,
                             text_color=INK, font=self.font(14), corner_radius=12)
        entry.pack(fill="x", padx=25)
        results = ctk.CTkScrollableFrame(box, fg_color="transparent", height=245)
        results.pack(fill="both", expand=True, padx=18, pady=(10, 16))
        actions = [("运行面板", lambda: self.show_page("overview")), ("账号与步数", lambda: self.show_page("settings")),
                   ("运行记录 / 日志搜索", lambda: self.show_page("logs")), ("自动任务 / 定时计划", lambda: self.show_page("tasks")),
                   ("运动轨迹 / 地图", lambda: self.show_page("sport")), ("切换项目目录", self.choose_project)]
        if self.current_page == "overview":
            actions.extend([("保存当前目标", self.save_quick_goal), ("保存当前目标并运行", self.start_run)])
        elif self.current_page == "settings":
            actions.append(("保存账号与步数设置", self.save_settings))
        elif self.current_page == "tasks":
            actions.append(("保存自动任务时间", self.save_task_clicked))
        visible = []

        def execute(command):
            box.destroy()
            self.palette = None
            self.after(30, command)

        def render(*_):
            for child in results.winfo_children():
                child.destroy()
            visible[:] = [item for item in actions if query.get().strip().casefold() in item[0].casefold()]
            for title, command in visible:
                button = self.button(results, title + "   ↗", lambda action=command: execute(action))
                button.configure(anchor="w", height=36, font=self.font(12))
                button.pack(fill="x", padx=3, pady=3)
        query.trace_add("write", render)
        box.bind("<Escape>", lambda _: execute(lambda: None))
        entry.bind("<Return>", lambda _: execute(visible[0][1]) if visible else None)
        render()
        self.after(100, lambda: entry.focus_set() if box.winfo_exists() else None)
        return "break"

    def show_help(self):
        box = ctk.CTkToplevel(self)
        box.title("move · 使用帮助")
        box.geometry("710x640")
        box.transient(self)
        box.configure(fg_color=BG)
        self.label(box, "move · 使用帮助", 23).pack(anchor="w", padx=27, pady=(25, 13))
        reader = ctk.CTkTextbox(box, fg_color=PANEL, text_color=INK, corner_radius=16,
                                font=self.font(12), wrap="word")
        reader.pack(fill="both", expand=True, padx=25)
        reader.insert("1.0", "首页目标\n拖动轨道、滑动横条或点选预设，只调整目标预览。点击“保存目标”后写入配置；有草稿时，“保存并运行”会保存目标再开始。刻度表示设定值。\n\n"
                      "账号与步数\n使用 Zepp Life 手机号或邮箱。在这里配置随机范围、按时间递增和多账号。已有密码留空保留。保存前会备份原配置。\n\n"
                      "日志与快速跳转\n运行记录支持关键词搜索和结果筛选。按 Ctrl+K 可快速切换页面、保存目标或运行。\n\n"
                      "自动任务\n点时间标签上的 × 删除，输入 HH:MM 后添加；修改后点击保存才生效。电脑需开机并登录 Windows。\n\n"
                      "运动轨迹\n联网加载 sport.gyvv.top 原站。网页上方可重试、打开大窗口、选择导出位置。原站的地图和生成服务需要网络。\n\n"
                      "本地文件\n首次优先读取 E:\\mimotion，也可切换项目目录。配置、登录缓存、备份和浏览器资料保存在所选目录，请保管好。分享软件请只分享发布文件。\n\n"
                      "来源与版本\n原核心来自 mimotion，沿用 Apache-2.0；版本 " + service.VERSION + "。结果以接口返回和第三方平台显示为准。")
        reader.configure(state="disabled")
        self.button(box, "知道了", box.destroy, primary=True, width=108).pack(anchor="e", padx=25, pady=19)

    def close_app(self):
        # Let the existing close confirmation protect an in-flight run.
        for timer in (self.page_transition_id, self.toast_clear_id):
            if timer:
                self.after_cancel(timer)
        self.page_transition_id = self.toast_clear_id = None
        super().close_app()

    def destroy(self):
        # Tk/CTk also own global DPI and appearance timers. Cancel interpreter
        # callbacks only at final destruction, after any close confirmation.
        try:
            pending = self.tk.call("after", "info")
            if isinstance(pending, str):
                pending = self.tk.splitlist(pending)
            for timer in pending:
                # Keep each widget's registered Tcl command until its own
                # destroy() removes it; only unschedule the timer here.
                self.tk.call("after", "cancel", timer)
        except tk.TclError:
            pass
        super().destroy()
