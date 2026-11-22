"""
Watchdog Permanente de Sistema Operacional para os Painéis 8080, 5174, 5176 e 5178.
Monitora continuamente:
  - Backend FastAPI (http://127.0.0.1:8080/health)
  - Painel 5174 (http://127.0.0.1:5174/)
  - Painel 5176 (http://127.0.0.1:5176/)
  - Painel 5178 (http://127.0.0.1:5178/) — Gráfico Diário Manual WIN/WDO

Roda de forma 100% desacoplada do Antigravity (via pythonw.exe / Task Scheduler)
para que reinicializações do agente nunca derrubem os servidores e qualquer
travamento/queda seja restaurado automaticamente em poucos segundos.
"""

import os
import sys
import time
import socket
import subprocess
import urllib.request
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DASHBOARD_DIR = os.path.join(PROJECT_ROOT, "regime-dashboard")
LOG_FILE = os.path.join(PROJECT_ROOT, "logs", "watchdog_dashboards.log")
PID_FILE = os.path.join(PROJECT_ROOT, "logs", "watchdog_dashboards.pid")

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000


def log(msg: str) -> None:
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            creationflags=CREATE_NO_WINDOW,
            stderr=subprocess.DEVNULL,
        ).decode("latin1", errors="ignore")
        return str(pid) in out
    except Exception:
        return False


def get_listening_pids_on_port(port: int) -> list[int]:
    pids = set()
    try:
        out = subprocess.check_output(
            ["netstat", "-ano"],
            creationflags=CREATE_NO_WINDOW,
            stderr=subprocess.DEVNULL,
        ).decode("latin1", errors="ignore")
        target = f":{port}"
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[0].upper() == "TCP" and "LISTENING" in parts[3].upper():
                if parts[1].endswith(target):
                    try:
                        pid = int(parts[4])
                        if pid > 0:
                            pids.add(pid)
                    except ValueError:
                        pass
    except Exception:
        pass
    return sorted(pids)


def kill_port_processes(port: int) -> None:
    pids = get_listening_pids_on_port(port)
    for pid in pids:
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                creationflags=CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            log(f"Processo antigo na porta {port} (PID {pid}) finalizado para reinício limpo.")
        except Exception as e:
            log(f"Erro ao finalizar PID {pid} na porta {port}: {e}")


def check_http_ok(url: str, timeout: float = 5.0) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "JumbaWatchdog/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 400
    except Exception:
        return False


def check_port_open(port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except Exception:
        return False


def _utf8_env() -> dict:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def start_backend_8080() -> None:
    kill_port_processes(8080)
    time.sleep(0.5)
    py_exe = sys.executable
    if py_exe.lower().endswith("pythonw.exe"):
        cand = os.path.join(os.path.dirname(py_exe), "python.exe")
        if os.path.exists(cand):
            py_exe = cand
    out_log = open(os.path.join(PROJECT_ROOT, "logs", "server_8080.log"), "a", encoding="utf-8")
    flags = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    env = _utf8_env()
    try:
        proc = subprocess.Popen(
            [py_exe, "server.py"],
            cwd=PROJECT_ROOT,
            env=env,
            stdout=out_log,
            stderr=out_log,
            stdin=subprocess.DEVNULL,
            creationflags=flags | CREATE_BREAKAWAY_FROM_JOB,
            close_fds=True,
        )
    except Exception:
        proc = subprocess.Popen(
            [py_exe, "server.py"],
            cwd=PROJECT_ROOT,
            env=env,
            stdout=out_log,
            stderr=out_log,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
        )
    log(f"Backend 8080 iniciado (PID {proc.pid}).")


def start_vite_port(port: int) -> None:
    kill_port_processes(port)
    time.sleep(0.5)
    node_exe = r"C:\Program Files\nodejs\node.exe"
    if not os.path.exists(node_exe):
        node_exe = "node"
    vite_bin = os.path.join(DASHBOARD_DIR, "node_modules", "vite", "bin", "vite.js")
    out_log = open(os.path.join(PROJECT_ROOT, "logs", f"vite_{port}.log"), "a", encoding="utf-8")
    flags = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    cmd = [node_exe, vite_bin, "--host", "::", "--port", str(port), "--strictPort"]
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=DASHBOARD_DIR,
            stdout=out_log,
            stderr=out_log,
            stdin=subprocess.DEVNULL,
            creationflags=flags | CREATE_BREAKAWAY_FROM_JOB,
            close_fds=True,
        )
    except Exception:
        proc = subprocess.Popen(
            cmd,
            cwd=DASHBOARD_DIR,
            stdout=out_log,
            stderr=out_log,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
        )
    log(f"Vite {port} iniciado (PID {proc.pid}).")


