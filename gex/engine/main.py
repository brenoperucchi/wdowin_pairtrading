import sys
import re
import datetime
import os
import numpy as np
from .b3_parser import get_b3_options_data
from .walls_calculator import calculate_gex_profile
from .firebase_publisher import push_walls_to_firebase
from .mt5_prices import get_mt5_prices, get_option_price
from .black76 import implied_volatility_newton_raphson

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

def get_previous_trading_day(ref_date=None):
    """
    Retorna o dia útil anterior ao ref_date (por padrão hoje).
    Se hoje for segunda, retorna sexta.
    Se hoje for domingo ou sábado, retorna sexta.
    """
    if ref_date is None:
        ref_date = datetime.date.today()
    if isinstance(ref_date, datetime.datetime):
        ref_date = ref_date.date()
        
    prev = ref_date - datetime.timedelta(days=1)
    while prev.weekday() >= 5: # 5 = Saturday, 6 = Sunday
        prev = prev - datetime.timedelta(days=1)
    return prev

def get_expected_trading_day():
    """
    Retorna a data esperada para o processamento do dia de hoje.
    Se já passou das 17:00, o esperado é hoje (se for dia útil).
    Caso contrário, é o dia útil anterior.
    """
    now = datetime.datetime.now()
    if now.hour >= 17:
        ref = now.date()
        while ref.weekday() >= 5:
            ref = ref - datetime.timedelta(days=1)
        return ref
    else:
        return get_previous_trading_day(now.date())

def prompt_user_anomaly(expected_date, trading_date, mt5_date, default_win, default_ibov):
    """
    Exibe um alerta de segurança e solicita ação do usuário em caso de inconsistência de datas.
    """
    print("\n" + "!" * 70)
    print(" [ALERTA] ALERTA DE SEGURANCA: INCONSISTENCIA DE DATAS DETECTADA!")
    print(f" Esperado para o processamento: {expected_date}")
    print(f" - Data do arquivo B3 CSV:      {trading_date or 'Nao encontrado'}")
    print(f" - Data dos precos do MT5:      {mt5_date or 'Nao encontrado'}")
    print("!" * 70 + "\n")
    
    while True:
        print("[1] Prosseguir mesmo assim (usar dados disponíveis)")
        print(f"[2] Digitar preços manualmente para o dia útil correto ({expected_date})")
        print("[3] Cancelar a execução")
        
        try:
            choice = input("Selecione uma opção (1/2/3): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nErro: Ambiente não interativo ou interrupção detectada. Cancelando por segurança.")
            sys.exit(1)
            
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
    Pipeline completo: B3 CSV -> Black-76 GEX -> Jumba Walls -> Firebase.
    
    Parametros:
        current_win:  Preco atual do contrato futuro WIN (ex: WINM26 = 188902)
        current_ibov: Preco spot do indice IBOVESPA (ex: 186000)
    """
    # Determinar a data esperada
    expected_date = get_expected_trading_day()
    
    print("=" * 50)
    print("  GEX ENGINE - Jumba Walls Replicator")
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
    r = 0.145
    
    # Filtra apenas o vencimento mais proximo (front-month)
    front_month = df_options['expiry'].min()
    df_front = df_options[df_options['expiry'] == front_month].copy()
    
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
    expiry_date_str = front_month[:10]
    
    expiry_days = int(np.busday_count(trading_date_str, expiry_date_str))
    expiry_days = max(1, expiry_days)
    
    T = max(1/252, expiry_days / 252)
    print(f"      Data Ref CSV: {trading_date_str} | Vencimento: {expiry_date_str} | Dias Uteis: {expiry_days} | T: {T:.4f}")
    
    # Encontrar ATM strike no front-month
    all_strikes = df_front['strike'].unique()
    atm_strike = min(all_strikes, key=lambda s: abs(s - current_ibov))
    
    # Buscar CALL ATM no front-month
    atm_calls = df_front[(df_front['strike'] == atm_strike) & (df_front['type'] == 'CALL')]
    if not atm_calls.empty:
        # Pega a de maior liquidez (normalmente o vencimento mais curto/ativo)
        atm_calls = atm_calls.sort_values(by='oi', ascending=False)
        atm_ticker = atm_calls.iloc[0]['ticker']
        print(f"      Opcao ATM identificada (front-month): {atm_ticker} (Strike {atm_strike})")
        
        c_market = get_option_price(atm_ticker)
        if c_market and c_market > 0:
            # Fator teorico pro K_WIN
            factor = (1 + r) ** T
            k_win = atm_strike * factor
            
            dynamic_iv = implied_volatility_newton_raphson(
                C_market=c_market,
                F=current_win,
                K=k_win,
                T=T,
                r=r,
                is_call=True
            )
            print(f"      Preco MT5: R$ {c_market:.2f} -> IV Calculada: {dynamic_iv*100:.2f}%")
        else:
            print(f"      Falha ao obter preco de {atm_ticker} no MT5. Usando IV fixo de 20%.")
    else:
        print("      Nao encontrou CALL ATM na base. Usando IV fixo de 20%.")
    
    print()
    
    # 3. Calculate GEX & Find Walls
    print("[3/6] Calculando GEX e gerando Walls...")
    walls = calculate_gex_profile(
        options_df=df_options, 
        current_win=current_win, 
        current_ibov=current_ibov,
        iv=dynamic_iv,
        expiry_days=expiry_days,
        r=r
    )
    
    print(f"\n      {len(walls)} linhas geradas:")
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
            
    report_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs", "DAILY_REPORT.txt")
    generate_gex_report(current_win, flip_price, walls, output_path=report_path)
        
    # 5. Publish to Firebase
    print(f"\n[5/7] Publicando no Firebase...")
    push_walls_to_firebase(walls)
    
    # 6. Export to ProfitChart
    print("\n[6/7] Gerando arquivo para Nelogica ProfitChart...")
    from .profit_exporter import export_to_profit
    
    # Caminhos para salvar
    base_file = "gex/docs/jumba_neologica"
    profit_folder = r"C:\Users\ryzen\AppData\Roaming\Nelogica\Profit\strategy\JumbaWalls.nne"
    
    try:
        # Sobrescreve o arquivo base do repositorio
        export_to_profit(walls, output_path=base_file, current_win=current_win)
        # Tenta salvar na pasta do Profit (se existir)
        profit_dir = os.path.dirname(profit_folder)
        if os.path.exists(profit_dir):
            export_to_profit(walls, output_path=profit_folder, current_win=current_win)
    except Exception as e:
        print(f"      Aviso: Nao foi possivel salvar no Profit ({e})")
        
    # 7. Export to TradingView
    print("\n[7/7] Gerando arquivo unificado para TradingView Pine Script...")
    from .tradingview_exporter import save_walls_to_cache, export_unified_tradingview
    tv_file = "gex/docs/jumba_tradingview.pine"
    try:
        save_walls_to_cache(walls, ticker="WIN", ref_date=trading_date)
        export_unified_tradingview(output_path=tv_file)
    except Exception as e:
        print(f"      Aviso: Nao foi possivel salvar para o TradingView ({e})")
    
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
