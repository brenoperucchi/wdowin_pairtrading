# 🔬 Guia de Otimização por Etapas — Setup Matador v4

> **Para quem é este guia?** Para quem já leu o [Guia de Estratégias](./GUIA_ESTRATEGIAS.md)
> e agora quer entender **como descobrimos os valores ideais** de cada parâmetro.
> Explicamos o processo passo a passo, como se fosse uma receita de cozinha.

---

## 🧭 Antes de Tudo: O que é "Otimizar"?

**Otimizar** é o processo de testar milhares de combinações de parâmetros no passado
para descobrir quais valores geram o melhor resultado. É como ajustar a receita de
um bolo: mais açúcar? menos farinha? mais tempo no forno?

### ⚠️ O Grande Perigo: Overfitting

> **Overfitting** = O robô "decorou a prova" em vez de "aprender a matéria".

**Analogia**: Imagine que você estuda para uma prova usando apenas as provas antigas.
Se você decora as respostas, tira 10 nas provas velhas — mas tira 2 na prova nova.
Isso é overfitting.

No trading quantitativo, overfitting acontece quando:
- Você testa **muitas combinações ao mesmo tempo** (ex: 10.000 combinações)
- O robô encontra um "acidente estatístico" que funcionou no passado
- Esse acidente **nunca mais se repete** no mercado real

### 🛡️ A Regra de Ouro: Isolamento de Variáveis

> **NUNCA otimize tudo ao mesmo tempo.**

Se você mistura parâmetros do Kalman + Z-Score + SL/TP + NWE + horários em um único teste,
você está testando **milhões** de combinações. Inevitavelmente uma delas será "perfeita"
no passado — e inútil no futuro.

A solução: **Otimize em etapas isoladas**, como um cientista.

---

## 📋 As 6 Etapas da Otimização

```
┌──────────────────────────────────────────┐
│  ETAPA 1: Preparar os Dados              │
│  ↓                                       │
│  ETAPA 2: Otimizar o Kalman (a "lente")  │
│  ↓                                       │
│  ETAPA 3: Otimizar os Z-Scores           │
│  ↓                                       │
│  ETAPA 4: Otimizar o NWE (filtro)        │
│  ↓                                       │
│  ETAPA 5: Otimizar SL/TP/Break-Even      │
│  ↓                                       │
│  ETAPA 6: Validar (provar que não é OVF) │
└──────────────────────────────────────────┘
```

A cada etapa, você **trava** os resultados anteriores. Os parâmetros da Etapa 2 ficam
fixos quando você faz a Etapa 3. E assim por diante.

---

## 📦 ETAPA 1: Preparar os Dados

### O que fazer

Antes de qualquer teste, você precisa buscar dados históricos do MetaTrader 5.

### Script

```bash
# O script já faz isso automaticamente:
cd "c:\Users\ryzen\Downloads\Antigravity\wdo win pair trading"
python research/backtest_matador.py
```

### O que ele faz por baixo

1. **Conecta ao MT5** e baixa ~50.000 barras M5 (≈1 ano) dos 3 ativos: WIN, WDO, DI
2. **Alinha os dados** no tempo (garante que barra 1 do WIN = barra 1 do WDO = barra 1 do DI)
3. **Gera os Z-Scores** de ambos os pares (WDO Kalman + DI Kalman)
4. **Roda backtests** com cenários pré-definidos

### Parâmetros que você controla

| Parâmetro | Valor Padrão | O que significa |
|-----------|-------------|-----------------|
| `BARS_TO_FETCH` | 50.000 | ~1 ano de dados M5 |
| `TIMEFRAME` | M5 | Barras de 5 minutos |

### 💡 Dica para Iniciantes

> Quanto mais dados melhor, mas com um limite:
> dados muito antigos (>2 anos) podem refletir um mercado que já não existe.
> O ideal é **1 a 2 anos** de dados M5.

---

