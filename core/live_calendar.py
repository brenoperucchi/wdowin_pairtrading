"""
Calendário do Live Trading (Jumba GEX/NWE)
==========================================
Fonte: jumba_live_deals_<Login>.csv, exportado em MQL5\\Files\\Common pelo
`Jumba_Portfolio_Live_Monitor` que roda no terminal da carteira ao vivo
("MetaTrader 5 Terminal - milhao", perfil Jumba_11_CARTEIRA_ALINHADA).

Não usa a API Python do MT5 (que só se conecta a um terminal por processo e
não responde via IPC para o terminal milhao). Agrega deals -> posição fechada
-> dia -> robô.

Uso standalone:
    python -m core.live_calendar            # imprime JSON
"""
import os
import csv
import glob
import json
from datetime import datetime

COMMON_FILES = os.path.join(os.environ.get("APPDATA", ""), "MetaQuotes", "Terminal", "Common", "Files")
LIVE_ACCOUNT = os.environ.get("JUMBA_LIVE_ACCOUNT", "62033102")  # conta do terminal milhao (XPMT5-DEMO)

# Custos operacionais usados em todo o projeto (iguais aos backtests alinhados)
COST_PER_CONTRACT = {"WIN": 2.0, "WDO": 5.0}

# Carteira aprovada (perfil Jumba_11_CARTEIRA_ALINHADA)
ACTIVE_PORTFOLIO = {88001, 88004, 88007, 88013, 88014, 88015, 88016, 89002, 89007, 89009, 89010}

ROBOT_NAMES = {
    88001: "Quebra/Absorção Mkt Wall", 88002: "Scalper Híbrido Limit B1", 88004: "Pullback Tendência WDO-Alinhado",
    88006: "Breno Stop B1 Ext", 88007: "Absorção Mkt Wall NY", 88008: "Fade Wall s/ Lunch",
    88012: "Piramidação 1+1L NY", 88013: "SmartGrid GEX+NWE", 88014: "SmartGrid Vel 1+2L",
    88015: "SmartGrid MainWall Z30", 88016: "SmartGrid MidWall",
    89002: "Scalper Híbrido CORE", 89006: "Breno Absorption Wick", 89007: "Absorção Mkt Wall NY",
    89009: "Cluster NWE30+50 Limit Wall", 89010: "Reversão NWE 12h-14h30", 89011: "SmartGrid GF+NextWall",
    89015: "MainWall Z30 Rev070",
}

DEAL_ENTRY_IN = 0
DEAL_REASON = {3: "SL", 4: "TP", 5: "STOP OUT", 0: "MANUAL", 1: "MANUAL", 2: "MANUAL"}


def magic_to_code(magic: int):
    if 88001 <= magic <= 88016:
        return f"EST-{magic - 88000:02d}", "WIN"
    if 89001 <= magic <= 89016:
        return f"WDO-{magic - 89000:02d}", "WDO"
    return None, None


def _deals_file(account: str):
    f = os.path.join(COMMON_FILES, f"jumba_live_deals_{account}.csv")
    if os.path.exists(f):
        return f
    cands = sorted(glob.glob(os.path.join(COMMON_FILES, "jumba_live_deals_*.csv")), key=os.path.getmtime)
    return cands[-1] if cands else None


def _open_positions(account: str):
    """Posições abertas pelo snapshot do monitor (jumba_portfolio_live_monitor_<login>.csv)."""
    f = os.path.join(COMMON_FILES, f"jumba_portfolio_live_monitor_{account}.csv")
    out = []
    if not os.path.exists(f):
        return out
    with open(f, encoding="latin-1", newline="") as fh:
        for r in csv.DictReader(fh, delimiter=";"):
            try:
                magic = int(r.get("Magic") or 0)
                d = int(r.get("OpenDir") or 0)
            except ValueError:
                continue
            code, asset = magic_to_code(magic)
            if code and d != 0:
                out.append(dict(robot=code, asset=asset, side=d, lots=float(r.get("OpenLots") or 0),
                                floating=float(r.get("FloatingBRL") or 0)))
    return out


