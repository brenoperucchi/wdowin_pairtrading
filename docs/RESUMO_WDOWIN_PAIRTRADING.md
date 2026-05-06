# Resumo: WIN×WDO Regime Monitor (Pair Trading)

**Versão do Documento:** 1.0 — Maio 2026  
**Versão do Projeto:** 2.4.0  
**Localização:** `/wdowin_pairtrading/`

---

## O que é

O **WIN×WDO Regime Monitor** é um sistema de **Statistical Arbitrage intraday** que explora a relação de cointegração entre o Mini Índice Bovespa (WIN$N) e o Mini Dólar (WDO$N) na B3.

Ele monitora em tempo real o desvio entre os dois ativos (Z-score), detecta quando o desvio é estatisticamente significativo, e gera sinais de **reversão à média**. A hipótese central: quando WIN e WDO se afastam demais da sua relação histórica, eles tendem a convergir.

**Metáfora:** É um "detector de elástico esticado" — quando o spread entre os dois ativos estica demais (Z-score alto), o sistema aposta na volta ao equilíbrio.

---

## Ativos e Dados

| Ativo | Símbolo | Função |
|-------|---------|--------|
| Mini Índice Bovespa | WIN$N | Perna principal (operada) |
| Mini Dólar | WDO$N | Perna de referência (hedge) |
| Futuro DI (taxa Selic) | DI1$N | Filtro macro adicional |

- **Timeframe:** M5 (5 minutos) — operação intraday
- **Sessão:** 09:00–17:40 (entradas até 15:00, saída forçada às 17:40)
- **Validação:** 2021–2026 (~5 anos, 100k+ barras OOS)

---

## Como Funciona

### A Relação WIN×WDO

WIN e WDO são cointegrados: quando o dólar sobe, o índice cai (correlação ρ ≈ -0.70 a -0.85). O spread entre eles tem um equilíbrio de longo prazo. O sistema compra WIN quando o spread está muito negativo e vende quando está muito positivo.

### Z-Score Dual Route

O sistema usa dois métodos para calcular o Z-score (desvio normalizado do spread):

| Método | Velocidade | Uso |
|--------|-----------|-----|
| **Kalman adaptativo** | Rápido, reage a mudanças | Sinais de compra |
| **OLS rolling** | Conservador, mais estável | Confirmação de vendas |

Essa assimetria é intencional: quedas do WIN são abruptas (usar Kalman) e altas são graduais (usar OLS mais lento).

### Setup Matador v4 — 3 Estratégias Paralelas

O motor de trading gerencia 3 slots independentes simultaneamente:

| Slot | Estratégia | Condição de Entrada |
|------|-----------|---------------------|
| **CONS_BASE** | Consenso WDO+DI | z_WDO e z_DI ambos além do limiar (1.4σ e 1.2σ) |
| **WDO_NWE** | Kalman + Filtro tendência | z_WDO além de 1.4σ E NWE confirma contra-tendência |
| **DI_NWE** | DI Kalman + Filtro tendência | z_DI além de 1.4σ E NWE confirma contra-tendência |

Cada slot tem seu próprio ciclo de entrada/saída e é independente dos outros.

### Gestão de Risco por Trade

| Parâmetro | Valor | Descrição |
|-----------|-------|-----------|
| Stop Loss | 300 pts | Perda máxima por trade |
| Take Profit | 800 pts | Alvo de lucro |
| Break-Even ativa em | +300 pts | Trava zero loss após ganho |
| Break-Even trava em | 0 pts | Posição sai no zero se reverter |
| Force Close | 17:40 | Fecha tudo ao fim da sessão |
| Contratos | 2 WIN | Tamanho fixo |

---

## Indicadores e Filtros

### Saúde da Relação (Regime Health)

Antes de qualquer entrada, o sistema verifica:

| Filtro | Critério de Bloqueio | Propósito |
|--------|---------------------|-----------|
| Correlação ρ | ρ > -0.40 → BLOQUEIA | Detecta quebra da relação |
| Drift do Beta Δβ | Δβ > 25% vs 20d → BLOQUEIA | Detecta instabilidade do hedge ratio |
| Cointegração (EG) | p-value ≥ 0.10 → zero qty | Valida relação estatisticamente |
| Anomalia Z | \|z\| ≥ 4.0 → BLOQUEIA | Evita eventos extremos |

### Filtro de Tendência (NWE)