## 🔭 ETAPA 2: Otimizar o Kalman (A "Lente" do Robô)

### O que estamos otimizando

O Filtro de Kalman é o "olho" do robô. Ele decide **qual é a relação real** entre
WIN e WDO (ou DI). Se esse olho estiver desregulado, todos os sinais serão errados.

### Os 3 parâmetros

| Parâmetro | Range Testado | O que faz |
|-----------|--------------|-----------|
| `trans_cov` (Q) | 1e-6 até 1e-2 | Velocidade de adaptação do Beta |
| `obs_cov` (R) | 1e0 até 1e4 | Tolerância ao ruído |
| `z_window` (W) | 20 até 100 | Memória do Z-Score |

### O que TRAVAR nesta etapa

| Parâmetro | Valor Travado | Justificativa |
|-----------|--------------|---------------|
| SL | 1.000 pts | Valor "neutro" que não influencia |
| TP | 1.000 pts | Valor "neutro" que não influencia |
| Z Entry | 2.0 | Valor alto para evitar sinais demais |
| NWE | Desligado | Ainda não otimizamos |

### Script

```bash
python research/optimize_core_models.py
```

### Como interpretar os resultados

O script gera uma tabela assim:

```
Q=1e-4  R=1e2  W=40  →  PnL: 6.453  DD: 725  Ret/DD: 8.9
Q=1e-3  R=1e2  W=40  →  PnL: 5.210  DD: 890  Ret/DD: 5.8
Q=1e-5  R=1e2  W=40  →  PnL: 4.100  DD: 610  Ret/DD: 6.7
```

### 📏 Métrica Principal: Ret/DD (Retorno sobre Drawdown)

> **Ret/DD** = Lucro Total ÷ Máxima Perda Consecutiva

**Analogia**: Se um motorista de Uber fatura R$ 5.000/mês mas bate o carro 3 vezes
(custo R$ 2.000 cada), o "Ret/DD" dele é ruim. Outro motorista fatura R$ 3.000 mas
nunca bate — esse tem Ret/DD melhor.

**Regra**: Escolha o Kalman com **maior Ret/DD**, NÃO o maior PnL.

| Métrica | Bom | Ótimo | Significado |
|---------|-----|-------|-------------|
| Ret/DD | > 3.0 | > 8.0 | Lucro é X vezes maior que o pior momento |
| Win Rate | > 45% | > 55% | Porcentagem de trades vencedores |
| Profit Factor | > 1.2 | > 1.8 | Lucro bruto ÷ Perda bruta |

### Resultado Atual (Validado)

| Par | Q | R | W | Justificativa |
|-----|---|---|---|--------------|
| **WDO** | 1e-4 | 1e2 | 40 | Relação estável, adaptação lenta |
| **DI** | 1e-3 | 1e1 | 60 | Relação volátil, adaptação rápida |

---

## 🔀 ETAPA 2B: Alternativa OLS (Quando NÃO usar Kalman)

> O Kalman é o método principal do sistema, mas o **OLS (Mínimos Quadrados)** é uma
> alternativa mais simples que pode funcionar melhor em certos cenários. Esta etapa
> ensina quando e como testar OLS no lugar do Kalman.

### Kalman vs OLS — Entendendo a Diferença

**Analogia do GPS**:

| Método | Analogia | Comportamento |
|--------|----------|---------------|
| **Kalman** | GPS com giroscópio | Atualiza a posição suavemente, "lembra" onde estava |
| **OLS** | GPS sem memória | Recalcula tudo do zero a cada barra usando uma janela fixa |

Em termos práticos:

```
Kalman: Beta(t) = Beta(t-1) ajustado pelo erro atual
        → "O beta de agora é o de antes, corrigido um pouco"

OLS:    Beta(t) = Regressão dos últimos W pontos
        → "Esquece tudo e recalcula usando as últimas W barras"
```

### Quando Testar OLS ao Invés de Kalman?

