# Auditoria Completa: Setup Matador × Painel × Histograma

**Criado:** 2026-05-01  
**Área:** dashboard / trade-engine / setup-matador  
**Prioridade:** ALTA  
**Origem:** Sessão de validação V5 — divergências encontradas entre engine, painel e spec

---

## Contexto

Na sessão de 01/05/2026 foram identificadas múltiplas divergências entre:
- O que o **Trade Engine** (`core/trade_engine.py`) executa
- O que o **Histograma** (`SignalHistogram.jsx`) mostra visualmente
- O que o **SETUP_MATADOR.md** documenta como spec

### Correções já aplicadas nesta sessão:
- [x] NWE do frontend corrigido (era non-causal com lookahead → agora causal idêntico ao backend)
- [x] Consensus agora usa z-scores brutos (sem NWE) — espelhando CONS_BASE do trade engine
- [x] Botões "Filtro NWE" e "Filtro Estatístico" removidos (redundantes com 3-band setup)

---

## Itens pendentes para próxima sessão

### 1. Alinhamento eixo X dos 3 gráficos
- [ ] ZScoreChart, SignalHistogram e IndexChart devem ter o eixo X perfeitamente alinhado
- O histograma (Bar chart) ainda está ligeiramente desalinhado horizontalmente dos Line charts
- Investigar se o `syncId` + `scale` do recharts Bar não funciona bem com Line charts
- Possível solução: converter barras para `<Area type="step">` ou aplicar `padding` calculado

### 2. Revisar filtro NWE no histograma (lógica de proximidade)
- [ ] O filtro NWE deveria funcionar assim:
  - **COMPRA**: preço precisa estar PERTO da banda **inferior** do envelope (lower + bandwidth * 0.1)
  - **VENDA**: preço precisa estar PERTO da banda **superior** do envelope (upper - bandwidth * 0.1)
- Atualmente o frontend filtra apenas por direção (isUp/isDown), ignorando a proximidade à banda
- O trade engine (`_eval_wdo_nwe` e `_eval_di_nwe`) TEM a lógica de proximidade (`NWE_BAND_MULT`)
- O frontend NÃO replica essa lógica — apenas zera z-scores baseado na direção
- **Ação:** Portar a lógica completa de proximidade do trade engine para o frontend

### 3. Auditoria Trade Engine ↔ Setup Matador
- [ ] Verificar se os parâmetros do trade engine batem com SETUP_MATADOR.md:
  - Z_ENTRY, Z_ATTENTION, Z_ANOMALY
  - SL/TP/BE valores
  - NWE_BAND_MULT
  - Horários de sessão (ENTRY_START/END, FORCE_CLOSE)
  - RHO_MIN threshold
- [ ] Verificar se os trades injetados (`inject_day_trades.py`) usam parâmetros corretos:
  - `z_in` gravado ERRADO para DI_NWE (grava z_wdo em vez de z_di)
  - `rho_in` recebe z_di em vez de correlação real
  - `TIME_OFFSET = 0` causa z-scores anômalos (-13.07)
  - PnL usa 2 contratos vs 1 no engine atual

### 4. Auditoria Histograma ↔ Trade Engine
- [ ] Confirmar que cada row do histograma espelha exatamente o setup correspondente:
  - **WDO NWE row**: z_wdo + NWE direction + NWE proximity filter
  - **DI NWE row**: z_di + NWE direction + NWE proximity filter  
  - **WDO DI row**: consenso com z_wdo E z_di (sem NWE), thresholds 1.4/1.2
- [ ] Verificar que cores do histograma correspondem aos thresholds corretos

---

## Referências

- `core/trade_engine.py` — Engine com 3 estratégias (CONS_BASE, WDO_NWE, DI_NWE)
- `core/signals.py:calc_nwe_with_bands()` — NWE backend (ground truth)
- `regime-dashboard/src/components/IndexChart.jsx:calcNWE()` — NWE frontend (corrigido)
- `regime-dashboard/src/components/SignalHistogram.jsx` — Histograma 3-band
- `regime-dashboard/src/App.jsx` — mergedSignals (lógica de filtragem NWE)
- `.planning/docs/SETUP_MATADOR.md` — Spec oficial
- `research/inject_day_trades.py` — Script de injeção de trades (com bugs conhecidos)
