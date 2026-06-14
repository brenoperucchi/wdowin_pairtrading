import sqlite3
import json
import numpy as np
import matplotlib.pyplot as plt
import os

_broker_list = ["XP", "UBS", "BTG", "IDEAL", "GENIAL", "JPMORGAN", "TULLETT", "MERRILL", "GOLDMAN", "MORGAN", "CITI", "ITAU", "BRADESCO"]

def calculate_directional_efficiency_for_slice(rows_slice, lookback_bars=None):
    if lookback_bars is not None:
        rows_slice = rows_slice[-lookback_bars:]
    if len(rows_slice) < 2:
        return {"WIN": {}}
    
    efficiency = {"WIN": {}}
    prev_prices = {"WIN": None}
    prev_nets = {"WIN": {b: None for b in _broker_list}}
    stats = {"WIN": {b: {"num": 0.0, "den": 0.0} for b in _broker_list}}
    
    for r in rows_slice:
        win_price = r["win_price"]
        flow_json = r["flow_json"]
        if not flow_json or win_price is None:
            continue
        try:
            flow_data = json.loads(flow_json)
        except Exception:
            continue
        
        sym = "WIN"
        price = win_price
        
        if prev_prices[sym] is not None:
            dPrice = price - prev_prices[sym]
        else:
            dPrice = 0.0
            
        sym_flow = flow_data.get(sym, {})
        for b in _broker_list:
            b_metrics = sym_flow.get(b, {})
            if isinstance(b_metrics, dict):
                net = b_metrics.get("net", None)
            elif isinstance(b_metrics, (int, float)):
                net = b_metrics
            else:
                net = None
                
            if net is None:
                continue
                
            prev_net = prev_nets[sym][b]
            if prev_net is not None:
                dNet = net - prev_net
            else:
                dNet = 0.0
                
            if prev_prices[sym] is not None and prev_net is not None:
                product = dPrice * dNet
                stats[sym][b]["num"] += product
                stats[sym][b]["den"] += abs(product)
                
            prev_nets[sym][b] = net
        prev_prices[sym] = price

    for b in _broker_list:
        den = stats["WIN"][b]["den"]
        num = stats["WIN"][b]["num"]
        if den > 0:
            eff = (num / den) * 100.0
            efficiency["WIN"][b] = round(eff, 1)
        else:
            efficiency["WIN"][b] = 0.0
    return efficiency

def calculate_flow_acceleration_for_slice(rows_slice):
    if len(rows_slice) < 2:
        return 0.0
    
    short_term_eff = calculate_directional_efficiency_for_slice(rows_slice, lookback_bars=5)
    dominant_players = {"WIN": []}
    sym_eff = short_term_eff.get("WIN", {})
    for b, eff in sym_eff.items():
        if eff >= 40.0:
            dominant_players["WIN"].append((b, eff / 100.0))
            
    M = min(5, len(rows_slice) - 1)
    sym = "WIN"
    doms = dominant_players[sym]
    if not doms:
        return 0.0
        
    price_curr = rows_slice[-1]["win_price"]
    price_prev = rows_slice[-1 - M]["win_price"]
    
    if price_curr is None or price_prev is None:
        return 0.0
        
    dPrice = abs(price_curr - price_prev)
    tick_unit = 100.0
    total_vol = 0.0
    prev_nets_all = {}
    
    for idx in range(len(rows_slice) - M - 1, len(rows_slice)):
        r = rows_slice[idx]
        flow_json = r["flow_json"]
        if not flow_json:
            continue
        try:
            flow_data = json.loads(flow_json).get(sym, {})
        except Exception:
            continue
            
        for b in _broker_list:
            val_b = flow_data.get(b, {})
            net = val_b.get("net", None) if isinstance(val_b, dict) else val_b
            if net is not None:
                if b in prev_nets_all:
                    total_vol += abs(net - prev_nets_all[b])
                prev_nets_all[b] = net
                
    if total_vol > 0:
        if dPrice == 0:
            lots_per_unit = float("inf")
        else:
            lots_per_unit = total_vol / (dPrice / tick_unit)
            
        flow_curr = json.loads(rows_slice[-1]["flow_json"]).get(sym, {}) if rows_slice[-1]["flow_json"] else {}
        flow_prev = json.loads(rows_slice[-2]["flow_json"]).get(sym, {}) if rows_slice[-2]["flow_json"] else {}
        
        dom_pressure = 0.0
        for b, weight in doms:
            c_val = flow_curr.get(b, {})
            p_val = flow_prev.get(b, {})
            net_curr = c_val.get("net", 0) if isinstance(c_val, dict) else c_val
            net_prev = p_val.get("net", 0) if isinstance(p_val, dict) else p_val
            dom_pressure += (net_curr - net_prev) * weight
            
        if lots_per_unit != float("inf"):
            scale_factor = 5.0
            iaf = (dom_pressure / lots_per_unit) * 100.0 * scale_factor
            iaf = max(-100.0, min(100.0, iaf))
            return round(iaf, 1)
            
    return 0.0

