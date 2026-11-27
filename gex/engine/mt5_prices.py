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
import json
import time
import MetaTrader5 as mt5
from datetime import datetime, timezone, timedelta

# Último ratio ETF→CFD válido por símbolo (usado se o MT5 estiver offline no run).
RATIO_CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "etf_ratio_cache.json")
RATIO_CACHE_MAX_AGE_DAYS = 5


def _load_ratio_cache():
    try:
        with open(RATIO_CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_ratio(symbol_mt5, etf_spot_price, ratio):
    try:
        cache = _load_ratio_cache()
        cache[symbol_mt5] = {"ratio": ratio, "etf_spot": etf_spot_price,
                             "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        os.makedirs(os.path.dirname(RATIO_CACHE_PATH), exist_ok=True)
        with open(RATIO_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        print(f"      [Ratio Cache] Aviso: não consegui salvar ratio de {symbol_mt5}: {e}")


def _cached_ratio(symbol_mt5, etf_spot_price):
    """Ratio em cache se recente (<= 5 dias) e se a base do ETF for compatível (±25%)."""
    entry = _load_ratio_cache().get(symbol_mt5)
    if not entry:
        return None, None
    try:
        age = datetime.now() - datetime.strptime(entry["saved_at"], "%Y-%m-%d %H:%M:%S")
        base = float(entry.get("etf_spot") or 0)
        if age.days > RATIO_CACHE_MAX_AGE_DAYS:
            return None, None
        if base > 0 and not (0.75 <= etf_spot_price / base <= 1.25):
            return None, None
        return float(entry["ratio"]), entry["saved_at"]
    except Exception:
        return None, None

MT5_PATH = os.environ.get("MW_MT5_PATH", "C:/Program Files/MetaTrader 5/terminal64.exe")
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


DXY_SYMBOL_ALIASES = ("DXY", "USDX", "DX")
# UUP ~29–30 e DXY ~100–110; fora dessa faixa o ratio não é crível.
DXY_RATIO_MIN = 3.0
DXY_RATIO_MAX = 4.0


def _symbol_candidates(symbol_mt5):
    """Tickmill usa DXY para o Dollar Index; USDX não existe nesse broker."""
    symbol_mt5 = (symbol_mt5 or "").strip()
    key = symbol_mt5.upper()
    seq = DXY_SYMBOL_ALIASES if key in DXY_SYMBOL_ALIASES else (symbol_mt5,)
    out, seen = [], set()
    # Se o pedido já é um alias conhecido, tenta ele primeiro.
    if symbol_mt5:
        seq = (symbol_mt5,) + tuple(s for s in seq if s.upper() != key)
    for name in seq:
        if name and name not in seen:
            out.append(name)
            seen.add(name)
    return out


def _public_dxy_spot():
    """Último fechamento oficial do ICE Dollar Index (Yahoo DX-Y.NYB)."""
    url = "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB?interval=1d&range=10d"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/142.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }
    try:
        import requests
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        result = resp.json()["chart"]["result"][0]
        closes = result["indicators"]["quote"][0]["close"]
        stamps = result["timestamp"]
        last_px, last_ts = None, None
        for ts, px in zip(stamps, closes):
            if px is not None and float(px) > 0:
                last_px, last_ts = float(px), ts
        if last_px is None:
            meta = result.get("meta") or {}
            last_px = float(meta.get("regularMarketPrice") or 0) or None
        if last_px and last_px > 50:
            when = datetime.fromtimestamp(last_ts, timezone.utc).strftime("%Y-%m-%d") if last_ts else "n/d"
            return last_px, when
    except Exception as e:
        print(f"      [DXY Público] Falha ao buscar DX-Y.NYB no Yahoo: {e}")
    return None, None


def get_synchronized_etf_ratio(etf_spot_price, symbol_mt5, fallback_ratio, terminal_path=TICKMILL_MT5_PATH):
    """
    Calcula a razão de conversão perfeitamente sincronizada entre o CFD do MT5
    e o preço Spot de fechamento de NY do ETF/Índice correspondente.

    Durante o pré-mercado / madrugada (antes da abertura de NY às 09:30 EST / 16:30 broker time),
    o preço Spot do ETF/Índice (CBOE/Yahoo) refere-se ao fechamento de ontem às 16:00 EST (22:55 broker time).
    Por isso, sincronizamos o ratio usando a barra do MT5 do fechamento de NY (22:55 broker time),
    evitando que o movimento overnight desloque os strikes!

    :param etf_spot_price: Preço spot de fechamento do ETF/Índice (ex: SPY $770.16 ou SPX 7722.60)
    :param symbol_mt5: Símbolo correspondente no MT5 (ex: 'US500')
    :param fallback_ratio: Razão padrão caso o MT5 esteja offline
    :return: (float ratio, float mt5_current_price, str status_msg)
    """
    if not etf_spot_price or etf_spot_price <= 0:
        return fallback_ratio, None, "Erro: Preço Spot ETF inválido"

    paths_to_try = [p for p in [terminal_path, MT5_PATH] if os.path.exists(p)]
    current_mt5_price = None
    sync_mt5_price = None
    sync_time_str = "Agora"
    resolved_symbol = symbol_mt5

    for p in paths_to_try:
        if not mt5.initialize(p):
            continue

        found = False
        for cand in _symbol_candidates(symbol_mt5):
            mt5.symbol_select(cand, True)
            rates = mt5.copy_rates_from_pos(cand, mt5.TIMEFRAME_M5, 0, 350)
            if rates is None or len(rates) == 0:
                continue

            last_bar = rates[-1]
            current_mt5_price = float(last_bar[4])
            last_dt = datetime.fromtimestamp(last_bar[0], timezone.utc)

            # O relógio do broker (Tickmill) é sempre Nova York + 7h (GMT+3 no verão, GMT+2 no inverno),
            # então o fechamento de NY (16:00 ET) é SEMPRE 23:00 broker e a última vela M5 do pregão
            # começa às 22:55 broker — o ano inteiro. (Antes aceitava 23:55, que é after-hours.)
            ny_close_bar = None
            for b in reversed(rates):
                dt = datetime.fromtimestamp(b[0], timezone.utc)
                if dt.date() < last_dt.date() and dt.hour == 22 and dt.minute == 55:
                    ny_close_bar = b
                    break

            # Se ainda não abriu o pregão regular de NY hoje (< 16:35 broker time) ou em replay matinal,
            # usa o fechamento de NY de ontem (22:55 broker) para preservar Zero-Repainting nas walls:
            force_ny_close = os.environ.get("GEX_USE_MORNING_ARCHIVE") == "1" or bool(os.environ.get("GEX_ARCHIVE_DATE"))
            if ny_close_bar is not None and (force_ny_close or last_dt.hour < 16 or (last_dt.hour == 16 and last_dt.minute < 35)):
                sync_mt5_price = float(ny_close_bar[4])
                ny_dt = datetime.fromtimestamp(ny_close_bar[0], timezone.utc)
                sync_time_str = f"NY Close {ny_dt.strftime('%Y-%m-%d %H:%M')} Broker"
            else:
                sync_mt5_price = current_mt5_price
                sync_time_str = f"Live {last_dt.strftime('%H:%M:%S')} Broker"

            resolved_symbol = cand
            found = True
            break

        mt5.shutdown()
        if found:
            break

    if sync_mt5_price and sync_mt5_price > 0:
        ratio = sync_mt5_price / etf_spot_price
        _save_ratio(resolved_symbol, etf_spot_price, ratio)
        if resolved_symbol != symbol_mt5:
            _save_ratio(symbol_mt5, etf_spot_price, ratio)
        alias_note = f" [símbolo MT5: {resolved_symbol}]" if resolved_symbol != symbol_mt5 else ""
        msg = (
            f"MT5 Sync ({resolved_symbol}: {sync_mt5_price:.4f} @ {sync_time_str} | Live: {current_mt5_price:.4f}) "
            f"/ Base Spot ({etf_spot_price:.4f}) -> Ratio: {ratio:.6f}{alias_note}"
        )
        return ratio, current_mt5_price, msg

    # DXY: fonte pública oficial (ICE via Yahoo) antes do cache/teórico.
    if (symbol_mt5 or "").upper() in DXY_SYMBOL_ALIASES:
        pub_px, pub_when = _public_dxy_spot()
        if pub_px and pub_px > 0:
            ratio = pub_px / etf_spot_price
            if DXY_RATIO_MIN <= ratio <= DXY_RATIO_MAX:
                _save_ratio(symbol_mt5, etf_spot_price, ratio)
                _save_ratio("DXY", etf_spot_price, ratio)
                msg = (
                    f"[DXY Público] Yahoo DX-Y.NYB {pub_px:.4f} ({pub_when}) "
                    f"/ UUP {etf_spot_price:.4f} -> Ratio: {ratio:.6f}"
                )
                print(f"      {msg}")
                return ratio, pub_px, msg
            print(
                f"      [DXY Público] Ratio {ratio:.6f} fora da faixa "
                f"{DXY_RATIO_MIN:.1f}–{DXY_RATIO_MAX:.1f}; ignorado."
            )

    cached, saved_at = _cached_ratio(symbol_mt5, etf_spot_price)
    if not cached and (symbol_mt5 or "").upper() in DXY_SYMBOL_ALIASES:
        for alias in DXY_SYMBOL_ALIASES:
            cached, saved_at = _cached_ratio(alias, etf_spot_price)
            if cached:
                break
    if cached:
        msg = f"[Ratio em Cache] MT5 offline para {symbol_mt5}. Usando último ratio válido ({saved_at}): {cached:.6f}"
        print(f"      {msg}")
        return cached, None, msg
    msg = (f"[ATENÇÃO - Fallback Teórico] MT5 offline para {symbol_mt5} e sem ratio recente em cache. "
           f"Usando ratio fixo {fallback_ratio:.6f} — níveis podem estar deslocados!")
    print(f"      {msg}")
    return fallback_ratio, None, msg


def _get_expected_trading_day():
    """
    Retorna a data esperada para o processamento do dia de hoje,
    respeitando feriados nacionais e a API de workday da B3.
    """
    try:
        from gex.engine.main import get_expected_trading_day
        return get_expected_trading_day()
    except Exception:
        pass
    now = datetime.now()
    prev = now.date() - timedelta(days=1)
    while prev.weekday() >= 5:
        prev -= timedelta(days=1)
    return prev


# Feriados nacionais fixos no Brasil (mês, dia) para cálculo determinístico de rolagem B3
_BR_HOLIDAYS_FIXED = {
    (1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (11, 20), (12, 25)
}


def _is_b3_business_day(d):
    return d.weekday() < 5 and (d.month, d.day) not in _BR_HOLIDAYS_FIXED


def _next_b3_business_day(d):
    nxt = d + timedelta(days=1)
    while not _is_b3_business_day(nxt):
        nxt += timedelta(days=1)
    return nxt


def get_b3_win_expiry_date(year, month):
    """
    Retorna a data de vencimento do contrato futuro de Índice (WIN/IND) na B3
    para um mês par (2, 4, 6, 8, 10, 12): a quarta-feira mais próxima do dia 15.
    Se cair em feriado nacional fixo, avança para o próximo dia útil.
    """
    d_15 = datetime(year, month, 15).date()
    days_to_wed = 2 - d_15.weekday()  # 2 = Quarta-feira
    wed = d_15 + timedelta(days=days_to_wed)
    candidates = [wed - timedelta(weeks=1), wed, wed + timedelta(weeks=1)]
    expiry = min(candidates, key=lambda d: abs((d - d_15).days))
    while not _is_b3_business_day(expiry):
        expiry += timedelta(days=1)
    return expiry


def get_b3_expected_win_contract(ref_date=None):
    """
    Determina de forma determinística o contrato WIN ativo para o pregão de `ref_date`,
    antecipando a rolagem às 07:30 da manhã na quarta-feira de vencimento (meses pares).

    Retorna:
        tuple: (expected_symbol, expiring_symbol, expiry_date)
               Ex: ('WINZ26', 'WINV26', date(2026, 12, 16)) em 2026-10-14.
    """
    if ref_date is None:
        ref_date = datetime.now().date()
    elif isinstance(ref_date, datetime):
        ref_date = ref_date.date()

    # Se hoje não é dia útil (ex: domingo), projeta para o próximo pregão útil
    effective_date = ref_date if _is_b3_business_day(ref_date) else _next_b3_business_day(ref_date)

    win_codes = {2: 'G', 4: 'J', 6: 'M', 8: 'Q', 10: 'V', 12: 'Z'}
    y = effective_date.year
    m = effective_date.month

    expiring_symbol = None
    if m % 2 == 1:
        active_m = m + 1
        active_y = y
    else:
        exp_this_month = get_b3_win_expiry_date(y, m)
        if effective_date >= exp_this_month:
            # No dia do vencimento (ou após), o mercado já rola para o próximo mês par logo na abertura!
            expiring_symbol = f"WIN{win_codes[m]}{str(y)[2:]}"
            if m == 12:
                active_m = 2
                active_y = y + 1
            else:
                active_m = m + 2
                active_y = y
        else:
            active_m = m
            active_y = y

    active_expiry = get_b3_win_expiry_date(active_y, active_m)
    expected_symbol = f"WIN{win_codes[active_m]}{str(active_y)[2:]}"
    return expected_symbol, expiring_symbol, active_expiry


def get_b3_expected_wdo_contract(ref_date=None):
    """
    Determina de forma determinística o contrato WDO ativo para o pregão de `ref_date`.
    Na B3, o WDO vence no 1º dia útil do mês, mas a liquidez inteira rola no
    ÚLTIMO dia útil do mês anterior (dia de formação da PTAX de liquidação).

    Retorna:
        tuple: (expected_symbol, expiring_symbol)
               Ex: ('WDOZ26', 'WDOX26') em 2026-10-30 (último dia útil de outubro) e novembro.
    """
    if ref_date is None:
        ref_date = datetime.now().date()
    elif isinstance(ref_date, datetime):
        ref_date = ref_date.date()

    effective_date = ref_date if _is_b3_business_day(ref_date) else _next_b3_business_day(ref_date)
    next_trading_date = _next_b3_business_day(effective_date)

    wdo_codes = {
        1: 'F', 2: 'G', 3: 'H', 4: 'J', 5: 'K', 6: 'M',
        7: 'N', 8: 'Q', 9: 'U', 10: 'V', 11: 'X', 12: 'Z'
    }

    y = effective_date.year
    m = effective_date.month

    # Se o próximo pregão útil já é no mês seguinte, hoje é o último dia útil do mês (Dia de Rolagem do WDO!)
    is_last_bday_of_month = (next_trading_date.month != m)

    if is_last_bday_of_month:
        # Ex: 30/10/2026 -> contrato que está fechando PTAX é Nov (X26), contrato líquido do dia é Dez (Z26)
        exp_m = m + 1
        exp_y = y
        if exp_m > 12:
            exp_m -= 12
            exp_y += 1

        act_m = m + 2
        act_y = y
        if act_m > 12:
            act_m -= 12
            act_y += 1
    else:
        # Dia normal do mês `m`: contrato ativo é `m + 1`; contrato `m` (se no 1º dia útil) está vencendo hoje
        exp_m = m
        exp_y = y
        act_m = m + 1
        act_y = y
        if act_m > 12:
            act_m -= 12
            act_y += 1

    expected_symbol = f"WDO{wdo_codes[act_m]}{str(act_y)[2:]}"
    expiring_symbol = f"WDO{wdo_codes[exp_m]}{str(exp_y)[2:]}"
    return expected_symbol, expiring_symbol


def _detect_active_win(ref_date=None):
    """
    Detecta automaticamente o contrato WIN ativo.
    Respeita o calendário oficial de rolagem da B3 (quarta-feira mais próxima do dia 15
    dos meses pares), evitando que às 07h30 da manhã do dia de vencimento o detector
    escolha o contrato que está morrendo por causa do volume D1 do dia anterior.
    """
    expected_win, expiring_win, _ = get_b3_expected_win_contract(ref_date)

    syms = mt5.symbols_get("WIN*")
    if not syms:
        return None

    # 1. Verificar se o contrato esperado pelo calendário oficial B3 está disponível e com cotação no MT5
    if expected_win:
        mt5.symbol_select(expected_win, True)
        tick_exp = mt5.symbol_info_tick(expected_win)
        rates_exp = mt5.copy_rates_from_pos(expected_win, mt5.TIMEFRAME_D1, 0, 2)
        if (tick_exp is not None and tick_exp.last > 0) or (rates_exp is not None and len(rates_exp) > 0):
            return expected_win

    best = None
    best_score = -1
    now_ts = time.time()

    for s in syms:
        # Filtrar: apenas contratos tipo WINM26, WINQ26, etc.
        if not re.match(r'^WIN[A-Z]\d{2}$', s.name):
            continue
        # Nunca selecionar o contrato que está expirando no dia da rolagem
        if expiring_win and s.name == expiring_win:
            continue
        if getattr(s, "expiration_time", 0) > 0 and s.expiration_time < now_ts - 86400:
            continue

        mt5.symbol_select(s.name, True)
        tick = mt5.symbol_info_tick(s.name)

        if tick is None or tick.last == 0:
            continue
        if tick.time > 0 and (now_ts - tick.time) > 10 * 86400:
            continue

        # Score = session_deals (numero de negocios do dia); antes das 09h00 usa tick_volume D1
        score = int(getattr(s, "session_deals", 0) or 0) * 1_000_000
        if score == 0:
            rates = mt5.copy_rates_from_pos(s.name, mt5.TIMEFRAME_D1, 0, 2)
            if rates is not None and len(rates) > 0:
                score = int(rates[-1]["tick_volume"])
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
    # Tenta conectar no terminal B3 que contem os simbolos WIN/IBOV
    paths_to_try = [
        MT5_PATH,
        "C:/Program Files/MetaTrader 5/terminal64.exe",
        TICKMILL_MT5_PATH
    ]
    init_success = False
    for p in paths_to_try:
        if os.path.exists(p) and mt5.initialize(p):
            syms = mt5.symbols_get("WIN*")
            if syms and len(syms) > 0:
                init_success = True
                break
            mt5.shutdown()
            
    if not init_success:
        # Fallback para inicialização genérica se nenhuma rota específica encontrou WIN*
        if mt5.initialize():
            init_success = True
                
    if not init_success:
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


def _mt5_running_safe(path: str) -> bool:
    """Verifica se o terminal já está aberto na sessão do usuário usando helper de core.mt5_client."""
    try:
        from core.mt5_client import _is_mt5_visible_running
    except ImportError:
        import sys
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if root not in sys.path:
            sys.path.insert(0, root)
        try:
            from core.mt5_client import _is_mt5_visible_running
        except ImportError:
            return True
    return _is_mt5_visible_running(path)


def init_mt5_robust(path=None, max_attempts=2):
    """
    Inicializa conexão com o MetaTrader 5 aplicando retries e priorizando o terminal com dados B3 (XP).
    """
    candidate_paths = [
        "C:/Program Files/MetaTrader 5/terminal64.exe",
        "C:/Program Files/MetaTrader 5 Terminal - milhao/terminal64.exe",
    ]
    if path:
        if path in candidate_paths:
            candidate_paths.remove(path)
        candidate_paths.insert(0, path)

    for p in candidate_paths:
        if not os.path.exists(p) or not _mt5_running_safe(p):
            continue
        for _attempt in range(max(1, max_attempts)):
            try:
                if mt5.initialize(p, timeout=3000):
                    info = mt5.terminal_info()
                    if info and info.connected:
                        return True
                    mt5.shutdown()
            except Exception:
                pass
            time.sleep(0.3)

    return False


def get_option_price(ticker, target_hour=16, target_minute=55, max_attempts=3, ref_date=None, allow_stale=True):
    """
    Busca o preco de fechamento de uma opcao no MT5.
    Tenta pegar a vela M5 exata do horario target (ex: 16:55).
    Quando ref_date é informado, restringe a busca às barras daquele pregão;
    com allow_stale=False, retorna None se não houver negócio na data de referência.

    :param ticker: Codigo da opcao (ex: IBOVK120)
    :param ref_date: Data de referência (date, datetime ou 'YYYY-MM-DD') opcional
    :param allow_stale: Se False, ignora barras/ticks de pregões anteriores a ref_date
    :return: float (preco de fechamento) ou None se falhar
    """
    term_info = mt5.terminal_info()
    if term_info is None or not getattr(term_info, "connected", False):
        if not init_mt5_robust(MT5_PATH):
            return None

    target_ref_date = None
    if ref_date is not None:
        if isinstance(ref_date, datetime):
            target_ref_date = ref_date.date()
        elif isinstance(ref_date, str):
            try:
                target_ref_date = datetime.strptime(ref_date[:10], "%Y-%m-%d").date()
            except ValueError:
                target_ref_date = None
        else:
            target_ref_date = ref_date

    mt5.symbol_select(ticker, True)
    # Terminal recem-iniciado (ou simbolo fora do Market Watch): o MT5 so entrega tick/barras
    # alguns instantes depois do symbol_select. Sem essa espera o 1o acesso volta vazio e o IV cai no fallback.
    for _ in range(10):
        _probe = mt5.copy_rates_from_pos(ticker, mt5.TIMEFRAME_M5, 0, 1)
        if _probe is not None and len(_probe) > 0:
            break
        time.sleep(0.5)
    tick = mt5.symbol_info_tick(ticker)

    # 1. Puxar ultimas velas M5 com retry resiliente
    rates = None
    for attempt in range(1, max_attempts + 1):
        rates = mt5.copy_rates_from_pos(ticker, mt5.TIMEFRAME_M5, 0, 500)
        if rates is not None and len(rates) > 0:
            break
        time.sleep(0.5)

    if rates is not None and len(rates) > 0:
        if target_ref_date is not None:
            day_bars = [
                b for b in rates
                if datetime.fromtimestamp(b[0], timezone.utc).date() == target_ref_date
            ]
            if day_bars:
                target_bar = day_bars[-1]
                found_exact = False
                for b in reversed(day_bars):
                    dt = datetime.fromtimestamp(b[0], timezone.utc)
                    if dt.hour == target_hour and dt.minute == target_minute:
                        target_bar = b
                        found_exact = True
                        break
                price = float(target_bar[4])
                if not found_exact:
                    print(f"MT5: {ticker} sem trade M5 as {target_hour}:{target_minute} em {target_ref_date}. Usando ultima M5 (R$ {price:.2f}).")
                else:
                    print(f"MT5: {ticker} preco capturado M5 as {target_hour}:{target_minute} em {target_ref_date} -> R$ {price:.2f}")
                return price
            if not allow_stale:
                rates_d1 = mt5.copy_rates_from_pos(ticker, mt5.TIMEFRAME_D1, 0, 5)
                if rates_d1 is not None and len(rates_d1) > 0:
                    d1_date = datetime.fromtimestamp(rates_d1[-1][0], timezone.utc).date()
                    if d1_date == target_ref_date and float(rates_d1[-1][4]) > 0:
                        price = float(rates_d1[-1][4])
                        print(f"MT5: {ticker} sem M5 em {target_ref_date}. Usando D1 da data -> R$ {price:.2f}")
                        return price
                print(f"MT5: {ticker} sem negocios em {target_ref_date} (ignorado para evitar IV defasada).")
                return None

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
        d1_date = datetime.fromtimestamp(rates_d1[-1][0], timezone.utc).date()
        if target_ref_date is None or allow_stale or d1_date == target_ref_date:
            price = float(rates_d1[-1][4])
            print(f"MT5: {ticker} sem velas M5. Usando fechamento D1 -> R$ {price:.2f}")
            return price

    # 3. Fallback para tick.last (somente quando permite dado fora da data de referência)
    if (target_ref_date is None or allow_stale) and tick is not None and tick.last > 0:
        price = float(tick.last)
        print(f"MT5: {ticker} sem historico de velas. Usando ultimo tick -> R$ {price:.2f}")
        return price

    return None


if __name__ == "__main__":
    f_win, s_ibov, _ = get_mt5_prices()
    if f_win and s_ibov:
        print(f"\nPronto para rodar:")
        print(f"  python -m gex.engine.main {f_win:.0f} {s_ibov:.0f}")
