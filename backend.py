"""Local configuration, isolated execution and Windows task integration."""
from __future__ import annotations

import base64
import contextlib
import ctypes
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import dotenv_values

VERSION = "1.2.0"
BJ = timezone(timedelta(hours=8))
DEFAULTS = {"USER": "", "PWD": "", "MIN_STEP": "18000", "MAX_STEP": "25000",
            "NO_TIME_RATE": "True", "SLEEP_GAP": "5", "USE_CONCURRENT": "False"}
EDITABLE = set(DEFAULTS)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def now() -> datetime:
    return datetime.now(BJ)


def atomic_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def mask_account(value: str) -> str:
    if "@" in value:
        local, domain = value.rsplit("@", 1)
        return local[:2] + "***@" + domain
    if len(value) < 7:
        return value[:1] + "***" + value[-1:]
    return value[:3] + "****" + value[-4:]


def redact(text: str, config: dict | None = None) -> str:
    """Scrub original engine diagnostics before displaying or saving them."""
    config = config or {}
    secrets = []
    for key, value in config.items():
        if any(part in key.upper() for part in ("PWD", "PASSWORD", "TOKEN", "KEY", "CHAT_ID")) and value:
            secrets.append(str(value))
            if key.upper() in ("PWD", "PASSWORD"):
                secrets.extend(str(value).split("#"))
    for value in sorted(set(secrets), key=len, reverse=True):
        if value:
            text = text.replace(value, "[已隐藏]")
    # Include URL parameters and JSON diagnostic output from the legacy helper.
    text = re.sub(
        r'''(?i)(["']?(?:access_token|app_token|login_token|refresh_token|apptoken|password|pwd|aes_key)["']?\s*[:=]\s*)(["']?)([^\s,"'&}\]]+)''',
        r"\1\2[已隐藏]", text,
    )
    for user in sorted(str(config.get("USER", "")).split("#"), key=len, reverse=True):
        if user:
            text = text.replace(user, mask_account(user))
    return text


def parse_int(value, name: str, lower: int, upper: int) -> int:
    if isinstance(value, bool) or not re.fullmatch(r"\d+", str(value)):
        raise ValueError(f"{name}需要填写整数。")
    result = int(value)
    if not lower <= result <= upper:
        raise ValueError(f"{name}需要在 {lower:,} 到 {upper:,} 之间。")
    return result


def validate_config(config: dict) -> dict:
    result = {**DEFAULTS, **config}
    users = str(result["USER"]).split("#")
    passwords = str(result["PWD"]).split("#")
    if len(users) != len(passwords) or not all(users) or not all(passwords):
        raise ValueError("请为每个账号填写对应的密码。")
    if len(users) > 50:
        raise ValueError("一次最多配置 50 个账号。")
    if len(set(users)) != len(users):
        raise ValueError("同一个账号只需要添加一次，请移除重复账号。")
    for user in users:
        if not re.fullmatch(r"(?:\+86)?\d{11}|[^\s@#]+@[^\s@#]+\.[^\s@#]+", user):
            raise ValueError("账号需要填写手机号或邮箱。")
    if any("\n" in item or "\r" in item or "\x00" in item for item in users + passwords):
        raise ValueError("账号和密码不能包含换行或空字符。")
    minimum = parse_int(result["MIN_STEP"], "最小步数", 0, 999999)
    maximum = parse_int(result["MAX_STEP"], "最大步数", 0, 999999)
    if maximum < minimum:
        raise ValueError("最大步数不能小于最小步数。")
    try:
        gap = float(result["SLEEP_GAP"])
    except (TypeError, ValueError):
        raise ValueError("账号运行间隔需要填写 0 到 300 之间的秒数。") from None
    if not 0 <= gap <= 300:
        raise ValueError("账号运行间隔需要填写 0 到 300 之间的秒数。")
    result.update(MIN_STEP=str(minimum), MAX_STEP=str(maximum), SLEEP_GAP=str(gap))
    return result


def quote_env(value: str) -> str:
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


