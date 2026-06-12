---
title: Implementação do Indicador e Gráfico em Tempo Real
date: 2026-06-12
priority: high
---

# Checklist de Implementação: Indicador Sintético de Fluxo Institucional

## Backend (Python)
- [ ] Criar cache circular em memória (`collections.deque` com tamanho 720) no `server.py` para armazenar o histórico de posições das corretoras a cada 5 segundos.
- [ ] Implementar thread ou tarefa assíncrona (`asyncio.create_task`) para capturar ticks a cada 5s de `_broker_flow` e cotação de preço do WIN.
- [ ] Desenvolver a lógica matemática do score de fluxo para as janelas de 5s, 15s e 60s, incluindo fluxo líquido normalizado, persistência, concentração do Top 3 e absorção direcional.
- [ ] Unificar as janelas na fórmula combinada: `ScoreFinal = 0.50 * Score_5s + 0.30 * Score_15s + 0.20 * Score_60s`.
- [ ] Criar endpoint `GET /api/flow/realtime` que retorna os dados formatados (timestamp, valor e cor correspondente).
- [ ] Ajustar `server.py` para sincronizar os dados em tempo real no Firebase RTDB se estiver rodando em produção.

## Frontend (React)
- [ ] Criar o componente `FlowScoreChart.jsx` usando a biblioteca `lightweight-charts` configurado com eixo X de 60 minutos.
- [ ] Configurar a linha única do gráfico para mudar de cor dinamicamente com base no valor (Verde, Vermelho, Amarelo).
- [ ] Integrar o polling do `/api/flow/realtime` (ou ler via Firebase onValue em prod) no arquivo `App.jsx`.
- [ ] Adicionar o gráfico `FlowScoreChart` no layout principal abaixo do `FlowDeltaChart` no arquivo `App.jsx`.
- [ ] Testar a sincronização dos eixos temporais (crosshairs e visibilidade horizontal) com os demais gráficos do dashboard.
