import MetaTrader5 as mt5
from datetime import datetime, timezone

if not mt5.initialize("C:/Program Files/MetaTrader 5/terminal64.exe"):
    print("Failed to initialize MT5")
    exit()

rates_ibov = mt5.copy_rates_from_pos("IBOV", mt5.TIMEFRAME_M5, 0, 500)
rates_win = mt5.copy_rates_from_pos("WINM26", mt5.TIMEFRAME_M5, 0, 500)

print(f"rates_ibov len: {len(rates_ibov)}")
print(f"rates_win len: {len(rates_win)}")

for b in reversed(rates_ibov):
    dt = datetime.fromtimestamp(b[0], timezone.utc)
    if dt.hour == 16 and dt.minute == 55:
        print(f"Found IBOV 16:55 candidate: {dt} | close={b[4]}")
        target_time = b[0]
        for wb in reversed(rates_win):
            if wb[0] == target_time:
                print(f"  Matched WIN 16:55 at: {datetime.fromtimestamp(wb[0], timezone.utc)} | close={wb[4]}")
                break

mt5.shutdown()
