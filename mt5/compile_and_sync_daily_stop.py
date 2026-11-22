"""Compila Jumba_Portfolio_Live_Monitor.mq5 e todos os EAs Jumba (com Jumba_SafetyGuard.mqh,
Jumba_GEX_NWE_Core.mqh e Jumba_WDO_GEX_NWE_Core.mqh atualizados) no terminal primário B3,
verifica 0 erros no log UTF-16 do MetaEditor, atualiza o repositório e sincroniza
APENAS para terminais MT5 que já possuem MQL5/Experts/Jumba_GEX_NWE (sem tocar em terminais Forex).
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
MT5_DIR = ROOT_DIR / "mt5"
INCLUDE_DIR = MT5_DIR / "Include"
EXPERTS_DIR = MT5_DIR / "Experts"
SUB_EXPERTS_DIR = EXPERTS_DIR / "Jumba_GEX_NWE"

METAEDITOR_CANDIDATES = [
    r"C:\Program Files\MetaTrader 5\metaeditor64.exe",
    r"C:\Program Files\MetaTrader 5 Terminal\metaeditor64.exe",
    r"C:\Program Files\MetaTrader 5btg\metaeditor64.exe",
]
PRIMARY_TERMINAL_HASH = "D0E8209F77C8CF37AD8BF550E51FF075"


def find_metaeditor() -> str:
    for cand in METAEDITOR_CANDIDATES:
        if os.path.isfile(cand):
            return cand
    raise FileNotFoundError("metaeditor64.exe não encontrado em nenhum caminho padrão.")


def _read_compile_log(log_path: Path) -> str:
    if not log_path.exists():
        return ""
    raw = log_path.read_bytes()
    for enc in ("utf-16", "utf-8-sig", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _assert_zero_errors(log_txt: str, ea_name: str) -> None:
    m = re.search(r"Result:\s*(\d+)\s+errors?,\s*(\d+)\s+warnings?", log_txt, flags=re.IGNORECASE)
    if not m:
        m = re.search(r"(\d+)\s+error\(s\),\s*(\d+)\s+warning\(s\)", log_txt, flags=re.IGNORECASE)
    if not m:
        raise RuntimeError(f"Log de compilação inválido para {ea_name}:\n{log_txt}")
    errors = int(m.group(1))
    if errors > 0:
        raise RuntimeError(f"Falha ao compilar {ea_name} ({errors} erro(s)):\n{log_txt}")


def compile_and_sync() -> None:
    metaeditor = find_metaeditor()

    # 0. Espelhar Jumba_Portfolio_Live_Monitor.mq5 em Experts/Jumba_GEX_NWE/
    mon_src = EXPERTS_DIR / "Jumba_Portfolio_Live_Monitor.mq5"
    mon_sub = SUB_EXPERTS_DIR / "Jumba_Portfolio_Live_Monitor.mq5"
    shutil.copy2(mon_src, mon_sub)

    appdata = Path(os.environ.get("APPDATA", ""))
    term_base = appdata / "MetaQuotes" / "Terminal"
    term_dirs = [Path(d) for d in glob.glob(str(term_base / "*")) if (Path(d) / "MQL5").is_dir()]
    if not term_dirs:
        raise RuntimeError(f"Nenhum diretório MT5 encontrado em {term_base}")

    primary_dir = next((td for td in term_dirs if PRIMARY_TERMINAL_HASH in td.name), term_dirs[0])
    primary_mql5 = primary_dir / "MQL5"
    print(f"MetaEditor : {metaeditor}")
    print(f"Primary MT5: {primary_dir.name}")

    # 1. Copiar .mqh atualizados para MQL5/Include do terminal primário
    inc_dst = primary_mql5 / "Include"
    inc_dst.mkdir(parents=True, exist_ok=True)
    for mqh in sorted(INCLUDE_DIR.glob("Jumba_*.mqh")):
        shutil.copy2(mqh, inc_dst / mqh.name)

    # 2. Lista de EAs Jumba para compilar
    ea_paths = sorted(
        list(EXPERTS_DIR.glob("Jumba_EST*.mq5"))
        + list(EXPERTS_DIR.glob("Jumba_WDO*.mq5"))
        + [
            EXPERTS_DIR / "Jumba_GEX_NWE_Portfolio_Master.mq5",
            EXPERTS_DIR / "Jumba_Portfolio_Live_Monitor.mq5",
        ]
    )
    # Remover duplicata se Jumba_WDO_GEX_NWE_Portfolio_Master veio no glob
    seen = set()
    unique_eas: list[Path] = []
    for p in ea_paths:
        if p.exists() and p.name not in seen:
            seen.add(p.name)
            unique_eas.append(p)

    compiled_ex5s: list[Path] = []
    dst_exp_dir = primary_mql5 / "Experts"
    dst_sub_dir = dst_exp_dir / "Jumba_GEX_NWE"
    dst_sub_dir.mkdir(parents=True, exist_ok=True)

    for src_mq5 in unique_eas:
        dst_mq5 = dst_exp_dir / src_mq5.name
        shutil.copy2(src_mq5, dst_mq5)
        log_fp = dst_exp_dir / f"{src_mq5.name}.log"
        if log_fp.exists():
            log_fp.unlink()

        subprocess.run([metaeditor, f"/compile:{dst_mq5}", f"/log:{log_fp}"], check=False)
        log_txt = _read_compile_log(log_fp)
        _assert_zero_errors(log_txt, src_mq5.name)

        ex5_fp = dst_mq5.with_suffix(".ex5")
        if not ex5_fp.is_file():
            raise RuntimeError(f".ex5 não gerado para {src_mq5.name}")

        # Copiar .ex5 de volta para mt5/Experts/ e mt5/Experts/Jumba_GEX_NWE/
        repo_ex5 = EXPERTS_DIR / ex5_fp.name
        repo_sub_ex5 = SUB_EXPERTS_DIR / ex5_fp.name
        shutil.copy2(ex5_fp, repo_ex5)
        shutil.copy2(ex5_fp, repo_sub_ex5)
        shutil.copy2(src_mq5, SUB_EXPERTS_DIR / src_mq5.name)
        compiled_ex5s.append(repo_ex5)
        print(f"  [OK 0 erros] {ex5_fp.name}")

    # 3. Sincronizar APENAS para terminais que já possuem MQL5/Experts/Jumba_GEX_NWE (nunca Forex)
    b3_terminals = [td for td in term_dirs if (td / "MQL5" / "Experts" / "Jumba_GEX_NWE").is_dir()]
    print(f"\nSincronizando {len(compiled_ex5s)} EAs + headers para {len(b3_terminals)} terminal(is) B3 Jumba:")
    for td in b3_terminals:
        mql5_d = td / "MQL5"
        t_inc = mql5_d / "Include"
        t_exp = mql5_d / "Experts"
        t_sub = t_exp / "Jumba_GEX_NWE"
        t_inc.mkdir(parents=True, exist_ok=True)
        t_sub.mkdir(parents=True, exist_ok=True)

        for mqh in sorted(INCLUDE_DIR.glob("Jumba_*.mqh")):
            shutil.copy2(mqh, t_inc / mqh.name)
        for src_mq5 in unique_eas:
            shutil.copy2(src_mq5, t_exp / src_mq5.name)
            shutil.copy2(src_mq5, t_sub / src_mq5.name)
        for ex5_fp in compiled_ex5s:
            shutil.copy2(ex5_fp, t_exp / ex5_fp.name)
            shutil.copy2(ex5_fp, t_sub / ex5_fp.name)

        orig = td / "origin.txt"
        orig_txt = ""
        if orig.exists():
            orig_txt = orig.read_bytes().decode("utf-16", errors="ignore").strip()
        print(f"  -> {td.name} ({orig_txt})")

    print(f"\n[SUCESSO] {len(compiled_ex5s)} EAs compilados com 0 erros e sincronizados nos terminais B3!")


if __name__ == "__main__":
    compile_and_sync()