def start_public_port(port: int, log_name: str, extra_args: list[str] | None = None) -> None:
    kill_port_processes(port)
    time.sleep(0.5)
    py_exe = sys.executable
    if py_exe.lower().endswith("pythonw.exe"):
        cand = os.path.join(os.path.dirname(py_exe), "python.exe")
        if os.path.exists(cand):
            py_exe = cand
    out_log = open(os.path.join(PROJECT_ROOT, "logs", log_name), "a", encoding="utf-8")
    flags = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    cmd = [py_exe, os.path.join(PROJECT_ROOT, "scripts", "painel_publico.py"), str(port)] + (extra_args or [])
    env = _utf8_env()
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=PROJECT_ROOT,
            env=env,
            stdout=out_log,
            stderr=out_log,
            stdin=subprocess.DEVNULL,
            creationflags=flags | CREATE_BREAKAWAY_FROM_JOB,
            close_fds=True,
        )
    except Exception:
        proc = subprocess.Popen(
            cmd,
            cwd=PROJECT_ROOT,
            env=env,
            stdout=out_log,
            stderr=out_log,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
        )
    log(f"Painel público {port} iniciado (PID {proc.pid}).")


def start_public_5199() -> None:
    start_public_port(5199, "painel_publico_5199.log")


def start_public_5198() -> None:
    start_public_port(5198, "painel_publico_5198.log", ["--mode", "5176"])


TUNNEL_TOKEN_FILE = os.path.join(PROJECT_ROOT, "config", "cloudflared_tunnel_token.txt")
SHARED_TUNNEL_FLAG = os.path.join(PROJECT_ROOT, "config", "cloudflared_shared_mfc.flag")
CF_PID_FILE = os.path.join(PROJECT_ROOT, "logs", "cloudflared_5199.pid")
CF_PID_FILE_5198 = os.path.join(PROJECT_ROOT, "logs", "cloudflared_5198.pid")


def is_windows_service_active(service_name: str) -> bool:
    try:
        out = subprocess.check_output(
            ["sc", "query", service_name],
            creationflags=CREATE_NO_WINDOW,
            stderr=subprocess.DEVNULL,
            text=True,
            errors="ignore",
        )
        return "RUNNING" in out.upper() or "START_PENDING" in out.upper()
    except Exception:
        return False


def _read_tunnel_token() -> str:
    if os.path.isfile(TUNNEL_TOKEN_FILE):
        try:
            with open(TUNNEL_TOKEN_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass
    return ""


def is_cloudflared_port_running(port: int, pid_file: str, allow_shared: bool = False) -> bool:
    if allow_shared:
        if os.path.isfile(SHARED_TUNNEL_FLAG):
            return True
        if is_windows_service_active("MagicWalls_Cloudflared"):
            return True
    if os.path.isfile(pid_file):
        try:
            with open(pid_file, "r", encoding="utf-8") as f:
                pid = int(f.read().strip())
            if is_pid_running(pid):
                return True
        except Exception:
            pass
    try:
        ps = (
            "Get-CimInstance Win32_Process -Filter \"Name='cloudflared.exe'\" | "
            f"Where-Object {{ $_.CommandLine -match '{port}|cloudflared_{port}' }} | "
            "Select-Object -ExpandProperty ProcessId"
        )
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            creationflags=CREATE_NO_WINDOW,
            stderr=subprocess.DEVNULL,
            text=True,
            errors="ignore",
            timeout=5,
        ).strip()
        return any(tok.isdigit() for tok in out.splitlines())
    except Exception:
        return False


def is_cloudflared_5199_running() -> bool:
    return is_cloudflared_port_running(5199, CF_PID_FILE, allow_shared=True)


