---
id: TASK-1.5
title: 'Fase 3b — Frontend: marcadores de trade no ZScoreChart e IndexChart'
status: Done
assignee: []
created_date: '2026-05-06 17:59'
updated_date: '2026-05-06 20:13'
labels:
  - frontend
  - feature
  - ui
milestone: Trades no Dashboard
dependencies:
  - TASK-1.3
references:
  - regime-dashboard/src/components/ZScoreChart.jsx
  - regime-dashboard/src/components/IndexChart.jsx
  - regime-dashboard/src/App.jsx
parent_task_id: TASK-1
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Contexto

Complemento visual do milestone: adicionar marcadores de trade ao `ZScoreChart` (Z-score × tempo) e ao `IndexChart` (preço WIN + bandas NWE). Ambos já usam Recharts com `bar_time` no eixo X.

**Depende de TASK-1.3** (App.jsx passando prop `trades` alinhada).

**Escopo de tooltip nesta task:** Os marcadores do ZScoreChart e IndexChart são **visuais apenas** (sem tooltip hover) — v1. Tooltip rico é exclusivo do SignalHistogram (TASK-1.4). Isso mantém consistência: adicionar tooltip a `ReferenceDot` no Recharts requer abordagem diferente e é custo adicional sem pedido explícito do gestor.

## Paleta de cores
```js
const STRAT_COLORS = {
  CONS_BASE: "#00d4ff",
  WDO_NWE:  "#c8a444",
  DI_NWE:   "#8a6dff",
};
```

## ZScoreChart — marcadores

Aceitar prop `trades = []`. Para cada trade, renderizar dentro do `<ComposedChart>` ou `<LineChart>`:

- **Entrada**: dot preenchido no ponto do Z-score de entrada
```jsx
<ReferenceDot
  key={`z-entry-${t.id}`}
  x={t.bar_time_in}
  y={t.z_in}
  r={5}
  fill={STRAT_COLORS[t.strategy] ?? "#fff"}
  stroke="none"
  label={{ value: t.direction === "BUY" ? "▲" : "▼", position: "top", fontSize: 10 }}
/>
```

- **Saída** (somente CLOSED, `bar_time_out !== null`): dot vazio
```jsx
const zOut = history.find(b => b.bar_time === t.bar_time_out)?.z ?? null;
if (zOut !== null) {
  <ReferenceDot
    key={`z-exit-${t.id}`}
    x={t.bar_time_out}
    y={zOut}
    r={5}
    fill="transparent"
    stroke={STRAT_COLORS[t.strategy] ?? "#fff"}
    strokeWidth={2}
  />
}
```

## IndexChart — marcadores

Aceitar prop `trades = []`. Para cada trade:

- **Entrada**: dot preenchido no preço de entrada
```jsx
<ReferenceDot
  key={`p-entry-${t.id}`}
  x={t.bar_time_in}
  y={t.price_win_in}
  r={5}
  fill={STRAT_COLORS[t.strategy] ?? "#fff"}
  stroke="none"
  label={{ value: t.direction === "BUY" ? "▲" : "▼", position: "top", fontSize: 10 }}
/>
```

- **Saída** (somente CLOSED, `bar_time_out !== null`): dot vazio
```jsx
const priceOut = t.price_win_out
  ?? history.find(b => b.bar_time === t.bar_time_out)?.win_price
  ?? null;
if (priceOut !== null) {
  <ReferenceDot
    key={`p-exit-${t.id}`}
    x={t.bar_time_out}
    y={priceOut}
    r={5}
    fill="transparent"
    stroke={STRAT_COLORS[t.strategy] ?? "#fff"}
    strokeWidth={2}
  />
}
```

## Constraints
- Trade OPEN: entrada visível, saída ausente
- `trades=[]` ou `bar_time_in=null`: nenhum dot renderizado
- Tooltip hover **não** implementado nesta task (v1) — escopo explicitamente restrito
- `npm run lint && npm run build` sem erros
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 ZScoreChart: dot preenchido em (bar_time_in, z_in) para cada entrada
- [ ] #2 ZScoreChart: dot vazio em (bar_time_out, z_da_barra) para cada saída CLOSED
- [ ] #3 IndexChart: dot preenchido em (bar_time_in, price_win_in) para cada entrada
- [ ] #4 IndexChart: dot vazio em (bar_time_out, price_win_out ou win_price_da_barra) para cada saída CLOSED
- [ ] #5 Trade OPEN não exibe dot de saída em nenhum dos gráficos
- [ ] #6 Cor do dot corresponde à estratégia (cyan/gold/purple)
- [ ] #7 trades=[] → ambos os gráficos idênticos ao estado atual
- [ ] #8 npm run lint e npm run build sem erros
- [ ] #9 Marcadores de ZScoreChart e IndexChart são visuais apenas (sem tooltip) — tooltip rico é exclusivo do SignalHistogram em v1
<!-- AC:END -->
