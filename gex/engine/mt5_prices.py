"""
mt5_prices.py — Busca F_WIN e S_IBOV do MetaTrader 5.

Logica de sincronizacao:
  1. Detecta automaticamente o contrato WIN ativo (maior volume)
  2. Pega o ultimo tick do IBOV (fechamento do indice spot)
  3. Busca a barra M5 do WIN no exato momento do fechamento do IBOV
  4. Retorna o fator sincronizado F_WIN/S_IBOV
"""

import re
import MetaTrader5 as mt5
from datetime import datetime, timezone

MT5_PATH = "C:/Program Files/MetaTrader 5/terminal64.exe"
SYMBOL_IBOV = "IBOV"


def _detect_active_win():
    """
    Detecta automaticamente o contrato WIN ativo.
    Busca todos os simbolos WIN[A-Z]NN e retorna o que tem maior volume.
    
    Calendario de vencimentos WIN (meses pares):
      F=Jan G=Fev H=Mar J=Abr K=Mai M=Jun
      N=Jul Q=Ago U=Set V=Out X=Nov Z=Dez
    """
    syms = mt5.symbols_get("WIN*")
    if not syms:
        return None
    
    best = None
    best_score = -1
    
    for s in syms:
        # Filtrar: apenas contratos tipo WINM26, WINQ26, etc.
        if not re.match(r'^WIN[A-Z]\d{2}$', s.name):
            continue
        
        mt5.symbol_select(s.name, True)
        tick = mt5.symbol_info_tick(s.name)
        
        if tick is None or tick.last == 0:
            continue
        
        # Score = session_deals (numero de negocios do dia)
        score = s.session_deals
        if score > best_score:
            best_score = score
            best = s.name
    
    return best


def get_mt5_prices():
    """
    Conecta ao MT5 e retorna (F_WIN, S_IBOV) sincronizados.
    
    Returns:
        tuple: (f_win, s_ibov) ou (None, None) se falhar
    """
    if not mt5.initialize(MT5_PATH):
        print(f"MT5: Erro ao inicializar ({mt5.last_error()})")
        print(f"     Verifique se o MetaTrader 5 esta aberto.")
        return None, None
    
    # --- Detectar contrato WIN ativo ---
    win_symbol = _detect_active_win()
    if win_symbol is None:
        # Fallback: tentar WIN$N
        mt5.symbol_select("WIN$N", True)
        tick = mt5.symbol_info_tick("WIN$N")
        if tick and tick.last > 0:
            win_symbol = "WIN$N"
        else:
            print("MT5: Nenhum contrato WIN ativo encontrado.")
            mt5.shutdown()
            return None, None
    
    print(f"MT5: Contrato ativo detectado: {win_symbol}")
    
    # --- Busca Sincronizada às 17h (M5) ---
    mt5.symbol_select(SYMBOL_IBOV, True)
    rates_ibov = mt5.copy_rates_from_pos(SYMBOL_IBOV, mt5.TIMEFRAME_M5, 0, 500)
    rates_win = mt5.copy_rates_from_pos(win_symbol, mt5.TIMEFRAME_M5, 0, 500)
    
    if rates_ibov is None or len(rates_ibov) == 0:
        print(f"MT5: {SYMBOL_IBOV} sem dados (M5).")
        mt5.shutdown()
        return None, None
        
    if rates_win is None or len(rates_win) == 0:
        print(f"MT5: {win_symbol} sem dados (M5).")
        mt5.shutdown()
        return None, None

    # Tenta achar a vela das 16:55 (cujo fechamento é as 17:00 exato) iterando de trás pra frente
    # Caso o MT5 esteja sem dados até as 17h, fallback para a última vela do IBOV e sincroniza o WIN
    target_ibov = rates_ibov[-1]
    for b in reversed(rates_ibov):
        dt = datetime.fromtimestamp(b[0], timezone.utc)
        if dt.hour == 16 and dt.minute == 55:
            target_ibov = b
            break
            
    # Procura a vela do WIN com o MESMO timestamp exato
    target_time = target_ibov[0]
    target_win = rates_win[-1]
    for b in reversed(rates_win):
        if b[0] == target_time:
            target_win = b
            break

    s_ibov = float(target_ibov[4])  # Close
    f_win = float(target_win[4])  # Close
    
    ibov_time = datetime.fromtimestamp(target_ibov[0], timezone.utc)
    win_bar_time = datetime.fromtimestamp(target_win[0], timezone.utc)
    sync_method = f"M5 Close das {ibov_time.strftime('%H:%M')}"
    
    # --- Output ---
    factor = f_win / s_ibov
    print(f"MT5: Precos capturados ({sync_method})")
    print(f"  S_IBOV ({SYMBOL_IBOV}):      {s_ibov:.2f}  @ {ibov_time}")
    print(f"  F_WIN  ({win_symbol}):  {f_win:.2f}  @ {win_bar_time}")
    print(f"  Factor:                   {factor:.6f}")
    
    if factor < 1.005 or factor > 1.040:
        print(f"  ALERTA: Factor {factor:.4f} fora do range (1.005 - 1.040)!")
    
    mt5.shutdown()
    return f_win, s_ibov


def get_option_price(ticker, target_hour=16, target_minute=55):
    """
    Busca o preco de fechamento de uma opcao no MT5.
    Tenta pegar a vela M5 exata do horario target (ex: 16:55).
    Se nao houver liquidez no momento exato, pega a ultima disponivel do dia.
    
    :param ticker: Codigo da opcao (ex: IBOVK120)
    :return: float (preco de fechamento) ou None se falhar
    """
    if not mt5.initialize(MT5_PATH):
        return None
        
    mt5.symbol_select(ticker, True)
    
    # Verifica se o simbolo existe e tem last price hoje
    tick = mt5.symbol_info_tick(ticker)
    if tick is None:
        return None
        
    # Puxar ultimas velas M5
    rates = mt5.copy_rates_from_pos(ticker, mt5.TIMEFRAME_M5, 0, 500)
    if rates is None or len(rates) == 0:
        return None
        
    # Tenta achar a vela especifica
    target_bar = rates[-1]
    found_exact = False
    
    for b in reversed(rates):
        dt = datetime.fromtimestamp(b[0], timezone.utc)
        if dt.hour == target_hour and dt.minute == target_minute:
            target_bar = b
            found_exact = True
            break
            
    # O preco de fechamento e o indice 4 na tupla do copy_rates
    price = float(target_bar[4])
    
    if not found_exact:
        print(f"MT5: {ticker} sem trade as {target_hour}:{target_minute}. Usando ultima (R$ {price:.2f}).")
    else:
        print(f"MT5: {ticker} preco capturado as {target_hour}:{target_minute} -> R$ {price:.2f}")
        
    return price


if __name__ == "__main__":
    f_win, s_ibov = get_mt5_prices()
    if f_win and s_ibov:
        print(f"\nPronto para rodar:")
        print(f"  python -m gex.engine.main {f_win:.0f} {s_ibov:.0f}")
