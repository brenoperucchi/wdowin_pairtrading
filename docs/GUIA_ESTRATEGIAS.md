# 📘 Guia Completo das Estratégias — Setup Matador v4

> **Para quem é este guia?** Para qualquer pessoa que vai começar a operar o sistema,
> mesmo sem experiência prévia em trading quantitativo. Explicamos cada parâmetro
> como se você estivesse aprendendo do zero.

---

## 🧭 Visão Geral: O que o Sistema Faz?

O Setup Matador opera **pair trading** (negociação de pares) nos mercados futuros da B3.
A ideia central é simples:

> **Dois ativos que andam juntos se separaram demais. Apostamos que vão voltar a se encontrar.**

Imagine dois cachorros presos pela mesma coleira (a relação estatística entre WIN e WDO).
Quando um puxa muito para um lado, a coleira vai puxar de volta. Nós operamos esse "puxão de volta".

### Os 3 Pares Monitorados

| Par | Ativo A | Ativo B | Relação |
|-----|---------|---------|---------|
| **WDO** | WIN (Mini Índice) | WDO (Mini Dólar) | Inversa — dólar sobe, bolsa cai |
| **DI** | WIN (Mini Índice) | DI1 (Juros Futuros) | Inversa — juros sobem, bolsa cai |
| **Consenso** | Combina os dois pares acima | — | Confirmação cruzada |

### As 3 Estratégias

O sistema roda **3 estratégias independentes** ao mesmo tempo, cada uma com sua posição:

| Estratégia | Código | Descrição Simples |
|------------|--------|-------------------|
| **WDO-NWE** | `WDO_NWE` | Usa o par WIN×WDO + filtro de tendência NWE |
| **DI-NWE** | `DI_NWE` | Usa o par WIN×DI + filtro de tendência NWE |
| **Consenso** | `CONS_BASE` | Só entra quando WDO **e** DI concordam (sem filtro NWE) |

---

## 📐 Conceitos Fundamentais (Leia Primeiro!)

Antes de entender os parâmetros, você precisa conhecer 4 conceitos:

### 1. 📊 Spread (Diferença Relativa)

O **spread** é a diferença entre o preço real do WIN e o preço "previsto" pelo modelo.

```
Spread = Preço_WIN - (Alpha + Beta × Preço_WDO)
```

- **Spread = 0**: Os ativos estão em equilíbrio perfeito.
- **Spread > 0**: WIN está "caro" em relação ao WDO → expectativa de queda do WIN.
- **Spread < 0**: WIN está "barato" em relação ao WDO → expectativa de alta do WIN.

### 2. 📏 Z-Score (Régua de Desvio)

O Z-Score transforma o spread em uma **escala padronizada** para facilitar decisões:

```
Z-Score = (Spread_atual - Média_do_Spread) / Desvio_Padrão_do_Spread
```

**Analogia**: Imagine um termômetro de -4 a +4:
- **0** = Temperatura normal (equilíbrio)
- **±1.2** = Começou a esquentar/esfriar (atenção)
- **±1.4** = Febre / hipotermia (hora de agir!)
- **±4.0** = Emergência médica (NÃO operar — algo anormal aconteceu)

### 3. 📈 Beta (Proporção do Par)

O **Beta** diz "para cada 1 ponto que o WDO mexe, o WIN mexe X pontos".

- Beta = -22.5 significa que se WDO sobe 1 ponto, WIN tende a cair 22.5 pontos.
- O Beta muda ao longo do tempo — por isso usamos o **Filtro de Kalman** para atualizá-lo.

### 4. 🌊 NWE (Envelope de Nadaraya-Watson)

O **NWE** é um "envelope de tendência" que envolve o preço do WIN, criando 3 linhas:
- **Linha Central**: Média suavizada do preço
- **Banda Superior**: Teto — preço raramente passa disso
- **Banda Inferior**: Piso — preço raramente cai abaixo disso

O NWE funciona como um **filtro contra-tendência**: só permite compras quando a tendência é de baixa (perto do piso) e vendas quando a tendência é de alta (perto do teto).

---

## 🔧 ESTRATÉGIA 1: WDO-NWE (WIN×WDO com Filtro NWE)

