# -*- coding: utf-8 -*-
"""
Opção A (Acrescentar) no painel localhost:5176:
Preserva `WIN_DIV_WALL`, `WDO_DIV_WALL`, `ESP_DIV_V22_WIN` (e todas as estratégias da 5174)
e injeta no histórico JSON (`data/processed/portfolio_4_sistematicas_equity_v1.json`)
as 4 novas estratégias independentes do motor `core/carteira_v32_estrategias.py`:
  - C1a_BRK_WIN (1 ct)
  - V1a_DIV_WDO (1 ct)
  - SYM_DIV_WIN (1 ct)
  - SYM_DIV_WDO (1 ct)

Uso: python research/div_master/carteira_v22/injetar_4_novas_5176.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import warnings
from datetime import datetime

warnings.filterwarnings("ignore")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DM = os.path.join(ROOT, "research", "div_master")
sys.path[:0] = [ROOT, os.path.join(DM, "especialistas"), HERE]

import bt  # noqa: E402
import research.flow_window_asg.inject_unified_div_opt2 as S  # noqa: E402
from core import carteira_v32_estrategias as C32  # noqa: E402
from paridade_4_estrategias import day_inputs  # noqa: E402
from research.div_wall.data import load_asset  # noqa: E402

JSON_PATH = os.path.join(ROOT, "data", "processed", "portfolio_4_sistematicas_equity_v1.json")
NEW_IDS = ("C1a_BRK_WIN", "V1a_DIV_WDO", "SYM_DIV_WIN", "SYM_DIV_WDO")
ALL_5176_IDS = ("WIN_DIV_WALL", "WDO_DIV_WALL", "ESP_DIV_V22_WIN", *NEW_IDS)
CARTEIRA_V32_5_IDS = ("ESP_DIV_V22_WIN", *NEW_IDS)


def trade_dd(st: dict, trades: list[dict]) -> dict:
    """Adiciona DD e Ret/DD trade a trade (ordem cronológica de saída)."""
    rows = sorted(trades, key=lambda t: (t["date"], t.get("exit_time", ""), t["time"]))
    eq, pk, dd = 0.0, 0.0, 0.0
    for t in rows:
        eq += float(t["brl_1c"])
        pk = max(pk, eq)
        dd = max(dd, pk - eq)
    st["max_dd_trade_brl_1c"] = round(dd, 2)
    st["ret_dd_trade"] = round(eq / dd, 2) if dd > 0 else 99.9
    return st


def build_new_trades(dates: list[str]) -> dict[str, list[dict]]:
    ds_map = {"WIN": bt.market("WIN"), "WDO": bt.market("WDO")}
    data_map = {
        "WIN": load_asset("WIN", "M5"),
        "WDO": load_asset("WDO", "M5"),
    }
    by_sid: dict[str, list[dict]] = {sid: [] for sid in NEW_IDS}

    for d in dates:
        for asset in ("WIN", "WDO"):
            DS, data = ds_map[asset], data_map[asset]
            if d not in DS or d not in data:
                continue
            fb, walls, ex = day_inputs(DS, data, asset, d)
            fmt_p = ".0f" if asset == "WIN" else ".1f"
            for t in C32.run_all_for_asset(asset, fb, walls, ex, is_live=False):
                sid = t["strategy_id"]
                cfg = C32.STRAT_CFGS[sid]
                why = {
                    "STOP": "❌ STOP",
                    "ALVO": "🎯 ALVO",
                    "TEMPO": f"⏱️ SAÍDA {cfg['tmax'] * 5}M",
                    "17:25": "⏱️ SAÍDA 17:25",
                }.get(t["exit_reason"], t["exit_reason"])
                lbl = f"{why} ({t['pts']:+{fmt_p}}p · R$ {t['brl_1c']:+.0f})"
                by_sid[sid].append(
                    {
                        "date": d,
                        "month": d[:7],
                        "time": t["time"],
                        "exit_time": t["exit_time"],
                        "asset": asset,
                        "strategy_id": sid,
                        "direction": t["direction"],
                        "entry_price": t["entry_price"],
                        "exit_price": t["exit_price"],
                        "tp_price": t["tp_price"],
                        "tp1_price": None,
                        "tp_tag": f"TP {t['tp_pts']:{fmt_p}}p",
                        "stop_price": t["stop_price"],
                        "be_triggered": False,
                        "be_trigger_price": None,
                        "be_stop_price": None,
                        "pts": t["pts"],
                        "brl_1c": t["brl_1c"],
                        "contracts": cfg["contracts"],
                        "label": lbl,
                        "status": "FECHADA",
                        "exit_reason": t["exit_reason"],
                        "in_flow": True,
                        "in_base": True,
                        "in_mt5_11": False,
                        "in_walls_flow": True,
                    }
                )
    return by_sid


META_MAP = {
    "C1a_BRK_WIN": {
        "id": "C1a_BRK_WIN",
        "asset": "WIN",
        "name": "WIN · Rompimento Convergente C1a (BRK_F1F2 · 1c)",
        "short": "WIN Brk Conv C1a",
        "window": "09:05–16:45 (s/ 11h)",
        "lotes": "1c",
        "tp_rule": "Alvo fixo +280p ou 24 barras (120 min)",
        "sl_be_rule": "SL fixo −280p · UM_POR_VEZ independente",
        "nwe_rule": "Tendência NWE50 esticada < +0,5 (ext50_trend < 0,5)",
        "flow_rule": "Rompimento BRK_F1F2 convergência k1w2 + perto/cruzando Wall · s/ 11h",
    },
    "V1a_DIV_WDO": {
        "id": "V1a_DIV_WDO",
        "asset": "WDO",
        "name": "WDO · Divergência V3.2 V1a (Wall z=3.5 · ProxWall · 1c)",
        "short": "WDO Div V3.2 V1a",
        "window": "09:00–17:00 (s/ 11h)",
        "lotes": "1c",
        "tp_rule": "ProxWall (Wall/MidWall) [4,0..22,0]p mín 2,5p ou 24 barras (120 min)",
        "sl_be_rule": "SL fixo −14,0p · UM_POR_VEZ independente",
        "nwe_rule": "Contexto NWE30: ext30 > 0,0 (esticado contra entrada)",
        "flow_rule": "Divergência V3.2 (open=True) Wall pura d_wall <= 3,5p · CONF · s/ 11h",
    },
    "SYM_DIV_WIN": {
        "id": "SYM_DIV_WIN",
        "asset": "WIN",
        "name": "WIN · Simétrica SYM_TOP1 (V3.2 Wall · CONF · 1c)",
        "short": "WIN Simétrica V3.2",
        "window": "09:05–16:45 (s/ 11h)",
        "lotes": "1c",
        "tp_rule": "Alvo fixo +240p ou 24 barras (120 min)",
        "sl_be_rule": "SL fixo −280p · UM_POR_VEZ independente",
        "nwe_rule": "Contexto NWE50: ext50 > −0,5 e slope50 > −0,5",
        "flow_rule": "Divergência V3.2 (open=True) na Wall · CONF · até 2º sinal/dir · s/ 11h",
    },
    "SYM_DIV_WDO": {
        "id": "SYM_DIV_WDO",
        "asset": "WDO",
        "name": "WDO · Simétrica SYM_TOP1 (V3.2 Wall · CONF · ProxWall · 1c)",
        "short": "WDO Simétrica V3.2",
        "window": "09:00–17:00 (s/ 11h)",
        "lotes": "1c",
        "tp_rule": "ProxWall (Wall/MidWall) [3,5..20,0]p mín 2,0p ou 18 barras (90 min)",
        "sl_be_rule": "SL fixo −14,0p · UM_POR_VEZ independente",
        "nwe_rule": "Contexto NWE50: ext50 > −0,5 e slope50 > −0,5",
        "flow_rule": "Divergência V3.2 (open=True) na Wall · CONF · até 2º sinal/dir · s/ 11h",
    },
}


def main() -> None:
    bak = JSON_PATH.replace(".json", f".backup_{datetime.now():%Y%m%d_%H%M%S}.json")
    shutil.copy2(JSON_PATH, bak)
    print("Backup criado:", bak)

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        p4 = json.load(f)

    dates = [d["date"] for d in p4["days"]]
    by_sid = build_new_trades(dates)

    # Limpa apenas eventuais entradas prévias das 4 novas (idempotência), preservando todo o resto!
    existing_5176_trades: list[dict] = []
    by_date_sid: dict[tuple[str, str], list[dict]] = {}
    for sid, trs in by_sid.items():
        for t in trs:
            by_date_sid.setdefault((t["date"], sid), []).append(t)

    for day in p4["days"]:
        d = day["date"]
        kept = [t for t in day.get("trades", []) if t.get("strategy_id") not in NEW_IDS]
        for t in kept:
            if t.get("strategy_id") in ("WIN_DIV_WALL", "WDO_DIV_WALL", "ESP_DIV_V22_WIN"):
                existing_5176_trades.append(t)
        add_today = []
        for sid in NEW_IDS:
            lst = by_date_sid.get((d, sid), [])
            pts = round(sum(float(t["pts"]) for t in lst), 2)
            for suf in ("", "_base", "_flow"):
                day[f"{sid}{suf}_pts"] = pts
                day[f"{sid}{suf}_ops"] = len(lst)
            add_today.extend(lst)
        day["trades"] = sorted(
            kept + add_today,
            key=lambda x: (x.get("time", ""), x.get("exit_time", ""), x.get("strategy_id", "")),
        )

    for sid in NEW_IDS:
        trs = by_sid[sid]
        st = trade_dd(S.compute_summary_from_trades(trs, dates), trs)
        p4["summary_1c"][sid] = {
            **st,
            "meta": META_MAP[sid],
            "base_mt5_variant": st,
            "flow_variant": st,
        }

    all_new_flat = [t for sid in NEW_IDS for t in by_sid[sid]]
    all_7_trades = existing_5176_trades + all_new_flat
    st_all7 = trade_dd(
        S.compute_summary_from_trades(
            sorted(all_7_trades, key=lambda x: (x["date"], x["time"], x["asset"])),
            dates,
        ),
        all_7_trades,
    )
    p4["summary_1c"]["PORTFOLIO_DIV_OPT2"] = st_all7

    # Resumo comparativo das 5 auditadas (E22 2c + C1a + V1a + SYM_WIN + SYM_WDO)
    cart_5_trades = [t for t in all_7_trades if t.get("strategy_id") in CARTEIRA_V32_5_IDS]
    st_cart5 = trade_dd(
        S.compute_summary_from_trades(
            sorted(cart_5_trades, key=lambda x: (x["date"], x["time"], x["asset"])),
            dates,
        ),
        cart_5_trades,
    )

    c5176 = p4.get("carteira_5176") or {}
    c5176["estrategias"] = list(ALL_5176_IDS)
    c5176["atualizado_4_novas"] = datetime.now().isoformat(timespec="seconds")
    c5176["backup_4_novas"] = os.path.basename(bak)
    p4["carteira_5176"] = c5176

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(p4, f, ensure_ascii=False)

    print("\nResumo injetado (execution M5 causal em core/carteira_v32_estrategias.py):")
    for sid in NEW_IDS:
        st = p4["summary_1c"][sid]
        print(
            f"  {sid:<14s}: {st['ops']:4d} ops | WR {st['wr_pct']:5.1f}% | PF {st['pf']:4.2f} | "
            f"Net R$ {st['tot_brl_1c']:+8.0f} | DD trade R$ {st['max_dd_trade_brl_1c']:5.0f} "
            f"(Ret/DD {st['ret_dd_trade']:5.2f})"
        )
    print(
        f"  {'CARTEIRA_5 (E22+4)':<14s}: {st_cart5['ops']:4d} ops | WR {st_cart5['wr_pct']:5.1f}% | PF {st_cart5['pf']:4.2f} | "
        f"Net R$ {st_cart5['tot_brl_1c']:+8.0f} | DD trade R$ {st_cart5['max_dd_trade_brl_1c']:5.0f} "
        f"(Ret/DD {st_cart5['ret_dd_trade']:5.2f})"
    )
    print(
        f"  {'TODAS_7_5176':<14s}: {st_all7['ops']:4d} ops | WR {st_all7['wr_pct']:5.1f}% | PF {st_all7['pf']:4.2f} | "
        f"Net R$ {st_all7['tot_brl_1c']:+8.0f} | DD trade R$ {st_all7['max_dd_trade_brl_1c']:5.0f} "
        f"(Ret/DD {st_all7['ret_dd_trade']:5.2f})"
    )


if __name__ == "__main__":
    main()