def main():
    date_str = "2026-06-12"
    conn = sqlite3.connect("trades.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT win_price, flow_json, timestamp, bar_time 
        FROM bar_history 
        WHERE date_str = ? 
        ORDER BY timestamp ASC
    """, (date_str,))
    rows = c.fetchall()
    conn.close()
    
    print(f"Loaded {len(rows)} bars for {date_str}.")
    if not rows:
        return
        
    iaf_values = []
    times = []
    prices = []
    
    # Reconstruct historical bars list and calculate IAF step-by-step
    bars_list = []
    for idx, r in enumerate(rows):
        bars_list.append({
            "win_price": r["win_price"],
            "flow_json": r["flow_json"]
        })
        
        # Calculate IAF for the current slice
        val = calculate_flow_acceleration_for_slice(bars_list)
        iaf_values.append(val)
        times.append(r["bar_time"])
        prices.append(r["win_price"])
        
        if idx % 10 == 0 or idx == len(rows) - 1:
            print(f"Bar {r['bar_time']}: Price = {r['win_price']}, IAF = {val}")
            
    # Save chart plot using Matplotlib
    plt.style.use('dark_background')
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True, gridspec_kw={'height_ratios': [1, 2]})
    
    # 1. Price Chart
    ax1.plot(times, prices, color='#00d4ff', linewidth=1.5, label='WIN Price')
    ax1.set_title(f'Preco WIN & Indice de Aceleracao do Fluxo (IAF) - {date_str}', fontsize=14, fontweight='bold', pad=10)
    ax1.ylabel_margin = 0.1
    ax1.set_ylabel('Preco (pts)', color='#00d4ff', fontweight='bold')
    ax1.tick_params(axis='y', labelcolor='#00d4ff')
    ax1.grid(True, color='#1c2e3a', linestyle='--', alpha=0.5)
    
    # 2. IAF Chart
    # Fill background zones for buying/selling acceleration
    ax2.axhspan(40.0, 100.0, color='#00e87a', alpha=0.1, label='Aceleracao de Compra (>= 40)')
    ax2.axhspan(-100.0, -40.0, color='#ff3860', alpha=0.1, label='Aceleracao de Venda (<= -40)')
    ax2.axhspan(-40.0, 40.0, color='#6f8a9c', alpha=0.03, label='Neutro')
    
    # Reference lines
    ax2.axhline(40.0, color='#00e87a', linestyle='--', linewidth=0.8, alpha=0.7)
    ax2.axhline(-40.0, color='#ff3860', linestyle='--', linewidth=0.8, alpha=0.7)
    ax2.axhline(0.0, color='#6f8a9c', linestyle='-', linewidth=0.5, alpha=0.5)
    
    # Plot IAF line
    ax2.plot(times, iaf_values, color='#ffcc00', linewidth=2, label='IAF (Lookback 25m)')
    
    # Color-code data points
    colors = []
    for val in iaf_values:
        if val >= 40.0:
            colors.append('#00e87a')
        elif val <= -40.0:
            colors.append('#ff3860')
        else:
            colors.append('#ffcc00')
            
    ax2.scatter(times, iaf_values, color=colors, s=15, zorder=3)
    
    ax2.set_ylim(-110, 110)
    ax2.set_ylabel('IAF Score', color='#ffcc00', fontweight='bold')
    ax2.tick_params(axis='y', labelcolor='#ffcc00')
    ax2.grid(True, color='#1c2e3a', linestyle='--', alpha=0.5)
    ax2.legend(loc='upper left', framealpha=0.8, facecolor='#0c1218', edgecolor='#1c2e3a')
    
    # Format X-axis ticks (showing every 10th label to avoid overlapping)
    plt.xticks(range(0, len(times), 10), [times[i] for i in range(0, len(times), 10)], rotation=45)
    plt.xlabel('Hora (M5)', fontweight='bold')
    
    plt.tight_layout()
    
    # Save the chart as an artifact
    output_dir = r"C:\Users\ryzen\.gemini\antigravity-ide\brain\3a757b4a-3478-4634-be83-d836ababff6e"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "iaf_history_20260612.png")
    plt.savefig(output_path, dpi=150)
    plt.close()
    
    print(f"Chart saved successfully at {output_path}")

if __name__ == "__main__":
    main()
