import sys
import re
import datetime
import os
import numpy as np
from .b3_parser import get_b3_options_data
from .walls_calculator import calculate_gex_profile
from .firebase_publisher import push_walls_to_firebase
from .mt5_prices import get_mt5_prices, get_option_price
from .black76 import black76_call_price, black76_put_price, implied_volatility_newton_raphson


def _estimate_robust_atm_iv(df_front, current_win, current_ibov, factor, T, r, trading_date):
    """
    Estima a IV ATM de forma robusta usando mediana ponderada por OI de múltiplos
    strikes líquidos (Calls + Puts) negociados na própria `trading_date`.
    """
    atm_band = max(2500.0, current_ibov * 0.025)
    atm_pool = df_front[
        (df_front['oi'] > 0) & ((df_front['strike'] - current_ibov).abs() <= atm_band)
    ].copy()

    if atm_pool.empty:
        return None, []

    atm_pool['dist'] = (atm_pool['strike'] - current_ibov).abs()
    atm_pool = atm_pool.sort_values(by=['dist', 'oi'], ascending=[True, False]).head(12)

    samples = []
    for _, row in atm_pool.iterrows():
        ticker = str(row['ticker'])
        opt_type = str(row['type']).upper()
        strike = float(row['strike'])
        oi = float(row['oi'])
        is_call = (opt_type == 'CALL')

        c_market = get_option_price(ticker, ref_date=trading_date, allow_stale=False)
        if not c_market or c_market <= 0:
            continue

        k_win = strike * factor
        iv_i = float(implied_volatility_newton_raphson(
            C_market=c_market,
            F=current_win,
            K=k_win,
            T=T,
            r=r,
            is_call=is_call,
        ))
        if not (0.08 <= iv_i <= 0.60):
            continue

        calc_px = float(
            black76_call_price(current_win, k_win, T, iv_i, r)
            if is_call
            else black76_put_price(current_win, k_win, T, iv_i, r)
        )
        if abs(calc_px - c_market) > max(50.0, c_market * 0.05):
            continue

        samples.append({
            'ticker': ticker,
            'type': opt_type,
            'strike': strike,
            'oi': oi,
            'price': float(c_market),
            'iv': iv_i,
        })

    if not samples:
        return None, []

    samples_sorted = sorted(samples, key=lambda s: s['iv'])
    total_oi = sum(s['oi'] for s in samples_sorted)
    if total_oi <= 0:
        median_iv = float(np.median([s['iv'] for s in samples_sorted]))
    else:
        cum_oi = 0.0
        median_iv = samples_sorted[-1]['iv']
        for s in samples_sorted:
            cum_oi += s['oi']
            if cum_oi >= 0.5 * total_oi:
                median_iv = s['iv']
                break

    clamped_iv = float(np.clip(median_iv, 0.10, 0.50))
    return clamped_iv, samples

def get_yfinance_ibov_close(target_date):
    """
    Tenta buscar o preço de fechamento do IBOV (^BVSP) no Yahoo Finance para uma data específica.
    """
    import yfinance as yf
    try:
        ticker = yf.Ticker("^BVSP")
        df = ticker.history(period="5d")
        if df.empty:
            return None
        
        for timestamp, row in df.iterrows():
            if timestamp.date() == target_date:
                return float(row['Close'])
    except Exception as e:
        print(f"      [yfinance] Erro ao buscar IBOV: {e}")
    return None

# Feriados nacionais fixos no Brasil (mês, dia)
BR_HOLIDAYS_FIXED = {
    (1, 1),   # Ano Novo
    (4, 21),  # Tiradentes
    (5, 1),   # Dia do Trabalho
    (9, 7),   # Independência do Brasil
    (10, 12), # Nossa Senhora Aparecida
    (11, 2),  # Finados
    (11, 15), # Proclamação da República
    (11, 20), # Consciência Negra
    (12, 25), # Natal
}

def is_b3_trading_day(d):
    """Retorna True se d for dia de semana e não for feriado nacional."""
    if d.weekday() >= 5: # 5 = Saturday, 6 = Sunday
        return False
    if (d.month, d.day) in BR_HOLIDAYS_FIXED:
        return False
    return True

def get_previous_trading_day(ref_date=None):
    """
    Retorna o dia útil anterior ao ref_date (por padrão hoje),
    pulando finais de semana e feriados nacionais brasileiros.
    """
    if ref_date is None:
        ref_date = datetime.date.today()
    if isinstance(ref_date, datetime.datetime):
        ref_date = ref_date.date()
        
    prev = ref_date - datetime.timedelta(days=1)
    while not is_b3_trading_day(prev):
        prev = prev - datetime.timedelta(days=1)
    return prev

