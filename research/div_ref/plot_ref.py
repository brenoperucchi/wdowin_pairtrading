"""Desenha preço + fluxo com as divergências do detector v3 (core.div_wall_signal.detect_divergences_v3)
para validar a definição com o usuário. Uso: python research/div_ref/plot_ref.py"""
import json, os, sys
from datetime import datetime, timezone
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from core.div_wall_signal import compute_flow, detect_divergences_v3, DivParamsV2  # noqa: E402
from core.profit_mt5_flow_engine import load_daily_magic_walls  # noqa: E402

OUT = os.path.join(ROOT, "research", "div_ref")
SESS = os.path.join(ROOT, "data", "processed", "gex_historical_sessions_v1")


def load_day(date, live_json=None):
    path = live_json if live_json else os.path.join(SESS, f"{date}.json")
    return json.load(open(path, encoding="utf-8-sig"))


def plot(date, asset, payload):
    bars = [dict(x) for x in payload[asset]["m5_cvd_series"] if not x.get("is_prev_day")]
    for x in bars:
        x["time"] = datetime.fromtimestamp(int(x["time"]), timezone.utc).strftime("%H:%M")
    fb = compute_flow(bars, asset)
    walls = load_daily_magic_walls(asset, date) or []
    z = np.zeros(len(fb))
    sigs = detect_divergences_v3(fb, walls, (z, z, z), DivParamsV2.default(asset, nwe_filter="none"))
    o = np.array([b["open"] for b in fb]); h = np.array([b["high"] for b in fb])
    lo = np.array([b["low"] for b in fb]); c = np.array([b["close"] for b in fb])
    w = np.array([b["wave"] for b in fb]); x = np.arange(len(fb))
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(18, 9), sharex=True, gridspec_kw={"height_ratios": [3, 1.3]})
    fig.patch.set_facecolor("#0d1117")
    for a in (a1, a2):
        a.set_facecolor("#0d1117"); a.tick_params(colors="#c9d1d9"); a.grid(color="#21262d")
    up = c >= o
    a1.vlines(x, lo, h, color="#8b949e", lw=0.8)
    a1.bar(x[up], (c - o)[up], bottom=o[up], color="#e6edf3", width=0.6)
    a1.bar(x[~up], (c - o)[~up], bottom=o[~up], color="#6e7681", width=0.6)
    ymin, ymax = lo.min(), h.max(); pad = (ymax - ymin) * 0.08
    for wl in walls:
        if wl.get("type") in ("Wall", "MidWall") and ymin - pad <= float(wl["price"]) <= ymax + pad:
            a1.axhline(float(wl["price"]), color="#f0f6fc" if wl["type"] == "Wall" else "#8b949e",
                       ls="-" if wl["type"] == "Wall" else "--", lw=0.9)
            a1.text(len(fb) + 0.5, float(wl["price"]), f"{wl['type']} {float(wl['price']):g}", color="#c9d1d9", fontsize=8, va="center")
    a1.set_ylim(ymin - pad, ymax + pad)
    a2.plot(x, w, color="#22d3ee", lw=1.4); a2.axhline(0, color="#484f58", ls="--", lw=0.8)
    for n, s in enumerate(sigs, 1):
        col = "#22c55e" if s.direction == 1 else "#ef4444"
        k, j = s.f1_idx, s.pivot_idx
        a1.plot([k, j], [s.f1_px, s.pivot_px], color=col, lw=2.2)
        kw = int(np.argmin(w[max(0, k - 1):k + 2]) if s.direction == 1 else np.argmax(w[max(0, k - 1):k + 2])) + max(0, k - 1)
        a2.plot([kw, j], [w[kw], w[j]], color=col, lw=2.2)
        yy = s.pivot_px - pad * 0.5 if s.direction == 1 else s.pivot_px + pad * 0.5
        a1.annotate(f"{n}", (s.idx, yy), color=col, fontsize=11, fontweight="bold", ha="center", va="center")
    ticks = list(range(0, len(fb), 6))
    a2.set_xticks(ticks); a2.set_xticklabels([fb[t]["time"] for t in ticks], color="#c9d1d9")
    a1.set_title(f"{asset} {date} — divergências v3 (verde compra, vermelho venda, número = barra do sinal)",
                 color="#e6edf3", fontsize=12)
    fig.tight_layout()
    fn = os.path.join(OUT, f"v3_{asset}_{date}.png"); fig.savefig(fn, dpi=90, facecolor=fig.get_facecolor()); plt.close(fig)
    lines = [f"{n}. {s.time} {'COMPRA' if s.direction == 1 else 'VENDA'}  F1 {fb[s.f1_idx]['time']} {s.f1_px:g} -> "
             f"F2 {fb[s.pivot_idx]['time']} {s.pivot_px:g}  ({'perto da' if s.wall_type == 'perto' else 'furou e voltou'} {s.wall_px:g})"
             for n, s in enumerate(sigs, 1)]
    return fn, lines


if __name__ == "__main__":
    live = sys.argv[1] if len(sys.argv) > 1 else None
    for date, src in (("2026-11-10", None), ("2026-11-11", live)):
        if date == "2026-11-11" and not live:
            continue
        pay = load_day(date, src)
        for asset in ("WIN", "WDO"):
            fn, lines = plot(date, asset, pay)
            print(fn); print("\n".join("   " + l for l in lines))
