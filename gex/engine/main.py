import sys
from .b3_parser import get_b3_options_data
from .walls_calculator import calculate_gex_profile
from .firebase_publisher import push_walls_to_firebase
from .mt5_prices import get_mt5_prices

def run_gex_pipeline(current_win, current_ibov):
    """
    Pipeline completo: B3 CSV -> Black-76 GEX -> Jumba Walls -> Firebase.
    
    Parametros:
        current_win:  Preco atual do contrato futuro WIN (ex: WINM26 = 188902)
        current_ibov: Preco spot do indice IBOVESPA (ex: 186000)
    """
    print("=" * 50)
    print("  GEX ENGINE - Jumba Walls Replicator")
    print("=" * 50)
    print(f"  F_WIN  = {current_win}")
    print(f"  S_IBOV = {current_ibov}")
    print(f"  Factor = {current_win / current_ibov:.6f}")
    print()
    
    # 1. Fetch Option Data
    print("[1/3] Carregando dados de OI da B3...")
    df_options = get_b3_options_data(current_ibov)
    
    if df_options.empty:
        print("ERRO: Nenhuma opcao encontrada. Verifique o arquivo CSV.")
        return
    
    print(f"      {len(df_options)} contratos de opcoes carregados.\n")
    
    # 2. Calculate GEX & Find Walls
    print("[2/3] Calculando GEX e gerando Walls...")
    walls = calculate_gex_profile(
        options_df=df_options, 
        current_win=current_win, 
        current_ibov=current_ibov,
        iv=0.20,          # Fixed IV for MVP (TODO: Newton-Raphson)
        expiry_days=27,   # ~27 dias uteis para o prox vencimento
        r=0.145           # Taxa de juros de 14.5% para o Fator Teorico
    )
    
    print(f"\n      {len(walls)} linhas geradas:")
    for w in walls:
        label = f"  {w['type']:12s} @ {w['price']:>12.3f} | Width {w['width']}"
        if w.get('strike_ibov'):
            label += f" | IBOV {w['strike_ibov']}"
        print(label)
        
    # 3. Publish to Firebase
    print(f"\n[3/3] Publicando no Firebase...")
    push_walls_to_firebase(walls)
    
    # 4. Export to ProfitChart
    print("\n[4/4] Gerando arquivo para Nelogica ProfitChart...")
    from .profit_exporter import export_to_profit
    
    # Caminhos para salvar
    base_file = "gex/docs/jumba_neologica"
    profit_folder = r"C:\Users\ryzen\AppData\Roaming\Nelogica\Profit\strategy\JumbaWalls.nne"
    
    try:
        # Sobrescreve o arquivo base do repositorio
        export_to_profit(walls, output_path=base_file)
        # Tenta salvar na pasta do Profit (se existir)
        import os
        profit_dir = os.path.dirname(profit_folder)
        if os.path.exists(profit_dir):
            export_to_profit(walls, output_path=profit_folder)
    except Exception as e:
        print(f"      Aviso: Nao foi possivel salvar no Profit ({e})")
    
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
        f_win, s_ibov = get_mt5_prices()
        
        if f_win is None or s_ibov is None:
            print("\nFalha ao obter precos do MT5.")
            print("Use o modo manual: python -m gex.engine.main <F_WIN> <S_IBOV>")
            sys.exit(1)
        
        print()
        run_gex_pipeline(current_win=f_win, current_ibov=s_ibov)
    else:
        print_usage()
