---
status: pending
area: backend
created: 2026-06-09
---

# Implementar Cálculo de Eficiência Direcional no Backend

## Objetivo
Calcular e expor no backend o índice de Eficiência Direcional (Player Price Influence) de cada corretora baseado em todo o dia corrente para os ativos WIN e WDO.

## Requisitos
1. Criar a função `calculate_directional_efficiency()` em `server.py` que:
   - Busque as barras fechadas de hoje em `trades.db` da tabela `bar_history`.
   - Ordene cronologicamente e extraia as variações de preço ($dPrice = Price_t - Price_{t-1}$) e variações de saldo ($dNet = Net_t - Net_{t-1}$) de cada corretora a partir do `flow_json`.
   - Calcule o score de eficiência direcional acumulado do dia para cada player: $\frac{\sum dPrice_t \cdot dNet_t}{\sum |dPrice_t \cdot dNet_t|} \times 100$.
2. Atualizar o endpoint `/api/flow` em `server.py` para injetar a chave `efficiency` contendo os scores de WIN e WDO para cada corretora ativa.
3. Testar a API localmente chamando `http://localhost:8080/api/flow` e conferindo a integridade dos dados retornados.
