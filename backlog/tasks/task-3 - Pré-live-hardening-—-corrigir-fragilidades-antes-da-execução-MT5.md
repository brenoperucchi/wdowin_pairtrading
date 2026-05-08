---
id: TASK-3
title: Pré-live hardening — corrigir fragilidades antes da execução MT5
status: To Do
assignee: []
created_date: '2026-05-07 00:42'
updated_date: '2026-05-07 21:23'
labels:
  - backend
  - frontend
  - risk
  - backtest
  - hardening
  - pre-live
milestone: m-1
dependencies: []
references:
  - core/trade_engine.py
  - server.py
  - core/config.py
  - core/signals.py
  - core/mt5_client.py
  - regime-dashboard/src/App.jsx
  - regime-dashboard/src/components
  - tests/
  - requirements.txt
  - regime-dashboard/package.json
  - backlog/tasks/task-2 - Execução-live-no-MT5-XP-DEMO-—-versão-robusta.md
  - research/backtest.py
  - research/backtest_pa.py
  - research/optimize_wdo.py
  - research/optimize_wdo_sltp.py
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Contexto

Antes de avançar para a TASK-2 (`Execução live no MT5`), precisamos endurecer o sistema atual. A revisão arquitetural identificou fragilidades que podem distorcer sinal, histórico, risco ou operação caso o sistema seja levado para live.

Hoje o projeto funciona como monitor/paper-trader com dashboard, mas ainda há desalinhamentos entre backtest e produção, gates estatísticos parcialmente informativos, persistência histórica incompleta e débitos de validação. Esta task deve resolver esses pontos ou deixar decisões explicitamente documentadas antes de qualquer `mt5.order_send`.

## Problemas Encontrados

1. `/api/regime` V1 chama `TradeEngine.evaluate(z_buy=..., z_sell=...)`, mas a assinatura atual é `z_wdo`/`z_di`; endpoint está quebrado ou obsoleto.
2. `bar_history` é lida/escrita em `server.py`, mas não há migration/tabela criada de forma confiável.
3. Produção e research/backtests usam parâmetros divergentes (`Z_ENTRY`, TP/SL, horários, filtros), reduzindo paridade entre setup validado e setup vivo.
4. Johansen/Engle-Granger/HMM aparecem no sistema, mas nem todos participam do bloqueio de entrada; falta um `risk_gate` centralizado com motivos explícitos.
5. O sistema se apresenta como pair/stat arb, mas o motor atual opera apenas WIN; WDO/DI são fontes de sinal. Precisamos decidir/documentar se é setup direcional de WIN com filtros ou se haverá hedge real no futuro.
6. `requirements.txt` não inclui dependências usadas em runtime/teste (`firebase-admin`, `pytest`), o que quebra validação em ambiente novo.
7. `npm run lint` geral falha por débitos existentes no frontend.
8. Fallback simulado do dashboard pode mascarar falha operacional se não estiver visualmente inequívoco.
9. Antes de live, faltam critérios de risco operacional: limite diário, max trades/dia, cooldown após loss, bloqueio por desconexão/rollover, e estado claro de mercado.

## Escopo

- Corrigir ou descontinuar explicitamente `/api/regime` V1.
- Criar migration idempotente para `bar_history` e teste mínimo de persistência/carregamento.
- Centralizar um `risk_gate` que gere `{ allowed, reasons, checks }` e seja usado pelo `TradeEngine` ou antes dele.
- Definir e documentar o conceito operacional atual: `WIN directional signal` vs `pair trading hedgeado`.
- Criar perfil único/versionado de parâmetros de produção e exigir que backtest de validação use esse perfil.
- Atualizar requirements e comandos de teste para ambiente limpo.
- Reduzir/zerar falhas de lint relevantes antes da TASK-2.
- Melhorar distinção visual/estado entre dashboard live, fallback simulado, erro Firebase e histórico.
- Documentar pendências que ficarem fora do escopo com justificativa.

## Fora de Escopo

