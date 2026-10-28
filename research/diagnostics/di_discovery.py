# research/di_discovery.py
"""
DI Futures Contract Discovery — Phase 1
========================================
Connects to MT5 and discovers all available DI1 futures contracts.
Reports on liquidity, data availability, and contract expiry.

Usage: python research/di_discovery.py
Requires: MT5 terminal open
"""
import os
import sys
import json
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import MetaTrader5 as mt5
import numpy as np

# Force unbuffered output on Windows
import functools
print = functools.partial(print, flush=True)
from core.config import MT5_PATH

# ─── DI contract month codes ────────────────────────────────────────────────
MONTH_CODES = {
    'F': 'Jan', 'G': 'Feb', 'H': 'Mar', 'J': 'Apr',
    'K': 'May', 'M': 'Jun', 'N': 'Jul', 'Q': 'Aug',
    'U': 'Sep', 'V': 'Oct', 'X': 'Nov', 'Z': 'Dec'
}

MONTH_NUMBERS = {
    'F': 1, 'G': 2, 'H': 3, 'J': 4,
    'K': 5, 'M': 6, 'N': 7, 'Q': 8,
    'U': 9, 'V': 10, 'X': 11, 'Z': 12
}


def parse_di_symbol(symbol: str) -> dict:
    """Parse DI symbol name into components.
    
    Examples: DI1F26 -> {month: Jan, year: 2026, code: F}
              DI1N25 -> {month: Jul, year: 2025, code: N}
    """
    name = symbol.upper()
    # Try patterns: DI1F26, DI1F2026, DIF26, etc.
    for prefix in ['DI1', 'DI']:
        if name.startswith(prefix):
            rest = name[len(prefix):]
            if len(rest) >= 2:
                code = rest[0]
                year_str = rest[1:]
                if code in MONTH_CODES:
                    try:
                        year = int(year_str)
                        if year < 100:
                            year += 2000
                        return {
                            'symbol': symbol,
                            'month_code': code,
                            'month_name': MONTH_CODES[code],
                            'month_num': MONTH_NUMBERS[code],
                            'year': year,
                            'expiry_label': f"{MONTH_CODES[code]}/{year}",
                        }
                    except ValueError:
                        pass
    return {'symbol': symbol, 'month_code': '?', 'month_name': '?', 'year': 0, 'expiry_label': '?'}