| Situação | Melhor Método | Por quê |
|----------|--------------|---------|
| Relação estável (WIN×WDO) | **Kalman** | Suaviza ruído, beta muda devagar |
| Relação volátil (WIN×DI) | **Testar ambos** | OLS pode reagir melhor a quebras |
| Mercado em crise / mudança de regime | **OLS** | Esquece o passado mais rápido |
| Dados com muitos gaps | **OLS** | Kalman "arrasta" erro de gaps |
| Início de operação (sem histórico) | **OLS** | Não precisa de burn-in |

### O Parâmetro do OLS: Apenas a Janela (Window)

O OLS tem **apenas 1 parâmetro** para otimizar (vs 3 do Kalman):

| Parâmetro | Range Testado | O que faz |
|-----------|--------------|-----------|
| `WINDOW` | 20 até 200 | Quantas barras usar na regressão |

**Analogia**: O tamanho da janela é como o "campo de visão" de um binóculo:
- **Window = 20** (40 barras × 5 min = 1h40) — Binóculo de perto → Beta muda rápido,
  reage a tudo, mas fica instável.
- **Window = 90** (nosso padrão) — Binóculo médio → Equilibra velocidade e estabilidade.
- **Window = 200** (1000 min ≈ 2 dias) — Binóculo de longe → Beta quase não muda,
  muito estável mas lento para reagir.

### Como o OLS Calcula o Z-Score

A matemática do OLS é mais direta que o Kalman:

```
1. Pega os últimos W preços de WIN e WDO
2. Faz uma regressão linear: WIN = α + β × WDO
3. Calcula o spread: Spread = WIN_real - WIN_previsto
4. Normaliza o spread: Z = (Spread - Média) / Desvio_Padrão
```

```python
# Versão simplificada do código real (ols_v2_phase1_zscores.py)
def rolling_ols(y, x, window):
    cov   = y.rolling(window).cov(x)      # Covariância
    var   = x.rolling(window).var()         # Variância
    beta  = cov / var                       # Beta = Cov(Y,X) / Var(X)
    spread = y - (beta * x)                 # Spread residual
    z_score = (spread - spread.mean()) / spread.std()
    return beta, spread, z_score
```

### Script para Otimizar OLS

```bash
# Fase 1 OLS: Grid search de Z-Scores com OLS como modelo base
python research/ols_v2_phase1_zscores.py
```

Este script:
1. Calcula o Rolling OLS com janela=40 para WDO e DI
2. Testa combinações de Z_WDO × Z_DI × Z_ATT (mesma lógica do Kalman)
3. Gera relatório com os melhores thresholds

### Scripts OLS Disponíveis (Pipeline Completo)

| Script | Etapa | O que faz |
|--------|-------|-----------|
| `ols_v2_phase1_zscores.py` | Z-Scores | Grid search Entry/Attention com OLS |
| `ols_v2_phase2_nwe.py` | NWE | Testa filtro NWE sobre sinais OLS |
| `ols_v2_phase3_exits.py` | SL/TP | Otimiza regras de saída com OLS |
| `ols_v2_phase4_breakeven.py` | Break-Even | Otimiza BE_ACT/BE_LOCK com OLS |
| `ols_v2_phase5_hours.py` | Horários | Testa janelas de horário com OLS |
| `ols_v2_phase6_cooldown.py` | Cooldown | Testa tempo mínimo entre trades |

> **Dica**: O pipeline OLS tem as mesmas 6 fases do Kalman. A única diferença é
> que no lugar de otimizar Q/R/W, você otimiza apenas a **janela do OLS**.

### Como Comparar Kalman vs OLS Cientificamente

Para decidir qual método usar, rode o script de comparação:

```bash
# Comparar 4 métodos de hedge ratio para o par WIN×WDO
python research/compare_hedge_methods.py --pair wdo

# Comparar para o par WIN×DI
python research/compare_hedge_methods.py --pair di
```