class ConfigStore:
    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()
        self.path = self.root / ".env"
        self.stamp: str | None = None

    def load(self) -> dict:
        raw = self.path.read_bytes() if self.path.exists() else b""
        self.stamp = hashlib.sha256(raw).hexdigest()
        values = {key: value for key, value in dotenv_values(
            stream=io.StringIO(raw.decode("utf-8-sig")), interpolate=False).items() if value is not None}
        config = {**DEFAULTS, **values}
        if values.get("CONFIG"):
            try:
                full = json.loads(values["CONFIG"])
                if not isinstance(full, dict):
                    raise ValueError()
                config.update({str(k): str(v) for k, v in full.items()})
            except (ValueError, TypeError):
                raise ValueError("现有 .env 中的 CONFIG 不是有效的 JSON 对象，请先修正。") from None
        return config

    def save(self, changes: dict) -> Path | None:
        raw = self.path.read_bytes() if self.path.exists() else b""
        if self.stamp is not None and hashlib.sha256(raw).hexdigest() != self.stamp:
            raise ValueError("配置文件刚被其他程序修改，请点击“重新载入”后再保存。")
        original = self.load()
        config = validate_config({**original, **changes})
        updates = {key: config[key] for key in EDITABLE}
        if original.get("CONFIG"):
            full = json.loads(original["CONFIG"])
            full.update(updates)
            updates["CONFIG"] = json.dumps(full, ensure_ascii=False)
        if not original.get("AES_KEY"):
            updates["AES_KEY"] = uuid.uuid4().hex[:16]
        lines = raw.decode("utf-8-sig").splitlines()
        used = set()
        output = []
        for line in lines:
            match = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z_0-9]*)\s*=", line)
            key = match.group(1) if match else None
            if key in updates:
                # Keep a single effective definition for each edited field.
                if key not in used:
                    output.append(f"{key}={quote_env(updates[key])}")
                    used.add(key)
            else:
                output.append(line)
        if not lines:
            output.extend(["# MiMotion 桌面版配置", "# 此文件包含账号信息，请妥善保管。"])
        output.extend(f"{key}={quote_env(value)}" for key, value in updates.items() if key not in used)
        self.root.mkdir(parents=True, exist_ok=True)
        backup = None
        if raw:
            backup = self.root / "backups" / ("settings-" + now().strftime("%Y%m%d-%H%M%S-%f") + ".env")
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(raw)
        tmp = self.path.with_name(".env." + uuid.uuid4().hex + ".tmp")
        try:
            tmp.write_text("\n".join(output) + "\n", encoding="utf-8")
            os.replace(tmp, self.path)
        finally:
            tmp.unlink(missing_ok=True)
        self.load()
        return backup


