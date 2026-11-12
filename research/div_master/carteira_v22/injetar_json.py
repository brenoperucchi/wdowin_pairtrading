# -*- coding: utf-8 -*-
"""
Carteira 5176 com motor de divergência único v2.2 (12/11/2026): regrava o histórico do painel em
data/processed/portfolio_4_sistematicas_equity_v1.json (sem tocar nas estratégias da 5174).

  - WIN_DIV_WALL / WDO_DIV_WALL: mesmo Sniper (pool de setups, gate 3 motores no WIN, saídas, horários, meta diária),
    com o filtro de divergência do v2.2 (confirmação do pivô, sem âncora, janela de 2 barras antes da entrada);
  - ESP_DIV_V22_WIN: especialista via core/especialista_v22.run (o mesmo código do motor ao vivo);
  - PORTFOLIO_DIV_OPT2: as três juntas.
Faz backup do JSON antes de gravar.
Uso: python research/div_master/carteira_v22/injetar_json.py
"""
import json, os, shutil, sys, warnings
from datetime import datetime
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DM = os.path.join(ROOT, "research", "div_master")
sys.path[:0] = [ROOT, os.path.join(DM, "especialistas"), os.path.join(DM, "frente1"), HERE]
import research.flow_window_asg.inject_unified_div_opt2 as S
import modulo as M, bt
import motores as F1
from core import especialista_v22 as E
from paridade_especialista import day_inputs
from research.div_wall.data import load_asset

JSON = os.path.join(ROOT, "data", "processed", "portfolio_4_sistematicas_equity_v1.json")
IDS = ("WIN_DIV_WALL", "WDO_DIV_WALL", E.STRATEGY_ID)


ENGINE = "v3.2"            # desde 12/11/2026: v3.2 sem módulo de abertura (modulo.V32_PROD); antes "v2.2"
ENGINE_TXT = "v3.2"


def v22_map(asset):
    mp = F1.engine_map(asset, ENGINE, "conf", False)
    out = {}
    for k, v in mp.items():
        if isinstance(k, tuple):
            if k[1] == "tmap":
                out[k] = v
        else:
            out[k] = [(s[0], s[1]) for s in v]
    return out


def trade_dd(st, trades):
    """Acrescenta ao resumo o DD trade a trade (ordem de saída), a métrica da pesquisa; o resumo padrão usa DD diário."""
    rows = sorted(trades, key=lambda t: (t["date"], t.get("exit_time", ""), t["time"]))
    eq, pk, dd = 0.0, 0.0, 0.0
    for t in rows:
        eq += float(t["brl_1c"])
        pk = max(pk, eq)
        dd = max(dd, pk - eq)
    st["max_dd_trade_brl_1c"] = round(dd, 2)
    st["ret_dd_trade"] = round(eq / dd, 2) if dd > 0 else 99.9
    return st


def esp_trades(dates):
    DS = bt.market("WIN")
    data = load_asset("WIN", "M5")
    out = []
    for d in dates:
        if d not in DS or d not in data:
            continue
        fb, walls, ex = day_inputs(DS, data, d)
        for t in E.run(fb, walls, ex):
            why = {"STOP": "❌ STOP 200", "BE": "🛡️ BE +20", "TEMPO": "⏱️ SAÍDA 60 MIN", "17:25": "⏱️ SAÍDA 17:25"}.get(t["exit_reason"], t["exit_reason"])
            out.append(dict(
                date=d, month=d[:7], time=t["time"], exit_time=t["exit_time"], asset="WIN", strategy_id=E.STRATEGY_ID,
                direction=t["direction"], entry_price=t["entry_price"], exit_price=t["exit_price"], tp_price=None,
                tp1_price=None, stop_price=t["stop_price"], be_triggered=t["be_triggered"],
                be_trigger_price=t["be_trigger_price"], be_stop_price=t["be_stop_price"], pts=t["pts"],
                brl_1c=t["brl_1c"], contracts=2, label=f"{why} ({t['pts']:+.0f}p · R$ {t['brl_1c']:+.0f})", status="FECHADA",
                exit_reason=t["exit_reason"], f1_time=t["f1_time"], f2_time=t["f2_time"], trigger_time=t["trigger_time"],
                in_flow=True, in_base=True, in_mt5_11=False, in_walls_flow=True))
    return out