def _named_config_covers_port(port: int) -> bool:
    cfg = os.path.join(PROJECT_ROOT, "config", "cloudflared-magicwalls.yml")
    if not os.path.isfile(cfg):
        return False
    try:
        with open(cfg, "r", encoding="utf-8") as f:
            return f"127.0.0.1:{port}" in f.read()
    except Exception:
        return False


def is_named_magicwalls_running() -> bool:
    if is_windows_service_active("MagicWalls_Cloudflared"):
        return True
    if os.path.isfile(CF_PID_FILE):
        try:
            with open(CF_PID_FILE, "r", encoding="utf-8") as f:
                pid = int(f.read().strip())
            if is_pid_running(pid):
                return True
        except Exception:
            pass
    try:
        ps = (
            "Get-CimInstance Win32_Process -Filter \"Name='cloudflared.exe'\" | "
            "Where-Object { $_.CommandLine -match 'run magicwalls' } | "
            "Select-Object -ExpandProperty ProcessId"
        )
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            creationflags=CREATE_NO_WINDOW,
            stderr=subprocess.DEVNULL,
            text=True,
            errors="ignore",
            timeout=5,
        ).strip()
        return any(tok.isdigit() for tok in out.splitlines())
    except Exception:
        return False


def is_cloudflared_5198_running() -> bool:
    if _named_config_covers_port(5198) and is_named_magicwalls_running():
        return True
    return is_cloudflared_port_running(5198, CF_PID_FILE_5198, allow_shared=False)


def start_cloudflared_tunnel(port: int, pid_file: str, log_filename: str, token: str = "", config: str = "") -> None:
    cf_exe = r"C:\Program Files (x86)\cloudflared\cloudflared.exe"
    if not os.path.exists(cf_exe):
        cf_exe = "cloudflared"
    cf_log_path = os.path.join(PROJECT_ROOT, "logs", log_filename)
    out_log = open(cf_log_path, "a", encoding="utf-8")
    flags = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    if config:
        cmd = [cf_exe, "--logfile", cf_log_path, "--config", config, "tunnel", "--no-autoupdate", "run", "magicwalls"]
    elif token:
        cmd = [cf_exe, "--logfile", cf_log_path, "tunnel", "run", "--token", token]
    else:
        cmd = [cf_exe, "--logfile", cf_log_path, "tunnel", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate"]
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=PROJECT_ROOT,
            stdout=out_log,
            stderr=out_log,
            stdin=subprocess.DEVNULL,
            creationflags=flags | CREATE_BREAKAWAY_FROM_JOB,
            close_fds=True,
        )
    except Exception:
        proc = subprocess.Popen(
            cmd,
            cwd=PROJECT_ROOT,
            stdout=out_log,
            stderr=out_log,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
        )
    try:
        with open(pid_file, "w", encoding="utf-8") as f:
            f.write(str(proc.pid))
    except Exception:
        pass
    kind = "Named Config" if config else ("Named Token" if token else f"Quick Tunnel {port}")
    log(f"Cloudflared tunnel ({kind}) iniciado (PID {proc.pid}).")


NAMED_TUNNEL_CONFIG = os.path.join(PROJECT_ROOT, "config", "cloudflared-magicwalls.yml")


def start_cloudflared_5199() -> None:
    if os.path.isfile(SHARED_TUNNEL_FLAG) or is_windows_service_active("MagicWalls_Cloudflared"):
        return
    if os.path.isfile(NAMED_TUNNEL_CONFIG):
        start_cloudflared_tunnel(5199, CF_PID_FILE, "cloudflared_5199.log", config=NAMED_TUNNEL_CONFIG)
        return
    start_cloudflared_tunnel(5199, CF_PID_FILE, "cloudflared_5199.log", _read_tunnel_token())


def start_cloudflared_5198() -> None:
    if _named_config_covers_port(5198) and is_named_magicwalls_running():
        return
    if _named_config_covers_port(5198):
        # Named ingress covers 5198; do not fall back to a quick tunnel.
        start_cloudflared_5199()
        return
    start_cloudflared_tunnel(5198, CF_PID_FILE_5198, "cloudflared_5198.log")