- Implementar `mt5.order_send`.
- Reconciliação de tickets MT5.
- Execução em conta real.
- Refatoração completa do dashboard ou dos scripts de research.

## Review Externo

Antes de mover para Done, pedir um review do Claude focado em:
- se os riscos pré-live foram realmente mitigados;
- se a TASK-2 pode começar sem carregar débitos críticos;
- se a lógica de negócio está descrita de forma honesta: direcional WIN vs stat arb hedgeado.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 `/api/regime` V1 está corrigido, removido ou documentado como obsoleto sem risco de uso acidental; README/CLAUDE/endpoints refletem a decisão.
- [x] #2 `bar_history` possui migration/tabela criada de forma idempotente e há teste ou script de verificação que cobre salvar/carregar barras.
- [x] #3 Função `risk_gate(...)` extraída para módulo dedicado (`core/risk_gate.py` ou similar) retorna `{allowed: bool, reasons: list[str], checks: dict}` e é consumida por `TradeEngine.evaluate()` substituindo o atual `safe_to_trade`/`beta_safe`; o cálculo em `server.py:608` é removido ou redirecionado para essa função (sem duplicação de lógica).
- [x] #4 Política explicita para Johansen e HMM (atualmente apenas informativos no fluxo de entrada): documentada em CLAUDE.md/README como bloqueia / reduz sizing / informa apenas. Cada decisão de WAIT no `risk_gate` registra o `reasons[]` em log estruturado para rastreabilidade.
- [x] #5 Produção e backtest usam um perfil único/versionado de parâmetros, ou há manifesto comparando exatamente os parâmetros vivos vs parâmetros do backtest.
- [x] #6 Conceito operacional está explicitado: sistema atual opera apenas WIN com filtros WDO/DI, ou plano de hedge real está documentado como futuro.
- [x] #7 `requirements.txt` inclui dependências necessárias para runtime e teste (`firebase-admin`, `pytest`, demais imports detectados); `python -m pytest tests/ -q` é executável em ambiente preparado.
- [x] #8 `npm run lint` não possui falhas críticas relacionadas ao escopo pré-live, ou as remanescentes estão listadas com justificativa e follow-up.
- [x] #9 `npm run build` passa.
- [x] #10 Dashboard diferencia claramente estado live, fallback simulado, Firebase indisponível, API offline e modo histórico. — JÁ CUMPRIDO em `regime-dashboard/src/App.jsx:618-630, 636-639, 667-676` (badges Topbar MT5 LIVE/SIMULADO/HISTÓRICO + banner de erro específico + footer DADOS REAIS/SIMULADOS); marcar como done sem trabalho adicional.
- [x] #11 Constantes de risco operacional adicionadas a `core/config.py` com valores default conservadores e implementadas como checks no `risk_gate`: `MAX_TRADES_PER_DAY` (sugestão default 4), `DAILY_LOSS_LIMIT_BRL` (default a calibrar a partir de histórico de `pnl_brl`), `LOSS_COOLDOWN_MIN` (sugestão default 30), `BLOCK_ON_MT5_DISCONNECT` (default True). Política de rollover de símbolos contínuos (WIN/WDO/DI mensal) documentada como processo manual em runbook.
- [ ] #12 Review do Claude anexado nas notas da task antes de mover para Done, com eventuais comentários resolvidos ou convertidos em follow-ups.
- [x] #13 Nomenclatura DOL/WDO documentada em `research/README.md` (ou doc equivalente): no escopo atual deste codebase, DOL ≡ WDO ≡ Mini Dólar (`SYMBOL_B='WDO$N'`), sem contrato cheio implementado; remover ambiguidade antes de investigar P&L.
- [x] #14 Escopo de cada script de research reconciliado com o motor de produção: `research/optimize_wdo.py`, `research/optimize_wdo_sltp.py`, `research/backtest.py`, `research/backtest_pa.py` são (a) reescritos para operar a perna WIN com filtros WDO/DI (paridade com `_eval_consensus`/`_eval_wdo_nwe`/`_eval_di_nwe` do trade_engine) ou (b) marcados em header como 'research exploratório, não validação de produção'. Não fazer fix sem antes decidir o que cada script deve testar.
- [x] #15 Script(s) marcado(s) como validação de produção incluem: slippage WIN (5 pts/lado, conservador), custos B3 estimados (emolumentos + corretagem por contrato — confirmar com XP), descarte de trades que cruzam rollover de WDO/DI/WIN.
- [ ] #16 P&L do backtest validado nos últimos 30 dias úteis é comparado com soma de `pnl_brl` em `matador_ops` no mesmo período (paper trading). Erro relativo < 10% = paridade aceita; ≥ 10% = bug investigado e resolvido em um dos lados antes de Done.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-05-07: Gestor reportou que o backtest Python em operação DOL não está funcionando bem. Isso fica explicitamente dentro da TASK-3, pois afeta validade de backtest, paridade setup/backtest/dashboard e decisão conceitual entre operar apenas WIN direcional versus operar perna DOL/WDO como hedge. Pontos iniciais a revisar: scripts research/backtest.py, research/backtest_pa.py, research/optimize_wdo.py e research/optimize_wdo_sltp.py; confirmar se "DOL" significa contrato cheio DOL ou mini dólar WDO usado no config atual (SYMBOL_B=WDO$N).