> **Resumo**: Detecta distorções entre WIN e Dólar (WDO), filtrando sinais falsos com o envelope NWE.

### Parâmetros do Filtro de Kalman (WDO)

| Parâmetro | Valor | O que faz |
|-----------|-------|-----------|
| `WDO_KALMAN_Q` | **0.0001** (1e-4) | Velocidade de adaptação do Beta |
| `WDO_KALMAN_R` | **100** (1e2) | Suavização do spread |
| `WDO_KALMAN_W` | **40** | Janela do Z-Score (barras) |

#### 🔍 `WDO_KALMAN_Q` — Ruído de Transição (Trans Cov)

**O que é**: Controla **o quanto o Beta pode mudar de uma barra para outra**.

**Analogia**: Imagine um leme de navio.
- **Q muito baixo** (ex: 1e-6) = Leme travado → Beta quase não muda, ignora mudanças reais do mercado.
- **Q muito alto** (ex: 1e-1) = Leme solto → Beta muda a cada segundo, fica instável.
- **Q = 1e-4** (nosso valor) = Leme equilibrado → Adapta-se a mudanças reais sem reagir a ruído.

**Na prática**: O WDO usa Q pequeno (1e-4) porque a relação WIN×WDO é **estável** — muda devagar ao longo de semanas/meses.

#### 🔍 `WDO_KALMAN_R` — Ruído de Observação (Obs Cov)

**O que é**: Define a **variância esperada do spread residual** (quanto de "barulho" é normal).

**Analogia**: O nível de ruído de fundo em uma sala.
- **R alto** (100) = Sala barulhenta → O filtro entende que variações grandes no spread são normais, não reage a cada flutuação.
- **R baixo** (1) = Sala silenciosa → Qualquer variação parece significativa.

**Na prática**: R=100 é adequado porque o spread WIN×WDO oscila centenas de pontos normalmente.

#### 🔍 `WDO_KALMAN_W` — Janela do Z-Score

**O que é**: Quantas **barras de 5 minutos** o sistema usa para calcular a média e desvio padrão do Z-Score.

- **W = 40** barras × 5 min = **200 minutos** ≈ 3.3 horas de mercado.

**Analogia**: O tamanho da "memória" do termômetro.
- **W pequeno** (20) = Memória curta → Z-Score reage rápido, mais sinais, mais falsos.
- **W grande** (100) = Memória longa → Z-Score lento, poucos sinais, mais confiáveis.
- **W = 40** = Balanço entre velocidade e confiabilidade.

### Parâmetros NWE (Envelope de Tendência)

| Parâmetro | Valor | O que faz |
|-----------|-------|-----------|
| `NWE_BANDWIDTH` | **8** | Suavidade da curva central |
| `NWE_LOOKBACK` | **95** | Barras para trás que influenciam |
| `NWE_MULT_MAE` | **3.0** | Largura das bandas |
| `NWE_BAND_MULT` | **0.10** | Zona de proximidade (10%) |

#### 🔍 `NWE_BANDWIDTH` — Largura do Kernel

**O que é**: Controla o quão **suave** é a linha central do envelope.

**Analogia**: O zoom de uma câmera focando no preço.
- **Bandwidth baixo** (2) = Zoom muito perto → Linha grudada no preço, segue cada zigue-zague.
- **Bandwidth alto** (20) = Zoom muito longe → Linha tão suave que ignora movimentos importantes.
- **Bandwidth = 8** = Zoom ideal → Captura a tendência sem reagir a ruído.

#### 🔍 `NWE_LOOKBACK` — Janela de Olhar para Trás

**O que é**: Quantas barras passadas o NWE considera para calcular cada ponto da curva.

- **95 barras** × 5 min = **~8 horas** de dados.

**Na prática**: Barras mais recentes têm peso muito maior (decaimento gaussiano), então o NWE dá importância ao passado recente mas ainda "lembra" do contexto de 8 horas.

#### 🔍 `NWE_MULT_MAE` — Multiplicador das Bandas

**O que é**: Define a **largura** das bandas superior e inferior.

```
Banda Superior = NWE_central + (Erro_Médio × 3.0)
Banda Inferior = NWE_central - (Erro_Médio × 3.0)
```

