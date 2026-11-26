"""
Baixa e consolida o catálogo oficial B3 de opções de IBOV para 2026
(`InstrumentsConsolidatedFile`), indexado por ISIN.

Uso: python -m research.gex_audit_bt.fetch_b3_ibov_catalog
"""
from __future__ import annotations

import csv
import glob
import io
import os
import re
import time
from collections import defaultdict

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(ROOT, "gex", "data")
OUT_DIR = os.path.join(ROOT, "research", "gex_audit_bt")
OUT_CSV = os.path.join(OUT_DIR, "b3_ibov_catalog_2026.csv")

START_DATE = "2026-01-02"
END_DATE = "2026-11-11"


def list_oi_files() -> list[tuple[str, str]]:
    """Lista [(YYYY-MM-DD, filepath), ...] ordenados para o intervalo do BT."""
    files = glob.glob(os.path.join(DATA_DIR, "Posições em aberto-*.csv"))
    out = []
    for f in files:
        m = re.search(r"(\d{2})-(\d{2})-(\d{4})", os.path.basename(f))
        if not m:
            continue
        d, mo, y = m.groups()
        iso = f"{y}-{mo}-{d}"
        if START_DATE <= iso <= END_DATE:
            out.append((iso, f))
    out.sort(key=lambda x: x[0])
    return out


def pick_bimonthly_dates(dated_files: list[tuple[str, str]]) -> list[str]:
    """Seleciona 2 datas por mês: 1º pregão do mês e pregão mais próximo do dia 15."""
    by_ym: dict[str, list[str]] = defaultdict(list)
    for iso, _ in dated_files:
        by_ym[iso[:7]].append(iso)

    picks = []
    for ym in sorted(by_ym):
        ds = sorted(by_ym[ym])
        picks.append(ds[0])
        mid = min(ds, key=lambda s: abs(int(s[8:10]) - 15))
        if mid != ds[0]:
            picks.append(mid)
    return picks


def download_instruments_for_date(session: requests.Session, date_iso: str) -> list[dict]:
    """Baixa InstrumentsConsolidatedFile de `date_iso` e extrai opções IBOV."""
    url_req = (
        "https://arquivos.b3.com.br/api/download/requestname"
        f"?fileName=InstrumentsConsolidatedFile&date={date_iso}"
    )
    tok = None
    for attempt in range(3):
        try:
            r = session.get(url_req, timeout=20)
            if r.status_code == 200:
                js = r.json()
                tok = js.get("token")
                if tok:
                    break
        except Exception:
            pass
        time.sleep(1.5)
    if not tok:
        return []

    url_dl = f"https://arquivos.b3.com.br/api/download/?token={tok}"
    raw_bytes = None
    for attempt in range(3):
        try:
            r2 = session.get(url_dl, timeout=60)
            if r2.status_code == 200 and len(r2.content) > 10000:
                raw_bytes = r2.content
                break
        except Exception:
            pass
        time.sleep(2.0)
    if not raw_bytes:
        return []

    text = raw_bytes.decode("latin1", errors="ignore")
    lines = text.splitlines()
    header_idx = None
    for i, ln in enumerate(lines[:10]):
        if "TckrSymb" in ln and "ISIN" in ln and "ExrcPric" in ln:
            header_idx = i
            break
    if header_idx is None:
        return []

    reader = csv.DictReader(io.StringIO("\n".join(lines[header_idx:])), delimiter=";")
    rows = []
    for rec in reader:
        tk = (rec.get("TckrSymb") or "").strip()
        cat = (rec.get("SctyCtgyNm") or "").strip()
        if not tk.startswith("IBOV") or cat != "OPTION ON INDEX":
            continue
        isin = (rec.get("ISIN") or "").strip()
        if not isin:
            continue
        opt_tp = (rec.get("OptnTp") or "").strip().upper()
        if opt_tp not in ("CALL", "PUT"):
            sg = (rec.get("SgmtNm") or "").upper()
            opt_tp = "PUT" if "PUT" in sg else ("CALL" if "CALL" in sg else "")
        if not opt_tp:
            continue
        exrc_raw = (rec.get("ExrcPric") or "").strip().replace(",", ".")
        exp_dt = (rec.get("XprtnDt") or "").strip()[:10]
        if not exrc_raw or not exp_dt:
            continue
        try:
            strike = float(exrc_raw)
        except ValueError:
            continue
        rows.append({
            "isin": isin,
            "ticker": tk,
            "type": opt_tp,
            "strike": strike,
            "expiry": exp_dt,
            "series_type": (rec.get("SrsTpNm") or "").strip(),
            "source_date": date_iso,
        })
    return rows


