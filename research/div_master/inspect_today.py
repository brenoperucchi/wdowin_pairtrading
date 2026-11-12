# -*- coding: utf-8 -*-
"""
Inspecao SOMENTE LEITURA do pregao de hoje (div_master, 11/11/2026).
- Le as barras M5 do motor ao vivo via GET http://localhost:8080/api/compass/etapa2 (nada e gravado).
- Le as Walls do dia em mt5/Files/jumba_gex_{win,wdo}_daily.csv.
- Roda os detectores existentes (sem alterar nenhum deles) e imprime o que cada um marca.
Uso: python research/div_master/inspect_today.py [WIN|WDO]
"""
import ast, csv, json, os, sys, urllib.request
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
from core import div_wall_signal as dws  # modulo puro (sem efeitos colaterais na importacao)

ASSET = (sys.argv[1] if len(sys.argv) > 1 else "WIN").upper()
IS_WIN = ASSET == "WIN"


def load_visual_detector():
    """Extrai so as 2 funcoes do Sniper 5176 do arquivo fonte (evita importar o modulo e suas dependencias)."""
    src_path = os.path.join(ROOT, "research", "flow_window_asg", "inject_unified_div_opt2.py")
    tree = ast.parse(open(src_path, encoding="utf-8").read())
    keep = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in
            ("compute_causal_3motor_bars", "detect_visual_swing_divergences")]
    ns = {}
    exec(compile(ast.Module(body=keep, type_ignores=[]), src_path, "exec"), ns)
    return ns["compute_causal_3motor_bars"], ns["detect_visual_swing_divergences"]


def load_walls(day):
    p = os.path.join(ROOT, "mt5", "Files", f"jumba_gex_{ASSET.lower()}_daily.csv")
    out = []
    with open(p, encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter=";"):
            if r["session_date"] == day:
                out.append({"type": r["type"], "price": float(r["price"]), "width": int(r["width"])})
    return out