- **Mult = 1.0** = Bandas apertadas → Preço ultrapassa com frequência.
- **Mult = 3.0** (nosso) = Bandas largas → Preço raramente ultrapassa → sinais mais raros mas confiáveis.

#### 🔍 `NWE_BAND_MULT` — Zona de Proximidade

**O que é**: Percentual da largura da banda que define a "zona de entrada permitida".

- **0.10 = 10%** da largura da banda.

**Como funciona na prática**:
1. O sistema calcula a distância entre banda superior e inferior (ex: 500 pontos).
2. A zona de proximidade = 500 × 0.10 = **50 pontos** de cada banda.
3. **Para COMPRAR**: O preço precisa estar a **no máximo 50 pontos** acima da banda inferior.
4. **Para VENDER**: O preço precisa estar a **no máximo 50 pontos** abaixo da banda superior.

### Lógica de Entrada (WDO-NWE)

Para a estratégia WDO-NWE gerar um sinal de **COMPRA**, TODAS as condições devem ser verdadeiras:

```
✅ Z-Score WDO ≤ -1.4          (WIN está "barato" vs WDO)
✅ NWE está BEARISH (caindo)    (tendência de queda confirma)
✅ Preço perto da banda inferior (dentro da zona de 10%)
✅ Não é anomalia (|Z| < 4.0)
✅ Dentro do horário (09:00-15:00)
✅ Beta estável
```

Para **VENDA**, é o espelho:
```
✅ Z-Score WDO ≥ +1.4
✅ NWE está BULLISH (subindo)
✅ Preço perto da banda superior
```

---

## 🔧 ESTRATÉGIA 2: DI-NWE (WIN×DI com Filtro NWE)

> **Resumo**: Detecta distorções entre WIN e Juros Futuros (DI), com o mesmo filtro NWE.

### Parâmetros do Filtro de Kalman (DI)

| Parâmetro | Valor | Comparação com WDO | Por quê |
|-----------|-------|---------------------|---------|
| `DI_KALMAN_Q` | **0.001** (1e-3) | 10× mais rápido | Relação WIN×DI muda mais rápido |
| `DI_KALMAN_R` | **10** (1e1) | 10× menos suave | DI tem menor amplitude |
| `DI_KALMAN_W` | **60** | 50% mais lento | Precisa de mais dados para estabilizar |
| `DI_BETA_INITIAL` | **-10000** | Escala diferente | WIN~135k vs DI~13.5 |

#### 🔍 Por que os valores são diferentes do WDO?

A relação WIN×DI é **mais instável** que WIN×WDO:
- O DI (taxa de juros) reage fortemente a decisões do Copom, dados de inflação, etc.
- A escala é absurda: WIN ≈ 135.000 pontos vs DI ≈ 13.5 pontos.
- Beta ≈ -10.000 (cada 1 ponto do DI = ~10.000 pontos no WIN).

Por isso:
- **Q mais alto** (1e-3): O Beta precisa se adaptar mais rápido às mudanças.
- **R mais baixo** (10): O spread tem menor amplitude, então menos "ruído" é tolerado.
- **W mais alto** (60): Usa 5 horas de dados para calcular o Z-Score, dando mais estabilidade.

### Parâmetros de Entrada (DI)

| Parâmetro | Valor | Descrição |
|-----------|-------|-----------|
| `DI_Z_ENTRY` | **1.4** | Threshold de entrada (igual ao WDO) |
| `DI_Z_ANOMALY` | **4.0** | Threshold de anomalia |
| `DI_Z_ATTENTION` | **1.2** | Zona de atenção no dashboard |
| `DI_BARS` | **250** | Barras enviadas ao dashboard |

### Lógica de Entrada (DI-NWE)

Idêntica à WDO-NWE, mas usando o Z-Score do par WIN×DI:

```
✅ Z-Score DI ≤ -1.4            (WIN barato vs Juros)
✅ NWE BEARISH + preço perto da banda inferior
✅ Sem anomalia, dentro do horário, Beta estável
```

### Filtro NWE (Compartilhado)

As estratégias WDO-NWE e DI-NWE usam **o mesmo envelope NWE** calculado sobre o preço do WIN. Os parâmetros NWE são idênticos para ambas.

