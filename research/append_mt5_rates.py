"""
Estende os caches `data/mt5_rates/mt5_{WIN,WDO}_N_{M1,M2,M5,M15}.csv` até a data pedida, só ACRESCENTANDO barras
(o histórico existente fica intacto — o terminal limita M1 a ~100 mil barras e um re-download perderia o começo).
Antes de anexar, confere se o MT5 devolve as mesmas barras do último dia já gravado (paridade com o cache).
Faz backup de cada CSV em data/mt5_rates/backup_<data>/.

Uso: python research/append_mt5_rates.py 2026-11-11 [--aceitar-revisao]
  --aceitar-revisao: o MT5 às vezes revisa a abertura de barras antigas em 1 tick, ou a última barra do dia foi gravada
  ainda em formação; com a flag o cache existente é mantido (paridade com o BT auditado) e só os dias novos entram.
"""
import datetime as dt
import os
import shutil
import sys

import MetaTrader5 as mt5
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RATES = os.path.join(ROOT, "data", "mt5_rates")
TERM = r"C:\Program Files\MetaTrader 5\terminal64.exe"
COLS = ["t", "open", "high", "low", "close", "tick_volume", "real_volume"]


def main(end: str):
    d_to = dt.datetime.fromisoformat(end) + dt.timedelta(hours=23, minutes=59)
    if not mt5.initialize(TERM, timeout=15000):
        raise SystemExit(f"MT5 não inicializou: {mt5.last_error()}")
    bak = os.path.join(RATES, f"backup_{dt.datetime.now():%Y%m%d_%H%M%S}")
    os.makedirs(bak, exist_ok=True)
    tfs = {"M1": mt5.TIMEFRAME_M1, "M2": mt5.TIMEFRAME_M2, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15}
    try:
        for sym in ("WIN$N", "WDO$N"):
            mt5.symbol_select(sym, True)
            for tfn, code in tfs.items():
                path = os.path.join(RATES, f"mt5_{sym.replace('$', '_')}_{tfn}.csv")
                old = pd.read_csv(path, parse_dates=["t"])
                last = old["t"].max()
                day0 = last.normalize()
                raw = mt5.copy_rates_range(sym, code, day0.to_pydatetime(), d_to)
                if raw is None or not len(raw):
                    print(f"{sym} {tfn}: MT5 sem barras ({mt5.last_error()})")
                    continue
                new = pd.DataFrame(raw)
                new["t"] = pd.to_datetime(new["time"], unit="s")
                new = new[COLS]
                # paridade do último dia já gravado (OHLC)
                ov = old[old["t"] >= day0].merge(new, on="t", suffixes=("_o", "_n"))
                bad = sum(int((ov[f"{c}_o"] - ov[f"{c}_n"]).abs().gt(1e-6).sum()) for c in ("open", "high", "low", "close"))
                add = new[new["t"] > last]
                if bad and not ACEITA_REVISAO:
                    print(f"{sym} {tfn}: ATENÇÃO {bad} valores OHLC do dia {day0.date()} diferem do cache — não anexado "
                          f"(use --aceitar-revisao para manter o cache e anexar só os dias novos)")
                    continue
                if bad:
                    print(f"{sym} {tfn}: {bad} valores OHLC de {day0.date()} revisados no MT5 — cache mantido")
                shutil.copy2(path, bak)
                out = pd.concat([old, add], ignore_index=True)
                out.to_csv(path, index=False)
                print(f"{sym} {tfn}: +{len(add)} barras ({add['t'].min()} → {add['t'].max()}) · "
                      f"conferidas {len(ov)} do dia {day0.date()}")
    finally:
        mt5.shutdown()
    print("backup:", bak)


ACEITA_REVISAO = "--aceitar-revisao" in sys.argv

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args[0] if args else dt.date.today().isoformat())