O script gera gráficos e uma tabela comparativa com 4 métricas:

| Métrica | O que mede | Bom para quem? |
|---------|-----------|----------------|
| **Half-Life** | Velocidade de reversão (em barras) | Menor = melhor |
| **Hurst** | Tendência vs reversão (0 a 1) | < 0.5 = mean-reverting ✅ |
| **ADF p-value** | Estacionariedade do spread | < 0.05 = estacionário ✅ |
| **Sharpe** | Retorno ajustado ao risco | Maior = melhor |

### Exemplo de Resultado Comparativo

```
     Method     Half-Life  Hurst   ADF p-value  Sharpe  Mean-Reverting?
     OLS             12.3  0.421        0.001    1.82  YES
     Kalman          15.1  0.389        0.000    2.14  YES    ← Vencedor
     Kalman Log      18.7  0.445        0.003    1.45  YES
     Johansen        22.4  0.512        0.082    0.91  MAYBE
```

**Como ler a tabela**:
- **Hurst < 0.5** = O spread reverte à média (queremos isso!)
- **ADF p-value < 0.05** = O spread é estacionário (não vaga aleatoriamente)
- **Sharpe** = Retorno por unidade de risco (quanto maior, melhor)
- O método com **melhor Sharpe + Hurst < 0.5** é o vencedor

### Decisão Final: Kalman ou OLS?

| Critério | Kalman Vence | OLS Vence |
|----------|-------------|-----------|
| Sharpe maior? | ✅ Geralmente sim | Às vezes (mercados voláteis) |
| Hurst menor? | ✅ Geralmente sim | Raramente |
| Simplicidade? | ❌ 3 parâmetros | ✅ 1 parâmetro |
| Risco de overfitting? | ⚠️ Médio (3 params) | ✅ Baixo (1 param) |
| Precisa de burn-in? | ⚠️ Sim (15.000 barras) | ✅ Não |

> **Recomendação para iniciantes**: Comece com **OLS janela=40** (mais simples,
> menos risco de overfitting). Depois compare com Kalman. Se o Kalman tiver Sharpe
> ≥20% melhor que OLS, vale a complexidade adicional.

### Resumo da Etapa 2B

```
┌───────────────────────────────────────────────────┐
│  1. Rode compare_hedge_methods.py --pair wdo      │
│  2. Compare Sharpe, Hurst e ADF entre os métodos  │
│  3. Se Kalman vencer → use Kalman (padrão)        │
│  4. Se OLS vencer → rode pipeline ols_v2_*        │
│  5. TRAVE o método escolhido antes da Etapa 3     │
└───────────────────────────────────────────────────┘
```

---

## 📊 ETAPA 3: Otimizar os Z-Scores (O "Gatilho")

### O que estamos otimizando

Agora que o Kalman está travado, queremos descobrir: **em que nível de Z-Score
devemos entrar?** Muito baixo = sinais demais (ruído). Muito alto = sinais de menos
(perder oportunidades).

### Os 3 parâmetros

| Parâmetro | Range Testado | O que faz |
|-----------|--------------|-----------|
| `Z_ENTRY` (WDO) | 1.2 até 2.6 | Quando o WDO é forte o suficiente |
| `Z_ENTRY` (DI) | 1.2 até 4.0 | Quando o DI é forte o suficiente |
| `Z_ATTENTION` | 1.0 até 1.6 | Nível mínimo para "o outro" confirmar |

### Script

```bash
python research/optimize_phase1_zscores.py
```

### Como funciona o Grid Search

O script testa **todas as combinações** dos 3 parâmetros:

```
Z_WDO = [1.4, 1.5, 1.6, ..., 2.5]    → 12 valores
Z_DI  = [2.2, 2.4, 2.6, ..., 4.0]    → 10 valores
Z_ATT = [1.2, 1.3, 1.4, 1.5, 1.6]    → 5 valores
                                        ─────────────
Total:                                   600 combinações
```