def discover_di_contracts():
    """Main discovery function."""
    
    print("=" * 65)
    print("  DI FUTURES CONTRACT DISCOVERY — Phase 1")
    print("=" * 65)
    print()
    
    # ── Connect to MT5 ───────────────────────────────────────────────
    kwargs = {}
    if MT5_PATH:
        kwargs["path"] = MT5_PATH
    
    if not mt5.initialize(**kwargs):
        print(f"[ERRO] Falha ao conectar MT5: {mt5.last_error()}")
        print("       Verifique se o MetaTrader 5 está aberto.")
        return None
    
    info = mt5.terminal_info()
    print(f"[MT5] Conectado — {info.name}")
    print(f"[MT5] Path: {info.path}")
    print()
    
    # ── Search for DI symbols ────────────────────────────────────────
    print("Buscando símbolos DI...")
    
    # Try multiple search patterns
    all_symbols = set()
    for pattern in ["*DI1*", "*DI*", "*di1*"]:
        symbols = mt5.symbols_get(pattern)
        if symbols:
            for s in symbols:
                name = s.name.upper()
                # Filter to only DI1 futures (not DIJ, DIDI, etc.)
                if 'DI1' in name or (name.startswith('DI') and len(name) <= 8):
                    all_symbols.add(s.name)
    
    if not all_symbols:
        print("[AVISO] Nenhum símbolo DI encontrado!")
        print("        Verificando todos os símbolos disponíveis...")
        all_mt5_symbols = mt5.symbols_get()
        if all_mt5_symbols:
            # List all symbols that might be interest rate related
            rate_symbols = []
            for s in all_mt5_symbols:
                name = s.name.upper()
                if any(kw in name for kw in ['DI', 'JURO', 'RATE', 'SELIC', 'CDI']):
                    rate_symbols.append(s.name)
            if rate_symbols:
                print(f"  Símbolos possivelmente relacionados a juros:")
                for s in sorted(rate_symbols):
                    print(f"    - {s}")
            else:
                print("  Nenhum símbolo de juros encontrado.")
                print(f"  Total de símbolos no terminal: {len(all_mt5_symbols)}")
                # Show first 50 symbols for reference
                print(f"  Primeiros 50 símbolos:")
                for s in sorted(all_mt5_symbols, key=lambda x: x.name)[:50]:
                    print(f"    - {s.name}")
        mt5.shutdown()
        return None
    
    print(f"  Encontrados {len(all_symbols)} símbolos DI")
    print()
    
    # ── Analyze each contract ────────────────────────────────────────
    contracts = []
    
    for idx, sym_name in enumerate(sorted(all_symbols)):
        print(f"  [{idx+1}/{len(all_symbols)}] Analisando {sym_name}...", end=" ")
        
        try:
            info_sym = mt5.symbol_info(sym_name)
            if info_sym is None:
                print("SKIP (sem info)")
                continue
            
            parsed = parse_di_symbol(sym_name)
            
            # Enable symbol for data access
            if not info_sym.visible:
                mt5.symbol_select(sym_name, True)
            
            # Get last tick
            tick = mt5.symbol_info_tick(sym_name)
            last_tick_time = None
            last_price = 0.0
            spread_pts = 0.0
            if tick:
                last_tick_time = datetime.fromtimestamp(tick.time)
                last_price = tick.last if tick.last > 0 else tick.bid
                spread_pts = tick.ask - tick.bid if tick.ask > 0 and tick.bid > 0 else 0
            
            # Try to get M5 bars
            bars_m5 = mt5.copy_rates_from_pos(sym_name, mt5.TIMEFRAME_M5, 0, 500)
            bars_count = len(bars_m5) if bars_m5 is not None else 0
            
            # Calculate average volume from recent bars
            avg_volume = 0.0
            if bars_m5 is not None and len(bars_m5) > 0:
                volumes = [r['tick_volume'] for r in bars_m5[-100:]]
                avg_volume = np.mean(volumes)
            
            # Get daily bars for longer-term volume
            bars_d1 = mt5.copy_rates_from_pos(sym_name, mt5.TIMEFRAME_D1, 0, 30)
            avg_daily_volume = 0.0
            if bars_d1 is not None and len(bars_d1) > 0:
                daily_volumes = [r['tick_volume'] for r in bars_d1]
                avg_daily_volume = np.mean(daily_volumes)
            
            # Determine if contract has recent data
            has_recent_data = False
            if last_tick_time:
                age = datetime.now() - last_tick_time
                has_recent_data = age < timedelta(days=3)  # Allow weekends
            
            contract = {
                **parsed,
                'last_tick': last_tick_time.isoformat() if last_tick_time else None,
                'last_price': last_price,
                'spread': spread_pts,
                'bars_m5_available': bars_count,
                'avg_m5_volume': round(avg_volume, 1),
                'avg_daily_volume': round(avg_daily_volume, 1),
                'has_recent_data': has_recent_data,
                'point': info_sym.point,
                'digits': info_sym.digits,
                'trade_mode': info_sym.trade_mode,
                'description': info_sym.description if hasattr(info_sym, 'description') else '',
            }
            
            contracts.append(contract)
            
            status = "[OK]" if has_recent_data else "[--]"
            print(f"{status} | Venc: {parsed['expiry_label']:10s} | "
                  f"Preco: {last_price:>10.2f} | Vol M5: {avg_volume:>8.1f} | "
                  f"Barras: {bars_count:>4d} | "
                  f"{'ATIVO' if has_recent_data else 'SEM DADOS'}")
        
        except Exception as e:
            print(f"ERRO: {e}")
    
    # ── Sort by liquidity ────────────────────────────────────────────
    active_contracts = [c for c in contracts if c['has_recent_data']]
    active_contracts.sort(key=lambda c: c['avg_daily_volume'], reverse=True)
    
    inactive_contracts = [c for c in contracts if not c['has_recent_data']]
    
    # ── Generate report ──────────────────────────────────────────────
    print()
    print("=" * 65)
    print("  RELATÓRIO DE CONTRATOS DI")
    print("=" * 65)
    print()
    print(f"  Total encontrados: {len(contracts)}")
    print(f"  Com dados ativos:  {len(active_contracts)}")
    print(f"  Inativos:          {len(inactive_contracts)}")
    print()
    
    if active_contracts:
        print("  TOP CONTRATOS POR LIQUIDEZ:")
        print("  " + "-" * 60)
        for i, c in enumerate(active_contracts[:10], 1):
            print(f"  #{i:2d} {c['symbol']:12s} | {c['expiry_label']:10s} | "
                  f"Preço: {c['last_price']:>10.2f} | "
                  f"Vol Diário: {c['avg_daily_volume']:>10.1f}")
        print()
        
        # Recommendation
        top = active_contracts[0]
        print(f"  >>> RECOMENDACAO: {top['symbol']} ({top['expiry_label']})")
        print(f"     Maior liquidez com volume diário médio de {top['avg_daily_volume']:.0f}")
        if len(active_contracts) >= 3:
            top3 = [c['symbol'] for c in active_contracts[:3]]
            print(f"     Top 3 para análise de cointegração: {', '.join(top3)}")
    
    # ── Save report ──────────────────────────────────────────────────
    report_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "reports")
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, "di_contracts_discovery.txt")
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("DI FUTURES CONTRACT DISCOVERY REPORT\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n")
        f.write(f"MT5 Terminal: {info.name}\n")
        f.write("=" * 70 + "\n\n")
        
        f.write(f"Total contracts found: {len(contracts)}\n")
        f.write(f"Active (with data):    {len(active_contracts)}\n")
        f.write(f"Inactive:              {len(inactive_contracts)}\n\n")
        
        if active_contracts:
            f.write("ACTIVE CONTRACTS (sorted by liquidity):\n")
            f.write("-" * 70 + "\n")
            f.write(f"{'#':>3s} {'Symbol':12s} {'Expiry':10s} {'Price':>12s} {'Vol M5':>10s} {'Vol D1':>12s} {'Bars M5':>8s}\n")
            f.write("-" * 70 + "\n")
            for i, c in enumerate(active_contracts, 1):
                f.write(f"{i:3d} {c['symbol']:12s} {c['expiry_label']:10s} "
                       f"{c['last_price']:12.2f} {c['avg_m5_volume']:10.1f} "
                       f"{c['avg_daily_volume']:12.1f} {c['bars_m5_available']:8d}\n")
            f.write("\n")
        
        if inactive_contracts:
            f.write("\nINACTIVE CONTRACTS:\n")
            f.write("-" * 70 + "\n")
            for c in inactive_contracts:
                f.write(f"  {c['symbol']:12s} {c['expiry_label']:10s} — sem dados recentes\n")
        
        f.write(f"\n\nRECOMMENDATION:\n")
        if active_contracts:
            f.write(f"  Best single contract: {active_contracts[0]['symbol']}\n")
            if len(active_contracts) >= 3:
                top3 = [c['symbol'] for c in active_contracts[:3]]
                f.write(f"  Top 3 for analysis:   {', '.join(top3)}\n")
        else:
            f.write("  No active DI contracts found in MT5.\n")
    
    print(f"\n  Relatorio salvo em: {report_path}")
    
    # ── Save JSON for Phase 2 ────────────────────────────────────────
    json_path = os.path.join(report_dir, "di_contracts.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'active_contracts': active_contracts,
            'inactive_contracts': [c['symbol'] for c in inactive_contracts],
            'recommendation': active_contracts[0]['symbol'] if active_contracts else None,
            'top_symbols': [c['symbol'] for c in active_contracts[:5]],
        }, f, indent=2, default=str)
    
    print(f"  JSON para Fase 2: {json_path}")
    
    mt5.shutdown()
    print()
    print("Discovery concluída!")
    
    return {
        'active': active_contracts,
        'inactive': inactive_contracts,
    }


if __name__ == "__main__":
    discover_di_contracts()
