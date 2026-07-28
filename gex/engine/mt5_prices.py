"""
mt5_prices.py — Busca F_WIN e S_IBOV do MetaTrader 5.

Logica de sincronizacao:
  1. Detecta automaticamente o contrato WIN ativo (maior volume)
  2. Pega o ultimo tick do IBOV (fechamento do indice spot)
  3. Busca a barra M5 do WIN no exato momento do fechamento do IBOV
  4. Retorna o fator sincronizado F_WIN/S_IBOV
"""

import os
import re
import time
import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta

MT5_PATH = "C:/Program Files/MetaTrader 5/terminal64.exe"
TICKMILL_MT5_PATH = "C:/Program Files/Tickmill MT5 Terminal/terminal64.exe"
SYMBOL_IBOV = "IBOV"


def get_global_mt5_price(symbol_mt5, terminal_path=TICKMILL_MT5_PATH):
    """
    Busca o preço de fechamento do último bar M1/M5 do símbolo no MT5 da corretora (ex: US500, USTEC, US30, XAUUSD, BTCUSD).
    Tenta primeiro no terminal Tickmill, com fallback para o terminal padrão se necessário.
    
    :param symbol_mt5: Código do ativo no MT5 (ex: 'US500', 'USTEC', 'US30', 'XAUUSD', 'BTCUSD', 'EURUSD', 'GBPUSD', 'USDJPY')
    :return: (float price, datetime bar_time) ou (None, None) se falhar
    """
    paths_to_try = [p for p in [terminal_path, MT5_PATH] if os.path.exists(p)]
    
    for p in paths_to_try:
        if not mt5.initialize(p):
            continue
            
        mt5.symbol_select(symbol_mt5, True)
        rates = mt5.copy_rates_from_pos(symbol_mt5, mt5.TIMEFRAME_M1, 0, 5)
        if rates is None or len(rates) == 0:
            rates = mt5.copy_rates_from_pos(symbol_mt5, mt5.TIMEFRAME_M5, 0, 5)
            
        if rates is not None and len(rates) > 0:
            last_bar = rates[-1]
            price = float(last_bar[4])  # Close
            bar_time = datetime.fromtimestamp(last_bar[0], timezone.utc)
            mt5.shutdown()
            return price, bar_time
            
        mt5.shutdown()
        
    return None, None


def get_synchronized_etf_ratio(etf_spot_price, symbol_mt5, fallback_ratio):
    """
    Calcula a razão de conversão perfeitamente sincronizada entre o CFD do MT5
    e o preço Spot do ETF correspondente.
    
    :param etf_spot_price: Preço spot atual do ETF (ex: SPY $748.28)
    :param symbol_mt5: Símbolo correspondente no MT5 (ex: 'US500')
    :param fallback_ratio: Razão padrão caso o MT5 esteja offline
    :return: (float ratio, float mt5_price, str status_msg)
    """
    if not etf_spot_price or etf_spot_price <= 0:
        return fallback_ratio, None, "Erro: Preço Spot ETF inválido"
        
    price_mt5, bar_time = get_global_mt5_price(symbol_mt5)
    
    if price_mt5 and price_mt5 > 0:
        ratio = price_mt5 / etf_spot_price
        time_str = bar_time.strftime('%H:%M:%S UTC') if bar_time else 'Agora'
        msg = f"MT5 ({symbol_mt5}: {price_mt5:.2f} @ {time_str}) / ETF Spot (${etf_spot_price:.2f}) -> Ratio: {ratio:.6f}"
        return ratio, price_mt5, msg
    else:
        msg = f"[Fallback Teórico] MT5 offline para {symbol_mt5}. Usando ratio padrão: {fallback_ratio:.6f}"
        return fallback_ratio, None, msg



def _get_expected_trading_day():
    """
    Retorna a data esperada para o processamento do dia de hoje.
    Se já passou das 17:00, o esperado é hoje (se for dia útil).
    Caso contrário, é o dia útil anterior.
    """
    now = datetime.now()
    
    def is_weekday(d):
        return d.weekday() < 5
        
    if now.hour >= 17:
        ref = now.date()
        while not is_weekday(ref):
            ref -= timedelta(days=1)
        return ref
    else:
        prev = now.date() - timedelta(days=1)
        while not is_weekday(prev):
            prev -= timedelta(days=1)
        return prev


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


