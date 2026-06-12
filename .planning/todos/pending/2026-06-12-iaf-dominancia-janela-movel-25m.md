---
status: pending
area: backend
created: 2026-06-12
---

# Implementar Janela Móvel de 25 Minutos para Dominância no IAF

## Objetivo
Atualizar o cálculo de dominância de players (Eficiência Direcional - DDE) no cálculo do IAF para usar a mesma janela móvel deslizante de 5 barras (25 minutos) da pressão, evitando a ancoragem do volume da abertura.

## Requisitos
1. **Atualizar `calculate_directional_efficiency` em `server.py`:**
   - Adicionar o parâmetro opcional `lookback_bars: int = None` na assinatura da função:
     ```python
     def calculate_directional_efficiency(lookback_bars: int = None):
     ```
   - Se `lookback_bars` for especificado, filtrar a lista de `rows` obtida da tabela `bar_history` para manter apenas os últimos `lookback_bars` registros antes de calcular a soma de `dPrice * dNet` e a eficiência de cada corretora:
     ```python
     if lookback_bars is not None:
         rows = rows[-lookback_bars:]
     ```
2. **Atualizar `calculate_flow_acceleration` em `server.py`:**
   - Dentro da função, calcular uma versão de curto prazo da eficiência com lookback de 5 barras para definir os players dominantes:
     ```python
     short_term_eff = calculate_directional_efficiency(lookback_bars=5)
     ```
   - Usar `short_term_eff` em vez do parâmetro de eficiência acumulada diária para identificar a lista de `dominant_players["WIN"]` e seus pesos.
3. **Verificar Endpoint `/api/flow`:**
   - Garantir que a chamada para `calculate_flow_acceleration` não force o uso de eficiência acumulada diária, de forma que o IAF seja sempre calculado com a dominância móvel de 25 minutos.
