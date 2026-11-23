"""
SUPERVISOR DE EXECUÇÃO DIÁRIA DO GEX (14 ATIVOS) COM RETRY INTELIGENTE DA B3

Regra Operacional:
- Na janela matinal (07:30 às 09:30), verifica se os dados de Posições em Aberto da B3
  do pregão anterior (D-1) já foram publicados.
- Se a B3 ainda não disponibilizou ou o download falhar:
  -> Aguarda 30 minutos e tenta novamente.
  -> Repete as tentativas (ex: 07:30, 08:00, 08:30, 09:00, 09:30).
  -> Se atingir 09:30, prossegue com a base local mais recente (fallback seguro) para
     garantir os níveis antes da abertura do mercado às 10h.
- Assim que a B3 responder com sucesso, executa imediatamente a esteira completa dos 14 ativos,
  atualiza relatórios, Pine Script do TradingView, IRAI dashboard e SQLite.
"""

import os
import sys
import time
import subprocess
import re
from datetime import datetime, date, time as dtime

# Garantir encoding UTF-8 no stdout
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Adicionar diretório raiz ao sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
GEX_DIR = os.path.dirname(SCRIPT_DIR)
PROJECT_ROOT = os.path.dirname(GEX_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from gex.engine.main import get_expected_trading_day
from gex.engine.b3_downloader import download_b3_positions
from gex.engine.b3_parser import get_b3_options_data, _find_latest_oi_file


def is_b3_data_ready(expected_date):
    """
    Verifica se o arquivo CSV de posições em aberto da B3 para a data esperada
    já existe localmente e contém dados válidos.
    """
    data_dir = os.path.join(GEX_DIR, 'data')
    parts = expected_date.strftime("%Y-%m-%d").split('-')
    date_str = f"{parts[2]}-{parts[1]}-{parts[0]}"
    expected_filename = f"Posições em aberto-{date_str}.csv"
    expected_path = os.path.join(data_dir, expected_filename)
    
    if os.path.exists(expected_path) and os.path.getsize(expected_path) > 1000000:
        return True, expected_path
        
    # Verificar pelo parser mais recente
    latest_file = _find_latest_oi_file()
    if latest_file:
        match_date = re.search(r"(\d{2})-(\d{2})-(\d{4})", os.path.basename(latest_file))
        if match_date:
            d, m, y = match_date.groups()
            file_date = date(int(y), int(m), int(d))
            if file_date == expected_date and os.path.getsize(latest_file) > 1000000:
                return True, latest_file
                
    return False, None


def wait_for_b3_with_retry(max_retry_time_str="09:20"):
    """
    Tenta baixar os dados da B3 para o expected_date.
    Se falhar ou não estiver disponível e o horário for antes das 09:20,
    aguarda 30 minutos (1800s) e tenta novamente até o limite de 09:20.
    O limite de 09:20 garante margem segura antes das 09:30 (limite de 2h da tarefa agendada)
    para que a esteira completa consiga rodar em modo fallback antes da abertura do mercado.
    """
    expected_date = get_expected_trading_day()
    max_hour, max_min = map(int, max_retry_time_str.split(':'))
    max_time = dtime(max_hour, max_min)
    
    attempt = 1
    print("=" * 60)
    print("  SUPERVISOR GEX - VERIFICAÇÃO DE DADOS DA B3")
    print("=" * 60)
    print(f"Data de Referência Esperada (D-1): {expected_date}")
    print(f"Janela de Retry Matinal:           07:30 até {max_retry_time_str} (a cada 30 min)")
    print("=" * 60)
    print()
    
    while True:
        now = datetime.now()
        current_time_str = now.strftime("%H:%M:%S")
        
        print(f"[{current_time_str}] [Tentativa {attempt}] Verificando disponibilidade dos dados da B3 para {expected_date}...")
        
        # 1. Checa se já temos o arquivo localmente
        ready, path = is_b3_data_ready(expected_date)
        if ready:
            print(f"[{current_time_str}] [SUCESSO] Base de dados de {expected_date} já disponível localmente ({os.path.basename(path)}).")
            return True
            
        # 2. Tenta fazer o download (via API REST ou Playwright)
        try:
            downloaded = download_b3_positions(target_date=expected_date)
            if downloaded:
                # Validar se o arquivo realmente contém opções válidas
                ready, path = is_b3_data_ready(expected_date)
                if ready:
                    print(f"[{current_time_str}] [SUCESSO] Download da B3 concluído com sucesso para {expected_date}!")
                    return True
        except Exception as e:
            print(f"[{current_time_str}] [Aviso] Erro durante a tentativa de download: {e}")
            
        # 3. Se não obteve os dados, reavaliar o horário atual (pois o download pode ter levado vários minutos)
        now = datetime.now()
        current_time_str = now.strftime("%H:%M:%S")
        current_t = now.time()
        
        # Se for horário noturno (ex: 19:30) ou se já passou das 09:30 da manhã:
        if now.hour >= 10 or (now.hour == max_hour and now.minute >= max_min) or (now.hour < 6):
            print(f"\n[{current_time_str}] [AVISO] Horário limite ({max_retry_time_str}) atingido ou fora da janela matinal.")
            print(f"           Prosseguindo com a base local mais recente disponível (modo fallback).")
            return False
            
        # 4. Calcular tempo de espera de 30 minutos (1800s)
        # Limitar o sono para não ultrapassar 09:30
        seconds_to_wait = 1800  # 30 minutos
        
        # Calcular quantos segundos restam até 09:30
        target_max_today = datetime.combine(now.date(), max_time)
        seconds_until_max = (target_max_today - now).total_seconds()
        
        if seconds_until_max <= 0:
            print(f"\n[{current_time_str}] [AVISO] Limite das {max_retry_time_str} alcançado. Prosseguindo...")
            return False
            
        wait_seconds = min(seconds_to_wait, max(60, int(seconds_until_max)))
        next_attempt_time = datetime.fromtimestamp(time.time() + wait_seconds).strftime("%H:%M:%S")
        
        print(f"\n[{current_time_str}] [RETRY] Dados de {expected_date} ainda não liberados pela B3.")
        print(f"           Aguardando {wait_seconds // 60} minutos para a próxima tentativa às {next_attempt_time} (Limite: {max_retry_time_str})...\n")
        
        time.sleep(wait_seconds)
        attempt += 1


def run_pipeline_step(step_name, module_name):
    """Executa um módulo da esteira via subprocess python."""
    print(f"\n>>> Executando {step_name} ({module_name})...")
    python_exe = sys.executable
    cmd = [python_exe, "-u", "-m", module_name]
    
    # Propagar variáveis de ambiente (como GEX_SCHEDULED=1)
    env = os.environ.copy()
    env["GEX_SCHEDULED"] = "1"
    
    try:
        res = subprocess.run(cmd, cwd=PROJECT_ROOT, env=env, timeout=900)
    except subprocess.TimeoutExpired:
        print(f"[Aviso] Etapa {step_name} excedeu 15 min e foi abortada. Continuando esteira...")
        return
    if res.returncode != 0:
        print(f"[Aviso] Etapa {step_name} retornou código {res.returncode}. Continuando esteira...")
    else:
        print(f"[OK] Etapa {step_name} concluída.")


def run_full_gex_pipeline():
    """Executa a esteira completa dos 14 ativos, relatórios, git e IRAI sync."""
    t0 = time.time()
    print("\n" + "=" * 60)
    print("  INICIANDO ATUALIZAÇÃO CONSOLIDADA DO GEX (14 ATIVOS)")
    print("=" * 60)
    
    steps = [
        ("[0/14] Calendário Econômico", "gex.engine.calendar_fetcher"),
        ("[1/14] WIN Futures (B3)", "gex.engine.main"),
        ("[2/14] Dólar Futuro / WDO (B3)", "gex.engine.main_dol"),
        ("[3/14] S&P 500 / ES (EUA)", "gex.engine.main_us"),
        ("[4/14] Nasdaq 100 / NQ (EUA)", "gex.engine.main_nq"),
        ("[5/14] Bitcoin / BTC-USD (Cripto)", "gex.engine.main_btc"),
        ("[6/14] EUR / USD (Forex)", "gex.engine.main_eur"),
        ("[7/14] GBP / USD (Forex)", "gex.engine.main_gbp"),
        ("[8/14] Ouro / XAUUSD (Metal)", "gex.engine.main_gold"),
        ("[9/14] Dow Jones / US30 (EUA)", "gex.engine.main_dow"),
        ("[10/14] USD / JPY (Forex)", "gex.engine.main_jpy"),
        ("[11/14] DAX 40 / DE40 (Alemanha)", "gex.engine.main_dax"),
        ("[12/14] Nikkei 225 / JP225 (Japão)", "gex.engine.main_nikkei"),
        ("[13/15] Russell 2000 / US2000 (EUA Small Caps)", "gex.engine.main_russell"),
        ("[14/15] China 50 / FXI (China)", "gex.engine.main_china"),
        ("[15/15] Dollar Index / DXY (EUA)", "gex.engine.main_dxy"),
    ]
    
    for name, mod in steps:
        run_pipeline_step(name, mod)
        
    print("\n" + "=" * 60)
    print("  SINCRONIZAÇÃO GIT & DASHBOARD IRAI")
    print("=" * 60)
    
    # 1. Commit Git
    print("\nSalvando relatórios e indicador consolidado no Git...")
    subprocess.run([
        "git", "add", "-f",
        "gex/data/*.csv", "gex/data/*.json",
        "gex/docs/magicwalls_neologica", "gex/docs/MagicWallManual.nts",
        "gex/docs/magicwalls_tradingview.pine", "gex/docs/DAILY_REPORT*.txt",
        "gex/docs/DAILY_ECONOMIC_CALENDAR.txt"
    ], cwd=PROJECT_ROOT)
    
    subprocess.run([
        "git", "commit", "-m",
        "chore(gex): atualizacao consolidada de GEX para 14 ativos e relatorios diarios"
    ], cwd=PROJECT_ROOT)
    
    # 2. Sincronização IRAI
    print("\n[SYNC] Sincronizando níveis GEX no dashboard IRAI...")
    irai_sync_script = os.path.join(PROJECT_ROOT, "..", "rastro_irado", "scripts", "sync_gex_to_irai.py")
    if os.path.exists(irai_sync_script):
        subprocess.run([sys.executable, irai_sync_script], cwd=PROJECT_ROOT)
    else:
        print(f"[Aviso] Script do IRAI não encontrado em: {irai_sync_script}")
        
    elapsed = time.time() - t0
    print("\n" + "=" * 60)
    print(f"  GEX Daily Update FINALIZADO com sucesso em {elapsed:.1f} segundos!")
    print("=" * 60 + "\n")


def main():
    os.environ["GEX_SCHEDULED"] = "1"
    
    now = datetime.now()
    if now.hour >= 17:
        print(f"[{now.strftime('%H:%M:%S')}] [SKIP] Execução pós-17h desativada. O modelo calcula apenas na janela matinal (07:30).")
        return
    
    # 1. Fase de Verificação e Retry da B3 (07:30 até 09:20)
    wait_for_b3_with_retry(max_retry_time_str="09:20")
    
    # 2. Fase de Execução da Esteira Completa
    run_full_gex_pipeline()


if __name__ == "__main__":
    main()