2026-05-07 (review Claude): Análise dos 9 problemas + AC #13 contra código real. **7 confirmados** (#1, #2, #3, #6, #7, #9 e parcial #4). **#4 parcial**: `safe_to_trade` em server.py:608 já centraliza 5 gates (pvalue, rho, beta_delta, beta_unstable, sessão); falta extrair em módulo + decidir Johansen/HMM (hoje informativos, nunca consultados em evaluate()). **#5 confirmado direcional puro**: trade_engine abre só qty_win=2, sem hedge — trabalho é doc, não código. **#10 (AC) já cumprido**: App.jsx:618-630, 636-639, 667-676 já têm badges Topbar (MT5 LIVE/SIMULADO/HISTÓRICO) + banner de erro específico + footer DADOS REAIS/SIMULADOS — marcar como done sem trabalho. **#13 (AC) DOL/WDO**: 'DOL' só aparece na própria task; nenhum script Python usa DOL$N — é apelido coloquial para WDO. Causa-raiz do 'backtest não funciona': **incoerência de escopo**. `optimize_wdo*.py` operam só WDO; `backtest*.py` operam 4 legs especulativos; produção opera só WIN. Backtest não é validação do motor. ACs #3, #4, #11 e #13 refinados com escopo afiado para evitar fechamento cosmético. Plano completo da review em /home/brenoperucchi/.claude/plans/stateful-toasting-pony.md.

2026-05-07 (slice 6c): scripts/reconcile_paper_vs_backtest.py implementa AC #16. Quatro estados: BLOCKED (0 paper trades — exit 0), MISSING_BACKTEST (sidecar JSON ausente — exit 2), PASS (|err| <10% — exit 0), FAIL (≥10% — exit 1). research/run_matador_v5_johansen.py agora emite portfolio_v5_summary.json após cada run com pnl_brl_gross+pnl_brl_net por leg/portfólio (matador_ops grava gross; backtest grava net; reconcile compara ambos lados em paralelo). Convenção de saída unificada: backtest realiza pts_favor real do bar (igual core/trade_engine.py:352), não TP/-SL/0 hardcoded — fix do medium #2 do codex round-9. AC #15 marcado done (slippage 5pts/lado + B3 R$1/contrato/RT + rollover discard via 5σ heuristic). **AC #16 fica BLOCKED até paper history acumular**: matador_ops tem 0 closed trades em 2026-05-07; reconcile reporta BLOCKED com exit 0 e a metodologia está em docs/PARAM_PROFILE.md §4. Re-rodar o script após algumas semanas de uptime do paper engine. Slice 6c desbloqueia slice 7 (lint frontend AC #8) e slice 8 (review final AC #12).