def load_live_calendar(account: str = LIVE_ACCOUNT) -> dict:
    path = _deals_file(account)
    if not path:
        return dict(ok=False, error="Arquivo jumba_live_deals_<login>.csv não encontrado em Common\\Files. "
                                    "Confira se o Jumba_Portfolio_Live_Monitor está rodando no MT5 milhao.",
                    trades=[], open_positions=[])
    acc = os.path.basename(path).replace("jumba_live_deals_", "").replace(".csv", "")

    pos = {}
    with open(path, encoding="latin-1", newline="") as fh:
        for r in csv.DictReader(fh, delimiter=";"):
            try:
                pid = int(r["position_id"])
                magic = int(r["magic"])
                entry = int(r["entry"])
                vol = float(r["volume"])
                t = datetime.strptime(r["time"], "%Y.%m.%d %H:%M:%S")
            except (KeyError, ValueError):
                continue
            p = pos.setdefault(pid, dict(magic=0, symbol=r.get("symbol", ""), t_in=None, t_out=None, side=0,
                                         lots_in=0.0, lots_out=0.0, profit=0.0, cost=0.0, px_in=0.0,
                                         px_out=0.0, reason=""))
            if magic_to_code(magic)[0]:
                p["magic"] = magic
            p["profit"] += float(r["profit"]) + float(r["swap"])
            p["cost"] += float(r["commission"]) + float(r["fee"])
            if entry == DEAL_ENTRY_IN:
                if p["t_in"] is None:
                    p["t_in"] = t
                    p["side"] = 1 if r["type"] == "0" else -1
                # preço médio de entrada (grids/piramidação com várias pernas)
                p["px_in"] = (p["px_in"] * p["lots_in"] + float(r["price"]) * vol) / (p["lots_in"] + vol)
                p["lots_in"] += vol
            else:
                p["t_out"] = t
                p["px_out"] = float(r["price"])
                p["lots_out"] += vol
                rs = int(r.get("reason") or -1)
                cm = (r.get("comment") or "").strip()
                p["reason"] = DEAL_REASON.get(rs) if rs in (3, 4, 5) else (cm[:24] or DEAL_REASON.get(rs, "EA"))

    trades = []
    for pid, p in pos.items():
        if not p["magic"] or p["t_out"] is None or p["lots_out"] + 1e-9 < p["lots_in"]:
            continue  # posição ainda aberta (ou parcial)
        code, asset = magic_to_code(p["magic"])
        est_cost = COST_PER_CONTRACT[asset] * p["lots_in"]
        trades.append(dict(
            position_id=pid, magic=p["magic"], robot=code, asset=asset,
            name=ROBOT_NAMES.get(p["magic"], ""), in_portfolio=p["magic"] in ACTIVE_PORTFOLIO,
            symbol=p["symbol"], side=p["side"], lots=p["lots_in"],
            t_in=p["t_in"].strftime("%Y-%m-%d %H:%M:%S") if p["t_in"] else None,
            t_out=p["t_out"].strftime("%Y-%m-%d %H:%M:%S"), date=p["t_out"].strftime("%Y-%m-%d"),
            px_in=round(p["px_in"], 1), px_out=p["px_out"], reason=p["reason"],
            pnl=round(p["profit"] + p["cost"], 2),          # resultado bruto da conta (sem comissão no demo)
            pnl_est_cost=round(p["profit"] - est_cost, 2),  # com custo estimado do projeto (R$2 WIN / R$5 WDO)
        ))
    trades.sort(key=lambda x: x["t_out"])

    return dict(
        ok=True, source=os.path.basename(path), account=acc,
        file_updated_at=datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S"),
        cost_per_contract=COST_PER_CONTRACT, active_portfolio=sorted(magic_to_code(m)[0] for m in ACTIVE_PORTFOLIO),
        trades=trades, open_positions=_open_positions(acc),
    )


if __name__ == "__main__":
    d = load_live_calendar()
    print(json.dumps({k: v for k, v in d.items() if k != "trades"}, ensure_ascii=False, indent=1))
    print(f"{len(d['trades'])} trades fechados")
    for t in d["trades"][-10:]:
        print(t["t_out"], t["robot"], t["lots"], t["pnl"], t["reason"])
