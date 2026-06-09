---
status: pending
area: dashboard
created: 2026-06-09
---

# Exibir a Coluna de Eficiência no Dashboard

## Objetivo
Aprimorar visualmente a tabela de corretoras do B3 BrokerFlowPanel com uma nova coluna premium que exibe graficamente a eficiência direcional (Price Influence) de cada player.

## Requisitos
1. Recuperar o objeto `efficiency` a partir dos dados retornados pelo endpoint `/api/flow` no componente React `App.jsx` ou passar como prop ao `BrokerFlowPanel.jsx`.
2. Adicionar uma nova coluna na tabela do `BrokerFlowPanel.jsx` chamada **"EFICIÊNCIA"** (entre *Gráfico 2 (Diretriz)* e *Saldo/Agressão*).
3. Criar uma renderização premium para a eficiência usando uma barra de balanço bidirecional centrada em 0%:
   - Centro fixo em 50% de largura da barra.
   - Preenchimento verde para a direita se o valor for positivo.
   - Preenchimento vermelho para a esquerda se o valor for negativo.
   - Badge numérico acima ou ao lado mostrando o percentual (ex: `+64.2%` ou `-30.5%`).
4. Adicionar suporte a ordenação ao clicar no cabeçalho **"EFICIÊNCIA"** da tabela.
