---
id: TASK-1.4
title: 'Fase 3a — Frontend: marcadores de trade no SignalHistogram'
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
  - regime-dashboard/src/components/SignalHistogram.jsx
  - regime-dashboard/src/App.jsx
parent_task_id: TASK-1
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Contexto

Pedido principal do gestor. O `SignalHistogram` mostra barras coloridas por sinal (Z-score) a cada candle M5. Precisamos sobrepor marcadores visuais onde trades reais foram abertos e fechados, permitindo paridade visual com os gráficos gerados pelo backtest.

**Depende de TASK-1.3** (App.jsx passando prop `trades` alinhada).

## Paleta de cores por estratégia
```js
const STRAT_COLORS = {
  CONS_BASE: "#00d4ff",  // cyan
  WDO_NWE:  "#c8a444",  // gold
  DI_NWE:   "#8a6dff",  // purple
};
```

## Abordagem de implementação — `<Customized>` do Recharts

**Usar `<Customized>` do Recharts** (não overlay `div` absoluto) para garantir alinhamento pixel-perfeito com as barras. O `<Customized>` recebe o estado interno do gráfico incluindo `xAxisMap`, `yAxisMap` e `data`, permitindo calcular a posição exata de cada barra.

```jsx
const TradeMarkers = ({ xAxisMap, yAxisMap, data, trades }) => {
  if (!trades?.length || !data?.length) return null;
  const xAxis = Object.values(xAxisMap)[0];
  const yAxis = Object.values(yAxisMap)[0];
  const totalBars = data.length;
  const barWidth = xAxis.width / totalBars;
  const chartBottom = yAxis.y + yAxis.height;

  const elements = [];

  for (const t of trades) {
    if (t.bar_time_in) {
      const idxIn = data.findIndex(b => b.bar_time === t.bar_time_in);
      if (idxIn !== -1) {
        const cx = xAxis.x + (idxIn + 0.5) * barWidth;
        const color = STRAT_COLORS[t.strategy] ?? "#ffffff";
        const symbol = t.direction === "BUY" ? "▲" : "▼";
        elements.push(
          <text key={`entry-${t.id}`} x={cx} y={chartBottom - 4}
            textAnchor="middle" fontSize={10} fill={color}>
            {symbol}
          </text>
        );
      }
    }
    if (t.bar_time_out) {
      const idxOut = data.findIndex(b => b.bar_time === t.bar_time_out);
      if (idxOut !== -1) {
        const cx = xAxis.x + (idxOut + 0.5) * barWidth;
        const color = STRAT_COLORS[t.strategy] ?? "#ffffff";
        elements.push(
          <text key={`exit-${t.id}`} x={cx} y={chartBottom - 14}
            textAnchor="middle" fontSize={10} fill={color}>
            ■
          </text>
        );
      }
    }
  }
  return <>{elements}</>;
};
```

Dentro do `<BarChart>`:
```jsx
<Customized component={<TradeMarkers trades={trades} />} />
```

## Tooltip no hover

Usar estado local `hoveredTrade` + elemento SVG `<title>` ou div absoluto simples para o tooltip:

```jsx
// Alternativa simples: <title> inline no SVG (nativo do browser)
<text ... >
  {symbol}
  <title>{`${t.strategy} | ${t.direction}\nZ: ${t.z_in?.toFixed(2)}\nSaída: ${t.exit_reason ?? "OPEN"}\nPnL: R$ ${t.pnl_brl ?? "-"}`}</title>
</text>
```

## Múltiplos eventos na mesma barra

Se `bar_time_in === bar_time_out` (entrada e saída no mesmo candle) ou múltiplos trades na mesma barra, deslocar verticalmente: entrada em `chartBottom - 4`, saída em `chartBottom - 14`, segunda entrada em `chartBottom - 24`, etc.

## Constraints
- `trades=[]` ou `trades=null` → `TradeMarkers` retorna `null` sem render
- Não quebrar layout existente (nenhum resize do chart)
- npm run lint sem erros
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Marcador ▲ aparece na barra correta para BUY com a cor da estratégia
- [ ] #2 Marcador ▼ aparece na barra correta para SELL com a cor da estratégia
- [ ] #3 Marcador ■ aparece na barra de saída com a cor da estratégia
- [ ] #4 Hover exibe tooltip: estratégia, direção, z_in, exit_reason, pnl_brl
- [ ] #5 Trade OPEN mostra entrada mas nenhuma saída
- [ ] #6 trades=[] → histograma visualmente idêntico ao estado atual
- [ ] #7 Múltiplos marcadores na mesma barra não se sobrepõem completamente
- [ ] #8 npm run lint sem erros em SignalHistogram.jsx
<!-- AC:END -->