Para cada combinação, roda o backtest completo e calcula PnL, Drawdown, Win Rate.

### Saída: Heatmap

O script gera um **mapa de calor** (heatmap) mostrando as melhores zonas:

```
               Z_DI →
          2.2   2.4   2.6   2.8   3.0
Z_WDO ↓  ┌─────┬─────┬─────┬─────┬─────┐
  1.4    │ 8.9 │ 7.2 │ 6.1 │ 5.0 │ 3.2 │  ← Quente = bom
  1.6    │ 7.1 │ 6.8 │ 5.5 │ 4.2 │ 2.8 │
  1.8    │ 5.2 │ 5.0 │ 4.1 │ 3.5 │ 2.1 │
  2.0    │ 3.8 │ 3.5 │ 3.0 │ 2.2 │ 1.5 │  ← Frio = ruim
         └─────┴─────┴─────┴─────┴─────┘
```

### 💡 Dica: O "Platô" é seu amigo

> Procure uma **região** que seja boa, não um **ponto** que seja o melhor.

Se Z_ENTRY=1.4 tem Ret/DD de 8.9, e Z_ENTRY=1.6 tem 7.1, ambos são bons.
Isso indica uma **zona robusta** (não é overfitting).

Se Z_ENTRY=2.37 tem Ret/DD de 12.0, mas 2.35 e 2.39 têm Ret/DD de 3.0,
isso é um **ponto isolado** (provável overfitting).

### Resultado Atual (Validado)

| Parâmetro | Valor | Justificativa |
|-----------|-------|---------------|
| `Z_ENTRY` | ±1.4 | Centro de um platô estável |
| `Z_ATTENTION` | ±1.2 | Confirmação cruzada flexível |
| `Z_ANOMALY` | ±4.0 | Breakdowns — bloqueio total |

---

## 🌊 ETAPA 4: Otimizar o NWE (O Filtro de Tendência)

### O que estamos otimizando

O NWE filtra sinais que vão "contra a maré". Queremos encontrar:
- A **suavidade ideal** da curva (bandwidth)
- O **contexto histórico** ideal (lookback)
- Se devemos operar **a favor** ou **contra** a tendência

### Os parâmetros

| Parâmetro | Range Testado | O que faz |
|-----------|--------------|-----------|
| `NWE_BANDWIDTH` | 2 até 10 | Suavidade da curva |
| `NWE_LOOKBACK` | 20 até 100 | Barras de contexto |
| `NWE_MULT_MAE` | 1.0 até 5.0 | Largura das bandas |
| Modo | Trend vs Fader | A favor ou contra tendência |

### Script

```bash
python research/optimize_nwe.py
```

### A Descoberta Crucial: Contra-Tendência Vence

O script testa o NWE em dois modos:

| Modo | Lógica | Resultado |
|------|--------|-----------|
| **Trend** (a favor) | Compra quando NWE sobe, vende quando NWE cai | ❌ Pior que sem filtro |
| **Fader** (contra) | Compra quando NWE cai, vende quando NWE sobe | ✅ Melhor que sem filtro |

**Por que contra-tendência funciona melhor?**

O pair trading é, por definição, uma estratégia de **reversão à média**. Quando o
Z-Score diz "compra" (WIN está barato), e o NWE mostra que WIN está caindo (tendência
de baixa), isso **confirma** que WIN está oversold — exatamente o que queremos.

Se o NWE mostrasse que WIN já está subindo, não faz sentido "comprar" algo que já se
recuperou.

### Resultado Atual (Validado)

| Parâmetro | Valor | Justificativa |
|-----------|-------|---------------|
| `NWE_BANDWIDTH` | 8 | Centro de platô (6-10 todos bons) |
| `NWE_LOOKBACK` | 95 | ~8 horas de contexto |
| `NWE_MULT_MAE` | 3.0 | Bandas largas = menos sinais, mais confiáveis |
| `NWE_BAND_MULT` | 0.10 | Zona de proximidade de 10% |
| Modo | **Fader (contra-tendência)** | Pair trading = reversão à média |