def main():
    raw = json.loads(urllib.request.urlopen("http://localhost:8080/api/compass/etapa2", timeout=90).read().decode("utf-8"))
    pay = raw[ASSET]
    ser = [b for b in pay["m5_dealer_vs_flow_series"] if not b.get("is_prev_day")]
    closed = [b for b in ser if b.get("is_bar_closed", True)]
    day = str(raw.get("timestamp", ""))[:10] or "2026-11-11"
    if len(day) != 10 or day[4] != "-":
        day = "2026-11-11"
    walls = load_walls(day)
    lv = [w for w in walls if w["type"] in ("Wall", "MidWall")]
    print(f"== {ASSET} {day} | barras de hoje {len(ser)} (fechadas {len(closed)}) {ser[0]['time']}..{ser[-1]['time']} | walls {len(lv)}")
    print("Walls/MidWalls na faixa do dia:")
    lo, hi = min(b["low"] for b in ser), max(b["high"] for b in ser)
    pad = 600 if IS_WIN else 15
    for w in sorted(walls, key=lambda x: x["price"]):
        if lo - pad <= w["price"] <= hi + pad:
            print(f"   {w['type']:<10} {w['price']:.2f} (w{w['width']})")

    def near(px):
        if not lv:
            return ("-", 0.0, 0.0)
        w = min(lv, key=lambda x: abs(x["price"] - px))
        return (w["type"], w["price"], px - w["price"])

    bars = [dict(b) for b in closed]
    fb = dws.compute_flow(bars, ASSET)
    print("\nBarras (onda do motor = smart_swing_wave; onda div_wall = compute_flow do mesmo dado):")
    print(" hora    open     high     low     close | wave_mot wave_dws  force   wyk  i_aggr i_pass   ret  cvd_inst  cvd_tot | wall_prox (dist low/high)")
    for b, f in zip(bars, fb):
        tl, pl, dl = near(b["low"]); th, ph, dh = near(b["high"])
        dd = dl if abs(dl) <= abs(dh) else dh
        pp = pl if abs(dl) <= abs(dh) else ph
        print(f" {b['time']} {b['open']:>8.1f} {b['high']:>8.1f} {b['low']:>8.1f} {b['close']:>8.1f} | "
              f"{b.get('smart_swing_wave',0):>8.0f} {f['wave']:>8.0f} {f['force']:>6.0f} {f['wyckoff_abs']:>6.0f} "
              f"{b.get('inst_aggr_delta',0):>6.0f} {b.get('inst_pass_delta',0):>6.0f} {b.get('ret_delta_bar',0):>5.0f} "
              f"{b.get('cvd_inst',0):>9.0f} {b.get('cvd_total',0):>8.0f} | {pp:.0f} ({dd:+.0f})")

    # pivos (L2/R1), igual ao div_wall_signal
    print("\nPivos L2/R1 (fundos F / topos T) com onda e CVDs:")
    for j in range(2, len(fb) - 1):
        for d, isp, key in ((1, dws._is_pivot_low, "low"), (-1, dws._is_pivot_high, "high")):
            if isp(fb, j, 2, 1):
                t, p, dist = near(fb[j][key])
                print(f"   {'F' if d==1 else 'T'} {fb[j]['time']} px={fb[j][key]:.1f} wave={fb[j]['wave']:.0f} "
                      f"cvd_inst={bars[j].get('cvd_inst',0):.0f} cvd_tot={bars[j].get('cvd_total',0):.0f} "
                      f"cvd_ret={bars[j].get('cvd_retail',0):.0f} | {t} {p:.0f} ({dist:+.0f})")

    # A) campo swing_divergence do motor (painel / 3 motores)
    print("\nA) motor gex_live_dealer_engine (campo swing_divergence, le barra i+1 e repinta):")
    for b in ser:
        sd = b.get("swing_divergence")
        if sd:
            print(f"   {sd.get('type')} {sd.get('prev_time')}->{sd.get('curr_time')} px {sd.get('prev_price')}->{sd.get('curr_price')} "
                  f"onda {sd.get('prev_wave')}->{sd.get('curr_wave')} near_wall={sd.get('near_wall')} driver={sd.get('driver')}")

    # B) detector do Sniper 5176
    c3m, vis = load_visual_detector()
    b3 = c3m(bars, IS_WIN)
    sv = vis(b3, lv, IS_WIN)
    print("\nB) Sniper 5176 detect_visual_swing_divergences (com Walls do dia):")
    for s in sv:
        i = s["sig_idx"]
        print(f"   {'COMPRA' if s['dir']==1 else 'VENDA'} sinal no fechamento {b3[i]['time']} pivo={s['pivot_px']:.1f} near_wall={s['near_wall']} | {near(s['pivot_px'])}")
    print("   (no painel 5176 so e desenhada se houver trade de setup ate 3 barras depois ou nas 3 ultimas barras)")

    # NWE: usa a do payload (motor) quando existir; senao NWE fria do dia
    if all(b.get("nwe_line") for b in bars):
        nwe = (np.array([b["nwe_line"] for b in bars]), np.array([b["nwe_upper"] for b in bars]), np.array([b["nwe_lower"] for b in bars]))
        nwe_src = "payload"
    else:
        nwe = dws.nwe_series(np.array([b["close"] for b in bars])); nwe_src = "fria"
    print(f"\n(NWE usada em C/D/E: {nwe_src})")

    print("\nC) div_wall v1 detect_signals (pivos L2/R1, F1-F2 3..20 barras, ext<=400/10, R=100/3):")
    for nf in ("none", "extreme"):
        sp = dws.SignalParams.default(ASSET, nwe_filter=nf, entry_start="09:00")
        for s in dws.detect_signals(fb, lv, nwe, sp):
            print(f"   [{nf}] {'COMPRA' if s.direction==1 else 'VENDA'} {s.time} F1 {fb[s.f1_idx]['time']}@{s.f1_px:.0f} -> F2 {fb[s.pivot_idx]['time']}@{s.pivot_px:.0f} onda {s.wave_f1:.0f}->{s.wave_f2:.0f} wall {s.wall_type} {s.wall_px:.0f}")

    print("\nD) divergencia v2 detect_divergences_v2:")
    for k in (0.5, 1.0, 1.5):
        for nf in ("none", "extreme"):
            for cf in ("PIVO", "FECHA_WALL"):
                R = 100.0 if IS_WIN else 3.0
                p = dws.DivParamsV2.default(ASSET, wave_k=k, nwe_filter=nf, confirm=cf, wall_radius=R)
                for s in dws.detect_divergences_v2(fb, lv, nwe, p):
                    print(f"   [k{k} {nf} {cf}] {'COMPRA' if s.direction==1 else 'VENDA'} {s.time} F1 {fb[s.f1_idx]['time']}@{s.f1_px:.0f} -> F2 {fb[s.pivot_idx]['time']}@{s.pivot_px:.0f} onda {s.wave_f1:.0f}->{s.wave_f2:.0f} {s.wall_type} {s.wall_px:.0f}")

    print("\nE) spring/upthrust detect_springs (M5 aqui; foi desenhado para M1):")
    for fm in ("none", "absorb"):
        p = dws.SpringParams.default(ASSET, flow_mode=fm, entry_start="09:00")
        for s in dws.detect_springs(fb, lv, nwe, p):
            print(f"   [{fm}] {'COMPRA' if s.direction==1 else 'VENDA'} {s.time} extremo {s.pivot_px:.0f} wall {s.wall_px:.0f}")

    print("\nF) sinais de setup do dia (signals_log do motor):")
    for s in sorted(pay.get("signals_log", []), key=lambda x: x.get("time", "")):
        print(f"   {s.get('time')} {s.get('strategy_id')} {s.get('direction')} {s.get('validation_status')} entrada={s.get('entry_price')} saida={s.get('exit_time')} pts={s.get('realized_pts')}")

    print("\nG) eventos de Wall do motor (local_gex):")
    lg = pay.get("local_gex") or {}
    for key in ("walls", "walls_clean", "all_walls", "nearby_walls"):
        for w in (lg.get(key) or []):
            evs = w.get("wall_events") or []
            if evs:
                print(f"   {w.get('type')} {w.get('price')}: " + ", ".join(f"{e.get('time')} {e.get('type')}" for e in evs) + f" | veredito={w.get('live_verdict')}")
    print("   chaves local_gex:", list(lg.keys())[:30])


if __name__ == "__main__":
    main()