def main():
    M.V22 = dict(M.V22, **M.V22_ABERTURA)
    M.V32 = dict(M.V32_PROD)
    bak = JSON.replace(".json", f".backup_{datetime.now():%Y%m%d_%H%M%S}.json")
    shutil.copy2(JSON, bak)
    print("backup:", bak)
    p4 = json.load(open(JSON, encoding="utf-8"))
    dates = [d["date"] for d in p4["days"]]

    # pool de entradas dos setups (igual ao inject original) e gate 3 motores
    win_bars_map, nwe_win_map = S.load_mt5_win_bars_and_nwe30()
    win_lkp, _, _ = S.build_win_3motor_and_visual_maps(dates)
    raw_win, raw_wdo = [], []
    for day in p4["days"]:
        d = day["date"]
        day["trades"] = [t for t in day.get("trades", []) if t.get("strategy_id") not in IDS]
        seen_w, seen_d = set(), set()
        for t in day["trades"]:
            key = (d, t["time"], t["direction"])
            if t.get("asset") == "WIN":
                tm = int(t["time"][:2]) * 60 + int(t["time"][3:5])
                info = win_lkp.get((d, tm - 5)) or {}
                ok3 = info.get("bull_3motor", False) if t["direction"] == "COMPRA" else info.get("bear_3motor", False)
                if key not in seen_w and ok3:
                    seen_w.add(key)
                    raw_win.append(t)
            elif t.get("asset") == "WDO" and t.get("strategy_id") in ("WDO_01", "WDO_05", "WDO_07", "WDO_10") and key not in seen_d:
                seen_d.add(key)
                tc = dict(t, strategy_id="WDO_DIV_WALL", contracts=1, in_flow=True, in_base=True, in_mt5_11=False, in_walls_flow=True)
                raw_wdo.append(tc)
    sim_win = S.simulate_win_div_2lots_opt2(raw_win, win_bars_map, nwe_win_map)
    win_tr = S.filter_sniper_and_daily_cap(sim_win, v22_map("WIN"), 2, "09:05", "16:45", [("12:00", "12:55")], 180.0)
    wdo_tr = S.filter_sniper_and_daily_cap(raw_wdo, v22_map("WDO"), 2, "09:00", "17:00", [("11:00", "11:55")], 120.0)
    esp_tr = esp_trades(dates)

    st_w = trade_dd(S.compute_summary_from_trades(win_tr, dates), win_tr)
    st_d = trade_dd(S.compute_summary_from_trades(wdo_tr, dates), wdo_tr)
    st_e = trade_dd(S.compute_summary_from_trades(esp_tr, dates), esp_tr)
    all_tr = win_tr + wdo_tr + esp_tr
    st_p = trade_dd(S.compute_summary_from_trades(sorted(all_tr, key=lambda x: (x["date"], x["time"], x["asset"])), dates), all_tr)
    flt = "Sniper: divergência do motor v3.2 (F1 no fluxo extremo, sem módulo de abertura) confirmada até 2 barras antes da entrada do setup"
    meta = {
        "WIN_DIV_WALL": dict(id="WIN_DIV_WALL", asset="WIN", name="WIN · Sniper Divergência v3.2 · 2c Mix (s/ 12h · Meta +R$180)",
                             short="WIN Sniper 2c Mix", window="09:05–16:45 (s/ 12h)", lotes="2c (1+1)",
                             tp_rule="L1: NWE30 Oposta Din (260..750p) · L2: Fixo 750p",
                             sl_be_rule="SL 240p/260p + BE +20p aos +180p · Meta +R$180/dia",
                             nwe_rule="TP1 na Banda Oposta NWE30 (front-run 15p)", flow_rule=flt),
        "WDO_DIV_WALL": dict(id="WDO_DIV_WALL", asset="WDO", name="WDO · Sniper Divergência v3.2 · 1c (s/ 11h NY · Meta +R$120)",
                             short="WDO Sniper 1c", window="09:00–17:00 (s/ 11h NY/PTAX)", lotes="1c",
                             tp_rule="Saída nativa de cada setup WDO", sl_be_rule="Saída nativa de cada setup · Meta +R$120/dia",
                             nwe_rule="—", flow_rule=flt),
        E.STRATEGY_ID: dict(id=E.STRATEGY_ID, asset="WIN", name="WIN · Especialista de Divergência v3.2 · 2c",
                            short="WIN Especialista 2c", window="10:00–15:55", lotes="2c",
                            tp_rule="Sem alvo · sai em 12 barras (60 min) ou 17:25", sl_be_rule="SL 200p · BE +20p aos +180p",
                            nwe_rule="Contexto NWE50: ext > −0,5 e slope > −0,5",
                            flow_rule="Divergência v3.2 na Wall/MidWall ou extremo do dia (sem super-confluência), gatilho Opção C, até o 2º sinal do dia por direção, um trade por vez"),
    }
    for sid, st in (("WIN_DIV_WALL", st_w), ("WDO_DIV_WALL", st_d), (E.STRATEGY_ID, st_e)):
        p4["summary_1c"][sid] = {**st, "meta": meta[sid], "base_mt5_variant": st, "flow_variant": st}
    p4["summary_1c"]["PORTFOLIO_DIV_OPT2"] = st_p
    by = {}
    for t in win_tr + wdo_tr + esp_tr:
        by.setdefault((t["date"], t["strategy_id"]), []).append(t)
    for day in p4["days"]:
        d = day["date"]
        add = []
        for sid in IDS:
            lst = by.get((d, sid), [])
            pts = round(sum(float(t["pts"]) for t in lst), 2)
            for suf in ("", "_base", "_flow"):
                day[f"{sid}{suf}_pts"] = pts
                day[f"{sid}{suf}_ops"] = len(lst)
            add += lst
        day["trades"] = sorted(day["trades"] + add, key=lambda x: (x.get("time", ""), x.get("exit_time", ""), x.get("strategy_id", "")))
    p4["carteira_5176"] = dict(motor="v3.2 sem módulo de abertura (V32_PROD)", atualizado=datetime.now().isoformat(timespec="seconds"),
                               estrategias=list(IDS), backup=os.path.basename(bak))
    json.dump(p4, open(JSON, "w", encoding="utf-8"), ensure_ascii=False)
    for nm, st in (("WIN_DIV_WALL", st_w), ("WDO_DIV_WALL", st_d), (E.STRATEGY_ID, st_e), ("CARTEIRA 5176", st_p)):
        print(f"{nm:18s} {st['ops']:4d} tr · WR {st['wr_pct']}% · PF {st['pf']} · R$ {st['tot_brl_1c']:,.0f} · "
              f"DD trade R$ {st['max_dd_trade_brl_1c']:,.0f} (Ret/DD {st['ret_dd_trade']}) · DD diário R$ {st['max_dd_brl_1c']:,.0f} "
              f"(Ret/DD {st['ret_dd']}) · {st['pos_months']}/{st['total_months']} M+")
    print("gravado:", JSON)


if __name__ == "__main__":
    main()
