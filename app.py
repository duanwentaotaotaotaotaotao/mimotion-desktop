"""MiMotion desktop UI. Launching the UI never submits step data."""
from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import uuid
from pathlib import Path
from tkinter import filedialog, messagebox

import backend as service


def arguments():
    parser = argparse.ArgumentParser(description="move")
    parser.add_argument("--project", type=Path)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--scheduled", action="store_true")
    parser.add_argument("--result", type=Path)
    parser.add_argument("--demo", action="store_true", help="离线模拟，不访问平台")
    parser.add_argument("--page", choices=["overview", "sport"], default="overview", help="首次打开的页面")
    parser.add_argument("--inspect-sport-report", type=Path, help=argparse.SUPPRESS)
    return parser.parse_args()


def preferences_path() -> Path:
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    return base / "MiMotion-project.json"


def resolve_project(explicit: Path | None) -> Path:
    if explicit:
        return explicit.resolve()
    try:
        stored = json.loads(preferences_path().read_text(encoding="utf-8"))
        selected = Path(stored["project"])
        if selected.is_dir():
            return selected.resolve()
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return service.default_project().resolve()


def launch_ui(project: Path, demo=False, initial_page="overview", sport_report=None):
    import customtkinter as ctk
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("green")
    app = MiMotionApp(project, demo)
    app.sport_inspect_report = sport_report
    if initial_page != "overview":
        app.show_page(initial_page)
    app.mainloop()


# The worker exits before importing any GUI modules.
if __name__ == "__main__" and any(item in sys.argv for item in ("--worker", "--scheduled")):
    worker_args = arguments()
    raise SystemExit(service.run_worker(resolve_project(worker_args.project), worker_args.result, worker_args.demo))

import customtkinter as ctk
from sport import SportPanel


BG = "#F5F4EF"
WHITE = "#FFFEFA"
INK = "#3E4944"
MUTED = "#818880"
BORDER = "#E0E5DA"
GREEN = "#7E9481"
SIDEBAR = "#EFF2EA"
LIME = "#7E9481"
PALE = "#ECEFE8"
RED = "#BA7D7A"
FONT = "Microsoft YaHei UI"