def acquire_single_instance_or_exit() -> None:
    os.makedirs(os.path.dirname(PID_FILE), exist_ok=True)
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r", encoding="utf-8") as f:
                old_pid = int(f.read().strip())
            if old_pid != os.getpid() and is_pid_running(old_pid):
                sys.exit(0)
        except Exception:
            pass
    with open(PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))


def run_watchdog(restart_all_on_boot: bool = False) -> None:
    acquire_single_instance_or_exit()
    log(f"Watchdog iniciado (PID {os.getpid()}, restart_all={restart_all_on_boot}).")

    if restart_all_on_boot:
        start_backend_8080()
        start_vite_port(5174)
        start_vite_port(5176)
        start_vite_port(5178)
        start_public_5199()
        start_public_5198()
        time.sleep(5.0)

    fail_counts = {8080: 0, 5174: 0, 5176: 0, 5178: 0, 5199: 0, 5198: 0}

    while True:
        try:
            # 1. Verifica Backend 8080
            if not check_port_open(8080):
                fail_counts[8080] += 2
            elif not check_http_ok("http://127.0.0.1:8080/health", timeout=6.0):
                fail_counts[8080] += 1
            else:
                fail_counts[8080] = 0

            if fail_counts[8080] >= 2:
                log("Porta 8080 sem resposta. Reiniciando server.py...")
                start_backend_8080()
                fail_counts[8080] = 0
                time.sleep(4.0)

            # 2. Verifica Frontends 5174, 5176 e 5178
            for vport in (5174, 5176, 5178):
                if not check_port_open(vport):
                    fail_counts[vport] += 2
                elif not check_http_ok(f"http://127.0.0.1:{vport}/", timeout=4.0):
                    fail_counts[vport] += 1
                else:
                    fail_counts[vport] = 0

                if fail_counts[vport] >= 2:
                    log(f"Porta {vport} sem resposta. Reiniciando Vite {vport}...")
                    start_vite_port(vport)
                    fail_counts[vport] = 0
                    time.sleep(2.0)

            # 3. Verifica Proxy Somente-Leitura 5199 (Cloudflare Tunnel) — se estiver no NSSM, não disputa a porta
            if is_windows_service_active("MagicWalls_Publico"):
                fail_counts[5199] = 0
            else:
                if not check_port_open(5199):
                    fail_counts[5199] += 2
                elif not check_http_ok("http://127.0.0.1:5199/health", timeout=4.0):
                    fail_counts[5199] += 1
                else:
                    fail_counts[5199] = 0

                if fail_counts[5199] >= 2:
                    log("Porta 5199 sem resposta. Reiniciando painel_publico.py...")
                    start_public_5199()
                    fail_counts[5199] = 0
                    time.sleep(2.0)

            # 3b. Verifica Proxy Somente-Leitura 5198 (Painel Público 5176 - Robôs Magic Walls)
            if not check_port_open(5198):
                fail_counts[5198] += 2
            elif not check_http_ok("http://127.0.0.1:5198/health", timeout=4.0):
                fail_counts[5198] += 1
            else:
                fail_counts[5198] = 0

            if fail_counts[5198] >= 2:
                log("Porta 5198 sem resposta. Reiniciando painel_publico.py (5198 --mode 5176)...")
                start_public_5198()
                fail_counts[5198] = 0
                time.sleep(2.0)

            # 4. Verifica Túneis Cloudflare (cloudflared.exe -> 5199 e 5198)
            if not is_cloudflared_5199_running():
                log("Túnel cloudflared 5199 ausente. Reiniciando cloudflared -> 5199...")
                start_cloudflared_5199()
                time.sleep(3.0)
            if not is_cloudflared_5198_running():
                log("Túnel cloudflared 5198 ausente. Reiniciando cloudflared -> 5198...")
                start_cloudflared_5198()
                time.sleep(3.0)

        except Exception as e:
            log(f"Erro no ciclo do watchdog: {e}")

        time.sleep(8.0)


if __name__ == "__main__":
    restart_flag = "--restart-all" in sys.argv
    run_watchdog(restart_all_on_boot=restart_flag)

