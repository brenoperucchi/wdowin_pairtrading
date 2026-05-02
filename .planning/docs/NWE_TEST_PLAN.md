# Integração do Filtro Nadaraya-Watson Envelope (NWE) ao Setup Matador

## Objetivo
Testar estatisticamente se a adição do filtro NWE (Nadaraya-Watson Envelope) melhora a performance do "Setup Matador" atual, filtrando sinais com base na inclinação da curva de preço suavizada do índice WIN.

## Como Funcionaria o NWE no Backtest?

O NWE é um algoritmo de regressão de kernel que cria uma linha suavizada não-paramétrica que persegue o preço, isolando a tendência principal (ruído é ignorado).

Na nossa arquitetura, teríamos duas formas de usar a inclinação (Slope) do NWE como filtro de bloqueio:

1.  **Filtro "A Favor da Tendência" (Trend-Following):**
    *   Sinal de COMPRA do Consenso (WDO+DI) só é autorizado se o NWE estiver **VERDE** (Subindo / Slope > 0). *Lógica: Comprar as quedas do spread apenas se o mercado macro do dia estiver subindo.*
    *   Sinal de VENDA do Consenso só é autorizado se o NWE estiver **VERMELHO** (Caindo / Slope < 0). *Lógica: Vender o topo do spread apenas se o mercado macro do dia estiver caindo.*

2.  **Filtro "Contra a Tendência" (Mean-Reversion Fader):**
    *   Sinal de COMPRA só autorizado se o NWE estiver VERMELHO.
    *   Sinal de VENDA só autorizado se o NWE estiver VERDE.
    *(No Frontend do Dashboard, o código Javascript atualmente faz essa segunda opção, apagando os sinais a favor da tendência).*

## Perguntas Abertas para Aprovação

1. No Javascript do painel, o Filtro NWE hoje apaga o sinal VERDE de compra quando a tendência está VERDE (Subindo). Ou seja, ele age como "Fader/Contra-Tendência". Você quer que eu teste essa lógica "Contra-Tendência", a lógica tradicional de "Comprar junto com a Tendência", ou ambas para compararmos?
2. O kernel no dashboard usa Janela de Lookback de 100 barras e Bandwidth 8. Posso replicar esses exatos parâmetros no motor de teste em Python?

## Etapas Técnicas

1.  Criar `research/optimize_nwe.py`.
2.  Traduzir a função matemática Javascript `calc_nwe()` exatamente para Python.
3.  Puxar 15.000 barras do banco de dados e processar `z_wdo`, `z_di` e `nwe_slope`.
4.  Cruzar as matrizes e apresentar se o lucro sobe ou desce com o filtro.
5.  Se aprovar, implementamos direto no robô de produção.
