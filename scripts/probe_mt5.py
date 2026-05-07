r"""
Probe MT5 connection and verify futures symbols are available.

Run from WSL:
    /mnt/c/Users/brenoperucchi/AppData/Local/Microsoft/WindowsApps/py.exe scripts/probe_mt5.py

Or from Windows directly:
    py.exe scripts\probe_mt5.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import MetaTrader5 as mt5
from core.config import MT5_PATH, MT5_PORTABLE, SYMBOL_A, SYMBOL_B, DI_SYMBOL


def main() -> int:
    kwargs = {"path": MT5_PATH, "timeout": 10000}
    if MT5_PORTABLE:
        kwargs["portable"] = True

    print(f"Initializing: path={MT5_PATH}  portable={MT5_PORTABLE}")
    if not mt5.initialize(**kwargs):
        print(f"FAIL initialize: {mt5.last_error()}")
        return 1

    info = mt5.terminal_info()
    acct = mt5.account_info()
    print(f"Terminal: {info.name} | path={info.path} | connected={info.connected}")
    print(f"Account:  login={acct.login} server={acct.server} name={acct.name!r}")

    failed = False
    for sym in (SYMBOL_A, SYMBOL_B, DI_SYMBOL):
        mt5.symbol_select(sym, True)
        s = mt5.symbol_info(sym)
        if s is None:
            print(f"  {sym:10s} -> MISSING ({mt5.last_error()})")
            failed = True
            continue
        tick = mt5.symbol_info_tick(sym)
        bid = tick.bid if tick else None
        ask = tick.ask if tick else None
        print(f"  {sym:10s} -> visible={s.visible} bid={bid} ask={ask} digits={s.digits}")

    mt5.shutdown()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
