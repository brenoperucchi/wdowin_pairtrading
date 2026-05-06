---
id: TASK-1.3
title: 'Fase 2 — Frontend: state todayTrades + helper de alinhamento M5 em App.jsx'
status: Done
assignee: []
created_date: '2026-05-06 17:59'
updated_date: '2026-05-06 20:13'
labels:
  - frontend
  - feature
milestone: Trades no Dashboard
dependencies:
  - TASK-1.2
references:
  - regime-dashboard/src/App.jsx
  - regime-dashboard/src/components/SignalHistogram.jsx
  - regime-dashboard/src/components/ZScoreChart.jsx
  - regime-dashboard/src/components/IndexChart.jsx
parent_task_id: TASK-1
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Contexto

O backend retorna `trades_today` no `/api/v2/regime` (implementado em TASK-1.2). O `App.jsx` precisa: capturar e armazenar esse array em state, alinhar cada trade ao candle M5 mais próximo no array `paddedSignals` (via `bar_time`), e passar os trades alinhados como prop para os 3 componentes de gráfico.

**Depende de TASK-1.2** (backend com trades_today implementado).

## Mudanças em App.jsx

### 1. Novo state
```js
const [todayTrades, setTodayTrades] = useState([]);
```

### 2. Captura no polling REST e no listener Firebase
```js
setTodayTrades(data.trades_today ?? []);
```

### 3. Helper de alinhamento (função pura)
Criar em `src/utils/tradeAlignment.js` ou no topo do App.jsx:

```js
export function alignTradesToBars(trades, history) {
  if (!trades?.length || !history?.length) return [];
  const barTimes = history.map(b => b.bar_time);
  const toMin = (s) => { const [h, m] = s.split(":").map(Number); return h * 60 + m; };

  const findBar = (timeStr) => {
    if (!timeStr) return null;
    const tMin = toMin(timeStr);
    let best = null;  // null se nenhuma barra <= timeStr
    for (const bt of barTimes) {
      if (toMin(bt) <= tMin) best = bt;
      else break;
    }
    return best;  // null evita marcador falso no início do gráfico
  };

  return trades.map(t => ({
    ...t,
    bar_time_in: findBar(t.time_in),
    bar_time_out: t.time_out ? findBar(t.time_out) : null,
  }));
}
```

**IMPORTANTE:** `best` inicia como `null` (não `barTimes[0]`). Se o trade for anterior ao primeiro candle disponível, `bar_time_in` será `null` e nenhum marcador falso será exibido.

### 4. useMemo para trades alinhados
```js
const alignedTrades = useMemo(
  () => alignTradesToBars(todayTrades, paddedSignals),
  [todayTrades, paddedSignals]
);
```

**Usar `paddedSignals` como fonte de alinhamento** — é o mesmo array usado pelos 3 gráficos.

### 5. Passar prop para os gráficos
**ATENÇÃO — manter os props existentes, apenas adicionar `trades`:**

```jsx
<ZScoreChart
    history={paddedSignals}          {/* já existente — NÃO ALTERAR */}
    sigColor={...}
    currentZ={...}
    useV2={true}
    hideXAxis={true}
    trades={alignedTrades}           {/* NOVO */}
/>
<SignalHistogram
    data={paddedSignals}             {/* já existente — NÃO ALTERAR */}
    trades={alignedTrades}           {/* NOVO */}
/>
<IndexChart
    history={paddedSignals}          {/* já existente — NÃO ALTERAR */}
    trades={alignedTrades}           {/* NOVO */}
/>
```

Modo histórico (`isViewingHistory`): passar `trades={[]}`.

## Notas
- Os 3 componentes receberão a prop `trades` mas TASK-1.4 e TASK-1.5 é que implementarão a renderização. Nesta task, apenas aceitar a prop sem warning (default `trades = []` na assinatura do componente).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 state todayTrades inicializa como []
- [ ] #2 todayTrades é preenchido tanto no polling REST quanto no listener Firebase
- [ ] #3 alignTradesToBars retorna [] quando trades ou history são vazios/null
- [ ] #4 Cada trade alinhado tem bar_time_in (HH:MM) correspondente à barra M5 correta (anterior mais próxima)
- [ ] #5 Trade com time_out tem bar_time_out; trade OPEN tem bar_time_out null
- [ ] #6 SignalHistogram, ZScoreChart e IndexChart recebem prop trades sem warnings React
- [ ] #7 Em modo histórico, prop trades é []
- [ ] #8 npm run lint sem erros em App.jsx
- [ ] #9 alignTradesToBars retorna bar_time_in null quando trade é anterior ao primeiro candle disponível (sem marcador falso)
<!-- AC:END -->
