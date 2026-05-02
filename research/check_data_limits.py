import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import MetaTrader5 as mt5
from core.config import SYMBOL_A, SYMBOL_B, DI_SYMBOL, TIMEFRAME, MT5_PATH
import datetime

def init_mt5():
    if not mt5.initialize(path=MT5_PATH):
        print("Erro ao inicializar MT5")
        sys.exit()

def check_history(symbol):
    # Try fetching up to 100,000 bars
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, 100000)
    if rates is None or len(rates) == 0:
        return 0, None, None
        
    oldest = datetime.datetime.fromtimestamp(rates[0]['time'])
    newest = datetime.datetime.fromtimestamp(rates[-1]['time'])
    return len(rates), oldest, newest

def main():
    init_mt5()
    print("=== MT5 HISTORICAL DATA LIMITS (M5) ===")
    
    symbols = [SYMBOL_A, SYMBOL_B, DI_SYMBOL, "DI1F29", "DI1F33"]
    
    for s in symbols:
        count, old, new = check_history(s)
        if count > 0:
            print(f"[{s:8s}] Barras: {count:6d} | Mais Antiga: {old} | Mais Recente: {new}")
        else:
            print(f"[{s:8s}] NENHUM DADO ENCONTRADO.")
            
    mt5.shutdown()

if __name__ == "__main__":
    main()