---

## 🔧 ESTRATÉGIA 3: CONSENSO (WDO + DI sem NWE)

> **Resumo**: Só entra quando **ambos os pares concordam na direção**. Não usa filtro NWE.

### Por que existe o Consenso?

O Consenso é a estratégia mais **conservadora**:
- Quando WIN×WDO diz "COMPRA" **E** WIN×DI também diz "COMPRA", a probabilidade de acerto é maior.
- O preço é: menos sinais, mas com maior taxa de acerto.

### Lógica de Entrada (Consenso)

O Consenso usa um sistema de **confirmação cruzada flexível**:

#### Para COMPRA:
```
Condição A: Z_WDO ≤ -1.4 (entry)  E  Z_DI ≤ -1.2 (atenção)
        OU
Condição B: Z_WDO ≤ -1.2 (atenção) E  Z_DI ≤ -1.4 (entry)
```

#### Para VENDA:
```
Condição A: Z_WDO ≥ +1.4 (entry)  E  Z_DI ≥ +1.2 (atenção)
        OU
Condição B: Z_WDO ≥ +1.2 (atenção) E  Z_DI ≥ +1.4 (entry)
```

**Traduzindo**: Um dos Z-Scores precisa estar no nível de ENTRADA (±1.4) e o outro pelo menos no nível de ATENÇÃO (±1.2). Não é necessário que ambos atinjam ±1.4.

### Diferença Crucial: Sem Filtro NWE

O Consenso **não** aplica o filtro NWE. A justificativa é que a confirmação cruzada entre dois pares independentes já é um filtro forte por si só.

---

## 🛡️ Parâmetros de Gestão de Risco (Todas as Estratégias)

Após entrar em uma operação, o sistema gerencia a posição com estes parâmetros:

### Stop Loss e Take Profit

| Parâmetro | BUY | SELL | O que faz |
|-----------|-----|------|-----------|
| `SL` (Stop Loss) | **300 pts** | **300 pts** | Perda máxima permitida |
| `TP` (Take Profit) | **800 pts** | **800 pts** | Lucro alvo |

**Em reais** (2 contratos WIN, R$0.20/pt):
- Stop Loss: 300 × 2 × R$0.20 = **R$ 120**
- Take Profit: 800 × 2 × R$0.20 = **R$ 320**

### Break-Even (Proteção de Lucro)

| Parâmetro | BUY | SELL | O que faz |
|-----------|-----|------|-----------|
| `BE_ACT` (Ativação) | **300 pts** | **300 pts** | Quando ativar o break-even |
| `BE_LOCK` (Travamento) | **0 pts** | **0 pts** | Nível onde o stop fica |

**Como funciona**:
1. Você entra comprando WIN a 135.000.
2. WIN sobe para 135.300 (+300 pts) → Break-even **ativa**.
3. A partir de agora, se WIN voltar para 135.000 (0 pts de lucro), o sistema fecha a posição.
4. Resultado: Você não perde dinheiro — sai no zero a zero.

### Sizing (Tamanho da Posição)

| Parâmetro | Valor | O que faz |
|-----------|-------|-----------|
| `WIN_CONTRACTS` | **2** | Quantidade de mini-contratos |
| `WIN_PV` | **R$ 0.20** | Valor por ponto por contrato |

### Horários de Operação

| Parâmetro | Valor | Descrição |
|-----------|-------|-----------|
| `ENTRY_START` | **09:00** | Início da janela de entrada |
| `ENTRY_END` | **15:00** | Fim da janela de entrada |
| `FORCE_CLOSE` | **17:40** | Fechamento forçado de tudo |

**Regras de horário**:
- **09:00 - 15:00**: Pode abrir novas posições.
- **15:01 - 17:39**: Não abre novas, mas gerencia as abertas (SL/TP/BE).
- **17:40**: Fecha tudo automaticamente (day trade — nunca dorme posicionado).

---

## 🔍 Indicadores de Saúde do Regime

O sistema monitora continuamente se a relação estatística entre os pares está saudável:

### Correlação (ρ - Rho)