---

## 🎯 ETAPA 5: Otimizar SL/TP/Break-Even (As Regras de Saída)

### O que estamos otimizando

Já sabemos **quando entrar**. Agora precisamos definir **quando sair**:
- Stop Loss: Quanto aceitar perder antes de desistir?
- Take Profit: Quanto lucro capturar?
- Break-Even: Quando proteger o lucro?

### ⚠️ Regra Importantíssima

> Os parâmetros de entrada (Kalman, Z-Score, NWE) estão **TODOS TRAVADOS**.
> A matemática não muda mais. Só estamos ajustando as regras de saída.

### Os parâmetros

| Parâmetro | Range Testado | O que faz |
|-----------|--------------|-----------|
| `SL` | 150 até 600 pts | Perda máxima |
| `TP` | 300 até 1500 pts | Lucro alvo |
| `BE_ACT` | 0 até 500 pts | Quando ativar break-even |
| `BE_LOCK` | 0 até 200 pts | Onde travar o stop |

### Script

```bash
python research/optimize_sltp.py
```

### Conceito-Chave: O Payoff Ratio

> **Payoff** = Ganho Médio ÷ Perda Média

| Payoff | O que significa | Exemplo |
|--------|-----------------|---------|
| 0.5 | Perde o dobro do que ganha | Precisa 67%+ de acerto |
| 1.0 | Ganha e perde igual | Precisa 51%+ de acerto |
| 2.0 | Ganha o dobro | Basta 34%+ de acerto |
| 2.67 | TP=800, SL=300 | Basta 27%+ de acerto ✅ |

No Setup Matador com TP=800 e SL=300:
- **Payoff = 2.67** — mesmo acertando só 30% dos trades, o sistema é lucrativo.
- Win Rate real ≈ **55%** — muito acima do mínimo necessário.

### A Dinâmica SL×TP

```
         SL curto    SL médio    SL longo
        ┌───────────┬───────────┬───────────┐
TP      │ Muitos SL │ Equilí-   │ Poucos SL │
curto   │ Alto giro │ brio      │ Payoff    │
        │ Caro em   │ bom       │ ruim      │
        │ corretagem│           │           │
        ├───────────┼───────────┼───────────┤
TP      │ IDEAL →   │ BOM       │ Payoff    │
médio   │ SL=300    │           │ razoável  │
        │ TP=800 ✅ │           │           │
        ├───────────┼───────────┼───────────┤
TP      │ Raro TP   │ Raro TP   │ Raro TP   │
longo   │ Depende   │ Depende   │ Depende   │
        │ de sorte  │ de sorte  │ de sorte  │
        └───────────┴───────────┴───────────┘
```

### Resultado Atual (Validado)

| Parâmetro | BUY | SELL | Justificativa |
|-----------|-----|------|---------------|
| `SL` | 300 pts | 300 pts | SL curto protege capital |
| `TP` | 800 pts | 800 pts | Payoff 2.67× compensa WR menor |
| `BE_ACT` | 300 pts | 300 pts | Ativa quando lucro = SL |
| `BE_LOCK` | 0 pts | 0 pts | Trava no ponto de entrada |

---

## ✅ ETAPA 6: Validação (Provar que NÃO é Overfitting)

Esta é a etapa **mais importante** e a que mais gente pula.

### 6.1 — Teste dos Modelos Isolados

> **Regra**: O Consenso deve ser **melhor** que cada modelo sozinho. Se não for,
> o segundo modelo está apenas maquiando o primeiro.

```bash
python research/plot_isolated.py
```

O script gera 3 curvas de equity (lucro acumulado):

