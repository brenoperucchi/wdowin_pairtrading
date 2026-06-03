# -*- coding: utf-8 -*-
"""
JUMBA FLOW - PROFIT CSV REAL-TIME BRIDGE
Monitora a pasta RTD/ por exportações em tempo real do Profit e atualiza o Dashboard.

Como rodar:
  .\.venv\Scripts\python.exe gex/engine/profit_csv_bridge.py
"""
import os
import time
import glob
import requests
import re

API_UPDATE_URL = "http://localhost:8080/api/flow/update"
RTD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "RTD")

# Lista de corretoras do Dashboard
BROKERS = ["XP", "UBS", "BTG", "IDEAL", "GENIAL", "JPMORGAN", "TULLETT", "MERRILL", "GOLDMAN", "MORGAN", "CITI", "ITAU", "BRADESCO"]

# Mapeamento de códigos B3 (para Times & Sales com corretoras do IND/DOL cheio)
B3_CODES = {
    16: "JPMORGAN",
    23: "GOLDMAN",
    40: "UBS",      # UBS / Link
    45: "UBS",
    72: "BRADESCO",
    85: "BTG",
    92: "MORGAN",    # Morgan Stanley
    114: "GENIAL",
    120: "XP",
    191: "ITAU",     # Itaú
    308: "CITI",
    1618: "IDEAL",
    3093: "IDEAL",
}

# Normalização de nomes de corretoras (para Saldo de Corretoras)
def match_broker_name(text):
    text_upper = str(text).upper().strip()
    
    # Casos especiais primeiro
    if "JP" in text_upper and "MORGAN" in text_upper:
        return "JPMORGAN"
    if "STANLEY" in text_upper or ("MORGAN" in text_upper and "JP" not in text_upper):
        return "MORGAN"
    if "PREBON" in text_upper or "TULLETT" in text_upper:
        return "TULLETT"
    if "LYNCH" in text_upper or "MERRILL" in text_upper:
        return "MERRILL"
    
    # Casos diretos
    for b in BROKERS:
        if b in text_upper:
            return b
            
    return None

def clean_value(val_str):
    """Limpa formatação de números da B3 (ex: 12.500 ou -8.400,00)."""
    val_str = str(val_str).replace(".", "").replace(",", ".").replace(" ", "").strip()
    try:
        if "." in val_str:
            return int(float(val_str))
        return int(val_str)
    except ValueError:
        return 0

