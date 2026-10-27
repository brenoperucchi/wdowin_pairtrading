# -*- coding: utf-8 -*-
"""
JUMBA FLOW - PROFIT CSV REAL-TIME BRIDGE (V2 - Incremental f.seek & Dual-Source)
Monitora a pasta RTD/ por exportações em tempo real do ProfitChart sem limite de 5 MB,
suportando tanto Times & Trades de 4 colunas (WIN/WDO) quanto 6/7 colunas (IND/DOL com corretora)
e tabelas de Saldo de Corretoras (*_saldo.csv).

Como rodar:
  .\.venv\Scripts\python.exe gex/engine/profit_csv_bridge.py
"""
import os
import sys
import time
import glob
import requests

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.profit_mt5_flow_engine import (
    flow_engine_singleton,
    BROKERS,
    B3_BROKER_CODES as B3_CODES,
    _match_broker_name as match_broker_name,
    _clean_int as clean_value,
    _clean_float as clean_price,
    RTD_DIR,
)

API_UPDATE_URL = "http://127.0.0.1:8080/api/flow/update"


def parse_csv_file(filepath: str):
    """Processa incrementalmente o arquivo CSV do Profit usando o motor vetorizado."""
    flow_engine_singleton._poll_profit_rtd_files()
    fname = os.path.basename(filepath).upper()
    if any(k in fname for k in ["WIN", "IND"]):
        symbol = "WIN"
        state = flow_engine_singleton.win_state
    elif any(k in fname for k in ["WDO", "DOL"]):
        symbol = "WDO"
        state = flow_engine_singleton.wdo_state
    else:
        return

    # Sincroniza saldos de corretoras com a API legada se o servidor estiver ouvindo
    for broker_name, b_data in state.brokers.items():
        if b_data["vol"] == 0 and b_data["net"] == 0:
            continue
        try:
            requests.get(
                API_UPDATE_URL,
                params={
                    "symbol": symbol,
                    "broker": broker_name,
                    "net": b_data["net"],
                    "avg": round(b_data["avg"], 2),
                    "buy": b_data["buy"],
                    "sell": b_data["sell"],
                },
                timeout=1.0,
            )
        except Exception:
            break


def main():
    print("=" * 70)
    print("  PROFIT CSV REAL-TIME BRIDGE V2 (f.seek Incremental + MT5 Dual-Source)")
    print("=" * 70)
    print(f"  Diretório monitorado: {RTD_DIR}")
    print("  Sem limite de 5 MB | Suporta WIN/WDO (4 cols), IND/DOL (6/7 cols) e *_saldo.csv")
    print("  Pressione Ctrl+C para sair.\n")

    os.makedirs(RTD_DIR, exist_ok=True)

    while True:
        try:
            snapshot = flow_engine_singleton.update()
            win_s = snapshot["win"]
            wdo_s = snapshot["wdo"]
            print(
                f"[{time.strftime('%H:%M:%S')}] "
                f"WIN ({win_s['active_contract']}): {win_s['last_price']:.0f} | "
                f"Delta={win_s['session_totals']['delta']:+.0f} (Inst={win_s['session_totals']['inst_delta']:+.0f}) | "
                f"Score={win_s['composite']['score']:+.1f} || "
                f"WDO ({wdo_s['active_contract']}): {wdo_s['last_price']:.1f} | "
                f"Delta={wdo_s['session_totals']['delta']:+.0f} (Inst={wdo_s['session_totals']['inst_delta']:+.0f}) | "
                f"Score={wdo_s['composite']['score']:+.1f}"
            )
            time.sleep(1.0)
        except KeyboardInterrupt:
            print("\nPonte CSV V2 encerrada.")
            break
        except Exception as e:
            print(f"[AVISO] Erro no ciclo do monitor: {e}")
            time.sleep(2.0)


if __name__ == "__main__":
    main()
