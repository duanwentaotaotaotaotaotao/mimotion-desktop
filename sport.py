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
        super().__init__(master, fg_color="#FFFFFF", corner_radius=0)
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
        top = ctk.CTkFrame(self, fg_color="#EDF3E8", corner_radius=9)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 9))
        top.grid_columnconfigure(0, weight=1)
        self.status_label = ctk.CTkLabel(top, text="正在打开运动轨迹…", anchor="w",
                                        text_color="#193D32", font=("Microsoft YaHei UI", 11))
        self.status_label.grid(row=0, column=0, sticky="ew", padx=13, pady=9)
        for column, (text, command) in enumerate([
            ("重新打开", self.restart), ("大窗口", self.open_large),
            ("导出目录", self.open_exports),
        ], 1):
            ctk.CTkButton(top, text=text, command=command, width=77, height=29,
                          fg_color="#DDE9D4", hover_color="#CFE1C1", text_color="#193D32",
                          font=("Microsoft YaHei UI", 11)).grid(row=0, column=column, padx=(0, 8), pady=8)
        self.surface = tk.Frame(self, background="#FFFFFF", bd=0, highlightthickness=0)
        self.surface.grid(row=1, column=0, sticky="nsew")
        self.message = tk.Label(self.surface, text="正在准备浏览器组件…", bg="#FFFFFF", fg="#748079",
                                font=("Microsoft YaHei UI", 14), justify="center")
        self.message.place(relx=.5, rely=.42, anchor="center")
        self.start_id = self.after(250, self.start)

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
            self.status_label.configure(text="正在加载 sport.gyvv.top…")
            self.message.configure(text="正在加载运动轨迹页面…\n首次打开可能需要一些时间。")
            self.last_status = {}
            self.poll()
        except (OSError, RuntimeError) as exc:
            self.status_label.configure(text="运动轨迹暂时无法打开")
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
                        self.status_label.configure(text="●  运动轨迹  ·  sport.gyvv.top  ·  在线")
                    elif state == "error":
                        self.status_label.configure(text="加载遇到问题，可重新打开或使用浏览器访问")
                        self.message.configure(text=str(status.get("message", "网站暂时无法加载")))
                    else:
                        self.status_label.configure(text="正在加载 sport.gyvv.top…")
            if self.process and self.process.poll() is not None:
                self.process = None
                self.status_label.configure(text="运动轨迹页面已关闭，点击“重新打开”继续")
                self.message.configure(text="点击上方“重新打开”加载运动轨迹。")
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
