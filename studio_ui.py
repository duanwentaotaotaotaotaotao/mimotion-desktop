"""Studio presentation and direct manipulation, with the existing local runner."""
from __future__ import annotations

import math
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk
from PIL import Image

import backend as service
from studio_widgets import AnimatedNumber, OrbitDial, PulseButton, BotanicalAccent

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
        self.settings_dirty = False
        self.settings_building = False
        self.settings_syncing = False
        self.settings_baseline = None
        self.last_synced_steps = None
        self.removed_accounts = []
        self.log_search_id = None
        self.log_buttons = {}
        self.displayed_log = None
        self.goal_editor = None
        super().__init__(project, demo)
        self.title("move" + (" · 离线演示" if demo else ""))
        self.geometry("1280x860")
        self.minsize(1120, 760)
        self.bind("<Control-k>", self.open_command_palette)
        self.bind("<Control-K>", self.open_command_palette)
        self.bind("<Control-s>", self.save_current_page)
        self.bind("<Control-S>", self.save_current_page)
        self.bind("<Control-f>", self.focus_log_search)
        self.bind("<Control-F>", self.focus_log_search)
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
        garden = BotanicalAccent(side, bg="#EFF2EA", width=170, height=165)
        garden.grid(row=8, column=0, sticky="sew", padx=19, pady=(8, 0))
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
        botanical = BotanicalAccent(top, bg=BG, landscape=True)
        botanical.place(relx=.60, rely=.5, relwidth=.30, relheight=1, anchor="center")
        self.heading = self.label(top, "今日目标", 25, bold=True, anchor="w")
        self.heading.grid(row=0, column=0, sticky="w", pady=(3, 0))
        self.subheading = self.label(top, "目标、账号与运行结果，一眼掌握。", 12, MUTED, anchor="w")
        self.subheading.grid(row=1, column=0, sticky="w", pady=(3, 0))
        self.project_badge = self.label(top, "", 10, SAGE, anchor="e")
        self.project_badge.grid(row=0, column=1, sticky="e", padx=(10, 0))
        self.button(top, "切换项目", self.choose_project, width=100).grid(row=1, column=1, sticky="e", pady=(6, 0))
        top.tk.call("lower", botanical._w, self.heading._w)

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
        if self.process:
            return super().choose_project()
        if not self._confirm_discard("切换项目"):
            return
        old = self.project
        super().choose_project()
        if self.project != old:
            self.goal_dirty = False
            self.quick_goal = None
            self.tasks_dirty = False
            self.task_revision = 0
            self.settings_dirty = False
            self.settings_baseline = self.last_synced_steps = None
            self.removed_accounts.clear()
            self.selected_log_name = self.displayed_log = None
            self.update_draft_indicators()
            self.update_overview()

    def update_draft_indicators(self):
        dirty = {"overview": self.goal_dirty, "settings": self.settings_dirty, "tasks": self.tasks_dirty}
        for key, title in (("overview", "今日目标"), ("settings", "账号设置"), ("logs", "运行记录"),
                           ("tasks", "自动计划"), ("sport", "运动路线")):
            if key in self.nav:
                self.nav[key].configure(text=title + ("  ·" if dirty.get(key) else ""))

    def _confirm_discard(self, reason, scopes=("overview", "settings", "tasks")):
        names = [title for key, dirty, title in (("overview", self.goal_dirty, "首页目标"),
                 ("settings", self.settings_dirty, "账号设置"), ("tasks", self.tasks_dirty, "计划时间"))
                 if key in scopes and dirty]
        return not names or messagebox.askokcancel(
            "还有未保存的修改", "、".join(names) + "尚未保存。\n" + reason + "会放弃这些修改，是否继续？\n\n取消后可在对应页面按 Ctrl+S 保存。", parent=self)

    def save_current_page(self, event=None):
        if self.palette and self.palette.winfo_exists() or self.goal_editor and self.goal_editor.winfo_exists():
            return "break"
        action = {"overview": self.save_quick_goal, "settings": self.save_settings,
                  "tasks": self.save_task_clicked}.get(self.current_page)
        if action:
            action()
        else:
            self.notify("当前页面无需保存。")
        return "break"

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
        self.journey_line = self.label(left, "给今天，一个小小的目标。", 19, INK)
        self.journey_line.grid(row=1, column=0, sticky="w", pady=(12, 0))
        self.journey_index = 0
        number_line = ctk.CTkFrame(left, fg_color="transparent")
        number_line.grid(row=2, column=0, sticky="ew", pady=(0, 0))
        self.goal_label = AnimatedNumber(number_line, value=0, text_color=INK,
                                         font=ctk.CTkFont(family="Bahnschrift", size=56, weight="bold"), anchor="w")
        self.goal_label.pack(side="left")
        self.goal_unit = self.label(number_line, "步 · 设定目标", 11, MUTED)
        self.goal_unit.pack(side="left", padx=(10, 0), pady=(22, 0))
        self.goal_edit_button = self.button(number_line, "精确输入", self.open_goal_editor, width=78)
        self.goal_edit_button.configure(height=28, font=self.font(10))
        self.goal_edit_button.pack(side="left", padx=(13, 0), pady=(20, 0))
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
        self.restore_goal_button = self.button(presets, "还原", self.restore_quick_goal, width=55, state="disabled")
        self.restore_goal_button.configure(height=28, font=self.font(10))
        self.restore_goal_button.pack(side="left", padx=(3, 0))
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
        with Image.open(Path(__file__).parent / "assets" / "mimotion.png") as portrait:
            self.dial.set_portrait(portrait, self.greet_journey)
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

    def greet_journey(self, event=None):
        lines = ("给今天，一个小小的目标。", "风会停下，旅途还会继续。", "走过的每一步，都算数。", "慢慢走，也会到达。")
        self.journey_index = (self.journey_index + 1) % len(lines)
        self.journey_line.configure(text=lines[self.journey_index], text_color=LAVENDER)
        self.dial.play_greeting()

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

    def _settings_steps(self):
        mode = self.mode.get()
        return mode, self.min_value.get(), self.min_value.get() if mode == "固定步数" else self.max_value.get()

    def _sync_step_fields(self, from_config=False):
        if "settings" not in self.pages or self.quick_goal is None:
            return
        # A target preview must not erase a separately edited random range.
        if self.last_synced_steps is not None and self._settings_steps() != self.last_synced_steps:
            return
        self.settings_syncing = True
        try:
            minimum = str(self.config_data["MIN_STEP"]) if from_config else str(self.quick_goal)
            maximum = str(self.config_data["MAX_STEP"]) if from_config else str(self.quick_goal)
            self.mode.set("固定步数" if minimum == maximum else "随机范围")
            self.min_value.set(minimum)
            self.max_value.set(maximum)
            self.change_mode(self.mode.get())
            self.last_synced_steps = self._settings_steps()
            if self.settings_baseline is not None:
                self.settings_baseline = (self.last_synced_steps, *self.settings_baseline[1:])
        finally:
            self.settings_syncing = False
        self.settings_changed()

    def on_goal_change(self, value):
        if self.process:
            self.dial.set_value(self.quick_goal, animate=False)
            return
        goal = max(0, min(999999, int(round(float(value)))))
        self.quick_goal = goal
        self.execution_state = "idle"
        self.goal_dirty = str(goal) != str(self.config_data.get("MIN_STEP")) or str(goal) != str(self.config_data.get("MAX_STEP"))
        self._sync_step_fields()
        self.update_overview()

    def restore_quick_goal(self):
        if self.process:
            return
        self.goal_dirty = False
        self.quick_goal = self._config_goal()
        self._sync_step_fields(from_config=True)
        self.update_overview()
        self.notify("已还原保存的目标，配置文件未改动。")

    def open_goal_editor(self):
        if self.process:
            return
        if self.goal_editor and self.goal_editor.winfo_exists():
            self.goal_editor.lift()
            return
        self.goal_editor_focus = self.focus_get()
        box = ctk.CTkToplevel(self)
        self.goal_editor = box
        box.title("move · 精确目标")
        box.geometry("420x280")
        box.resizable(False, False)
        box.transient(self)
        box.configure(fg_color=BG)
        box.grab_set()
        self.label(box, "想走多少步？", 22, bold=True).pack(anchor="w", padx=25, pady=(23, 5))
        self.label(box, "先预览，点击首页保存后生效。", 11, MUTED).pack(anchor="w", padx=25)
        self.goal_input_var = ctk.StringVar(value=str(self.quick_goal))
        self.goal_input_entry = ctk.CTkEntry(box, textvariable=self.goal_input_var, height=45,
                                            font=self.font(23), fg_color=PANEL, border_color=BORDER, text_color=INK)
        self.goal_input_entry.pack(fill="x", padx=25, pady=(17, 5))
        self.goal_input_error = self.label(box, "0–999,999 之间的整数", 10, MUTED)
        self.goal_input_error.pack(anchor="w", padx=25)
        actions = ctk.CTkFrame(box, fg_color="transparent")
        actions.pack(fill="x", padx=25, pady=(15, 20))
        self.button(actions, "应用预览", self.apply_goal_input, primary=True, width=110).pack(side="right")
        self.button(actions, "取消", self.close_goal_editor, width=85).pack(side="right", padx=9)
        box.bind("<Escape>", lambda _: self.close_goal_editor())
        self.goal_input_entry.bind("<Return>", lambda _: self.apply_goal_input())
        box.protocol("WM_DELETE_WINDOW", self.close_goal_editor)
        self.after(90, self._focus_goal_input)

    def _focus_goal_input(self):
        if self.goal_editor and self.goal_editor.winfo_exists():
            self.goal_input_entry.focus_set()
            self.goal_input_entry.select_range(0, "end")

    def apply_goal_input(self):
        try:
            goal = service.parse_int(self.goal_input_var.get().strip(), "目标步数", 0, 999999)
        except ValueError as exc:
            self.goal_input_entry.configure(border_color=RED)
            self.goal_input_error.configure(text=str(exc), text_color=RED)
            self.goal_input_entry.focus_set()
            return False
        if self.process:
            self.close_goal_editor()
            return False
        self.on_goal_change(goal)
        self.close_goal_editor()
        return True

    def close_goal_editor(self):
        if self.goal_editor:
            self.goal_editor.destroy()
            self.goal_editor = None
        previous = getattr(self, "goal_editor_focus", None)
        if previous and previous.winfo_exists():
            previous.focus_set()

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
        status = {"success": "模拟完成" if self.demo else "本次执行完成", "error": "本次需要检查", "stopped": "本次已停止"}
        self.run_status.configure(text="●  运行中" if running else "●  " + status.get(state, "离线演示" if self.demo else "准备就绪"),
                                  text_color=RED if state == "error" else SAGE)
        self.run_button.configure(state="disabled" if running else "normal",
                                  text="正在运行…" if running else "先保存账号设置" if self.settings_dirty else ("保存并运行" if self.goal_dirty else "立即运行"))
        self.stop_button.configure(state="normal" if running else "disabled")
        self.save_goal_button.configure(state="normal" if self.goal_dirty and not running else "disabled",
                                        text="保存目标" if self.goal_dirty else "目标已保存")
        self.restore_goal_button.configure(state="normal" if self.goal_dirty and not running else "disabled")
        self.goal_edit_button.configure(state="disabled" if running else "normal")
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
        self.update_draft_indicators()

    def build_settings(self, frame):
        self.settings_building = True
        super().build_settings(frame)
        if self.goal_dirty:
            self._sync_step_fields()
        self.settings_note = self.label(frame, "", 10, MUTED, anchor="w")
        self.settings_note.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self.undo_account_button = self.button(self.settings_actions, "撤销删除", self.undo_remove_account,
                                                width=95, state="disabled")
        self.undo_account_button.pack(side="left", padx=9)
        for variable in (self.mode, self.min_value, self.max_value, self.ramp_var, self.gap_value):
            variable.trace_add("write", self.settings_changed)
        self.last_synced_steps = self._settings_steps()
        self.settings_baseline = self._settings_snapshot()
        self.settings_building = False
        self.settings_changed()

    def _settings_snapshot(self):
        accounts = []
        for row in self.account_rows:
            user = row["user"].get().strip()
            password = row["password"].get()
            if not password and user == row["original_user"]:
                password = row["original_password"]
            if user or password:
                accounts.append((user, password))
        return self._settings_steps(), self.ramp_var.get(), self.gap_value.get().strip(), tuple(accounts)

    def settings_changed(self, *_):
        if self.settings_building or self.settings_syncing or self.settings_baseline is None or "settings" not in self.pages:
            return
        self.settings_dirty = self._settings_snapshot() != self.settings_baseline
        self.settings_note.configure(text="有未保存的修改  ·  Ctrl+S 保存" if self.settings_dirty else "设置已保存  ·  Ctrl+S 保存当前页面",
                                     text_color=LAVENDER if self.settings_dirty else MUTED)
        self.settings_save_button.configure(text="保存修改" if self.settings_dirty else "保存设置")
        self.undo_account_button.configure(state="normal" if self.removed_accounts else "disabled")
        for row in self.account_rows:
            changed_user = row["user"].get().strip() != row["original_user"]
            text = "新密码 · 待保存" if row["password"].get() else (
                "账号已更改，请填写密码" if changed_user and row["original_password"] else
                "密码 · 已保存" if row["original_password"] else "登录密码")
            row["password_hint"].configure(text=text, text_color=LAVENDER if changed_user else SAGE if row["original_password"] else MUTED)
            for widget in (row["user_entry"], row["password_entry"]):
                widget.configure(border_color=BORDER)
        self.min_entry.configure(border_color=BORDER)
        self.max_entry.configure(border_color=BORDER)
        self.gap_entry.configure(border_color=BORDER)
        if "overview" in self.pages and not self.process:
            self.run_button.configure(text="先保存账号设置" if self.settings_dirty else "保存并运行" if self.goal_dirty else "立即运行")
        self.update_draft_indicators()

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
        user_entry = ctk.CTkEntry(row, textvariable=user_var, height=38, fg_color=BG, border_color=BORDER,
                                 text_color=INK, font=self.font(12))
        user_entry.grid(row=1, column=0, sticky="ew", padx=(12, 10), pady=(1, 11))
        password_entry = ctk.CTkEntry(row, textvariable=pass_var, show="●", height=38,
                                     fg_color=BG, border_color=BORDER, text_color=INK, font=self.font(12))
        password_entry.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=(1, 11))
        entry = {"frame": row, "user": user_var, "password": pass_var, "original_user": user,
                 "original_password": password, "password_entry": password_entry, "password_hint": hint,
                 "user_entry": user_entry}
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
        user_var.trace_add("write", self.settings_changed)
        pass_var.trace_add("write", self.settings_changed)
        self.settings_changed()
        if not self.settings_building and not user:
            user_entry.focus_set()

    def remove_account(self, entry):
        index = self.account_rows.index(entry)
        entry["frame"].pack_forget()
        self.account_rows.remove(entry)
        self.removed_accounts.append((index, entry))
        if not self.account_rows:
            self.add_account()
            self.account_rows[-1]["auto_placeholder"] = True
        self.settings_changed()
        self.notify("账号已从编辑列表移除，可点击“撤销删除”；保存后生效。")

    def undo_remove_account(self):
        if not self.removed_accounts:
            return
        if len(self.account_rows) >= 50:
            self.notify("最多可添加 50 个账号，请先移除一个空行再撤销。", True)
            return
        index, row = self.removed_accounts.pop()
        for placeholder in list(self.account_rows):
            if placeholder.get("auto_placeholder") and not placeholder["user"].get() and not placeholder["password"].get():
                placeholder["frame"].destroy()
                self.account_rows.remove(placeholder)
        index = min(index, len(self.account_rows))
        options = {"before": self.account_rows[index]["frame"]} if index < len(self.account_rows) else {}
        row["frame"].pack(fill="x", pady=(0, 10), **options)
        self.account_rows.insert(index, row)
        self.settings_changed()
        row["user_entry"].focus_set()
        self.notify("已撤销删除，账号内容已恢复。")

    def _field_error(self, widget, text):
        widget.configure(border_color=RED)
        widget.focus_set()
        self.update_idletasks()
        canvas = self.settings_scroll._parent_canvas
        bounds = canvas.bbox("all")
        if bounds and bounds[3] > canvas.winfo_height():
            y = canvas.canvasy(0) + widget.winfo_rooty() - canvas.winfo_rooty() - 75
            canvas.yview_moveto(max(0, y) / bounds[3])
        raise ValueError(text)

    def collect_settings(self):
        users = set()
        active_rows = 0
        for index, row in enumerate(self.account_rows, 1):
            user, password = row["user"].get().strip(), row["password"].get()
            if not password and user == row["original_user"]:
                password = row["original_password"]
            if not user and not password:
                continue
            active_rows += 1
            if not user:
                self._field_error(row["user_entry"], f"第 {index} 个账号：请填写手机号或邮箱。")
            if not password:
                self._field_error(row["password_entry"], f"第 {index} 个账号：请填写密码；更改账号后需要重新输入密码。")
            if "#" in user or "#" in password:
                self._field_error(row["user_entry"] if "#" in user else row["password_entry"], "账号和密码中不能包含 #。")
            if any(c in password for c in ("\n", "\r", "\x00")):
                self._field_error(row["password_entry"], f"第 {index} 个账号：密码不能包含换行或空字符。")
            try:
                service.validate_config({"USER": user, "PWD": password})
            except ValueError as exc:
                self._field_error(row["user_entry"], f"第 {index} 个账号：{exc}")
            if user in users:
                self._field_error(row["user_entry"], f"第 {index} 个账号重复，请移除重复账号。")
            users.add(user)
        if not active_rows:
            self._field_error(self.account_rows[0]["user_entry"], "请先填写一个 Zepp Life 账号和密码。")
        for variable, widget, title in ((self.min_value, self.min_entry, "目标步数" if self.mode.get() == "固定步数" else "最小步数"),
                                         (self.max_value, self.max_entry, "最大步数")):
            if widget is self.max_entry and self.mode.get() == "固定步数":
                continue
            try:
                service.parse_int(variable.get().strip(), title, 0, 999999)
            except ValueError as exc:
                self._field_error(widget, str(exc))
        if self.mode.get() != "固定步数" and int(self.max_value.get()) < int(self.min_value.get()):
            self._field_error(self.max_entry, "最大步数不能小于最小步数。")
        try:
            service.validate_config({"USER": "demo@example.com", "PWD": "validation-only", "SLEEP_GAP": self.gap_value.get().strip()})
        except ValueError as exc:
            self._field_error(self.gap_entry, str(exc))
        return super().collect_settings()

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
            for _, removed in self.removed_accounts:
                removed["frame"].destroy()
            self.removed_accounts.clear()
            self.last_synced_steps = self._settings_steps()
            self.settings_baseline = self._settings_snapshot()
            self.settings_changed()
        return saved

    def reset_settings(self):
        if not self._confirm_discard("重新载入", scopes=("overview", "settings")):
            return
        self.goal_dirty = False
        self.quick_goal = None
        self.settings_dirty = False
        self.settings_baseline = self.last_synced_steps = None
        self.removed_accounts.clear()
        super().reset_settings()
        self.update_overview()

    def build_logs(self, frame):
        frame.grid_rowconfigure(2, weight=1)
        toolbar = ctk.CTkFrame(frame, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        toolbar.grid_columnconfigure(1, weight=1)
        self.log_search = ctk.StringVar(value="")
        self.log_filter = ctk.StringVar(value="全部")
        self.log_search_entry = ctk.CTkEntry(toolbar, textvariable=self.log_search, height=42, fg_color=PANEL,
                                            border_color=BORDER, corner_radius=12, text_color=INK, font=self.font(12))
        self.label(toolbar, "搜索日志", 11, MUTED).grid(row=0, column=0, padx=(0, 12))
        self.log_search_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self.log_search_entry.bind("<Escape>", lambda _: self.clear_log_filters())
        self.log_search_entry.bind("<Return>", lambda _: self.render_logs())
        self.clear_log_button = self.button(toolbar, "清除", self.clear_log_filters, width=60, state="disabled")
        self.clear_log_button.grid(row=0, column=2, padx=(0, 8))
        self.button(toolbar, "刷新", self.refresh_logs, width=65).grid(row=0, column=3, padx=(0, 8))
        self.button(toolbar, "日志文件夹 ↗", self.open_logs_folder, width=115).grid(row=0, column=4)
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
        self.copy_log_button = self.button(reader, "复制记录", self.copy_selected_log, width=85, state="disabled")
        self.copy_log_button.configure(height=28, font=self.font(10))
        self.copy_log_button.grid(row=0, column=1, padx=(0, 18), pady=(13, 9))
        self.log_text = ctk.CTkTextbox(reader, fg_color=PANEL, text_color="#3E4944", wrap="word",
                                      font=self.font(12), corner_radius=0)
        self.log_text.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=14, pady=(0, 13))
        self.log_text.configure(state="disabled")
        self.log_search.trace_add("write", self.schedule_log_search)

    def focus_log_search(self, event=None):
        if self.palette and self.palette.winfo_exists() or self.goal_editor and self.goal_editor.winfo_exists():
            return "break"
        self.show_page("logs")
        self.log_search_entry.focus_set()
        self.log_search_entry.select_range(0, "end")
        return "break"

    def schedule_log_search(self, *_):
        if self.log_search_id:
            self.after_cancel(self.log_search_id)
        self.log_search_id = self.after(150, self.render_logs)

    def clear_log_filters(self):
        self.log_search.set("")
        self.log_filter.set("全部")
        self.render_logs()
        self.log_search_entry.focus_set()
        return "break"

    def copy_selected_log(self):
        if self.displayed_log:
            self.clipboard_clear()
            self.clipboard_append(self.displayed_log[1])
            self.notify("记录已复制，账号和敏感信息已隐藏。")

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
        if self.log_search_id:
            self.after_cancel(self.log_search_id)
            self.log_search_id = None
        if "logs" not in self.pages or not hasattr(self, "log_list"):
            return
        rows = self.filtered_logs()
        for child in self.log_list.winfo_children():
            child.destroy()
        self.log_buttons.clear()
        self.log_count.configure(text=f"{len(rows)} 条匹配  /  共 {len(self.logs)} 条")
        self.clear_log_button.configure(state="normal" if self.log_search.get() or self.log_filter.get() != "全部" else "disabled")
        for index, item in enumerate(rows):
            color = SAGE if item["state"] == "success" else RED if item["state"] == "failed" else MUTED
            button = self.button(self.log_list, f"{item['time']}\n{item['summary']}", lambda value=item: self.select_log(value))
            button.configure(height=67, corner_radius=11, anchor="w", text_color=color,
                             font=self.font(11), fg_color=RAISED)
            button.grid(row=index, column=0, sticky="ew", padx=4, pady=4)
            self.log_buttons[item["name"]] = button
        selected = next((item for item in rows if item["name"] == self.selected_log_name), None)
        if rows:
            self.select_log(selected or rows[0])
        else:
            self.displayed_log = None
            self.copy_log_button.configure(state="disabled")
            self.label(self.log_list, "没有找到记录" if self.logs else "还没有记录", 12, MUTED).grid(row=0, column=0, padx=15, pady=30)
            self.log_title.configure(text="没有匹配的记录" if self.logs else "等待第一条记录")
            self.log_text.configure(state="normal")
            self.log_text.delete("1.0", "end")
            self.log_text.insert("1.0", "试试其他关键词，或切换筛选条件。" if self.logs else "运行后的结果和排查信息，会出现在这里。")
            self.log_text.configure(state="disabled")

    def select_log(self, item):
        self.selected_log_name = item["name"]
        for name, button in self.log_buttons.items():
            selected = name == item["name"]
            button.configure(fg_color="#E4EBDD" if selected else RAISED,
                             border_color=ACCENT if selected else BORDER, border_width=1 if selected else 0)
        signature = item["name"], item["text"]
        if signature != self.displayed_log:
            super().select_log(item)
            self.displayed_log = signature
        self.copy_log_button.configure(state="normal")
        reader = self.log_text._textbox
        reader.tag_remove("search_match", "1.0", "end")
        query = self.log_search.get().strip()
        if query:
            reader.tag_configure("search_match", background="#E8E0F0", foreground=INK)
            index = "1.0"
            while True:
                index = reader.search(query, index, stopindex="end", nocase=True)
                if not index:
                    break
                end = f"{index}+{len(query)}c"
                reader.tag_add("search_match", index, end)
                index = end

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
        self.new_time_entry = ctk.CTkEntry(add, textvariable=self.new_time_var, height=33, width=82, fg_color=BG,
                                            border_color=BORDER, text_color=INK, font=self.font(12))
        self.new_time_entry.pack(side="left")
        self.new_time_entry.bind("<Return>", lambda _: self.add_task_time())
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
            if combined != times:
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
        if self.settings_dirty:
            self.show_page("settings")
            self.notify("账号设置还有未保存的修改，请先保存或重新载入，再开始运行。", True)
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
        if self.goal_editor and self.goal_editor.winfo_exists():
            return "break"
        if self.palette and self.palette.winfo_exists():
            self.palette.lift()
            return "break"
        self.palette_focus = self.focus_get()
        box = ctk.CTkToplevel(self)
        self.palette = box
        box.title("move · 快速跳转")
        box.geometry("580x440")
        box.resizable(False, False)
        box.configure(fg_color=BG)
        box.transient(self)
        box.grab_set()
        self.label(box, "想去哪里？", 23, bold=True).pack(anchor="w", padx=25, pady=(22, 2))
        self.label(box, "↑ ↓ 选择  ·  Enter 打开  ·  Esc 返回", 11, MUTED).pack(anchor="w", padx=25, pady=(0, 12))
        self.palette_query = ctk.StringVar(value="")
        self.palette_entry = ctk.CTkEntry(box, textvariable=self.palette_query, height=42, fg_color=PANEL, border_color=BORDER,
                                          text_color=INK, font=self.font(14), corner_radius=12)
        self.palette_entry.pack(fill="x", padx=25)
        self.palette_results = ctk.CTkScrollableFrame(box, fg_color="transparent", height=245)
        self.palette_results.pack(fill="both", expand=True, padx=18, pady=(10, 16))
        self.palette_actions = [("今日目标 / 首页", lambda: self.show_page("overview")), ("账号设置 / 步数范围", lambda: self.show_page("settings")),
                   ("运行记录 / 日志搜索", lambda: self.show_page("logs")), ("自动任务 / 定时计划", lambda: self.show_page("tasks")),
                   ("运动轨迹 / 地图", lambda: self.show_page("sport")), ("切换项目目录", self.choose_project)]
        if self.current_page == "overview" and not self.process:
            self.palette_actions.extend([("精确输入目标", self.open_goal_editor), ("保存当前目标", self.save_quick_goal),
                                          ("检查未保存的账号设置" if self.settings_dirty else "保存目标并运行" if self.goal_dirty else "立即运行已保存目标", self.start_run)])
            if self.goal_dirty:
                self.palette_actions.append(("还原已保存的目标", self.restore_quick_goal))
        elif self.current_page == "settings":
            self.palette_actions.append(("保存账号与步数设置", self.save_settings))
        elif self.current_page == "tasks":
            self.palette_actions.append(("保存自动任务时间", self.save_task_clicked))
        self.palette_query.trace_add("write", self.render_palette)
        box.bind("<Escape>", lambda _: self.close_palette())
        self.palette_entry.bind("<Down>", lambda _: self.move_palette_selection(1))
        self.palette_entry.bind("<Up>", lambda _: self.move_palette_selection(-1))
        self.palette_entry.bind("<Return>", lambda _: self.execute_palette_selection())
        box.protocol("WM_DELETE_WINDOW", self.close_palette)
        self.render_palette()
        self.after(100, lambda: self.palette_entry.focus_set() if self.palette and self.palette.winfo_exists() else None)
        return "break"

    def render_palette(self, *_):
        for child in self.palette_results.winfo_children():
            child.destroy()
        query = self.palette_query.get().strip().casefold()
        self.palette_visible = [item for item in self.palette_actions if query in item[0].casefold()]
        self.palette_buttons = []
        self.palette_index = 0
        self.palette_results._parent_canvas.yview_moveto(0)
        for index, (title, command) in enumerate(self.palette_visible):
            button = self.button(self.palette_results, title + "   ↗", lambda i=index: self.execute_palette_selection(i))
            button.configure(anchor="w", height=36, font=self.font(12))
            button.pack(fill="x", padx=3, pady=3)
            self.palette_buttons.append(button)
        if not self.palette_visible:
            self.label(self.palette_results, "没有匹配的操作", 15, INK).pack(pady=(33, 8))
            self.label(self.palette_results, "试试“目标”“日志”或“地图”。", 11, MUTED).pack()
        self._highlight_palette()

    def _highlight_palette(self):
        for index, button in enumerate(self.palette_buttons):
            selected = index == self.palette_index
            button.configure(fg_color="#DFE7DC" if selected else RAISED,
                             text_color=INK if selected else MUTED,
                             border_width=1 if selected else 0, border_color=ACCENT)

    def move_palette_selection(self, delta):
        if self.palette_visible:
            self.palette_index = (self.palette_index + delta) % len(self.palette_visible)
            self._highlight_palette()
            self.palette.update_idletasks()
            canvas = self.palette_results._parent_canvas
            button = self.palette_buttons[self.palette_index]
            y = button.winfo_rooty() - canvas.winfo_rooty()
            bounds = canvas.bbox("all")
            if bounds and (y < 0 or y + button.winfo_height() > canvas.winfo_height()):
                canvas.yview_moveto(max(0, canvas.canvasy(0) + y - 60) / max(1, bounds[3]))
        return "break"

    def execute_palette_selection(self, index=None):
        if not self.palette_visible:
            return "break"
        command = self.palette_visible[self.palette_index if index is None else index][1]
        self.close_palette()
        self.after(30, command)
        return "break"

    def close_palette(self):
        if self.palette:
            self.palette.destroy()
            self.palette = None
        previous = getattr(self, "palette_focus", None)
        if previous and previous.winfo_exists():
            previous.focus_set()
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
        reader.insert("1.0", "首页目标\n拖动刻度、滑动横条或点选预设，只调整目标预览。也可精确输入整数，点“还原”恢复保存的目标。点击“保存目标”后写入配置；有草稿时，“保存并运行”会保存目标再开始。刻度表示设定值。轻触芙莉莲头像，会有一点旅途回应。\n\n"
                      "账号与步数\n使用 Zepp Life 手机号或邮箱。在这里配置随机范围、按时间递增和多账号。已有密码留空保留，更改账号后需重新填写密码。错误输入会高亮定位；删除账号可以撤销。导航上的小点表示未保存的修改。保存前会备份原配置。\n\n"
                      "日志与快速跳转\n运行记录支持关键词搜索、匹配高亮、结果筛选和复制脱敏记录。Ctrl+F 聚焦搜索，Esc 清除筛选。按 Ctrl+K 搜索操作，用上下键选择、Enter 执行、Esc 返回。Ctrl+S 保存当前页面的目标、设置或计划时间。\n\n"
                      "自动任务\n点时间标签上的 × 删除，输入 HH:MM 后添加；修改后点击保存才生效。电脑需开机并登录 Windows。\n\n"
                      "运动轨迹\n联网加载 sport.gyvv.top 原站。网页上方可重试、打开大窗口、选择导出位置。原站的地图和生成服务需要网络。\n\n"
                      "本地文件\n首次优先读取 E:\\mimotion，也可切换项目目录。配置、登录缓存、备份和浏览器资料保存在所选目录，请保管好。分享软件请只分享发布文件。\n\n"
                      "来源与版本\n原核心来自 mimotion，沿用 Apache-2.0；版本 " + service.VERSION + "。结果以接口返回和第三方平台显示为准。")
        reader.configure(state="disabled")
        self.button(box, "知道了", box.destroy, primary=True, width=108).pack(anchor="e", padx=25, pady=19)

    def close_app(self):
        if not self._confirm_discard("关闭软件"):
            return
        # Let the existing close confirmation protect an in-flight run.
        for timer in (self.page_transition_id, self.toast_clear_id, self.log_search_id):
            if timer:
                self.after_cancel(timer)
        self.page_transition_id = self.toast_clear_id = self.log_search_id = None
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