def get_mt5_prices(max_retries=6, retry_delay=5):
    """
    Conecta ao MT5 e retorna (F_WIN, S_IBOV) sincronizados.
    Aplica um mecanismo de retry com sleep para aguardar a sincronização de rede do terminal.
    
    Returns:
        tuple: (f_win, s_ibov, win_bar_time) ou (None, None, None) se falhar
    """
    if not mt5.initialize(MT5_PATH):
        print(f"MT5: Erro ao inicializar ({mt5.last_error()})")
        print(f"     Verifique se o MetaTrader 5 esta aberto.")
        return None, None, None
    
    # 1. Aguarda a conexão do terminal com o servidor da corretora
    connected = False
    for attempt in range(1, 11):
        info = mt5.terminal_info()
        if info and info.connected:
            connected = True
            break
        print(f"MT5: Aguardando conexão com o servidor da corretora (tentativa {attempt}/10)...")
        time.sleep(2)
        
    if not connected:
        print("MT5: Terminal não está conectado à rede da corretora.")
        mt5.shutdown()
        return None, None, None

    expected_date = _get_expected_trading_day()
    rates_ibov = None
    rates_win = None
    win_symbol = None
    
    # 2. Loop de sincronização de dados históricos (M5)
    for attempt in range(1, max_retries + 1):
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
                return None, None, None

        mt5.symbol_select(SYMBOL_IBOV, True)
        rates_ibov = mt5.copy_rates_from_pos(SYMBOL_IBOV, mt5.TIMEFRAME_M5, 0, 500)
        rates_win = mt5.copy_rates_from_pos(win_symbol, mt5.TIMEFRAME_M5, 0, 500)
        
        if rates_ibov is None or len(rates_ibov) == 0 or rates_win is None or len(rates_win) == 0:
            print(f"MT5: Sem dados de barras M5 (Tentativa {attempt}/{max_retries}). Aguardando...")
            time.sleep(retry_delay)
            continue
            
        # Determina a data da última barra carregada para o IBOV
        last_bar_time = datetime.fromtimestamp(rates_ibov[-1][0], timezone.utc).date()
        
        # Se os dados locais estiverem mais antigos que o dia esperado, aguarda e tenta novamente
        if last_bar_time < expected_date:
            print(f"MT5: Dados locais desatualizados ({last_bar_time} vs esperado {expected_date}). Tentativa {attempt}/{max_retries}...")
            # Força seleção para disparar requisição ao servidor
            mt5.symbol_select(SYMBOL_IBOV, True)
            mt5.symbol_select(win_symbol, True)
            time.sleep(retry_delay)
            continue
            
        # Se os dados estão na data correta (ou posterior), interrompe o loop
        break

    if rates_ibov is None or len(rates_ibov) == 0:
        print(f"MT5: {SYMBOL_IBOV} sem dados (M5) após retentativas.")
        mt5.shutdown()
        return None, None, None
        
    if rates_win is None or len(rates_win) == 0:
        print(f"MT5: {win_symbol} sem dados (M5) após retentativas.")
        mt5.shutdown()
        return None, None, None

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
    return f_win, s_ibov, win_bar_time


def init_mt5_robust(path=None, max_attempts=3):
    """
    Inicializa conexão com o MetaTrader 5 aplicando retries e priorizando o terminal com dados B3 (XP).
    """
    candidate_paths = [
        "C:/Program Files/MetaTrader 5 Terminal/terminal64.exe",
        "C:/Program Files/MetaTrader 5/terminal64.exe"
    ]
    if path and path not in candidate_paths:
        candidate_paths.insert(0, path)
        
    for p in candidate_paths:
        if not os.path.exists(p):
            continue
        for attempt in range(1, max_attempts + 1):
            if mt5.initialize(p):
                info = mt5.terminal_info()
                if info and info.connected:
                    return True
            time.sleep(0.3)
            
    for attempt in range(1, max_attempts + 1):
        if mt5.initialize():
            return True
        time.sleep(0.3)
    return False


def get_option_price(ticker, target_hour=16, target_minute=55, max_attempts=3):
    """
    Busca o preco de fechamento de uma opcao no MT5.
    Tenta pegar a vela M5 exata do horario target (ex: 16:55).
    Se nao houver liquidez no momento exato, pega a ultima M5, D1 ou o tick.last.
    
    :param ticker: Codigo da opcao (ex: IBOVK120)
    :return: float (preco de fechamento) ou None se falhar
    """
    if not init_mt5_robust(MT5_PATH):
        return None
        
    mt5.symbol_select(ticker, True)
    tick = mt5.symbol_info_tick(ticker)
    
    # 1. Puxar ultimas velas M5 com retry resiliente
    rates = None
    for attempt in range(1, max_attempts + 1):
        rates = mt5.copy_rates_from_pos(ticker, mt5.TIMEFRAME_M5, 0, 500)
        if rates is not None and len(rates) > 0:
            break
        time.sleep(0.5)
        
    if rates is not None and len(rates) > 0:
        target_bar = rates[-1]
        found_exact = False
        latest_date = datetime.fromtimestamp(rates[-1][0], timezone.utc).date()
        
        for b in reversed(rates):
            dt = datetime.fromtimestamp(b[0], timezone.utc)
            if dt.date() == latest_date and dt.hour == target_hour and dt.minute == target_minute:
                target_bar = b
                found_exact = True
                break
                
        price = float(target_bar[4])
        if not found_exact:
            print(f"MT5: {ticker} sem trade M5 as {target_hour}:{target_minute} em {latest_date}. Usando ultima M5 (R$ {price:.2f}).")
        else:
            print(f"MT5: {ticker} preco capturado M5 as {target_hour}:{target_minute} em {latest_date} -> R$ {price:.2f}")
        return price
        
    # 2. Fallback para vela D1 (diaria)
    rates_d1 = mt5.copy_rates_from_pos(ticker, mt5.TIMEFRAME_D1, 0, 5)
    if rates_d1 is not None and len(rates_d1) > 0:
        price = float(rates_d1[-1][4])
        print(f"MT5: {ticker} sem velas M5. Usando fechamento D1 -> R$ {price:.2f}")
        return price

    # 3. Fallback para tick.last
    if tick is not None and tick.last > 0:
        price = float(tick.last)
        print(f"MT5: {ticker} sem historico de velas. Usando ultimo tick -> R$ {price:.2f}")
        return price
        
    return None


if __name__ == "__main__":
    f_win, s_ibov, _ = get_mt5_prices()
    if f_win and s_ibov:
        print(f"\nPronto para rodar:")
        print(f"  python -m gex.engine.main {f_win:.0f} {s_ibov:.0f}")