def scan_oi_isins(dated_files: list[tuple[str, str]]) -> tuple[dict[str, float], dict[str, list[str]], int]:
    """Lê todos os CSVs de Posições em Aberto e mapeia ISIN -> OI acumulado e datas."""
    from gex.engine.b3_dol_parser import parse_b3_oi

    isin_oi: dict[str, float] = defaultdict(float)
    isin_dates: dict[str, list[str]] = defaultdict(list)
    total_rows = 0

    for iso, fp in dated_files:
        header_idx = 0
        with open(fp, "r", encoding="latin1") as f:
            for i, ln in enumerate(f):
                if ln.startswith("Instrumento financeiro"):
                    header_idx = i
                    break
        df = pd.read_csv(fp, sep=";", encoding="latin1", skiprows=header_idx, dtype=str, low_memory=False)
        tk_col = df.iloc[:, 0].astype(str).str.strip()
        seg_col = df.iloc[:, 4].astype(str).str.strip()
        mask = tk_col.str.startswith("IBOV") & (
            seg_col.str.contains("EQUITY CALL", na=False) | seg_col.str.contains("EQUITY PUT", na=False)
        )
        sub = df[mask]
        for _, row in sub.iterrows():
            oi = parse_b3_oi(row.iloc[11]) if len(row) > 11 else 0
            if oi <= 0:
                continue
            isin = str(row.iloc[1]).strip()
            total_rows += 1
            isin_oi[isin] += oi
            if not isin_dates[isin] or isin_dates[isin][-1] != iso:
                isin_dates[isin].append(iso)

    return isin_oi, isin_dates, total_rows


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    dated_files = list_oi_files()
    print(f"Arquivos OI no periodo {START_DATE}..{END_DATE}: {len(dated_files)}")

    picks = pick_bimonthly_dates(dated_files)
    print(f"Baixando InstrumentsConsolidatedFile em {len(picks)} datas (2/mes)...")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://arquivos.b3.com.br/bdi/tabelas?lang=pt-BR",
    })

    catalog: dict[str, dict] = {}
    for i, d_iso in enumerate(picks, 1):
        items = download_instruments_for_date(session, d_iso)
        added = 0
        for it in items:
            if it["isin"] not in catalog:
                catalog[it["isin"]] = it
                added += 1
        print(f"  [{i:2d}/{len(picks)}] {d_iso}: {len(items)} opcoes IBOV (+{added} novos ISINs, total={len(catalog)})", flush=True)

    print("\nVerificando cobertura contra todos os CSVs de Posicoes em Aberto...")
    isin_oi, isin_dates, total_rows = scan_oi_isins(dated_files)
    missing_isins = [k for k in isin_oi if k not in catalog]
    print(f"ISINs unicos com OI>0: {len(isin_oi)} | Faltantes apos 1a passada: {len(missing_isins)}")

    # Cobertura por datas extras onde faltam ISINs (greedy set cover ate 10 datas)
    extra_fetched = 0
    while missing_isins and extra_fetched < 10:
        date_score: dict[str, float] = defaultdict(float)
        for mis in missing_isins:
            for d_iso in isin_dates[mis]:
                date_score[d_iso] += isin_oi[mis]
        if not date_score:
            break
        best_date = max(date_score, key=lambda k: date_score[k])
        extra_fetched += 1
        items = download_instruments_for_date(session, best_date)
        added = 0
        for it in items:
            if it["isin"] not in catalog:
                catalog[it["isin"]] = it
                added += 1
        missing_isins = [k for k in isin_oi if k not in catalog]
        print(f"  [Extra {extra_fetched:2d}] {best_date}: +{added} ISINs | faltantes={len(missing_isins)}", flush=True)

    total_oi = sum(isin_oi.values())
    cov_isins = len(isin_oi) - len(missing_isins)
    cov_oi = sum(v for k, v in isin_oi.items() if k in catalog)
    print(
        f"\nCobertura final: {cov_isins}/{len(isin_oi)} ISINs ({100*cov_isins/max(1,len(isin_oi)):.2f}%) | "
        f"OI coberto: {100*cov_oi/max(1,total_oi):.2f}% ({total_rows} linhas OI>0)"
    )

    out_df = pd.DataFrame(sorted(catalog.values(), key=lambda x: (x["expiry"], x["strike"], x["type"], x["isin"])))
    out_df.to_csv(OUT_CSV, index=False, encoding="utf-8")
    print(f"Catalogo salvo em: {OUT_CSV} ({len(out_df)} ISINs unicos)")


if __name__ == "__main__":
    main()