2026-05-07 (slice 6c-fix, codex round-10): quatro findings.

**HIGH — window mismatch**: sidecar era agregado de ~1.2 anos (BARS=35000) vs paper de 30 dias — PASS/FAIL falso. Fix: research/run_matador_v5_johansen.py agora emite `daily[]` por leg/portfólio com {date, trades, pnl_brl_net, pnl_brl_gross}. scripts/reconcile_paper_vs_backtest.py filtra ambos os lados pelo mesmo business-day cutoff via `aggregate_backtest_window()`. Adicionado novo estado WINDOW_NOT_COVERED (exit 4) quando sidecar.last_bar_date < cutoff.

**MEDIUM — calendar vs business days**: --days 30 era timedelta(days=30) (~21 pregões). Fix: helper `business_days_ago(today, n)` skipa Mon-Fri only (B3 holidays NÃO excluídos por ora; ambos lados vêem o mesmo gap, viés cancela). Help text muda "calendar days" → "BUSINESS days". --today flag adicionado para reconciliar contra paper histórico.

**MEDIUM — MT5 import bloqueia WSL**: scripts/reconcile_paper_vs_backtest.py:41 importava cfg que importava MetaTrader5; rodando em Linux sem MT5 falhava antes do BLOCKED. Fix: core/config.py:12 envolve `import MetaTrader5 as mt5` em try/except com `_MT5Stub` (só expomos `TIMEFRAME_M5 = 5`, que é o único atributo lido). Módulos que realmente precisam do MT5 (mt5_client.py, server.py) importam diretamente e quebram alto se falta.

**LOW — TASK-3 hygiene**: codex sinalizou #1/#2/#3/#4/#11/#14 abertos mas já trabalhados. Verificado contra código: AC #1 (server.py só tem /api/v2/regime e /api/di-regime, V1 removido), AC #2 (server.py:196 init_bar_history idempotente + tests/test_bar_history.py), AC #3 (core/risk_gate.py existente), AC #4 (risk_gate.py linhas 9-10 documentam Johansen/HMM como INFORMATIONAL ONLY, com `informational` no return dict + reasons[] estruturado), AC #11 (config.py:138-141 + docs/RUNBOOK_ROLLOVER.md), AC #14 (18 scripts stamped slice 6a). Marcados done.

Validado em Linux puro (sem MT5): 5 branches do reconciler verificadas (BLOCKED/PASS/FAIL/WINDOW_NOT_COVERED/MISSING_BACKTEST), 108/108 pytest verde via Windows runtime.

2026-05-07 (slice 6c-fix-r11, codex round-11): três findings medium, todos corrigidos antes da slice 7.

**MED — janela sem upper bound**: filtro era apenas `date >= cutoff` em ambos os lados. Com `--today` para reconciliação histórica, datas futuras (relativas ao anchor) vazavam para o cálculo. Fix: `load_paper_trades(db, cutoff, today)` agora aplica `date(timestamp_out) BETWEEN ? AND ?`; `aggregate_backtest_window(daily, cutoff, today)` aplica `cutoff_iso <= entry["date"] <= today_iso`. Verificado com fixture: --today=2026-05-07 com row de 2026-05-08 (R$999) é descartada em ambos os lados.

**MED — business_days_ago off-by-one**: prior version retornava N-1 pregões antes de hoje; combinado com filtro inclusivo `>=`, `--days 1` cobria 2 pregões (hoje + ontem). Fix: counter inicia em 1 quando hoje é dia útil, então `--days 1` cobre só hoje, `--days 2` cobre hoje + pregão anterior, etc. Verificado: Thu N=1→Thu, Thu N=2→Wed, Mon N=2→Fri (skip do weekend).