def get_expected_trading_day():
    """
    Retorna a data esperada para o processamento do dia de hoje.
    Antes das 17h, consulta primeiro a API oficial de workday da B3 para máxima precisão.
    Fallback: se já passou das 17:00, o esperado é hoje (se for dia útil).
    Caso contrário, é o dia de pregão anterior (respeitando feriados).
    """
    now = datetime.datetime.now()
    if now.hour < 17:
        try:
            import requests
            r_wd = requests.get("https://arquivos.b3.com.br/bdi/table/workday?", timeout=4)
            if r_wd.status_code == 200:
                raw_wd = r_wd.json().strip('"')
                b3_date_str = raw_wd.split("T")[0]
                return datetime.date.fromisoformat(b3_date_str)
        except Exception:
            pass

    return get_previous_trading_day(now.date())

def prompt_user_anomaly(expected_date, trading_date, mt5_date, default_win, default_ibov):
    """
    Exibe um alerta de segurança e solicita ação do usuário em caso de inconsistência de datas.
    Em modo agendado (GEX_SCHEDULED=1 ou stdin não-interativo), prossegue automaticamente.
    """
    print("\n" + "!" * 70)
    print(" [ALERTA] ALERTA DE SEGURANCA: INCONSISTENCIA DE DATAS DETECTADA!")
    print(f" Esperado para o processamento: {expected_date}")
    print(f" - Data do arquivo B3 CSV:      {trading_date or 'Nao encontrado'}")
    print(f" - Data dos precos do MT5:      {mt5_date or 'Nao encontrado'}")
    print("!" * 70 + "\n")
    
    # Modo agendado/não-interativo: prosseguir automaticamente
    is_scheduled = os.environ.get("GEX_SCHEDULED", "0") == "1"
    is_interactive = sys.stdin.isatty() if hasattr(sys.stdin, 'isatty') else False
    
    if is_scheduled or not is_interactive:
        print("[AUTO] Modo agendado detectado — prosseguindo automaticamente com dados disponíveis.")
        print(f"       Usando dados do último dia útil disponível (CSV: {trading_date}, MT5: {mt5_date}).")
        return default_win, default_ibov
    
    while True:
        print("[1] Prosseguir mesmo assim (usar dados disponíveis)")
        print(f"[2] Digitar preços manualmente para o dia útil correto ({expected_date})")
        print("[3] Cancelar a execução")
        
        try:
            choice = input("Selecione uma opção (1/2/3): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nErro: Ambiente não interativo ou interrupção detectada. Prosseguindo automaticamente.")
            return default_win, default_ibov
            
        if choice == '1':
            print("\n>> Prosseguindo com os dados disponíveis...")
            return default_win, default_ibov
        elif choice == '2':
            print(f"\n>> Digitação Manual para o dia {expected_date}:")
            while True:
                try:
                    f_win_str = input(f"Digite o preço do contrato WIN (ex: {default_win or 179000}): ").strip()
                    f_win = float(f_win_str)
                    break
                except ValueError:
                    print("Por favor, digite um número válido.")
            while True:
                try:
                    s_ibov_str = input(f"Digite o preço do índice IBOV (ex: {default_ibov or 177000}): ").strip()
                    s_ibov = float(s_ibov_str)
                    break
                except ValueError:
                    print("Por favor, digite um número válido.")
            return f_win, s_ibov
        elif choice == '3':
            print("\n>> Execução cancelada pelo usuário.")
            sys.exit(1)
        else:
            print("Opção inválida. Escolha 1, 2 ou 3.\n")