O **Nadaraya-Watson Envelope (NWE)** é um filtro de suavização não-paramétrico. Evita que o sistema compre WIN em plena queda ou venda em plena alta — opera apenas contra tendências locais, não contra tendências maiores.

### Filtro de Regime (HMM Background)

Thread de fundo classifica o regime do WIN a cada 30 minutos (BULL/BEAR/CHOP). Em regime BULL tendencial, o sistema é mais conservador nas entradas de venda (consenso baseado em backtest).

---

## Arquitetura

```
wdowin_pairtrading/
├── core/
│   ├── config.py          ← Todos os parâmetros centralizados
│   ├── signals.py         ← Z-score, beta OLS, NWE, ρ
│   ├── kalman_filter.py   ← Beta dinâmico adaptativo
│   ├── mt5_client.py      ← Coleta de dados MT5
│   ├── trade_engine.py    ← Setup Matador (3 slots)
│   └── hmm_background.py  ← Regime M30 em background
├── server.py              ← FastAPI (6 endpoints)
├── trades.db              ← SQLite: todas as operações
├── frontend/              ← React + Recharts (dashboard)
│   └── src/components/    ← 7 componentes visuais
├── research/              ← 21 scripts de backtest e otimização
├── tests/                 ← 24 testes unitários
└── docs/                  ← SPEC, ARCHITECTURE, DECISIONS
```

---

## Estado Atual

| Componente | Status |
|-----------|--------|
| Core quantitativo (Kalman, OLS, Johansen, NWE) | ✅ Completo |
| Setup Matador (3 slots, paper trading) | ✅ Completo |
| Dashboard React + Firebase | ✅ Completo |
| Banco de dados (SQLite) | ✅ Completo |
| HMM de regime background (M30) | ✅ Completo |
| Testes unitários (24 testes) | ✅ Completo |
| Backtesting (21 scripts) | ✅ Completo |
| Execução real no MT5 (order_send) | ❌ Não implementado |
| Métricas risk-ajustadas (Sharpe, DD) | ❌ Faltando |
| Simulação de custos (corretagem) | ❌ Faltando |

**Modo atual:** Paper trading — sinais gerados e simulados, nenhuma ordem real enviada ao MT5.

---

## Pontos Fortes para B3

1. **Kalman adaptativo calibrado para WDO/WIN:** 5 anos de dados, Q e R calibrados, validado OOS

2. **Três estratégias em paralelo:** Diversifica fontes de sinal sem aumentar correlação de trades

3. **Assimetria de Z-score (Kalman para compra, OLS para venda):** Reflete comportamento real do mercado brasileiro — quedas abruptas, altas graduais

4. **Filtros multicamada:** ρ + Δβ + Johansen + Anomalia = poucas entradas, mas de alta qualidade

5. **Break-even dinâmico:** Protege lucros sem sacrificar o potencial do trade

6. **NWE causal:** Sem lookahead, funciona em tempo real sem repainting

7. **DI como terceiro vetor:** Usa taxa de juros (DI1$N) como filtro macro — único no mercado B3

8. **Infraestrutura de produção pronta:** Firebase, PM2, SQLite, API REST

---

## Limitações Críticas

| Problema | Impacto |
|----------|---------|
| Paper trading apenas | Não opera dinheiro real ainda |
| Dependência Windows (MT5) | Impossível migrar para Linux sem reengenharia |
| Parâmetros estáticos | Não se adapta a mudanças de volatilidade ao longo das semanas |
| Sem Sharpe/Drawdown na UI | Dificulta avaliação de risco real |
| Sem simulação de custos | PnL simulado inflado vs realidade |
| Sem recuperação de estado | Crash do servidor perde posições em memória |
| Timeframe único (M5) | Não combina com visão de D1 ou H4 |

---

## Dependências Principais

```python
fastapi, uvicorn      # API
numpy, pandas         # Cálculos
statsmodels           # Engle-Granger, Johansen
hmmlearn              # Regime background
MetaTrader5           # Dados e (futuro) ordens
firebase-admin        # Dashboard público
ta                    # Indicadores técnicos
```

---

## Tempo Estimado para Produção Real

**1–2 semanas** para execução real:
1. Implementar `core/mt5_executor.py` com `order_send()`
2. Testar em conta demo por 2–4 semanas
3. Adicionar métricas de risco (Sharpe, DD)
4. Simular custos de corretagem no PnL