def parse_csv_file(filepath):
    fname = os.path.basename(filepath)
    symbol = "WIN" if "WIN" in fname.upper() else ("WDO" if "WDO" in fname.upper() else None)
    if not symbol:
        return
        
    try:
        with open(filepath, 'r', encoding='latin1', errors='replace') as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
    except PermissionError:
        # Arquivo sendo escrito pelo Profit, tenta no próximo ciclo
        return
        
    if not lines:
        return
        
    first_line = lines[0]
    
    # 1. Detectar se é Saldo de Corretoras
    # Formato comum: Corretora;Posição;Preço Médio;... ou Agente;Posicao;...
    is_saldo = any(k in first_line.upper() for k in ["CORRETORA", "AGENTE", "POSIÇÃO", "POSICAO", "SALDO"])
    
    if is_saldo:
        # Encontra o separador (; ou ,)
        sep = ';' if ';' in first_line else ','
        cols = [c.strip().upper() for c in first_line.split(sep)]
        
        # Encontrar índices
        broker_col = -1
        net_col = -1
        avg_col = -1
        
        for idx, col in enumerate(cols):
            if any(k in col for k in ["CORRETORA", "AGENTE", "NOME"]):
                broker_col = idx
            elif any(k in col for k in ["POSIÇÃO", "POSICAO", "SALDO"]):
                net_col = idx
            elif any(k in col for k in ["MÉDIO", "MEDIO", "PREÇO", "PRECO"]):
                avg_col = idx
                
        if broker_col == -1 or net_col == -1:
            print(f"[ERRO] Formato de colunas inválido no Saldo de Corretoras: {first_line}")
            return
            
        print(f"[{time.strftime('%H:%M:%S')}] Lendo Saldo de Corretoras para {symbol} ({fname})")
        for line in lines[1:]:
            parts = line.split(sep)
            if len(parts) <= max(broker_col, net_col):
                continue
                
            raw_broker = parts[broker_col]
            broker_name = match_broker_name(raw_broker)
            if not broker_name:
                continue
                
            net_val = clean_value(parts[net_col])
            avg_val = clean_value(parts[avg_col]) if avg_col != -1 and len(parts) > avg_col else 0.0
            
            # Envia a atualização de saldo final diretamente
            try:
                requests.get(API_UPDATE_URL, params={
                    "symbol": symbol,
                    "broker": broker_name,
                    "net": net_val,
                    "avg": avg_val
                }, timeout=0.5)
            except Exception as e:
                pass
                
    # 2. Detectar se é Times & Sales (Lista de Negócios)
    # Formato: 09:00:00:123;Compra;174200,00;500;120;85 (7 colunas) ou 4 colunas (anônimo)
    else:
        sep = ';' if ';' in first_line else ','
        parts = first_line.split(sep)
        
        if len(parts) == 4:
            # Negócios anônimos (mini contratos WIN/WDO normais)
            # Imprime aviso de instrução para o usuário uma vez
            if not hasattr(parse_csv_file, "_warned_anonymous"):
                parse_csv_file._warned_anonymous = True
                print("!" * 70)
                print(f" [AVISO] O arquivo {fname} contém negócios ANÔNIMOS de Times & Sales.")
                print(" Para mini-contratos WIN/WDO, a B3 não divulga os executores por negócio.")
                print(" >>> SOLUÇÃO: No Profit, abra a tabela 'Saldo de Corretoras' e exporte-a")
                print(f"     em Tempo Real para a pasta RTD/ (ex: {symbol}M26_saldo.csv).")
                print("!" * 70)
            return
            
        if len(parts) >= 6:
            # Formato de 6 ou 7 colunas com corretoras (IND/DOL cheio ou pós-leilão)
            # Reconstroi o saldo de cada corretora acumulando os negócios
            print(f"[{time.strftime('%H:%M:%S')}] Processando Times & Sales para {symbol} ({len(lines)} negócios)...")
            
            broker_nets = {b: 0 for b in BROKERS}
            
            for line in lines:
                parts = line.split(sep)
                if len(parts) < 6:
                    continue
                    
                # Ex: Time;Side;Price;Quantity;BuyerCode;SellerCode
                side = parts[1].upper()
                qty = clean_value(parts[3])
                
                try:
                    buyer_code = int(parts[4])
                    seller_code = int(parts[5])
                except ValueError:
                    continue
                    
                buyer = B3_CODES.get(buyer_code)
                seller = B3_CODES.get(seller_code)
                
                if buyer:
                    broker_nets[buyer] += qty
                if seller:
                    broker_nets[seller] -= qty
                    
            # Enviar os saldos agregados para o servidor
            for broker_name, net_val in broker_nets.items():
                try:
                    requests.get(API_UPDATE_URL, params={
                        "symbol": symbol,
                        "broker": broker_name,
                        "net": net_val
                    }, timeout=0.5)
                except Exception as e:
                    pass

def main():
    print("=" * 65)
    print("  PROFIT CSV REAL-TIME BRIDGE (JUMBA FLOW)")
    print("=" * 65)
    print(f"  Diretório monitorado: {RTD_DIR}")
    print("  Aguardando alterações nos arquivos do Profit...")
    print("  Pressione Ctrl+C para sair.\n")
    
    # Criar pasta RTD se não existir
    os.makedirs(RTD_DIR, exist_ok=True)
    
    last_sizes = {}
    
    while True:
        try:
            csv_files = glob.glob(os.path.join(RTD_DIR, "*.csv"))
            
            for filepath in csv_files:
                fname = os.path.basename(filepath)
                # Ignorar arquivos muito antigos de outros pregões se houver novos de hoje
                # Pegar data de hoje no formato ddmmyyyy para conferir
                today_str = time.strftime("%d_%m_%Y")
                
                # Se houver arquivos de hoje, focar neles. Caso contrário, lê o que tiver.
                today_files = [f for f in csv_files if today_str in f]
                if today_files and today_str not in fname:
                    continue
                    
                size = os.path.getsize(filepath)
                old_size = last_sizes.get(filepath, -1)
                
                if size != old_size:
                    last_sizes[filepath] = size
                    parse_csv_file(filepath)
                    
            time.sleep(1.0)
            
        except KeyboardInterrupt:
            print("\nPonte CSV encerrada.")
            break
        except Exception as e:
            print(f"[AVISO] Erro no loop do monitor: {e}")
            time.sleep(2)

if __name__ == "__main__":
    main()
