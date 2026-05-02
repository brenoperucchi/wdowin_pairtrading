# Playbook de Otimização Quantitativa (Pair Trading)

Este documento centraliza o conhecimento, a metodologia e as melhores práticas matemáticas aplicadas na otimização dos robôs de Pair Trading (WDO×WIN e DI×WIN) do sistema *Rastro Irado / Setup Matador*.

A otimização de robôs quantitativos, se feita de forma incorreta, gera "Overfitting" (Superajuste) — um cenário onde o robô gera lucros astronômicos no *Backtest*, mas perde dinheiro no mercado real porque apenas decorou o ruído do passado em vez de capturar o sinal subjacente.

---

## 1. Regra de Ouro: Isolamento de Variáveis (A Lei do "Não Tudo ao Mesmo Tempo")

O erro número 1 de qualquer desenvolvedor quant é jogar todos os parâmetros do modelo e todas as regras financeiras em um único "moedor" (Loop ou Grid Search) ao mesmo tempo. 

Cruzar centenas de parâmetros do Filtro de Kalman (`trans_cov`, `obs_cov`) + dezenas de parâmetros de Cointegração (`johansen_window`) + Regras de Saída (`Take Profit`, `Stop Loss`) cria um universo de milhões de possibilidades. Inevitavelmente, uma dessas possibilidades será uma distorção estatística perfeita para o passado que irá quebrar no futuro.

### A Metodologia de Fases (Abordagem Científica)

Otimize sempre em duas fases completamente isoladas:

*   **Fase 1: Otimização do "Core" Matemático (A Lente do Robô)**
    *   **O que testar:** Apenas parâmetros matemáticos. `trans_cov`, `obs_cov`, e janelas de Z-Score.
    *   **O que travar:** As regras financeiras. Defina um Stop Loss e Take Profit padrão e fixo, e mantenha as zonas de entrada imóveis (ex: Z=1.6). 
    *   **Objetivo:** Descobrir quais parâmetros fazem as linhas do Kalman ou do Johansen acompanharem o preço real sem muito "lag" (atraso) e encontrarem as inflexões de forma limpa.

*   **Fase 2: Otimização das Regras de Trade (O Gatilho)**
    *   **O que testar:** `Z-Score de Entrada`, `Stop Loss (SL)`, e `Take Profit (TP)`.
    *   **O que travar:** O modelo matemático. Pegue o melhor Kalman e Johansen da Fase 1 e congele (Hardcode). A matemática não pode mais mudar.
    *   **Objetivo:** Descobrir se o modelo matemático funciona melhor com alvos longos, stops curtos, ou se precisa antecipar a entrada.

---

## 2. A Filosofia do "Consenso" (Hedge Estrutural)

Em modelos de regressão linear para arbitragem, sinais falsos são o maior dreno de capital. A técnica de Consenso exige que duas fontes de dados independentes (ex: Fluxo vs Juros) validem uma ineficiência direcional antes que qualquer ordem seja executada.

### Parâmetros de Consenso (A Regra "Sinal + Atenção")
No nosso *Setup Matador*, exigimos:
1.  **WDO (Kalman):** Esteja na Zona de Sinal (ex: > 1.4)
2.  **DI (Johansen):** Esteja ao menos na Zona de Atenção (ex: > 1.2) na mesma direção temporal.

### 2.1 Verificação Anti-Overfitting (Testes Isolados)

Sempre que criar um modelo de Consenso, você **precisa provar** que o Filtro B não está apenas maquiando o Filtro A.

Para comprovar isso, rode os relatórios isolados com os exatos mesmos TPs e SLs otimizados para o sistema de consenso (Ex: TP 800, SL 300, Entrada 1.4).

**Resultados Documentados do Setup Matador (15.000 Barras M5):**
*   **Modelo WDO (Isolado):** Fez 1.598 trades, Win Rate 53.8%, Drawdown de R$ 725,00. PnL: R$ 6.453. *(Sinal ruidoso, giro excessivo, paga muita corretagem)*.
*   **Modelo DI (Isolado):** Fez 532 trades, Win Rate 38.0%, Drawdown de R$ 818,00. PnL: R$ 3.158. *(Sinal atrasado, perde a maioria, sobrevive pelo TP longo).*
*   **Modelo Consenso (WDO + DI):** Fez apenas 528 trades, Win Rate saltou para **58.1%**, e o Drawdown despencou para **R$ 248,00**. PnL R$ 3.053.

**A Prova:** O número de trades caiu para 1/3, a taxa de acerto superou o melhor modelo isolado, e o Drawdown caiu 65%. Isso significa que o Johansen DI efetivamente cortou os trades perdedores do WDO, o que comprova que o sistema é estatisticamente robusto e não apenas viciado na curva de capital.

![Curvas Isoladas](assets/isolated_curves.png)
---

## 3. Guia de Parâmetros e Significados

Se for rodar scripts futuros de otimização em `research/`, tenha isso em mente:

*   **Kalman `trans_cov` (Variância de Transição):** 
    *   Valores altos (`1e-3` a `1e-4`): Modo Scalper. Assume que o mercado muda rápido e a relação dos ativos se rompe constantemente. Segue o preço muito de perto. 
    *   Valores baixos (`1e-5` a `1e-6`): Modo Swing. Assume relação estável. Demora mais para dar sinal.
*   **Kalman `obs_cov` (Variância de Observação):**
    *   Confiança na medição. Geralmente mantida entre `1e2` e `1e4`.
*   **Johansen `WINDOW` (Lookback):**
    *   Cointegração precisa de janelas maiores que OLS. Para juros curtos (DI), janelas de `100` a `150` barras M5 se mostraram as ideais para capturar o prêmio de risco do dia anterior.

## 4. Ferramental

1.  Use `research/optimize_core_models.py` para descobrir limites matemáticos de um modelo.
2.  Use `research/optimize_consensus.py` para cruzar matrizes vetoriais independentes e encontrar alinhamentos de *Hedge*.
3.  Use `research/optimize_trade_rules.py` (com Core travado) para perfilar TP, SL e níveis de entrada, buscando o Stop curto e Alvo longo perfeito (como o famoso SL 300 / TP 800 descoberto nesta iteração).
4.  Use `research/plot_isolated.py` para comprovar que os sinais da otimização cruzada não sofrem de Overfitting.