def log_entries(root: Path, config: dict, limit=60) -> list[dict]:
    logs = root / "logs"
    if not logs.is_dir():
        return []
    paths = sorted(logs.glob("run-*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    items = []
    for path in paths:
        try:
            with path.open("rb") as source:
                size = path.stat().st_size
                if size > 90000:
                    source.seek(size - 90000)
                text = source.read().decode("utf-8-sig", errors="replace")
            summary = re.search(r"执行账号总数\s*(\d+)[，,]\s*成功[：:]\s*(\d+)[，,]\s*失败[：:]\s*(\d+)", text)
            if "[已停止]" in text:
                state, desc = "stopped", "已停止"
            elif "[正在运行]" in text and not summary and "[运行结束]" not in text:
                state, desc = "unknown", "未完成"
            elif summary:
                _, succeeded, failed = map(int, summary.groups())
                state = "success" if failed == 0 else "failed"
                desc = f"成功 {succeeded} / 失败 {failed}"
            elif "[执行失败]" in text or "Traceback" in text or "登录失败" in text or "登陆失败" in text:
                state, desc = "failed", "运行失败"
            else:
                state, desc = "unknown", "查看详情"
            items.append({"name": path.name, "path": path, "state": state, "summary": desc,
                          "time": datetime.fromtimestamp(path.stat().st_mtime, BJ).strftime("%m-%d %H:%M:%S"),
                          "text": redact(text, config)})
        except OSError:
            continue
    return items


class SafeLog(io.TextIOBase):
    def __init__(self, target, config):
        self.target = target
        self.config = config
        self.pending = ""
        self.lock = threading.RLock()

    @property
    def encoding(self):
        return "utf-8"

    def write(self, value):
        with self.lock:
            self.pending += value
            while "\n" in self.pending:
                line, self.pending = self.pending.split("\n", 1)
                self.target.write(redact(line, self.config) + "\n")
                self.target.flush()
        return len(value)

    def flush(self):
        with self.lock:
            if self.target.closed:
                self.pending = ""
                return
            if self.pending:
                self.target.write(redact(self.pending, self.config))
                self.pending = ""
            self.target.flush()


@contextlib.contextmanager
def project_lock(root: Path):
    import msvcrt
    folder = root / ".mimotion-desktop"
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "run.lock").open("a+b") as lock:
        if os.fstat(lock.fileno()).st_size == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise RuntimeError("这个项目已有一个桌面版任务在运行。") from None
        try:
            yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def run_engine(root: Path, config: dict) -> list[dict]:
    # All network calls happen only in this explicitly launched worker.
    import requests
    original_request = requests.sessions.Session.request

    def timed_request(session, method, url, **kwargs):
        kwargs.setdefault("timeout", (10, 25))
        return original_request(session, method, url, **kwargs)

    requests.sessions.Session.request = timed_request
    import engine
    import util.push_util as push_util
    engine.config = config
    engine.time_bj = engine.get_beijing_time()
    key = str(config.get("AES_KEY", "")).encode("utf-8")
    engine.encrypt_support = len(key) == 16
    engine.aes_key = key
    engine.user_tokens = engine.prepare_user_tokens() if engine.encrypt_support else {}
    engine.users, engine.passwords = config["USER"], config["PWD"]
    engine.min_step, engine.max_step = engine.get_min_max_by_time()
    engine.sleep_seconds = float(config["SLEEP_GAP"])
    engine.use_concurrent = str(config.get("USE_CONCURRENT", "False")).lower() == "true"
    engine.push_config = push_util.PushConfig(
        push_plus_token=config.get("PUSH_PLUS_TOKEN"), push_plus_hour=config.get("PUSH_PLUS_HOUR"),
        push_plus_max=int(config.get("PUSH_PLUS_MAX") or 30),
        push_wechat_webhook_key=config.get("PUSH_WECHAT_WEBHOOK_KEY"),
        telegram_bot_token=config.get("TELEGRAM_BOT_TOKEN"), telegram_chat_id=config.get("TELEGRAM_CHAT_ID"))
    results = []
    original_run = engine.run_single_account

    def collect(*args):
        result = original_run(*args)
        results.append({"user": mask_account(str(result["user"])), "success": bool(result["success"]),
                        "msg": redact(str(result["msg"]), config)})
        return result

    engine.run_single_account = collect
    try:
        engine.execute()
    finally:
        engine.run_single_account = original_run
        requests.sessions.Session.request = original_request
    return results


def run_worker(root: Path, result_path: Path | None = None, demo=False) -> int:
    root = root.resolve()
    config = {}
    result = {"status": "failed", "started": now().isoformat(), "results": []}
    log_path = None
    try:
        with project_lock(root):
            config = validate_config(ConfigStore(root).load())
            logs = root / "logs"
            logs.mkdir(parents=True, exist_ok=True)
            log_path = logs / ("run-" + now().strftime("%Y%m%d-%H%M%S-%f") + ".log")
            result["log"] = log_path.name
            with log_path.open("w", encoding="utf-8", buffering=1) as target:
                safe = SafeLog(target, config)
                with contextlib.redirect_stdout(safe), contextlib.redirect_stderr(safe):
                    print(f"==== move {now():%Y-%m-%d %H:%M:%S} ====")
                    print("[正在运行]" + (" 本次为离线模拟，不访问平台。" if demo else ""))
                    old_cwd = Path.cwd()
                    try:
                        os.chdir(root)
                        if demo:
                            # Exercise the actual bundled engine and native crypto libraries,
                            # without opening a network connection.
                            import engine
                            import requests
                            from util.aes_help import encrypt_data, decrypt_data
                            check_key = b"local-check-key!"
                            assert decrypt_data(encrypt_data(b"MiMotion", check_key), check_key) == b"MiMotion"
                            assert Path(requests.certs.where()).is_file()
                            assert engine.get_beijing_time().tzinfo is not None
                            print("运行环境检查通过（核心、加密、时区与证书）。")
                            print("正在检查账号配置…")
                            time.sleep(0.45)
                            rows = [{"user": mask_account(user), "success": True,
                                     "msg": f"离线模拟完成，目标步数 {config['MAX_STEP']}"}
                                    for user in config["USER"].split("#")]
                            print(f"执行账号总数{len(rows)}，成功：{len(rows)}，失败：0")
                        else:
                            rows = run_engine(root, config)
                        result["results"] = rows
                        result["status"] = "success" if rows and all(row["success"] for row in rows) else "failed"
                        result["message"] = "离线模拟已完成" if demo else ("运行完成" if result["status"] == "success" else "部分或全部账号运行失败")
                    except Exception as exc:
                        result["message"] = redact(str(exc), config)
                        print("[执行失败] " + result["message"])
                    finally:
                        os.chdir(old_cwd)
                        print("[运行结束]")
                        safe.flush()
    except Exception as exc:
        result["message"] = redact(str(exc), config)
    result["finished"] = now().isoformat()
    if result_path is not None:
        atomic_json(result_path, result)
    return 0 if result["status"] == "success" else 1


def app_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, str(Path(__file__).with_name("app.py"))]