def run_gex_pipeline(current_win, current_ibov, mt5_date=None):
    """
    Pipeline completo: B3 CSV -> Black-76 GEX -> Magic Walls Walls -> Firebase.
    
    Parametros:
        current_win:  Preco atual do contrato futuro WIN (ex: WINM26 = 188902)
        current_ibov: Preco spot do indice IBOVESPA (ex: 186000)
    """
    # Determinar a data esperada
    expected_date = get_expected_trading_day()
    
    print("=" * 50)
    print("  GEX ENGINE - Magic Walls Walls Replicator")
    print("=" * 50)
    print(f"  F_WIN  = {current_win}")
    print(f"  S_IBOV = {current_ibov}")
    print(f"  Factor = {current_win / current_ibov:.6f}")
    print()
    
    # 1. Fetch Option Data
    print("[1/6] Carregando dados de OI da B3...")
    try:
        from .b3_downloader import download_b3_positions
        download_b3_positions(target_date=expected_date)
    except Exception as e:
        print(f"      Aviso: Falha ao automatizar download da B3 ({e}).")
        print("      Tentando prosseguir com o arquivo CSV mais recente disponível localmente...")
        
    df_options = get_b3_options_data(current_ibov)
    
    if df_options.empty:
        print("ERRO: Nenhuma opcao encontrada. Verifique o arquivo CSV.")
        return
        
    # Extrair data real do CSV lido
    from .b3_parser import _find_latest_oi_file
    latest_file = _find_latest_oi_file()
    trading_date = None
    if latest_file:
        match_date = re.search(r"(\d{2})-(\d{2})-(\d{4})", os.path.basename(latest_file))
        if match_date:
            d, m, y = match_date.groups()
            trading_date = datetime.date(int(y), int(m), int(d))
            
    anomaly = False
    if trading_date != expected_date:
        anomaly = True
    if mt5_date and mt5_date != expected_date:
        # Se os preços do MT5 estão desatualizados, tentamos buscar a data correta no Yahoo Finance
        print(f"\n[Aviso] Preços do MT5 estão desatualizados ({mt5_date} vs esperado {expected_date}).")
        print(f"        Tentando buscar fechamento oficial de {expected_date} no Yahoo Finance (^BVSP)...")
        yf_ibov = get_yfinance_ibov_close(expected_date)
        if yf_ibov is not None:
            old_factor = current_win / current_ibov if current_ibov else 1.0083
            estimated_win = round(yf_ibov * old_factor)
            print(f"        [Sucesso Yahoo Finance] IBOV fechamento em {expected_date}: {yf_ibov}")
            print(f"        Estimando WIN futuro usando fator anterior ({old_factor:.6f}) -> {estimated_win}")
            current_ibov = yf_ibov
            current_win = estimated_win
            mt5_date = expected_date
            
            # Recalcula se ainda há anomalia
            if trading_date == expected_date:
                anomaly = False  # Anomalia resolvida!
        else:
            print("        Não foi possível obter dados no Yahoo Finance. Mantendo verificação normal.")
            anomaly = True
            
    if anomaly:
        current_win, current_ibov = prompt_user_anomaly(
            expected_date=expected_date,
            trading_date=trading_date,
            mt5_date=mt5_date,
            default_win=current_win,
            default_ibov=current_ibov
        )
    
    print(f"      {len(df_options)} contratos de opcoes carregados.\n")
    
    # 2. Dynamic Implied Volatility via Newton-Raphson
    print("[2/6] Calculando Volatilidade Implicita (Newton-Raphson)...")
    dynamic_iv = 0.20
    r_anchored = 0.1400  # Selic do início do ciclo (novo ciclo Out/26 = 14.00%)
    r_current = 0.1400   # Selic atual pós-COPOM (para o recálculo dinâmico)
    r = r_anchored
    
    # Calcula data de hoje ou extrai da data do CSV
    from .b3_parser import _find_latest_oi_file
    latest_file = _find_latest_oi_file()
    trading_date = None
    if latest_file:
        match_date = re.search(r"(\d{2})-(\d{2})-(\d{4})", os.path.basename(latest_file))
        if match_date:
            d, m, y = match_date.groups()
            trading_date = datetime.date(int(y), int(m), int(d))
            
    if not trading_date:
        trading_date = datetime.date.today()
        
    trading_date_str = trading_date.isoformat()

    # Filtra apenas vencimentos que não expiraram (>= data de negociação)
    session_date = max(trading_date, datetime.date.today())
    session_date_str = session_date.isoformat()
    df_future_opts = df_options[df_options['expiry'].str[:10] > session_date_str].copy()
    df_options = df_future_opts if not df_future_opts.empty else df_options[df_options['expiry'].str[:10] >= trading_date_str].copy()
    
    # Filtra apenas o vencimento mais proximo (front-month) com liquidez minima
    MIN_CONTRACTS = 5
    MIN_STRIKES = 3
    all_expiries = sorted(df_options['expiry'].unique())
    
    front_month = None
    for exp in all_expiries:
        exp_df = df_options[df_options['expiry'] == exp]
        n_contracts = len(exp_df)
        n_strikes = exp_df['strike'].nunique()
        if n_contracts >= MIN_CONTRACTS and n_strikes >= MIN_STRIKES:
            front_month = exp
            break
        else:
            print(f"      [Skip] Vencimento {exp} ignorado: {n_contracts} contratos, {n_strikes} strikes (min: {MIN_CONTRACTS}/{MIN_STRIKES})")
    
    if front_month is None:
        # Fallback: usar o vencimento com mais contratos
        front_month = df_options.groupby('expiry').size().idxmax()
        print(f"      [Fallback] Nenhum vencimento atingiu o minimo. Usando {front_month} (maior OI).")
    
    df_front = df_options[df_options['expiry'] == front_month].copy()
    
    expiry_date_str = front_month[:10]
    
    expiry_days = int(np.busday_count(session_date_str, expiry_date_str))
    expiry_days = max(1, expiry_days)
    
    T = max(1/252, expiry_days / 252)
    print(f"      Data Ref CSV: {trading_date_str} | Vencimento: {expiry_date_str} | Dias Uteis: {expiry_days} | T: {T:.4f}")
    
    # Calcular fator para Newton-Raphson multi-strike ATM
    mt5_factor = (current_win / current_ibov) if (current_win and current_ibov and current_ibov > 0) else None
    factor_iv = mt5_factor if (mt5_factor and 0.995 <= mt5_factor <= 1.045) else ((1 + r) ** T)

    est_iv, iv_samples = _estimate_robust_atm_iv(
        df_front=df_front,
        current_win=current_win,
        current_ibov=current_ibov,
        factor=factor_iv,
        T=T,
        r=r,
        trading_date=trading_date,
    )
    if est_iv is not None:
        dynamic_iv = est_iv
        sample_desc = ", ".join(
            f"{s['ticker']}({s['iv']*100:.1f}%)" for s in iv_samples[:6]
        )
        print(f"      IV Multi-Strike ATM ({len(iv_samples)} amostras em {trading_date_str}): {sample_desc}")
        print(f"      IV Consolidada (Mediana Ponderada por OI): {dynamic_iv*100:.2f}%")
    else:
        # Fallback legado: CALL ATM única (permitindo vela mais recente)
        all_strikes = df_front['strike'].unique()
        atm_strike = min(all_strikes, key=lambda s: abs(s - current_ibov))
        atm_calls = df_front[(df_front['strike'] == atm_strike) & (df_front['type'] == 'CALL')]
        if not atm_calls.empty:
            atm_calls = atm_calls.sort_values(by='oi', ascending=False)
            atm_ticker = atm_calls.iloc[0]['ticker']
            print(f"      Opcao ATM fallback (front-month): {atm_ticker} (Strike {atm_strike})")

            c_market = get_option_price(atm_ticker, ref_date=trading_date, allow_stale=True)
            if c_market and c_market > 0:
                k_win = atm_strike * factor_iv
                raw_iv = implied_volatility_newton_raphson(
                    C_market=c_market,
                    F=current_win,
                    K=k_win,
                    T=T,
                    r=r,
                    is_call=True
                )
                dynamic_iv = float(np.clip(raw_iv, 0.10, 0.50))
                print(f"      Preco MT5: R$ {c_market:.2f} -> IV Fallback: {dynamic_iv*100:.2f}%")
            else:
                print(f"      Falha ao obter preco de {atm_ticker} no MT5. Usando IV fixo de 20%.")
        else:
            print("      Nao encontrou CALL ATM na base. Usando IV fixo de 20%.")
    
    print()
    
    # 3. Calculate GEX & Find Walls (Modo Ancorado de Custodia - RastroWeb)
    print("[3/6] Calculando GEX e gerando Walls (Modo Ancorado de Custodia)...")
    walls = calculate_gex_profile(
        options_df=df_options, 
        current_win=current_win, 
        current_ibov=current_ibov,
        iv=dynamic_iv,
        expiry_days=expiry_days,
        r=r_anchored,
        use_anchored_factor=True,
        ref_date=session_date
    )
    
    # Tambem calcula a versao dinamica para exportar MagicWall_Dinamico
    walls_dynamic = calculate_gex_profile(
        options_df=df_options, 
        current_win=current_win, 
        current_ibov=current_ibov,
        iv=dynamic_iv,
        expiry_days=expiry_days,
        r=r_current,
        use_anchored_factor=False,
        ref_date=session_date
    )
    
    print(f"\n      {len(walls)} linhas geradas (Modo Ancorado):")
    for w in walls:
        label = f"  {w['type']:12s} @ {w['price']:>12.3f} | Width {w['width']}"
        if w.get('strike_ibov'):
            label += f" | IBOV {w['strike_ibov']}"
        print(label)
        
    # 4. Gerar Relatorio Diario
    print("\n[4/6] Gerando Relatorio de Tendencia...")
    from .analyzer import generate_gex_report
    
    # Encontra o GammaFlip para passar pro analisador
    flip_price = current_ibov # fallback
    for w in walls:
        if w['type'] == 'GammaFlip':
            flip_price = w['price']
            break
    generate_gex_report(current_win, flip_price, walls, output_path="gex/docs/DAILY_REPORT.txt")
            
    
    # 6. Deploy Nelogica (Scalper + Profit + Clipboard) - Ambos os Formatos
    print("\n[6/7] Deploy Nelogica (Scalper + Profit + Clipboard)...")
    from .profit_exporter import export_all
    
    try:
        export_all(ticker="WIN", walls=walls, current_price=current_win, strategy_name="MagicWall")
        export_all(ticker="WIN", walls=walls_dynamic, current_price=current_win, strategy_name="MagicWall_Dinamico")
    except Exception as e:
        print(f"      Aviso: Falha no deploy Nelogica ({e})")
        # Fallback: pelo menos salvar o arquivo base
        try:
            from .profit_exporter import export_to_profit
            export_to_profit(walls, output_path="gex/docs/magicwalls_neologica", current_win=current_win)
        except Exception:
            pass
        
    # 7. Export to TradingView
    print("\n[7/7] Gerando arquivo unificado para TradingView Pine Script...")
    from .tradingview_exporter import save_walls_to_cache, export_unified_tradingview
    tv_file = "gex/docs/magicwalls_tradingview.pine"
    try:
        save_walls_to_cache(walls, ticker="WIN", ref_date=trading_date, current_price=current_win)
        export_unified_tradingview(output_path=tv_file)
    except Exception as e:
        print(f"      Aviso: Nao foi possivel salvar para o TradingView ({e})")
    
    # 8. Export to MT5 Common\Files + Firebase Backup
    print("\n[8/8] Exportando MagicWalls para MetaTrader 5 (Common\\Files + Firebase)...")
    try:
        from .mt5_exporter import export_to_mt5_common
        export_to_mt5_common(walls=walls, ref_date=trading_date, current_win=current_win)
    except Exception as e:
        print(f"      Aviso: Falha ao exportar para MT5 Common\\Files ({e})")
    try:
        push_walls_to_firebase(walls)
    except Exception as e:
        print(f"      Aviso: Falha ao publicar no Firebase ({e})")

    print("\n" + "=" * 50)
    print("  Pipeline concluido com sucesso!")
    print("=" * 50)