class BaseMiMotionApp(ctk.CTk):
    def __init__(self, project: Path, demo=False):
        super().__init__()
        self.demo = demo
        self.project = project.resolve()
        self.store = service.ConfigStore(self.project)
        self.config_data = dict(service.DEFAULTS)
        self.last_error = ""
        self.events = queue.Queue()
        self.process = None
        self.result_path = None
        self.cancelled = False
        self.closing = False
        self.task = {}
        self.task_busy = False
        self.logs = []
        self.pages = {}
        self.nav = {}
        self.account_rows = []
        self.current_page = "overview"
        self.title("MiMotion 桌面助手" + (" · 离线演示" if demo else ""))
        self.geometry("1200x820")
        self.minsize(1100, 760)
        self.configure(fg_color=BG)
        self.protocol("WM_DELETE_WINDOW", self.close_app)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._sidebar()
        self.main = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(1, weight=1)
        self._topbar()
        self.content = ctk.CTkFrame(self.main, fg_color="transparent")
        self.content.grid(row=1, column=0, sticky="nsew", padx=30, pady=(0, 12))
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)
        self.toast = ctk.CTkLabel(self.main, text="", anchor="w", height=30, text_color=MUTED,
                                 font=self.font(12))
        self.toast.grid(row=2, column=0, sticky="ew", padx=32, pady=(0, 10))
        self.reload_data()
        self.show_page("overview")
        self.after(100, self._drain_events)
        self.after(250, self._icon)
        self.after(500, self.refresh_task)

    @staticmethod
    def font(size=13, bold=False):
        return ctk.CTkFont(family=FONT, size=size, weight="bold" if bold else "normal")

    def label(self, parent, text, size=13, color=INK, bold=False, **kwargs):
        return ctk.CTkLabel(parent, text=text, font=self.font(size, bold), text_color=color, **kwargs)

    def button(self, parent, text, command, primary=False, **kwargs):
        return ctk.CTkButton(parent, text=text, command=command, font=self.font(13, primary),
                            height=40, corner_radius=9,
                            fg_color=LIME if primary else "#EDF1E9", text_color=INK,
                            hover_color="#B4DF7E" if primary else "#E0E7DB", **kwargs)

    def card(self, parent, **kwargs):
        return ctk.CTkFrame(parent, fg_color=WHITE, corner_radius=15,
                           border_width=1, border_color=BORDER, **kwargs)

    def _icon(self):
        try:
            self.iconbitmap(str(Path(__file__).parent / "assets" / "mimotion.ico"))
        except tk.TclError:
            pass

    def _sidebar(self):
        side = ctk.CTkFrame(self, width=210, corner_radius=0, fg_color=SIDEBAR)
        side.grid(row=0, column=0, sticky="nsew")
        side.grid_propagate(False)
        side.grid_columnconfigure(0, weight=1)
        side.grid_rowconfigure(8, weight=1)
        brand = ctk.CTkFrame(side, fg_color="transparent")
        brand.grid(row=0, column=0, padx=23, pady=(32, 5), sticky="ew")
        ctk.CTkLabel(brand, text="m", width=36, height=36, fg_color=LIME, text_color=SIDEBAR,
                     corner_radius=10, font=self.font(26, True)).pack(side="left")
        self.label(brand, "MiMotion", 20, "#F5F9EF", True).pack(side="left", padx=(10, 0))
        self.label(side, "把日常操作，交给一个界面。", 11, "#A0B6A9").grid(row=1, column=0, pady=(0, 35))
        for row, (key, symbol, title) in enumerate([
            ("overview", "◉", "运行面板"), ("settings", "≡", "账号与步数"),
            ("logs", "↗", "运行记录"), ("tasks", "◷", "自动任务"),
            ("sport", "◇", "运动轨迹"),
        ], 2):
            btn = ctk.CTkButton(side, text=f"{symbol}    {title}", anchor="w", height=45,
                                corner_radius=9, font=self.font(14), fg_color="transparent",
                                hover_color="#25483C", text_color="#BBCEC0",
                                command=lambda page=key: self.show_page(page))
            btn.grid(row=row, column=0, sticky="ew", padx=17, pady=4)
            self.nav[key] = btn
        note = ctk.CTkFrame(side, fg_color="#1E3C33", corner_radius=12)
        note.grid(row=9, column=0, sticky="ew", padx=18, pady=(15, 20))
        self.label(note, "●  本机运行", 12, LIME, True).pack(anchor="w", padx=16, pady=(14, 4))
        self.label(note, "配置与记录保存在本机\n步数与轨迹按操作联网", 11, "#B0C2B6",
                   justify="left").pack(anchor="w", padx=16, pady=(0, 14))
        self.button(side, f"使用帮助  ·  v{service.VERSION}", self.show_help).grid(
            row=10, column=0, padx=18, pady=(0, 24), sticky="ew")

    def _topbar(self):
        top = ctk.CTkFrame(self.main, fg_color="transparent", height=110)
        top.grid(row=0, column=0, sticky="ew", padx=30, pady=(25, 20))
        top.grid_columnconfigure(0, weight=1)
        self.heading = self.label(top, "运行面板", 27, bold=True, anchor="w")
        self.heading.grid(row=0, column=0, sticky="w")
        self.subheading = self.label(top, "目标、账号与运行结果，一眼掌握。", 12, MUTED, anchor="w")
        self.subheading.grid(row=1, column=0, sticky="w", pady=(5, 0))
        self.project_badge = self.label(top, "", 11, GREEN, anchor="e")
        self.project_badge.grid(row=0, column=1, padx=(12, 0), sticky="e")
        self.button(top, "切换项目目录", self.choose_project, width=125).grid(row=1, column=1, pady=(5, 0), sticky="e")

    def notify(self, text, error=False):
        self.last_error = text if error else ""
        self.toast.configure(text=("  " + text), text_color=RED if error else GREEN)

    def reload_data(self):
        try:
            self.config_data = self.store.load()
        except (OSError, ValueError) as exc:
            self.config_data = dict(service.DEFAULTS)
            self.notify(str(exc), True)
        self.logs = service.log_entries(self.project, self.config_data)
        path_label = str(self.project)
        if len(path_label) > 43:
            path_label = "…" + path_label[-42:]
        self.project_badge.configure(text=("离线演示  ·  " if self.demo else "本机项目  ·  ") + self.project.name)

    def choose_project(self):
        if self.process:
            self.notify("请等本次运行结束后再切换项目目录。", True)
            return
        chosen = filedialog.askdirectory(title="选择 mimotion 项目目录", initialdir=str(self.project.parent))
        if not chosen:
            return
        self.project = Path(chosen).resolve()
        self.store = service.ConfigStore(self.project)
        for page in self.pages.values():
            page.destroy()
        self.pages.clear()
        self.task = {}
        self.reload_data()
        self.show_page("overview")
        try:
            service.atomic_json(preferences_path(), {"project": str(self.project)})
        except OSError:
            self.notify("目录已切换；此位置不能保存目录偏好，下次可重新选择。")
        self.refresh_task()

    def show_page(self, name):
        titles = {
            "overview": ("运行面板", "目标、账号与运行结果，一眼掌握。"),
            "settings": ("账号与步数", "填写一次，日常操作更轻松。"),
            "logs": ("运行记录", "每次执行都有记录，结果可以随时回看。"),
            "tasks": ("自动任务", "由 Windows 按设定时间自动运行。"),
            "sport": ("运动轨迹", "绘制运动路线、调整参数，导出运动文件。"),
        }
        self.current_page = name
        self.heading.configure(text=titles[name][0])
        self.subheading.configure(text=titles[name][1])
        for key, btn in self.nav.items():
            btn.configure(fg_color="#2A4C3F" if key == name else "transparent",
                          text_color=LIME if key == name else "#BBCEC0")
        for page in self.pages.values():
            page.grid_remove()
        if name not in self.pages:
            frame = ctk.CTkFrame(self.content, fg_color="transparent")
            frame.grid_columnconfigure(0, weight=1)
            self.pages[name] = frame
            getattr(self, "build_" + name)(frame)
        self.pages[name].grid(row=0, column=0, sticky="nsew")
        if name == "overview":
            self.update_overview()
        elif name == "logs":
            self.refresh_logs()
        elif name == "tasks":
            self.update_task_view()

    def build_sport(self, frame):
        frame.grid_rowconfigure(0, weight=1)
        panel = SportPanel(frame, self.project, self.notify, getattr(self, "sport_inspect_report", None))
        panel.grid(row=0, column=0, sticky="nsew")
        self.sport_panel = panel

    def build_overview(self, frame):
        hero = ctk.CTkFrame(frame, fg_color=GREEN, corner_radius=18, height=220)
        hero.grid(row=0, column=0, sticky="ew")
        hero.grid_propagate(False)
        hero.grid_columnconfigure(0, weight=1)
        self.label(hero, "本 次 目 标", 12, "#C8DCC9", True).grid(row=0, column=0, sticky="w", padx=28, pady=(23, 0))
        self.goal_label = self.label(hero, "—", 50, "#F0FAE7", True, anchor="w")
        self.goal_label.grid(row=1, column=0, sticky="w", padx=26, pady=(2, 0))
        self.goal_note = self.label(hero, "", 12, "#C6D9C6", anchor="w")
        self.goal_note.grid(row=2, column=0, sticky="w", padx=28, pady=(3, 17))
        controls = ctk.CTkFrame(hero, fg_color="transparent")
        controls.grid(row=1, column=1, rowspan=2, sticky="e", padx=28, pady=(0, 18))
        self.run_button = self.button(controls, "▶   立即运行", self.start_run, primary=True, width=154)
        self.run_button.pack(pady=(0, 9))
        self.stop_button = self.button(controls, "停止本次", self.stop_run, width=154, state="disabled")
        self.stop_button.pack()
        self.run_status = self.label(hero, "", 11, LIME)
        self.run_status.grid(row=0, column=1, padx=28, pady=(23, 0), sticky="e")

        metrics = ctk.CTkFrame(frame, fg_color="transparent")
        metrics.grid(row=1, column=0, sticky="ew", pady=17)
        metrics.grid_columnconfigure((0, 1, 2), weight=1, uniform="metrics")
        self.metric_values = []
        self.metric_details = []
        for col, title in enumerate(("已配置账号", "最近运行", "自动任务")):
            card = self.card(metrics, height=113)
            card.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 6, 0 if col == 2 else 6))
            card.grid_propagate(False)
            self.label(card, title, 11, MUTED).pack(anchor="w", padx=19, pady=(13, 2))
            value = self.label(card, "—", 22, bold=True)
            value.pack(anchor="w", padx=19)
            detail = self.label(card, "", 11, MUTED)
            detail.pack(anchor="w", padx=19, pady=(0, 10))
            self.metric_values.append(value)
            self.metric_details.append(detail)

        recent = self.card(frame)
        recent.grid(row=2, column=0, sticky="nsew")
        frame.grid_rowconfigure(2, weight=1)
        recent.grid_columnconfigure(0, weight=1)
        header = ctk.CTkFrame(recent, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=21, pady=(15, 4))
        self.label(header, "最近记录", 15, bold=True).pack(side="left")
        ctk.CTkButton(header, text="查看全部  →", width=100, height=30, font=self.font(11),
                       fg_color="transparent", hover_color=PALE, text_color=GREEN,
                       command=lambda: self.show_page("logs")).pack(side="right")
        self.recent_list = ctk.CTkFrame(recent, fg_color="transparent")
        self.recent_list.grid(row=1, column=0, sticky="ew", padx=21, pady=(0, 13))
        self.recent_list.grid_columnconfigure(1, weight=1)

    def update_overview(self):
        if "overview" not in self.pages:
            return
        cfg = self.config_data
        minimum, maximum = str(cfg.get("MIN_STEP", "18000")), str(cfg.get("MAX_STEP", "25000"))
        try:
            target = f"{int(maximum):,}" if minimum == maximum else f"{int(minimum):,} – {int(maximum):,}"
        except ValueError:
            target = "请检查设置"
        self.goal_label.configure(text=target, font=self.font(50 if len(target) < 12 else 33, True))
        ramp = str(cfg.get("NO_TIME_RATE", "True")).lower() not in ("true", "1", "yes")
        mode = "固定步数" if minimum == maximum else "随机范围"
        self.goal_note.configure(text=f"{mode}  ·  {'随时间递增' if ramp else '直接使用设定值'}  ·  北京时间")
        self.run_status.configure(text="●  正在运行" if self.process else ("●  离线演示" if self.demo else "●  等待运行"))
        self.run_button.configure(state="disabled" if self.process else "normal",
                                  text="运行中…" if self.process else "▶   立即运行")
        self.stop_button.configure(state="normal" if self.process else "disabled")
        users = [item for item in str(cfg.get("USER", "")).split("#") if item]
        self.metric_values[0].configure(text=f"{len(users):02d}")
        self.metric_details[0].configure(text=service.mask_account(users[0]) if len(users) == 1 else ("支持多个账号" if users else "前往“账号与步数”添加"))
        latest = self.logs[0] if self.logs else None
        status_labels = {"success": "执行成功", "failed": "需要检查", "stopped": "已停止", "unknown": "查看记录"}
        self.metric_values[1].configure(text=status_labels.get(latest["state"], "查看记录") if latest else "暂无记录")
        self.metric_details[1].configure(text=latest["time"] if latest else "点击运行后显示结果")
        if self.task.get("found"):
            self.metric_values[2].configure(text="已开启" if self.task.get("enabled") else "已暂停")
            self.metric_details[2].configure(text=f"每天 {len(self.task.get('times', []))} 个运行时间")
        else:
            self.metric_values[2].configure(text="待检查" if self.task.get("unavailable") else "未设置")
            self.metric_details[2].configure(text="可在自动任务中查看")
        for child in self.recent_list.winfo_children():
            child.destroy()
        if not self.logs:
            self.label(self.recent_list, "还没有运行记录", 13, MUTED).grid(row=0, column=0, sticky="w", pady=(17, 6))
            self.label(self.recent_list, "配置账号后，点击上方“立即运行”开始。", 11, MUTED).grid(row=1, column=0, sticky="w", pady=(0, 10))
        for row, item in enumerate(self.logs[:3]):
            color = GREEN if item["state"] == "success" else (RED if item["state"] == "failed" else MUTED)
            self.label(self.recent_list, "●", 14, color).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=10)
            self.label(self.recent_list, item["summary"], 12).grid(row=row, column=1, sticky="w")
            self.label(self.recent_list, item["time"], 11, MUTED).grid(row=row, column=2, sticky="e")

    def build_settings(self, frame):
        frame.grid_rowconfigure(0, weight=1)
        scroll = ctk.CTkScrollableFrame(frame, fg_color="transparent", corner_radius=0)
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)
        step_card = self.card(scroll)
        step_card.grid(row=0, column=0, sticky="ew", padx=(3, 9), pady=(0, 14))
        step_card.grid_columnconfigure(0, weight=1)
        self.label(step_card, "01   步数设置", 15, bold=True).grid(row=0, column=0, sticky="w", padx=22, pady=(18, 12))
        minimum = str(self.config_data["MIN_STEP"])
        maximum = str(self.config_data["MAX_STEP"])
        self.mode = ctk.StringVar(value="固定步数" if minimum == maximum else "随机范围")
        ctk.CTkSegmentedButton(step_card, values=["固定步数", "随机范围"], variable=self.mode,
                               command=self.change_mode, selected_color="#DDE7D9",
                               selected_hover_color="#D3E0CE", unselected_color="#20242E",
                               unselected_hover_color="#E4EBDD", text_color=INK,
                               font=self.font(12), height=36).grid(row=1, column=0, sticky="w", padx=22)
        numbers = ctk.CTkFrame(step_card, fg_color="transparent")
        numbers.grid(row=2, column=0, sticky="ew", padx=22, pady=(13, 4))
        numbers.grid_columnconfigure((0, 1), weight=1)
        self.min_caption = self.label(numbers, "目标步数" if minimum == maximum else "最小步数", 11, MUTED)
        self.min_caption.grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.max_caption = self.label(numbers, "最大步数", 11, MUTED)
        self.max_caption.grid(row=0, column=1, sticky="w", padx=(16, 0), pady=(0, 6))
        self.min_value = ctk.StringVar(value=minimum)
        self.max_value = ctk.StringVar(value=maximum)
        self.min_entry = ctk.CTkEntry(numbers, textvariable=self.min_value, height=43, font=self.font(21),
                                     fg_color=BG, border_color=BORDER)
        self.min_entry.grid(row=1, column=0, sticky="ew")
        self.max_entry = ctk.CTkEntry(numbers, textvariable=self.max_value, height=43, font=self.font(21),
                                     fg_color=BG, border_color=BORDER)
        self.max_entry.grid(row=1, column=1, sticky="ew", padx=(16, 0))
        ramp = str(self.config_data.get("NO_TIME_RATE", "True")).lower() not in ("true", "1", "yes")
        self.ramp_var = ctk.BooleanVar(value=ramp)
        ctk.CTkSwitch(step_card, text="按当天时间逐渐递增，22:00 达到目标", variable=self.ramp_var,
                      progress_color=GREEN, font=self.font(12), text_color=INK).grid(
            row=3, column=0, sticky="w", padx=22, pady=(15, 18))
        self.change_mode(self.mode.get())

        account_card = self.card(scroll)
        account_card.grid(row=1, column=0, sticky="ew", padx=(3, 9), pady=(0, 14))
        account_card.grid_columnconfigure(0, weight=1)
        self.label(account_card, "02   Zepp Life 账号", 15, bold=True).grid(row=0, column=0, sticky="w", padx=22, pady=(18, 3))
        self.label(account_card, "填写 Zepp Life 的手机号或邮箱；已有密码留空即可保留。", 11, MUTED).grid(
            row=1, column=0, sticky="w", padx=22, pady=(0, 11))
        self.accounts_host = ctk.CTkFrame(account_card, fg_color="transparent")
        self.accounts_host.grid(row=2, column=0, sticky="ew", padx=22)
        self.accounts_host.grid_columnconfigure(0, weight=1)
        self.account_rows = []
        users = str(self.config_data.get("USER", "")).split("#")
        passwords = str(self.config_data.get("PWD", "")).split("#")
        for index, user in enumerate(users):
            self.add_account(user, passwords[index] if index < len(passwords) else "")
        self.button(account_card, "+  添加账号", self.add_account, width=120).grid(
            row=3, column=0, sticky="w", padx=22, pady=(5, 16))

        advanced = self.card(scroll)
        advanced.grid(row=2, column=0, sticky="ew", padx=(3, 9), pady=(0, 7))
        self.label(advanced, "多账号运行间隔", 12).grid(row=0, column=0, sticky="w", padx=22, pady=17)
        self.gap_value = ctk.StringVar(value=str(self.config_data.get("SLEEP_GAP", "5")))
        ctk.CTkEntry(advanced, textvariable=self.gap_value, width=75, height=35,
                      border_color=BORDER, fg_color=BG, font=self.font(12)).grid(row=0, column=1)
        self.label(advanced, "秒", 12, MUTED).grid(row=0, column=2, padx=(8, 22))
        buttons = ctk.CTkFrame(frame, fg_color="transparent")
        buttons.grid(row=1, column=0, sticky="ew", pady=(13, 0))
        self.button(buttons, "保存设置", self.save_settings, primary=True, width=143).pack(side="right")
        self.button(buttons, "重新载入", self.reset_settings, width=110).pack(side="right", padx=10)
        self.button(buttons, "重置登录缓存", self.reset_tokens, width=130).pack(side="left")

    def change_mode(self, value):
        fixed = value == "固定步数"
        self.min_caption.configure(text="目标步数" if fixed else "最小步数")
        self.min_entry.grid_configure(columnspan=2 if fixed else 1)
        if fixed:
            self.max_entry.grid_remove()
            self.max_caption.grid_remove()
        else:
            self.max_entry.grid()
            self.max_caption.grid()

    def add_account(self, user="", password=""):
        if len(self.account_rows) >= 50:
            self.notify("最多可添加 50 个账号。", True)
            return
        row = ctk.CTkFrame(self.accounts_host, fg_color="transparent")
        row.pack(fill="x", pady=(0, 9))
        row.grid_columnconfigure((0, 1), weight=1)
        user_var = ctk.StringVar(value=user)
        pass_var = ctk.StringVar(value="")
        ctk.CTkEntry(row, textvariable=user_var, placeholder_text="手机号 / 邮箱", height=38,
                      fg_color=BG, border_color=BORDER, font=self.font(12)).grid(row=0, column=0, sticky="ew")
        password_entry = ctk.CTkEntry(row, textvariable=pass_var, placeholder_text="已保存，留空保留" if password else "密码",
                                    show="●", height=38, fg_color=BG, border_color=BORDER, font=self.font(12))
        password_entry.grid(row=0, column=1, sticky="ew", padx=(10, 8))
        entry = {"frame": row, "user": user_var, "password": pass_var,
                 "original_user": user, "original_password": password, "password_entry": password_entry}
        ctk.CTkButton(row, text="×", width=33, height=36, fg_color="#F5EBE7", hover_color="#EAD7D0",
                       text_color=RED, font=self.font(18), command=lambda: self.remove_account(entry)).grid(row=0, column=2)
        self.account_rows.append(entry)

    def remove_account(self, entry):
        entry["frame"].destroy()
        self.account_rows.remove(entry)
        if not self.account_rows:
            self.add_account()

    def collect_settings(self):
        users, passwords = [], []
        for row in self.account_rows:
            user = row["user"].get().strip()
            password = row["password"].get()
            if not password and user == row["original_user"]:
                password = row["original_password"]
            if not user and not password:
                continue
            if "#" in user or "#" in password:
                raise ValueError("原项目使用 # 分隔多账号，账号和密码中不能包含 #。")
            users.append(user)
            passwords.append(password)
        minimum = self.min_value.get().strip()
        maximum = minimum if self.mode.get() == "固定步数" else self.max_value.get().strip()
        changes = {"USER": "#".join(users), "PWD": "#".join(passwords), "MIN_STEP": minimum,
                   "MAX_STEP": maximum, "NO_TIME_RATE": "False" if self.ramp_var.get() else "True",
                   "SLEEP_GAP": self.gap_value.get().strip()}
        return service.validate_config({**self.config_data, **changes})

    def save_settings(self):
        if self.process:
            self.notify("请等本次运行结束后再保存设置。", True)
            return False
        try:
            changes = self.collect_settings()
            backup = self.store.save(changes)
            self.reload_data()
            self.max_value.set(str(self.config_data["MAX_STEP"]))
            # Refresh memory-only password preservation without displaying passwords.
            users = self.config_data["USER"].split("#")
            passwords = self.config_data["PWD"].split("#")
            for row in self.account_rows:
                user = row["user"].get().strip()
                if user in users:
                    row.update(original_user=user, original_password=passwords[users.index(user)])
                    row["password"].set("")
                    row["password_entry"].configure(placeholder_text="已保存，留空保留")
            self.update_overview()
            self.notify("设置已保存，原配置已备份。" if backup else "设置已保存。")
            return True
        except (OSError, ValueError) as exc:
            self.notify(str(exc), True)
            return False

    def reset_settings(self):
        self.reload_data()
        if "settings" in self.pages:
            self.pages.pop("settings").destroy()
        self.show_page("settings")
        self.notify("已从项目目录重新载入配置。")

    def reset_tokens(self):
        if self.process:
            self.notify("请等本次运行结束后再重置登录缓存。", True)
            return
        cache = self.project / "encrypted_tokens.data"
        if not cache.exists():
            self.notify("当前没有保存的登录缓存。")
            return
        try:
            backup = self.project / "backups" / ("tokens-" + service.now().strftime("%Y%m%d-%H%M%S-%f") + ".data")
            backup.parent.mkdir(parents=True, exist_ok=True)
            cache.replace(backup)
            self.notify("登录缓存已备份并重置，下次运行将重新登录。")
        except OSError as exc:
            self.notify(str(exc), True)

    def build_logs(self, frame):
        toolbar = ctk.CTkFrame(frame, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 13))
        self.label(toolbar, "最近 60 条记录", 12, MUTED).pack(side="left")
        self.button(toolbar, "刷新记录", self.refresh_logs, width=110).pack(side="right")
        self.button(toolbar, "打开日志目录", self.open_logs_folder, width=130).pack(side="right", padx=9)
        split = ctk.CTkFrame(frame, fg_color="transparent")
        split.grid(row=1, column=0, sticky="nsew")
        frame.grid_rowconfigure(1, weight=1)
        split.grid_rowconfigure(0, weight=1)
        split.grid_columnconfigure(1, weight=1)
        self.log_list = ctk.CTkScrollableFrame(split, width=214, fg_color=WHITE, border_width=1,
                                             border_color=BORDER, corner_radius=13)
        self.log_list.grid(row=0, column=0, sticky="nsew", padx=(0, 13))
        self.log_list.grid_columnconfigure(0, weight=1)
        reader = self.card(split)
        reader.grid(row=0, column=1, sticky="nsew")
        reader.grid_columnconfigure(0, weight=1)
        reader.grid_rowconfigure(1, weight=1)
        self.log_title = self.label(reader, "选择一条记录", 12, bold=True, anchor="w")
        self.log_title.grid(row=0, column=0, sticky="ew", padx=18, pady=(17, 9))
        self.log_text = ctk.CTkTextbox(reader, fg_color=WHITE, text_color=INK, wrap="word",
                                      font=ctk.CTkFont(family="Consolas", size=12), corner_radius=0)
        self.log_text.grid(row=1, column=0, sticky="nsew", padx=13, pady=(0, 14))
        self.log_text.configure(state="disabled")

    def refresh_logs(self):
        self.logs = service.log_entries(self.project, self.config_data)
        self.update_overview()
        if "logs" not in self.pages:
            return
        for child in self.log_list.winfo_children():
            child.destroy()
        for index, item in enumerate(self.logs):
            color = GREEN if item["state"] == "success" else (RED if item["state"] == "failed" else MUTED)
            btn = ctk.CTkButton(self.log_list, text=f"{item['time']}\n{item['summary']}", height=61,
                                corner_radius=8, anchor="w", fg_color=BG, hover_color=PALE,
                                text_color=color, font=self.font(11),
                                command=lambda value=item: self.select_log(value))
            btn.grid(row=index, column=0, sticky="ew", padx=5, pady=4)
        if self.logs:
            self.select_log(self.logs[0])
        else:
            self.log_title.configure(text="暂无运行记录")
            self.log_text.configure(state="normal")
            self.log_text.delete("1.0", "end")
            self.log_text.insert("1.0", "运行后，这里会显示结果和排查信息。")
            self.log_text.configure(state="disabled")

    def select_log(self, item):
        self.log_title.configure(text=item["name"])
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.insert("1.0", item["text"])
        self.log_text.configure(state="disabled")

    def open_logs_folder(self):
        logs = self.project / "logs"
        if not logs.is_dir():
            self.notify("还没有日志，运行后会自动创建。")
            return
        os.startfile(str(logs))

    def build_tasks(self, frame):
        card = self.card(frame)
        card.grid(row=0, column=0, sticky="ew")
        card.grid_columnconfigure(0, weight=1)
        self.label(card, "每日自动运行", 17, bold=True).grid(row=0, column=0, sticky="w", padx=25, pady=(22, 10))
        self.task_status = self.label(card, "正在检查…", 13, GREEN, anchor="w")
        self.task_status.grid(row=1, column=0, sticky="ew", padx=25, pady=(0, 15))
        self.label(card, "运行时间（北京时间，多个时间用逗号分隔）", 12, MUTED).grid(
            row=2, column=0, sticky="w", padx=25, pady=(0, 8))
        self.times_var = ctk.StringVar(value="08:00, 11:30, 15:00, 18:30, 21:00, 22:40")
        self.times_entry = ctk.CTkEntry(card, textvariable=self.times_var, font=self.font(16), height=46,
                                       fg_color=BG, border_color=BORDER)
        self.times_entry.grid(row=3, column=0, sticky="ew", padx=25)
        self.task_note = self.label(card, "", 12, MUTED, justify="left", anchor="w", wraplength=720)
        self.task_note.grid(row=4, column=0, sticky="ew", padx=25, pady=(13, 18))
        buttons = ctk.CTkFrame(card, fg_color="transparent")
        buttons.grid(row=5, column=0, sticky="ew", padx=25, pady=(0, 23))
        self.task_save_button = self.button(buttons, "保存自动任务", self.save_task_clicked, primary=True, width=145)
        self.task_save_button.pack(side="left")
        self.task_toggle_button = self.button(buttons, "暂停自动任务", self.toggle_task_clicked, width=135)
        self.task_toggle_button.pack(side="left", padx=10)
        self.button(buttons, "刷新状态", self.refresh_task, width=110).pack(side="right")
        hint = self.card(frame)
        hint.grid(row=1, column=0, sticky="ew", pady=17)
        self.label(hint, "运行条件", 14, bold=True).pack(anchor="w", padx=24, pady=(20, 7))
        self.label(hint, "电脑需要开机并登录 Windows；关闭软件窗口后，自动任务仍可运行。\n新建任务会在错过时间后补跑；电脑关机期间无法执行。\n保存现有任务时会保留原来的运行程序，只更新运行时间。", 12, MUTED,
                   justify="left", anchor="w").pack(anchor="w", padx=24, pady=(0, 20))
        self.button(frame, "打开系统任务计划程序", lambda: os.startfile("taskschd.msc"), width=200).grid(
            row=2, column=0, sticky="w")

    def update_task_view(self):
        self.update_overview()
        if "tasks" not in self.pages:
            return
        info = self.task
        if info.get("found"):
            self.task_status.configure(text=("●  已开启" if info.get("enabled") else "●  已暂停") + "  ·  " + info["name"])
            if not self.task_busy and info.get("times"):
                self.times_var.set(", ".join(info["times"]))
            self.task_note.configure(text="下次计划运行：" + str(info.get("next", "待定")))
        else:
            self.task_status.configure(text="暂时无法读取系统任务" if info.get("unavailable") else "尚未设置自动任务")
            self.task_note.configure(text="可打开系统任务计划程序查看；保存时会尝试连接系统任务服务。" if info.get("unavailable") else
                                     "填写时间并保存即可创建任务。请将软件保留在当前位置，供任务调用。")
        self.task_toggle_button.configure(text="暂停自动任务" if info.get("enabled") else "启用自动任务",
                                          state="normal" if info.get("found") and not self.task_busy else "disabled")
        self.task_save_button.configure(state="disabled" if self.task_busy else "normal")

    def async_task(self, action, completed_message=None):
        if self.task_busy:
            return
        self.task_busy = True
        root = self.project
        self.update_task_view()

        def job():
            try:
                action()
                self.events.put(("task", root, service.task_info(root), None, completed_message))
            except Exception as exc:
                self.events.put(("task", root, None, str(exc), None))
        threading.Thread(target=job, daemon=True).start()

    def refresh_task(self):
        self.async_task(lambda: None)

    def save_task_clicked(self):
        if self.demo:
            self.notify("离线演示模式不会修改 Windows 自动任务。")
            return
        try:
            service.validate_config(self.config_data)
            times = service.validate_times(self.times_var.get())
        except ValueError as exc:
            self.notify(str(exc), True)
            return
        root, info = self.project, dict(self.task)
        self.async_task(lambda: service.save_task(root, times, info), "自动任务已保存。")
        self.notify("正在保存自动任务…")

    def toggle_task_clicked(self):
        if self.demo:
            self.notify("离线演示模式不会修改 Windows 自动任务。")
            return
        root, info = self.project, dict(self.task)
        self.async_task(lambda: service.toggle_task(root, info), "自动任务已暂停。" if info.get("enabled") else "自动任务已启用。")

    def _drain_events(self):
        if self.closing:
            return
        try:
            while True:
                kind, root, info, error, completed_message = self.events.get_nowait()
                if kind == "task":
                    self.task_busy = False
                    if root == self.project:
                        if info is not None:
                            self.task = info
                        self.update_task_view()
                        if error:
                            self.notify(error, True)
                        elif completed_message:
                            self.notify(completed_message)
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    def start_run(self):
        if self.process:
            return
        self.reload_data()
        try:
            service.validate_config(self.config_data)
            stamp = service.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
            self.result_path = self.project / ".mimotion-desktop" / "results" / (stamp + ".json")
            command = service.app_command() + ["--worker", "--project", str(self.project), "--result", str(self.result_path)]
            if self.demo:
                command.append("--demo")
            self.cancelled = False
            self.process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL, creationflags=service.NO_WINDOW)
            self.run_started = time.monotonic()
            self.update_overview()
            self.notify("离线模拟中，不会访问平台。" if self.demo else "正在运行，可在运行记录中查看结果。")
            self.after(200, self.poll_run)
        except (OSError, ValueError) as exc:
            self.show_page("settings")
            self.notify(str(exc), True)

    def poll_run(self):
        if not self.process or self.closing:
            return
        code = self.process.poll()
        if code is None:
            if time.monotonic() - self.run_started > 1800:
                self.stop_run()
                self.notify("运行超过 30 分钟，已停止。请检查网络或账号设置。", True)
            else:
                self.after(200, self.poll_run)
            return
        result = None
        try:
            if self.result_path and self.result_path.exists():
                result = json.loads(self.result_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        self.process = None
        self.refresh_logs()
        if self.cancelled:
            self.notify("已停止本次运行。")
        elif result:
            self.notify(str(result.get("message", "运行已结束")), result.get("status") != "success")
        else:
            self.notify("运行进程已结束，但未返回结果。请查看日志或重新运行。", True)
        self.update_overview()

    def stop_run(self):
        if not self.process or self.process.poll() is not None:
            return
        self.cancelled = True
        self.process.terminate()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()
        for item in service.log_entries(self.project, self.config_data, limit=2):
            if "[正在运行]" in item["text"] and "[运行结束]" not in item["text"]:
                try:
                    with item["path"].open("a", encoding="utf-8") as target:
                        target.write("\n[已停止] 用户停止了本次桌面版任务。\n")
                except OSError:
                    pass
                break

    def show_help(self):
        box = ctk.CTkToplevel(self)
        box.title("MiMotion · 使用帮助")
        box.geometry("700x620")
        box.transient(self)
        box.configure(fg_color=BG)
        self.label(box, "从脚本，到一个顺手的界面。", 23, bold=True).pack(anchor="w", padx=30, pady=(28, 16))
        text = ("1. 首次打开会读取 E:\\mimotion，也可以切换到自己的项目目录。\n\n"
                "2. 在“账号与步数”中填写 Zepp Life 账号，设置固定步数或随机范围，\n   点击“保存设置”。已有密码留空即可保留。\n\n"
                "3. 回到运行面板点击“立即运行”。结果以平台接口返回为准，\n   微信或支付宝的显示还取决于平台绑定及同步情况。\n\n"
                "4. 自动任务需要电脑开机并登录 Windows。保存前不会自动创建任务。\n\n"
                "5. “运动轨迹”内置 sport.gyvv.top 在线工具，可画路线和导出文件，\n   导出文件保存在项目的“轨迹导出”目录；大窗口适合地图编辑。\n\n"
                "6. 设置保存在项目 .env 中，保存前自动备份；分享软件请只分享 exe，\n   请保管好自己的配置、缓存和日志文件。\n\n"
                "本软件封装自本机 mimotion 项目，沿用 Apache-2.0 许可。\n"
                "版本 " + service.VERSION + "  ·  Windows 64 位")
        self.label(box, text, 12, MUTED, justify="left", anchor="nw").pack(fill="both", expand=True, padx=30)
        self.button(box, "知道了", box.destroy, primary=True, width=110).pack(anchor="e", padx=30, pady=22)

    def close_app(self):
        if self.process and self.process.poll() is None:
            if not messagebox.askyesno("正在运行", "关闭窗口将停止本次手动运行，是否关闭？", parent=self):
                return
            self.stop_run()
        self.closing = True
        if hasattr(self, "sport_panel"):
            self.sport_panel.close()
        self.destroy()


from studio_ui import StudioInterface


class MiMotionApp(StudioInterface, BaseMiMotionApp):
    pass


if __name__ == "__main__":
    args = arguments()
    root = resolve_project(args.project)
    if args.worker or args.scheduled:
        raise SystemExit(service.run_worker(root, args.result, args.demo))
    launch_ui(root, args.demo, args.page, args.inspect_sport_report)
