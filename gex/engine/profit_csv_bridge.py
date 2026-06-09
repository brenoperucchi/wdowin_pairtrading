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

API_UPDATE_URL = "http://127.0.0.1:8080/api/flow/update"
RTD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "RTD")

# Lista de corretoras do Dashboard
BROKERS = ["XP", "UBS", "BTG", "IDEAL", "GENIAL", "JPMORGAN", "TULLETT", "MERRILL", "GOLDMAN", "MORGAN", "CITI", "ITAU", "BRADESCO"]

# Mapeamento de códigos B3 (para Times & Sales com corretoras do IND/DOL cheio)
B3_CODES = {
    3: "XP",         # XP Investimentos
    8: "UBS",        # UBS Brasil
    13: "MERRILL",   # Merrill Lynch (código 13 no Profit)
    16: "JPMORGAN",  # JP Morgan
    23: "GOLDMAN",   # Goldman Sachs
    39: "BRADESCO",  # Ágora (Bradesco)
    40: "MORGAN",    # Morgan Stanley (código 40 no Profit)
    45: "UBS",       # Link / UBS
    72: "BRADESCO",  # Bradesco
    85: "BTG",       # BTG Pactual
    92: "MORGAN",    # Morgan Stanley secundário
    107: "CITI",     # Citibank (código 107 no Profit)
    114: "GENIAL",   # Genial
    120: "XP",       # XP secundário
    127: "TULLETT",  # Tullett Prebon (código 127 no Profit)
    191: "ITAU",     # Itaú
    238: "GOLDMAN",  # Goldman Sachs secundário
    308: "CITI",     # Citigroup
    1618: "IDEAL",   # Ideal
    3093: "IDEAL",   # Ideal secundário
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

def clean_price(price_str):
    """Limpa formatação de preços da B3 com suporte a decimal float (ex: 169.520,00 ou 169520,00)."""
    price_str = str(price_str).replace(".", "").replace(",", ".").replace(" ", "").strip()
    try:
        return float(price_str)
    except ValueError:
        return 0.0

def parse_csv_file(filepath):
    fname = os.path.basename(filepath)
    symbol = "WIN" if "WIN" in fname.upper() else None
    if not symbol:
        return
        
    try:
        with open(filepath, 'r', encoding='latin1', errors='replace') as f:
            first_line = f.readline().strip()
    except PermissionError:
        # Arquivo sendo escrito pelo Profit, tenta no próximo ciclo
        return
        
    if not first_line:
        return
        
    is_saldo = any(k in first_line.upper() for k in ["CORRETORA", "AGENTE", "POSIÇÃO", "POSICAO", "SALDO"])
    
    # Se não for saldo de corretoras, validar se devemos pular para evitar ler arquivo gigantesco
    if not is_saldo:
        # Ignorar Times & Sales anônimos de mini-contratos WIN/WDO
        sep = ';' if ';' in first_line else ','
        parts = first_line.split(sep)
        if len(parts) == 4 or len(parts) < 6:
            # Negócios anônimos, pula imediatamente sem ler o resto do arquivo!
            if not hasattr(parse_csv_file, "_warned_anonymous"):
                parse_csv_file._warned_anonymous = True
                print("!" * 70)
                print(f" [AVISO] O arquivo {fname} contém negócios ANÔNIMOS de Times & Sales.")
                print(" Para mini-contratos WIN/WDO, a B3 não divulga os executores por negócio.")
                print(" >>> SOLUÇÃO: No Profit, abra a tabela 'Saldo de Corretoras' e exporte-a")
                print(f"     em Tempo Real para a pasta RTD/ (ex: {symbol}M26_saldo.csv).")
                print("!" * 70)
            return
            
        # Limite de tamanho para Times & Sales normais para evitar lentidão extrema
        if os.path.getsize(filepath) > 5 * 1024 * 1024:
            print(f"[AVISO] Arquivo {fname} ignorado por exceder o limite de 5MB para Times & Sales.")
            return

    # Só agora lemos o arquivo inteiro
    try:
        with open(filepath, 'r', encoding='latin1', errors='replace') as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
    except Exception:
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
        buy_col = -1
        sell_col = -1
        
        # 1. Procurar corretora, médio
        for idx, col in enumerate(cols):
            if any(k in col for k in ["CORRETORA", "AGENTE", "NOME"]):
                broker_col = idx
            elif any(k in col for k in ["MÉDIO", "MEDIO", "PREÇO", "PRECO"]):
                avg_col = idx
                
        # 2. Procurar Coluna Net (Posição)
        for idx, col in enumerate(cols):
            if any(k in col for k in ["POSIÇÃO", "POSICAO", "SALDO"]) and not "AGRES" in col:
                net_col = idx
                break
        if net_col == -1:
            for idx, col in enumerate(cols):
                if any(k in col for k in ["POSIÇÃO", "POSICAO", "SALDO"]):
                    net_col = idx
                    break

        # 3. Procurar Colunas de Agressão Compra e Venda
        for idx, col in enumerate(cols):
            if any(k in col for k in ["AGRES", "AGR", "AGRESSÃO", "AGRESSAO"]):
                if any(k in col for k in ["COMPRA", "COMPRAS", "BUY"]):
                    buy_col = idx
                elif any(k in col for k in ["VENDA", "VENDAS", "SELL"]):
                    sell_col = idx

        # 4. Fallback para Colunas de Compra/Venda Totais se agressão não encontrada
        if buy_col == -1:
            for idx, col in enumerate(cols):
                if any(k in col for k in ["QTD COMPRA", "QTD_COMPRA", "COMPRAS", "COMPRA", "BUY"]) and not "AGRES" in col:
                    buy_col = idx
                    break
        if sell_col == -1:
            for idx, col in enumerate(cols):
                if any(k in col for k in ["QTD VENDA", "QTD_VENDA", "VENDAS", "VENDA", "SELL"]) and not "AGRES" in col:
                    sell_col = idx
                    break
                
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
            avg_val = clean_price(parts[avg_col]) if avg_col != -1 and len(parts) > avg_col else 0.0
            buy_val = clean_value(parts[buy_col]) if buy_col != -1 and len(parts) > buy_col else 0
            sell_val = clean_value(parts[sell_col]) if sell_col != -1 and len(parts) > sell_col else 0
            
            # Envia a atualização de saldo final diretamente
            try:
                requests.get(API_UPDATE_URL, params={
                    "symbol": symbol,
                    "broker": broker_name,
                    "net": net_val,
                    "avg": avg_val,
                    "buy": buy_val,
                    "sell": sell_val
                }, timeout=2.0)
            except Exception as e:
                print(f"[ERRO API {broker_name}] {e}")
                
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
            # Reconstroi o saldo e a agressão acumulando os negócios
            print(f"[{time.strftime('%H:%M:%S')}] Processando Times & Sales para {symbol} ({len(lines)} negócios)...")
            
            # Estrutura para acumular quantidades e valores para o cálculo do preço médio e agressão
            broker_stats = {
                b: {
                    "buy_qty": 0,
                    "buy_val": 0.0,
                    "sell_qty": 0,
                    "sell_val": 0.0,
                    "aggr_buy": 0,
                    "aggr_sell": 0
                } for b in BROKERS
            }
            
            for line in lines:
                parts = line.split(sep)
                if len(parts) < 6:
                    continue
                    
                # Ex: Time;Side;Price;Quantity;BuyerCode;SellerCode
                price = clean_price(parts[2])
                qty = clean_value(parts[3])
                
                if price <= 0 or qty <= 0:
                    continue
                
                try:
                    buyer_code = int(parts[4])
                    seller_code = int(parts[5])
                except ValueError:
                    continue
                    
                buyer = B3_CODES.get(buyer_code)
                seller = B3_CODES.get(seller_code)
                
                side = parts[1].strip().upper()
                
                # Preço médio e Net
                if buyer:
                    broker_stats[buyer]["buy_qty"] += qty
                    broker_stats[buyer]["buy_val"] += qty * price
                if seller:
                    broker_stats[seller]["sell_qty"] += qty
                    broker_stats[seller]["sell_val"] += qty * price
                    
                # Agressão
                # 1. Tentar pela coluna de agressor explícita se houver (geralmente coluna 7, índice 6)
                aggressor = parts[6].strip().upper() if len(parts) >= 7 else None
                if aggressor:
                    if "COMPRA" in aggressor or "COMPRADOR" in aggressor:
                        if buyer:
                            broker_stats[buyer]["aggr_buy"] += qty
                    elif "VENDA" in aggressor or "VENDEDOR" in aggressor:
                        if seller:
                            broker_stats[seller]["aggr_sell"] += qty
                else:
                    # 2. Fallback para a coluna Side (coluna 2, índice 1)
                    if "COMPRA" in side:
                        if buyer:
                            broker_stats[buyer]["aggr_buy"] += qty
                    elif "VENDA" in side:
                        if seller:
                            broker_stats[seller]["aggr_sell"] += qty
                    
            # Enviar os saldos agregados e preços médios para o servidor
            for broker_name, stats in broker_stats.items():
                net_val = stats["buy_qty"] - stats["sell_qty"]
                
                # Preço médio: média ponderada das compras (se líquido comprado) ou das vendas (se líquido vendido)
                if net_val > 0:
                    avg_val = stats["buy_val"] / stats["buy_qty"] if stats["buy_qty"] > 0 else 0.0
                elif net_val < 0:
                    avg_val = stats["sell_val"] / stats["sell_qty"] if stats["sell_qty"] > 0 else 0.0
                else:
                    avg_val = 0.0
                
                try:
                    requests.get(API_UPDATE_URL, params={
                        "symbol": symbol,
                        "broker": broker_name,
                        "net": net_val,
                        "avg": round(avg_val, 2),
                        "buy": stats["aggr_buy"],
                        "sell": stats["aggr_sell"]
                    }, timeout=2.0)
                except Exception as e:
                    print(f"[ERRO API {broker_name}] {e}")

def main():
    print("=" * 65)
    print("  PROFIT CSV REAL-TIME BRIDGE (JUMBA FLOW)")
    print("=" * 65)
    print(f"  Diretório monitorado: {RTD_DIR}")
    print("  Aguardando alterações nos arquivos do Profit...")
    print("  Pressione Ctrl+C para sair.\n")
    
    # Criar pasta RTD se não existir
    os.makedirs(RTD_DIR, exist_ok=True)
    
    last_states = {}
    
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
                    if "saldo" not in fname.lower():
                        continue
                    
                try:
                    size = os.path.getsize(filepath)
                    mtime = os.path.getmtime(filepath)
                except OSError:
                    continue  # Arquivo pode estar bloqueado ou deletado temporariamente
                    
                old_state = last_states.get(filepath, (0, 0))
                
                if size != old_state[0] or mtime != old_state[1]:
                    last_states[filepath] = (size, mtime)
                    parse_csv_file(filepath)
                    
            time.sleep(0.1)
            
        except KeyboardInterrupt:
            print("\nPonte CSV encerrada.")
            break
        except Exception as e:
            print(f"[AVISO] Erro no loop do monitor: {e}")
            time.sleep(2)

if __name__ == "__main__":
    main()
