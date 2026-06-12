---
title: Sensibilidade Intraday do IAF e Janela Móvel
date: 2026-06-12
context: Socratic exploration of IAF indicator responsiveness to intraday player dominance
---

# Sensibilidade Intraday do IAF (Acelerador de Pressão) e Janela Móvel

Detalhamento das decisões de design e justificativas técnicas para a migração da dominância de players de um modelo diário acumulado para uma janela móvel de 25 minutos.

## 1. O Problema da Ancoragem de Volume
O período de abertura do mercado de futuros da B3 (09:00 às 10:00) concentra os maiores picos de volume e volatilidade do dia. No modelo antigo, a dominância das corretoras (Eficiência Direcional - DDE) era acumulada ao longo de toda a sessão desde a abertura. 
Isso criava os seguintes problemas à tarde:
* **Perda de Sensibilidade:** Um player que operou bilhões de contratos na abertura mantinha o peso de dominância máximo mesmo que estivesse totalmente inativo após o meio-dia.
* **Inércia do Sistema:** Novos players que passavam a atuar fortemente no período da tarde não conseguiam atingir a classificação de dominância (DDE >= 40%) porque o denominador da fórmula acumulava todo o histórico da manhã.

## 2. A Solução: Alinhamento de Janelas Móveis
Para manter a continuidade e suavidade dos dados sem causar descontinuidades abruptas (efeito de borda de resets periódicos a cada 30 minutos), decidimos adotar uma **janela móvel deslizante**.

* **Parâmetro Escolhido:** 5 barras de 5 minutos (total de 25 minutos).
* **Alinhamento:** Esse período coincide perfeitamente com a janela de cálculo da pressão de Kyle's Lambda e desvio de preço já utilizados pelo IAF.
* **Comportamento Dinâmico:** A cada nova barra de 5 minutos:
  1. A dominância de players (DDE curta) é recalculada utilizando apenas a variação de preço e saldo de agressão das últimas 5 barras.
  2. O peso de dominância de cada player se adapta instantaneamente à estrutura atual do livro e fita de ordens.
  3. O IAF resultante torna-se sensível aos movimentos de players que estão provocando deslocamento de preço *no exato momento*, filtrando as memórias da manhã.
