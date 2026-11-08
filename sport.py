"""An isolated native WebView2 module for the original online route editor."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import tkinter as tk
import uuid
import webbrowser

import customtkinter as ctk

SPORT_URL = "https://sport.gyvv.top/"
BG = "#F5F4EF"
SURFACE = "#FFFEFA"
RAISED = "#ECEFE8"
TEXT = "#3E4944"
MUTED = "#818880"
ACCENT = "#7E9481"
SAGE = "#7E9481"
LAVENDER = "#B5A9C7"
ERROR = "#BA7D7A"
BORDER = "#E0E5DA"
HOST_FILES = ("MiMotion.SportHost.exe", "MiMotion.SportHost.exe.config", "Microsoft.Web.WebView2.Core.dll",
              "Microsoft.Web.WebView2.WinForms.dll", "WebView2Loader.dll", "LICENSE-WebView2.txt")


def stage_host(project: Path) -> Path:
    """Keep a running browser independent of the single-file exe extraction dir."""
    source = Path(__file__).parent / "assets" / "sport_host"
    entries = []
    fingerprint = hashlib.sha256()
    for name in HOST_FILES:
        file = source / name
        if not file.is_file():
            raise RuntimeError("运动轨迹组件不完整，请重新下载完整软件。")
        payload = file.read_bytes()
        fingerprint.update(name.encode("utf-8") + b"\0" + hashlib.sha256(payload).digest())
        entries.append((name, file, hashlib.sha256(payload).hexdigest()))
    target = project / ".mimotion-desktop" / "sport-host" / fingerprint.hexdigest()[:16]
    target.mkdir(parents=True, exist_ok=True)
    for name, original, expected_hash in entries:
        staged = target / name
        if staged.is_file() and hashlib.sha256(staged.read_bytes()).hexdigest() == expected_hash:
            continue
        temporary = target / (name + "." + uuid.uuid4().hex + ".tmp")
        try:
            shutil.copyfile(original, temporary)
            os.replace(temporary, staged)
        finally:
            temporary.unlink(missing_ok=True)
    return target / HOST_FILES[0]


def close_host(process, quit_file: Path | None, status_file: Path | None = None):
    if process is None or process.poll() is not None:
        return
    if quit_file:
        try:
            quit_file.parent.mkdir(parents=True, exist_ok=True)
            quit_file.touch()
        except OSError:
            pass
    if status_file:
        try:
            status = json.loads(status_file.read_text(encoding="utf-8-sig"))
            hwnd = int(status.get("hwnd", 0))
            if hwnd:
                user32 = ctypes.windll.user32
                user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
                owner = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(owner))
                if owner.value == process.pid:
                    user32.PostMessageW(ctypes.c_void_p(hwnd), 0x0010, 0, 0)
        except (OSError, ValueError, TypeError):
            pass
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()


class SportPanel(ctk.CTkFrame):
    """A real child browser inside the existing desktop content area."""
    def __init__(self, master, project: Path, notify, inspect_report: Path | None = None):
        super().__init__(master, fg_color=BG, corner_radius=0)
        self.project = Path(project)
        self.notify = notify
        self.inspect_report = inspect_report
        self.process = None
        self.popups = []
        self.status_file = None
        self.quit_file = None
        self.last_status = {}
        self.started_at = 0
        self.closed = False
        self.poll_id = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        top = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=8, border_width=1, border_color=BORDER)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        top.grid_columnconfigure(0, weight=1)
        self.status_label = ctk.CTkLabel(top, text="◌  正在打开路线工作台", anchor="w",
                                        text_color=MUTED, font=("Microsoft YaHei UI", 12))
        self.status_label.grid(row=0, column=0, sticky="ew", padx=17, pady=(13, 11))
        for column, (text, command) in enumerate([
            ("↻  重新连接", self.restart), ("↗  大窗口", self.open_large),
            ("导出文件", self.open_exports),
        ], 1):
            primary = column == 3
            ctk.CTkButton(top, text=text, command=command, width=96, height=34, corner_radius=7,
                          fg_color=ACCENT if primary else RAISED,
                          hover_color="#6D8471" if primary else BORDER,
                          text_color="#FFFFFF" if primary else TEXT,
                          border_width=0 if primary else 1, border_color=BORDER,
                          font=("Microsoft YaHei UI", 11, "bold" if primary else "normal")).grid(row=0, column=column, padx=(0, 10), pady=11)
        self.progress = ctk.CTkProgressBar(top, height=2, fg_color=SURFACE, progress_color=ACCENT,
                                          mode="indeterminate", corner_radius=0)
        self.progress.grid(row=1, column=0, columnspan=4, sticky="ew", padx=14, pady=(0, 2))
        self.progress.start()
        self.surface = tk.Frame(self, background=BG, bd=0, highlightthickness=0)
        self.surface.grid(row=1, column=0, sticky="nsew")
        self.message = tk.Label(self.surface, text="正在打开路线工作台\n\n地图载入后，可直接绘制、编辑与导出。", bg=BG, fg=MUTED,
                                font=("Microsoft YaHei UI", 14), justify="center")
        self.message.place(relx=.5, rely=.42, anchor="center")
        self.start_id = self.after(250, self.start)

    def _loading(self):
        self.progress.stop()
        self.progress.configure(mode="indeterminate", progress_color=ACCENT)
        self.progress.start()

    def _settled(self, value=1, color=SAGE):
        self.progress.stop()
        self.progress.configure(mode="determinate", progress_color=color)
        self.progress.set(value)

    def start(self):
        self.start_id = None
        if self.closed or (self.process and self.process.poll() is None):
            return
        if self.surface.winfo_width() < 100 or self.surface.winfo_height() < 100:
            self.start_id = self.after(200, self.start)
            return
        try:
            executable = stage_host(self.project)
            sessions = self.project / ".mimotion-desktop" / "sport-sessions"
            sessions.mkdir(parents=True, exist_ok=True)
            session = uuid.uuid4().hex
            self.status_file = sessions / (session + ".json")
            self.quit_file = sessions / (session + ".quit")
            args = [str(executable), "--parent", str(self.surface.winfo_id()), "--project", str(self.project),
                    "--status-file", str(self.status_file), "--quit-file", str(self.quit_file)]
            if self.inspect_report:
                args += ["--inspect-report", str(self.inspect_report)]
            self.process = subprocess.Popen(args, cwd=str(executable.parent), stdin=subprocess.DEVNULL,
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.started_at = time.monotonic()
            self.status_label.configure(text="◌  正在连接 sport.gyvv.top", text_color=MUTED)
            self._loading()
            self.message.configure(text="正在打开路线工作台\n\n地图载入后，可直接绘制、编辑与导出。")
            self.last_status = {}
            self.poll()
        except (OSError, RuntimeError) as exc:
            self._settled(0, ERROR)
            self.status_label.configure(text="●  暂时无法打开", text_color=ERROR)
            self.message.configure(text=str(exc) + "\n可点击“重新打开”重试。")
            self.notify(str(exc), True)

    def poll(self):
        if self.closed:
            return
        try:
            if self.status_file and self.status_file.is_file():
                status = json.loads(self.status_file.read_text(encoding="utf-8-sig"))
                if status != self.last_status:
                    self.last_status = status
                    state = status.get("state")
                    if state == "ready":
                        self._settled()
                        self.status_label.configure(text="●  路线工作台已就绪  ·  sport.gyvv.top", text_color=SAGE)
                    elif state == "error":
                        self._settled(0, ERROR)
                        self.status_label.configure(text="●  连接遇到问题，点击重新连接", text_color=ERROR)
                        self.message.configure(text=str(status.get("message", "网站暂时无法加载")))
                    else:
                        self._loading()
                        self.status_label.configure(text="◌  正在加载地图与编辑器", text_color=MUTED)
            if self.process and self.process.poll() is not None:
                self.process = None
                self._settled(0, MUTED)
                self.status_label.configure(text="○  工作台已关闭", text_color=MUTED)
                self.message.configure(text="路线工作台已关闭\n\n点击上方“重新连接”继续编辑。")
                return
        except (OSError, ValueError, TypeError):
            pass
        self.poll_id = self.after(350, self.poll)

    def restart(self):
        if self.start_id:
            self.after_cancel(self.start_id)
            self.start_id = None
        if self.poll_id:
            self.after_cancel(self.poll_id)
            self.poll_id = None
        close_host(self.process, self.quit_file, self.status_file)
        self.process = None
        self.start()

    def open_large(self):
        try:
            executable = stage_host(self.project)
            sessions = self.project / ".mimotion-desktop" / "sport-sessions"
            sessions.mkdir(parents=True, exist_ok=True)
            name = uuid.uuid4().hex
            quit_file = sessions / (name + ".quit")
            status_file = sessions / (name + ".json")
            process = subprocess.Popen([str(executable), "--project", str(self.project),
                                        "--status-file", str(status_file), "--quit-file", str(quit_file)],
                                       cwd=str(executable.parent), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.popups.append((process, quit_file, status_file))
        except (OSError, RuntimeError) as exc:
            self.notify(str(exc), True)

    def open_exports(self):
        try:
            destination = self.last_status.get("export_dir")
            if not destination:
                preference_file = self.project / ".mimotion-desktop" / "sport-settings.json"
                if preference_file.is_file():
                    destination = json.loads(preference_file.read_text(encoding="utf-8-sig")).get("export_dir")
            folder = Path(destination) if destination else self.project / "轨迹导出"
            folder.mkdir(parents=True, exist_ok=True)
            os.startfile(str(folder))
        except (OSError, ValueError, TypeError) as exc:
            self.notify(str(exc), True)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.progress.stop()
        if self.start_id:
            self.after_cancel(self.start_id)
            self.start_id = None
        if self.poll_id:
            self.after_cancel(self.poll_id)
        close_host(self.process, self.quit_file, self.status_file)
        self.process = None
        for process, quit_file, status_file in self.popups:
            close_host(process, quit_file, status_file)
        self.popups.clear()

    def destroy(self):
        self.close()
        super().destroy()