| Modelo | Trades | Win Rate | Drawdown | PnL |
|--------|--------|----------|----------|-----|
| WDO Isolado | 1.598 | 53.8% | R$ 725 | R$ 6.453 |
| DI Isolado | 532 | 38.0% | R$ 818 | R$ 3.158 |
| **Consenso** | **528** | **58.1%** | **R$ 248** | **R$ 3.053** |

**Interpretação**:
- O Consenso faz **3× menos trades** que o WDO sozinho
- A Win Rate **subiu** de 53.8% para 58.1%
- O Drawdown **caiu 65%** (de R$ 725 para R$ 248)
- Isso prova que o DI está **filtrando os trades ruins** do WDO, não maquiando

### 6.2 — Walk-Forward Analysis (WFA)

> **WFA** = A prova final de que o modelo funciona em dados que ele **nunca viu**.

**Analogia**: É como fazer provas simuladas em lotes:
1. Estuda com as provas de janeiro a dezembro (12 meses)
2. Faz a "prova surpresa" de janeiro a março do ano seguinte (3 meses)
3. Anota a nota
4. Agora estuda com março a fevereiro (próximos 12 meses)
5. Faz a prova de março a junho
6. Repete até acabar os dados

```
┌─────────────────────────────────────────────────────┐
│ Dados:   Jan  Fev  Mar  Abr  Mai  Jun  Jul  Ago... │
│                                                     │
│ Janela 1: [  TREINO 12 meses  ] [TESTE 3m]         │
│ Janela 2:      [  TREINO 12 meses  ] [TESTE 3m]    │
│ Janela 3:           [  TREINO 12 meses  ] [TEST]    │
│                                                     │
│ Métricas OOS = média dos resultados nos [TESTE]     │
└─────────────────────────────────────────────────────┘
```

### Script

```bash
python research/wfa_runner.py
```

### O que olhar no WFA

| Métrica OOS | Bom | Ruim | Significado |
|-------------|-----|------|-------------|
| Acurácia | > 50% | < 48% | Acerta mais que erra |
| Consistency | > 70% janelas | < 50% janelas | Funciona na maioria dos períodos |
| Profit Factor | > 1.0 | < 0.8 | Ganha mais do que perde |

### 6.3 — Checklist de Sanidade

Antes de colocar qualquer otimização em produção, responda:

| # | Pergunta | Resposta Esperada |
|---|----------|-------------------|
| 1 | O resultado está num "platô" ou num "pico isolado"? | Platô ✅ |
| 2 | Faz sentido financeiro? (Payoff > 1.5, WR > 40%) | Sim ✅ |
| 3 | O modelo isolado mais fraco tem WR > 35%? | Sim ✅ |
| 4 | O Consenso reduziu o Drawdown vs Isolado? | Sim ✅ |
| 5 | O WFA tem performance positiva em > 50% das janelas? | Sim ✅ |
| 6 | O número de trades é > 200 (relevância estatística)? | Sim ✅ |

Se qualquer resposta for "Não", **volte à etapa anterior** e ajuste.

---

## 🔄 Fluxo Completo Resumido

```
                    ┌─────────────┐
                    │ BUSCAR DADOS│
                    │  (50k bars) │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  KALMAN Q/R │  ← SL/TP travado em 1000/1000
                    │  + WINDOW   │
                    └──────┬──────┘
                           │ Melhor Q/R/W → TRAVA
                    ┌──────▼──────┐
                    │  Z-SCORES   │  ← Kalman travado
                    │  Entry/Att  │
                    └──────┬──────┘
                           │ Melhor Z → TRAVA
                    ┌──────▼──────┐
                    │  NWE FILTER │  ← Kalman + Z travados
                    │  BW/LB/Mode │
                    └──────┬──────┘
                           │ Melhor NWE → TRAVA
                    ┌──────▼──────┐
                    │   SL / TP   │  ← Tudo travado menos SL/TP/BE
                    │  Break-Even │
                    └──────┬──────┘
                           │ Melhor SL/TP/BE → TRAVA
                    ┌──────▼──────┐
                    │  VALIDAÇÃO  │  ← Isolados + WFA
                    │  Anti-OVF   │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  PRODUÇÃO   │  ← Copiar para config.py
                    └─────────────┘
```