| Nível | ρ valor | Semáforo | Ação |
|-------|---------|----------|------|
| FORTE | ≤ -0.70 | 🟢 | Operar normalmente |
| ATENÇÃO | -0.70 a -0.55 | 🟡 | Reduzir tamanho |
| FRACA | -0.55 a -0.40 | 🟠 | Não abrir novas |
| QUEBRADA | > -0.40 | 🔴 | Parar completamente |

**O que é**: ρ mede o quão "juntos" WIN e WDO andam. Valor -0.70 significa forte correlação inversa (um sobe, outro desce).

### Estabilidade do Beta

| Nível | Variação | Semáforo | Ação |
|-------|----------|----------|------|
| ESTÁVEL | < 5% | 🟢 | Operar normalmente |
| DERIVANDO | 5-15% | 🟡 | Reduzir tamanho |
| INSTÁVEL | 15-25% | 🟠 | Suspender entradas |
| BREAKDOWN | > 25% | 🔴 | Não operar |

**O que é**: Se o Beta mudou muito comparado à média de 20 dias, a relação pode estar quebrando.

### Teste de Cointegração (Engle-Granger)

| P-valor | Interpretação | Efeito no Sistema |
|---------|---------------|-------------------|
| < 0.05 | Cointegração forte | Sizing normal |
| 0.05 - 0.10 | Cointegração fraca | Sizing pela metade |
| > 0.10 | Sem cointegração | Não operar |

---

## 🚦 Entradas Só no Fechamento da Barra

> **Regra Fundamental**: Novas entradas são avaliadas **apenas quando uma barra M5 fecha**.
> Saídas (SL/TP/BE) são verificadas **a cada 2.5 segundos**.

Isso garante paridade com o backtest — evita que o sistema reaja a "wicks" (sombras) intra-barra.

---

## 📝 Resumo Rápido — Tabela de Todos os Parâmetros

### Kalman Filter

| Parâmetro | WDO | DI | Função |
|-----------|-----|-----|--------|
| Q (trans_cov) | 1e-4 | 1e-3 | Velocidade de adaptação |
| R (obs_cov) | 1e2 | 1e1 | Tolerância ao ruído |
| W (z-window) | 40 | 60 | Memória do Z-Score |
| Beta inicial | -22.5 | -10000 | Ponto de partida |

### NWE (só WDO-NWE e DI-NWE)

| Parâmetro | Valor | Função |
|-----------|-------|--------|
| Bandwidth | 8 | Suavidade da curva |
| Lookback | 95 | Barras de contexto |
| MAE Mult | 3.0 | Largura das bandas |
| Band Mult | 0.10 | Zona de proximidade |

### Entrada e Saída

| Parâmetro | Valor | Função |
|-----------|-------|--------|
| Z Entry | ±1.4 | Threshold de entrada |
| Z Attention | ±1.2 | Zona de atenção |
| Z Anomaly | ±4.0 | Bloqueio de emergência |
| Stop Loss | 300 pts | Perda máxima |
| Take Profit | 800 pts | Lucro alvo |
| BE Ativação | 300 pts | Protege o lucro |
| BE Lock | 0 pts | Nível de proteção |
| Contratos | 2 WIN | Tamanho da posição |
| Horário | 09:00-15:00 | Janela de entradas |

---

## ❓ Perguntas Frequentes

**P: Posso operar as 3 estratégias ao mesmo tempo?**
R: Sim! Cada uma gerencia sua posição independentemente. Você pode ter 3 trades abertos simultaneamente.

**P: Qual estratégia é mais segura?**
R: O **Consenso** é a mais conservadora (menos sinais, maior taxa de acerto). As estratégias NWE são mais ativas.

**P: O que acontece se a internet cair?**
R: As posições ficam abertas. No retorno, o sistema retoma o gerenciamento. O FORCE_CLOSE às 17:40 garante que nenhuma posição dorme aberta.

**P: Preciso fazer algo manualmente?**
R: Não. O sistema é signal-only com paper trading. Você observa os sinais no dashboard e pode decidir se segue ou não.

---

*Documento gerado em 12/05/2026 — Setup Matador v4*
*Fonte: config.py, trade_engine.py, signals.py, kalman_filter.py*
