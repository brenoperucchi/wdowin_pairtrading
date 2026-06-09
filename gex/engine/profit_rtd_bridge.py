# -*- coding: utf-8 -*-
"""
JUMBA WALLS - PROFIT SCALPER PRO RTD BRIDGE
Ponte de Sincronização em Tempo Real entre o Profit e o Regime Dashboard

Como rodar:
  .\.venv\Scripts\python.exe gex/engine/profit_rtd_bridge.py --mode excel

Requisitos:
  - pywin32 (instalado no .venv)
  - requests (instalado no .venv)
"""
import sys
import time
import requests
import argparse

API_UPDATE_URL = "http://localhost:8080/api/flow/update"

BROKERS_MAP = {
    "XP": "XP",
    "UBS": "UBS",
    "BTG": "BTG",
    "IDEAL": "IDEAL",
    "GENIAL": "GENIAL",
    "JPMORGAN": "JPMORGAN",
    "TULLETT": "TULLETT",
    "MERRILL": "MERRILL",
    "GOLDMAN": "GOLDMAN",
    "ITAU": "ITAU",
    "BRADESCO": "BRADESCO"
}

def run_excel_bridge():
    """
    MODO RECOMENDADO: Excel COM Bridge
    1. Abra uma planilha do Excel.
    2. Na Coluna A (Linhas 2 a 12), digite os nomes das corretoras:
       A2: XP
       A3: UBS
       A4: BTG
       A5: IDEAL
       A6: GENIAL
       A7: JPMORGAN
       A8: TULLETT
       A9: MERRILL
       A10: GOLDMAN
       A11: ITAU
       A12: BRADESCO
    3. Na Coluna B, insira as fórmulas RTD para WIN (ex: WINM26 ou WIN$N):
       B2: =RTD("Nelogica.Profit.RTD"; ; "WINM26"; "XP"; "NET")
       B3: =RTD("Nelogica.Profit.RTD"; ; "WINM26"; "UBS"; "NET")
       ...
    4. Na Coluna C, insira as fórmulas RTD para WDO (ex: WDON26 ou WDO$N):
       C2: =RTD("Nelogica.Profit.RTD"; ; "WDON26"; "XP"; "NET")
       C3: =RTD("Nelogica.Profit.RTD"; ; "WDON26"; "UBS"; "NET")
       ...
    5. Deixe a planilha do Excel aberta no seu computador.
    6. Execute este script.
    """
    print("=" * 65)
    print("  PROFIT RTD BRIDGE — MODO EXCEL COM")
    print("=" * 65)
    print("Tentando conectar com o Excel em execução...")
    
    try:
        import win32com.client
    except ImportError:
        print("[ERRO] Biblioteca 'pywin32' não encontrada. Instale usando: pip install pywin32")
        return
        
    excel = None
    for attempt in range(5):
        try:
            excel = win32com.client.GetActiveObject("Excel.Application")
            break
        except Exception:
            print(f"  Aguardando o Excel estar aberto (Tentativa {attempt + 1}/5)...")
            time.sleep(2)
            
    if not excel:
        print("\n[ERRO] Não foi possível conectar ao Excel em execução.")
        print("Certifique-se de que o Excel está aberto com a planilha contendo as fórmulas RTD.")
        sys.exit(1)
        
    print("[OK] Conectado ao Excel com sucesso!")
    
    sheet = excel.ActiveSheet
    print(f"[OK] Lendo planilha ativa: '{sheet.Name}'")
    print("Iniciando loop de atualização. Pressione Ctrl+C para encerrar.\n")
    
    while True:
        try:
            # Lendo as linhas da planilha
            for row in range(2, 13):
                broker_cell = sheet.Cells(row, 1).Value
                if not broker_cell:
                    continue
                    
                broker_name = str(broker_cell).strip().upper()
                if broker_name not in BROKERS_MAP:
                    continue
                    
                win_net_cell = sheet.Cells(row, 2).Value
                win_buy_cell = sheet.Cells(row, 4).Value
                win_sell_cell = sheet.Cells(row, 5).Value
                
                # Conversão para inteiros com filtro para erros do Excel (ex: -2146826246 para #N/A)
                try:
                    win_net = int(win_net_cell) if win_net_cell is not None else None
                    if win_net is not None and win_net < -1000000:
                        win_net = None
                except (ValueError, TypeError):
                    win_net = None
                    
                try:
                    win_buy = int(win_buy_cell) if win_buy_cell is not None else 0
                except (ValueError, TypeError):
                    win_buy = 0

                try:
                    win_sell = int(win_sell_cell) if win_sell_cell is not None else 0
                except (ValueError, TypeError):
                    win_sell = 0
                
                # Enviar para a API local
                if win_net is not None:
                    requests.get(API_UPDATE_URL, params={
                        "symbol": "WIN",
                        "broker": broker_name,
                        "net": win_net,
                        "buy": win_buy,
                        "sell": win_sell
                    }, timeout=1.0)
            
            print(f"[{time.strftime('%H:%M:%S')}] Posições líquidas atualizadas via Excel.")
            time.sleep(1.0)  # Polling a cada 1 segundo
            
        except KeyboardInterrupt:
            print("\nPonte encerrada pelo usuário.")
            break
        except Exception as e:
            print(f"[AVISO] Erro na leitura/transmissão: {e}")
            time.sleep(2)

def run_direct_rtd_bridge():
    """
    MODO DIRETO: Nelogica COM RTD Connection (Experimental/Bitness Dependent)
    """
    print("=" * 65)
    print("  PROFIT RTD BRIDGE — MODO DIRECT COM")
    print("=" * 65)
    print("Tentando instanciar o servidor COM da Nelogica...")
    
    try:
        import win32com.client
    except ImportError:
        print("[ERRO] pywin32 não encontrado.")
        return
        
    try:
        # Tenta instanciar
        rtd = win32com.client.Dispatch("Nelogica.Profit.RTD")
        print("[OK] Servidor RTD 'Nelogica.Profit.RTD' instanciado com sucesso!")
        print("Atenção: Este modo exige registro de DLLs e correspondência de bits (64-bit).")
        # NOTA: Como a API de conexão direta do RTD em COM puro exige callbacks assíncronos que costumam
        # falhar fora do Excel, recomendamos fortemente o uso do `--mode excel` para estabilidade.
        print("\n[Aviso] COM Direto exige suporte IRtdServer completo. Recomendado usar o modo '--mode excel'.")
        
    except Exception as e:
        print(f"[ERRO] Falha ao despachar o RTD direto da Nelogica: {e}")
        print("\n>>> DICA: Use o modo '--mode excel' que funciona sempre! <<<")
        print("Como rodar: python gex/engine/profit_rtd_bridge.py --mode excel")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ponte RTD Profit para o Regime Dashboard")
    parser.add_argument("--mode", type=str, default="excel", choices=["excel", "direct"],
                        help="Modo de conexão: 'excel' (recomendado) ou 'direct'")
    args = parser.parse_args()
    
    if args.mode == "excel":
        run_excel_bridge()
    else:
        run_direct_rtd_bridge()
