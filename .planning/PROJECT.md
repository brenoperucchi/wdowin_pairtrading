# WIN×WDO Pair Trading & Real-time Flow Dashboard

## What This Is

Um painel analítico de arbitragem estatística (pair trading) de B3 (WIN e WDO) com precificação de Kalman Filter, bandas NWE, rastreamento de corretoras e indicador sintético de fluxo institucional em tempo real de alta frequência.

## Core Value

Fornecer sinais de arbitragem estatística e análise de fluxo institucional (WIN) rápidos, precisivos e visualmente claros para orientar decisões operacionais.

## Requirements

### Validated

- ✓ **REQ-001: Player Price Influence (Directional Efficiency)** — Cálculo e exibição da eficiência direcional histórica acumulada por corretora.
- ✓ **Cálculo de Spread e Z-score (WDO/WIN/DI)** — Precificação matemática dinâmica usando Filtro de Kalman e OLS.
- ✓ **Filtro Nadaraya-Watson Envelope (NWE)** — Canal envelope adaptativo dinâmico como filtro de tendência de preço.
- ✓ **Integração de Níveis GEX** — Importação e visualização dos níveis diários de GEX (Walls) obtidos do Firebase RTDB.

### Active

- [ ] **REQ-002: Indicador Sintético de Fluxo Institucional em Tempo Real (WIN)** — Computação de score unificado (-100 a +100) com janelas rápidas (5s, 15s, 60s) e exibição em gráfico de linha única dinâmica de 60 minutos.

### Out of Scope

- **Coleta de fluxo para WDO** — Limitado a WIN para manter o MVP focado e rápido.
- **Gráfico de múltiplas linhas de score** — Exibição simplificada de linha única para facilitar leitura rápida.

## Context

- **Ambiente Técnico:** Python (FastAPI/MT5) no backend e React (Vite/Lightweight Charts) no frontend.
- **Ponte de Dados:** Ponte RTD/CSV (`profit_rtd_bridge.py` e `profit_csv_bridge.py`) enviando dados do Profit para o backend FastAPI.
- **Base de Dados:** `trades.db` contendo histórico de operações e barras fechadas com dados de fluxo salvos.

## Constraints

- **Tempo Real**: Atualizações a cada 5 segundos no backend, com polling de alta frequência no frontend.
- **Janela Móvel**: O gráfico deve exibir estritamente os últimos 60 minutos de dados (720 pontos em 5s).
- **Sem OOM**: Evitar acúmulo infinito de dados na memória do frontend e backend.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Processamento no Backend | Cálculos matemáticos de janelas móveis são mais robustos e eficientes se processados em Python. | — Pending |
| Resolução de 5s no Gráfico | Oferece a granularidade ideal recomendada pela especificação para leitura ágil sem sobrecarga. | — Pending |

---
*Last updated: 2026-06-12 after Socratic exploration of Institutional Flow Indicator*