---

## 📂 Scripts Disponíveis (Referência Rápida)

### Etapa 2 — Kalman
| Script | O que faz |
|--------|-----------|
| `optimize_core_models.py` | Grid search Q × R × W |
| `compare_hedge_methods.py` | Compara Kalman vs OLS vs Johansen |

### Etapa 3 — Z-Scores
| Script | O que faz |
|--------|-----------|
| `optimize_phase1_zscores.py` | Grid search Z_WDO × Z_DI × Z_ATT |
| `optimize_zscore_thresholds.py` | Busca fina nos thresholds |
| `optimize_consensus.py` | Otimiza regras de Consenso |

### Etapa 4 — NWE
| Script | O que faz |
|--------|-----------|
| `optimize_nwe.py` | Grid search Bandwidth × Lookback |
| `optimize_nwe_bands.py` | Otimiza MAE Mult + Band Mult |
| `optimize_nwe_grid.py` | Grid completo NWE |

### Etapa 5 — Saídas
| Script | O que faz |
|--------|-----------|
| `optimize_sltp.py` | Grid search SL × TP |
| `optimize_breakeven.py` | Grid search BE_ACT × BE_LOCK |
| `optimize_trade_rules.py` | Combina SL/TP/BE |

### Etapa 6 — Validação
| Script | O que faz |
|--------|-----------|
| `plot_isolated.py` | Curvas isoladas WDO / DI / Consenso |
| `wfa_runner.py` | Walk-Forward Analysis |
| `equity_curve.py` | Curva de equity final |
| `backtest_matador.py` | Backtest multi-cenário |

### Visualização
| Script | O que faz |
|--------|-----------|
| `plot_equity.py` | Gráfico de lucro acumulado |
| `plot_nwe_visual.py` | Visualiza o envelope NWE no preço |
| `plot_grid_results.py` | Heatmaps dos grid searches |
| `plot_portfolio_v4.py` | Portfolio completo (3 estratégias) |

---

## ❓ Perguntas Frequentes

**P: Com que frequência devo re-otimizar?**
R: A cada **3-6 meses**, ou quando o mercado mudar de regime (ex: nova taxa Selic,
crise, mudança de governo). Nunca re-otimize após uma sequência de perdas — isso é
viés emocional.

**P: Posso pular a Etapa 6 (Validação)?**
R: **NÃO.** Pular a validação é o erro mais caro que existe em quant trading.
Sem validação, você está apostando, não operando.

**P: Por que não usamos machine learning (IA) para tudo?**
R: Nós temos modelos ML no `wfa_runner.py` (HMM, LSTM, XGBoost), mas eles funcionam
como **filtros de direção**, não como geradores de sinal. O pair trading estatístico
(Kalman + Z-Score) é matematicamente mais robusto para reversão à média.

**P: Quanto tempo demora uma otimização completa?**
R: Depende do número de combinações e do hardware:
- Etapa 2 (Kalman): ~5-15 minutos
- Etapa 3 (Z-Scores): ~10-30 minutos
- Etapa 4 (NWE): ~15-45 minutos
- Etapa 5 (SL/TP): ~10-20 minutos
- Etapa 6 (WFA): ~30-60 minutos

**P: Os dados do MT5 precisam estar abertos durante a otimização?**
R: Sim. O MetaTrader 5 precisa estar rodando e conectado à corretora para que os
scripts busquem as barras históricas.

---

*Documento gerado em 12/05/2026 — Setup Matador v4*
*Referência: .planning/docs/OPTIMIZATION_PLAYBOOK.md + research/*.py*
