# Roadmap: WIN×WDO Pair Trading & Real-time Flow Dashboard

## Overview

Implementação do indicador sintético de fluxo institucional em tempo real de alta frequência para o WIN, incluindo infraestrutura de cache no backend, computação de pontuação ponderada em três janelas temporais e plotagem de linha dinâmica de 60 minutos no dashboard React.

## Phases

- [ ] **Phase 1: Indicador e Gráfico de Fluxo Sintético** - Implementar cache circular, cálculo do score de fluxo no backend e gráfico dinâmico em tempo real de 5s no frontend.

## Phase Details

### Phase 1: Indicador e Gráfico de Fluxo Sintético
**Goal**: Desenvolver o cálculo do indicador sintético de fluxo no backend Python e a exibição do gráfico de linha única dinâmica no frontend React.
**Depends on**: Nothing
**Requirements**: REQ-002
**Success Criteria**:
  1. O backend em Python coleta e armazena os snapshots de fluxo e cotação de preço do WIN a cada 5 segundos em um cache circular limitado a 720 pontos (60 minutos).
  2. O backend calcula o score sintético de fluxo consolidando janelas de 5s, 15s e 60s e expõe os dados em `GET /api/flow/realtime`.
  3. O dashboard React renderiza o gráfico de linha única abaixo do `FlowDeltaChart` atualizando dinamicamente e com cores correspondentes à pressão do fluxo (verde/vermelho/amarelo).
**Plans**: 1 plan

Plans:
- [ ] 01-01: Implementação da infraestrutura de cache do backend, lógica do score sintético e componente FlowScoreChart no React.

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Indicador e Gráfico de Fluxo Sintético | 0/1 | Not started | - |
