---
title: Design do Indicador Sintético de Fluxo
date: 2026-06-12
context: Socratic exploration for institutional flow chart on dashboard
---

# Design do Indicador Sintético de Fluxo Institucional (WIN)

Detalhamento das decisões de design e arquitetura para a implementação do indicador sintético de fluxo em tempo real de alta frequência.

## 1. Formulação Matemática (Alinhada à Spec)

O indicador consolidado de fluxo será calculado em três janelas temporais ($5\text{s}$, $15\text{s}$ e $60\text{s}$) e unificado na pontuação final:

$$\text{ScoreFinal}_t = 0.50 \cdot \text{Score}_{5\text{s}} + 0.30 \cdot \text{Score}_{15\text{s}} + 0.20 \cdot \text{Score}_{60\text{s}}$$

Para cada janela, usaremos a fórmula MVP:

$$\text{ScoreFluxo}_t = 100 \cdot (0.40 \cdot \text{FLN}_t + 0.30 \cdot \text{PERS}_t + 0.20 \cdot \text{CONC\_DIR}_t + 0.10 \cdot \text{ABS\_DIR}_t)$$

Onde:
* **$\text{FLN}_t$ (Fluxo Normalizado):** $\frac{\text{NetFlow}_t}{\text{VolumeAgressor}_t}$
* **$\text{PERS}_t$ (Persistência):** $\frac{\sum_{i=0}^{N} \text{NetFlow}_{t-i}}{\sum_{i=0}^{N} |\text{NetFlow}_{t-i}|}$ (Janela móvel de $10$ períodos)
* **$\text{CONC\_DIR}_t$ (Concentração Direcionada):** $\text{Concentração}_{\text{Top3}} \cdot \text{Sinal}(\text{FluxoLíquido}_{\text{Top3}})$
* **$\text{ABS\_DIR}_t$ (Absorção Direcional):** Sinal indicando se há grande agressão contra o preço parado.

## 2. Arquitetura de Dados no Backend (Python)

* **Cache em Memória:** O servidor manterá um cache circular na memória (`collections.deque` de tamanho máximo $720$) contendo os snapshots de fluxo capturados a cada 5 segundos.
* **Coletor de Alta Frequência:** Um loop secundário assíncrono capturará o estado atual de `_broker_flow` e da cotação do preço do WIN a cada 5 segundos para calcular os scores de fluxo das três janelas temporais.
* **Endpoint API:** Criação da rota `GET /api/flow/realtime` retornando a lista ordenada dos últimos 720 pontos estruturados para consumo direto do Lightweight Charts no React: `[ { time: timestamp, value: score, color: string }, ... ]`.

## 3. Visualização no Frontend (React)

* **Componente:** `FlowScoreChart.jsx` usando `lightweight-charts` para renderizar uma única linha contínua do score.
* **Regra de Cores Dinâmica:**
  * $\text{Score} \ge +40$: Verde (Compra institucional)
  * $\text{Score} \le -40$: Vermelho (Venda institucional)
  * Outros casos: Amarelo (Fluxo neutro / conflito)
* **Layout:** Inserido na pilha de gráficos do dashboard principal, logo abaixo do `FlowDeltaChart`, com limite visual de 60 minutos no eixo horizontal.
