"""
Watchdog Permanente de Sistema Operacional para os Painéis 8080, 5174 e 5176.
Monitora continuamente:
  - Backend FastAPI (http://127.0.0.1:8080/health)
  - Painel 5174 (http://127.0.0.1:5174/)
  - Painel 5176 (http://127.0.0.1:5176/)

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
    try:
        proc = subprocess.Popen(
            [py_exe, "server.py"],
            cwd=PROJECT_ROOT,
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
    cmd = [node_exe, vite_bin, "--host", "0.0.0.0", "--port", str(port), "--strictPort"]
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
        time.sleep(5.0)

    fail_counts = {8080: 0, 5174: 0, 5176: 0}

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

            # 2. Verifica Frontends 5174 e 5176
            for vport in (5174, 5176):
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

        except Exception as e:
            log(f"Erro no ciclo do watchdog: {e}")

        time.sleep(8.0)


if __name__ == "__main__":
    restart_flag = "--restart-all" in sys.argv
    run_watchdog(restart_all_on_boot=restart_flag)