def print_usage():
    print("""
USO:
  python -m gex.engine.main                    (busca precos do MT5 automaticamente)
  python -m gex.engine.main <F_WIN> <S_IBOV>   (valores manuais)

PARAMETROS:
  F_WIN   = Preco atual do contrato futuro WIN (ex: WINM26)
  S_IBOV  = Preco spot do indice IBOVESPA

EXEMPLOS:
  python -m gex.engine.main                  <- usa MT5
  python -m gex.engine.main 189500 187200    <- manual

PRE-REQUISITOS:
  1. Arquivo 'Posicoes em aberto-*.csv' em gex/data/ (ou raiz do projeto)
  2. serviceAccountKey.json na raiz do projeto
  3. MetaTrader 5 aberto (para modo automatico)
""")

if __name__ == "__main__":
    if len(sys.argv) == 3:
        # Modo manual: valores passados via CLI
        try:
            f_win = float(sys.argv[1])
            s_ibov = float(sys.argv[2])
            run_gex_pipeline(current_win=f_win, current_ibov=s_ibov)
        except ValueError:
            print("ERRO: F_WIN e S_IBOV devem ser numeros.")
            print_usage()
    elif len(sys.argv) == 1:
        # Modo automatico: buscar do MT5
        print("[MT5] Buscando precos automaticamente...\n")
        f_win, s_ibov, win_bar_time = get_mt5_prices()
        
        if f_win is None or s_ibov is None:
            print("\nFalha ao obter precos do MT5.")
            print("Use o modo manual: python -m gex.engine.main <F_WIN> <S_IBOV>")
            sys.exit(1)
            
        mt5_date = win_bar_time.date() if win_bar_time else None
        
        print()
        run_gex_pipeline(current_win=f_win, current_ibov=s_ibov, mt5_date=mt5_date)
    else:
        print_usage()