**MED — portfólio subcontava trades**: `p1 = pnl_wdo1 + pnl_di1 + pnl_cp1` somava arrays bar-a-bar; `_daily_aggregate(p1)` contava barras não-zero, então duas pernas fechando na mesma barra M5 viravam 1 trade (e cancelamento exato a + b = 0 sumia). Fix: novo helper `_daily_sum_legs(*leg_dailies)` soma os daily das pernas (counts e pnl agregam corretamente), e novo `_summary_portfolio` recomputa top-level trades/net/gross a partir desse sum. `_daily_aggregate` ganhou warning na docstring contra uso em portfolios. Verificado: 2 pernas mesma data → trades=2 (não 1); cancelamento exato → ainda trades=2 com pnl_net=0.

Validação: 108/108 pytest, py_compile OK, 5 branches do reconciler re-verificadas com nova lógica window+inclusive, fixture de window upper bound passa.

2026-05-07 (slice 6c-fix-r12, codex round-12): um finding medium, corrigido antes da slice 7.

**MED — WINDOW_NOT_COVERED parcial**: o gate só rejeitava `last_bar_date < cutoff`. Para janela [2026-05-01..2026-05-07], um sidecar terminando em 2026-05-06 passava → paper inclui 2026-05-07 mas backtest fica zerado nesse dia → falso PASS. Codex reproduziu localmente. Fix: scripts/reconcile_paper_vs_backtest.py:248-275 agora exige `last_bar >= today` E `first_bar <= cutoff`; senão WINDOW_NOT_COVERED com mensagem específica do tipo (cabeça ou cauda descoberta), incluindo a janela e o range do sidecar para diagnóstico. Verificado com seis fixtures: cauda descoberta (round-12 case) → WNC, cabeça descoberta → WNC, cobertura exata → PASS, sidecar mais largo que janela → PASS (não falso WNC), BLOCKED ainda funciona, FAIL ainda funciona.

2026-05-07 (slice 7, AC #8): lint frontend zerado. Baseline: 32 erros, 0 warnings. Categorias e fixes:

**`react-hooks/static-components` (16 erros)**: componentes inline (`Row` em TradingGuide.jsx, `Gauge`+`Gate` em RegimeHealthPanel.jsx) eram redeclarados a cada render → reset de state. Movidos para top-level do arquivo, mantendo a destructure de props.

**`no-unused-vars` (14 erros)**:
- App.jsx state slots não-lidos (`histLoading`, `fullHistory`) → trocado para `[, setHistLoading]`/`[, setFullHistory]` (mantém os setters chamados, descarta o valor não usado).
- Catch params (`} catch (e) {...}`) → `} catch {...}` (4 sites: 295, 324, 451, 462) — também resolve os 2 `no-empty` ao adicionar comentário descritivo dentro dos blocos.
- `rhoStatus`, `betaHealth`, `isAnom` removidos (declarados, nunca consumidos). Cascading: `currentRho`, `betaOls`, `betaRef20d`, `betaDeltaPct` ficaram orphan após remover `rhoStatus`/`betaHealth` — também removidos.
- `hasAnyTrades` em PerformancePanel.jsx removido (declarado, nunca lido).
- `sigColor`/`currentZ`/`hideXAxis` em ZScoreChart.jsx eram dead-passed: removido de ambas as pontas (signature do componente + call-site no App.jsx).

**`react-refresh/only-export-components` (1 erro)**: App.jsx exportava `alignTradesToBars` (não-componente). Confirmado via grep: nenhum consumidor externo (uso só dentro do próprio App.jsx, sem testes JS no projeto). Removido o `export`, agora função local.

**`no-empty` (2 erros)**: resolvidos junto com os catches via comentário descritivo (`/* AudioContext.close may throw on already-closed */` etc).

Validação: `npx eslint . --format json` retorna 0 erros / 0 warnings; `npm run build` ok (760KB, mesma chunk-size warning pré-existente — fora de escopo); 108/108 pytest verde via Windows runtime. AC #8 marcado done.
<!-- SECTION:NOTES:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 Sem avanço para TASK-2 até esta task estar Done ou explicitamente aprovada como exceção.
- [ ] #2 Notas finais resumem o que foi corrigido, o que ficou pendente e o risco residual.
<!-- DOD:END -->