def powershell(script: str, timeout=20) -> str:
    preamble = "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; $ErrorActionPreference='Stop'; "
    encoded = base64.b64encode((preamble + script).encode("utf-16-le")).decode("ascii")
    exe = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    completed = subprocess.run([str(exe), "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                               capture_output=True, encoding="utf-8", errors="replace", timeout=timeout,
                               creationflags=NO_WINDOW)
    if completed.returncode:
        raise RuntimeError("无法访问任务计划程序。请使用“打开系统任务计划程序”检查当前用户权限。")
    return completed.stdout.strip().lstrip("\ufeff")


def ps_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def own_task_name(root: Path) -> str:
    return "MiMotion-Desktop-" + hashlib.sha256(str(root.resolve()).lower().encode()).hexdigest()[:10]


def task_info(root: Path) -> dict:
    script = r'''
    $names=@(__OWN__, 'mimotion-Steps'); $found=$null;
    foreach($name in $names) {
        $task=Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue;
        if($task) {
            $actionText=($task.Actions|ForEach-Object{$_.Execute+' '+$_.Arguments}) -join ' ';
            if($actionText.IndexOf(__ROOT__,[StringComparison]::OrdinalIgnoreCase) -ge 0) {$found=$task; break}
        }
    }
    if(-not $found) { @{found=$false}|ConvertTo-Json -Compress; exit 0 }
    $info=$found|Get-ScheduledTaskInfo;
    @{found=$true; name=$found.TaskName; enabled=[bool]$found.Settings.Enabled;
      state=[string]$found.State; times=@($found.Triggers|ForEach-Object{if($_.StartBoundary){([datetime]$_.StartBoundary).ToString('HH:mm')}});
      next=$info.NextRunTime.ToString('yyyy-MM-dd HH:mm');last_result=$info.LastTaskResult} | ConvertTo-Json -Compress
    '''.replace("__OWN__", ps_quote(own_task_name(root))).replace("__ROOT__", ps_quote(str(root.resolve())))
    try:
        return json.loads(powershell(script))
    except (RuntimeError, ValueError, subprocess.TimeoutExpired):
        return {"found": False, "unavailable": True}


def validate_times(value: str) -> list[str]:
    times = re.split(r"[,，;；\s]+", value.strip())
    if not times or any(not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", item) for item in times):
        raise ValueError("请输入 24 小时时间，例如 08:00, 18:30；多个时间用逗号分隔。")
    result = sorted(set(times))
    if len(result) > 24:
        raise ValueError("每天最多设置 24 个运行时间。")
    return result


def save_task(root: Path, times: list[str], existing: dict | None = None):
    times = validate_times(",".join(times))
    existing = existing or {}
    quoted_times = ",".join(ps_quote(item) for item in times)
    common = f"$triggers=@({quoted_times})|ForEach-Object{{New-ScheduledTaskTrigger -Daily -At $_}}; "
    if existing.get("found"):
        name = str(existing["name"])
        if name not in (own_task_name(root), "mimotion-Steps"):
            raise ValueError("任务名称不属于此项目。")
        script = common + f"""
        $task=Get-ScheduledTask -TaskName {ps_quote(name)};
        $actions=($task.Actions|ForEach-Object{{$_.Execute+' '+$_.Arguments}}) -join ' ';
        if($actions.IndexOf({ps_quote(str(root.resolve()))},[StringComparison]::OrdinalIgnoreCase) -lt 0) {{throw 'Project mismatch'}};
        Set-ScheduledTask -TaskName {ps_quote(name)} -Trigger $triggers | Out-Null;
        """
    else:
        command = app_command()
        arguments = subprocess.list2cmdline(command[1:] + ["--scheduled", "--project", str(root.resolve())])
        script = common + f"""
        $action=New-ScheduledTaskAction -Execute {ps_quote(command[0])} -Argument {ps_quote(arguments)} -WorkingDirectory {ps_quote(str(root.resolve()))};
        $settings=New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew;
        $who=[System.Security.Principal.WindowsIdentity]::GetCurrent().Name;
        $principal=New-ScheduledTaskPrincipal -UserId $who -LogonType Interactive -RunLevel Limited;
        Register-ScheduledTask -TaskName {ps_quote(own_task_name(root))} -Action $action -Trigger $triggers -Settings $settings -Principal $principal -Force | Out-Null;
        """
    powershell(script)


def toggle_task(root: Path, info: dict):
    name = info.get("name")
    if name not in (own_task_name(root), "mimotion-Steps"):
        raise ValueError("未找到此项目的自动任务。")
    action = "Disable" if info.get("enabled") else "Enable"
    powershell(f"{action}-ScheduledTask -TaskName {ps_quote(name)} | Out-Null")


def default_project() -> Path:
    existing = Path(r"E:\mimotion")
    if existing.is_dir() and (existing / ".env").is_file():
        return existing
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    return base / "data"
