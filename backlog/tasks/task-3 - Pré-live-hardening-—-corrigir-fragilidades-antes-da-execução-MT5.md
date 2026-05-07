---
id: TASK-3
title: Pré-live hardening — corrigir fragilidades antes da execução MT5
status: To Do
assignee: []
created_date: '2026-05-07 00:42'
updated_date: '2026-05-07 21:05'
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
- [ ] #1 `/api/regime` V1 está corrigido, removido ou documentado como obsoleto sem risco de uso acidental; README/CLAUDE/endpoints refletem a decisão.
- [ ] #2 `bar_history` possui migration/tabela criada de forma idempotente e há teste ou script de verificação que cobre salvar/carregar barras.
- [ ] #3 Função `risk_gate(...)` extraída para módulo dedicado (`core/risk_gate.py` ou similar) retorna `{allowed: bool, reasons: list[str], checks: dict}` e é consumida por `TradeEngine.evaluate()` substituindo o atual `safe_to_trade`/`beta_safe`; o cálculo em `server.py:608` é removido ou redirecionado para essa função (sem duplicação de lógica).
- [ ] #4 Política explicita para Johansen e HMM (atualmente apenas informativos no fluxo de entrada): documentada em CLAUDE.md/README como bloqueia / reduz sizing / informa apenas. Cada decisão de WAIT no `risk_gate` registra o `reasons[]` em log estruturado para rastreabilidade.
- [x] #5 Produção e backtest usam um perfil único/versionado de parâmetros, ou há manifesto comparando exatamente os parâmetros vivos vs parâmetros do backtest.
- [x] #6 Conceito operacional está explicitado: sistema atual opera apenas WIN com filtros WDO/DI, ou plano de hedge real está documentado como futuro.
- [x] #7 `requirements.txt` inclui dependências necessárias para runtime e teste (`firebase-admin`, `pytest`, demais imports detectados); `python -m pytest tests/ -q` é executável em ambiente preparado.
- [ ] #8 `npm run lint` não possui falhas críticas relacionadas ao escopo pré-live, ou as remanescentes estão listadas com justificativa e follow-up.
- [x] #9 `npm run build` passa.
- [x] #10 Dashboard diferencia claramente estado live, fallback simulado, Firebase indisponível, API offline e modo histórico. — JÁ CUMPRIDO em `regime-dashboard/src/App.jsx:618-630, 636-639, 667-676` (badges Topbar MT5 LIVE/SIMULADO/HISTÓRICO + banner de erro específico + footer DADOS REAIS/SIMULADOS); marcar como done sem trabalho adicional.
- [ ] #11 Constantes de risco operacional adicionadas a `core/config.py` com valores default conservadores e implementadas como checks no `risk_gate`: `MAX_TRADES_PER_DAY` (sugestão default 4), `DAILY_LOSS_LIMIT_BRL` (default a calibrar a partir de histórico de `pnl_brl`), `LOSS_COOLDOWN_MIN` (sugestão default 30), `BLOCK_ON_MT5_DISCONNECT` (default True). Política de rollover de símbolos contínuos (WIN/WDO/DI mensal) documentada como processo manual em runbook.
- [ ] #12 Review do Claude anexado nas notas da task antes de mover para Done, com eventuais comentários resolvidos ou convertidos em follow-ups.
- [x] #13 Nomenclatura DOL/WDO documentada em `research/README.md` (ou doc equivalente): no escopo atual deste codebase, DOL ≡ WDO ≡ Mini Dólar (`SYMBOL_B='WDO$N'`), sem contrato cheio implementado; remover ambiguidade antes de investigar P&L.
- [ ] #14 Escopo de cada script de research reconciliado com o motor de produção: `research/optimize_wdo.py`, `research/optimize_wdo_sltp.py`, `research/backtest.py`, `research/backtest_pa.py` são (a) reescritos para operar a perna WIN com filtros WDO/DI (paridade com `_eval_consensus`/`_eval_wdo_nwe`/`_eval_di_nwe` do trade_engine) ou (b) marcados em header como 'research exploratório, não validação de produção'. Não fazer fix sem antes decidir o que cada script deve testar.
- [x] #15 Script(s) marcado(s) como validação de produção incluem: slippage WIN (5 pts/lado, conservador), custos B3 estimados (emolumentos + corretagem por contrato — confirmar com XP), descarte de trades que cruzam rollover de WDO/DI/WIN.
- [ ] #16 P&L do backtest validado nos últimos 30 dias úteis é comparado com soma de `pnl_brl` em `matador_ops` no mesmo período (paper trading). Erro relativo < 10% = paridade aceita; ≥ 10% = bug investigado e resolvido em um dos lados antes de Done.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-05-07: Gestor reportou que o backtest Python em operação DOL não está funcionando bem. Isso fica explicitamente dentro da TASK-3, pois afeta validade de backtest, paridade setup/backtest/dashboard e decisão conceitual entre operar apenas WIN direcional versus operar perna DOL/WDO como hedge. Pontos iniciais a revisar: scripts research/backtest.py, research/backtest_pa.py, research/optimize_wdo.py e research/optimize_wdo_sltp.py; confirmar se "DOL" significa contrato cheio DOL ou mini dólar WDO usado no config atual (SYMBOL_B=WDO$N).

2026-05-07 (review Claude): Análise dos 9 problemas + AC #13 contra código real. **7 confirmados** (#1, #2, #3, #6, #7, #9 e parcial #4). **#4 parcial**: `safe_to_trade` em server.py:608 já centraliza 5 gates (pvalue, rho, beta_delta, beta_unstable, sessão); falta extrair em módulo + decidir Johansen/HMM (hoje informativos, nunca consultados em evaluate()). **#5 confirmado direcional puro**: trade_engine abre só qty_win=2, sem hedge — trabalho é doc, não código. **#10 (AC) já cumprido**: App.jsx:618-630, 636-639, 667-676 já têm badges Topbar (MT5 LIVE/SIMULADO/HISTÓRICO) + banner de erro específico + footer DADOS REAIS/SIMULADOS — marcar como done sem trabalho. **#13 (AC) DOL/WDO**: 'DOL' só aparece na própria task; nenhum script Python usa DOL$N — é apelido coloquial para WDO. Causa-raiz do 'backtest não funciona': **incoerência de escopo**. `optimize_wdo*.py` operam só WDO; `backtest*.py` operam 4 legs especulativos; produção opera só WIN. Backtest não é validação do motor. ACs #3, #4, #11 e #13 refinados com escopo afiado para evitar fechamento cosmético. Plano completo da review em /home/brenoperucchi/.claude/plans/stateful-toasting-pony.md.

2026-05-07 (slice 6c): scripts/reconcile_paper_vs_backtest.py implementa AC #16. Quatro estados: BLOCKED (0 paper trades — exit 0), MISSING_BACKTEST (sidecar JSON ausente — exit 2), PASS (|err| <10% — exit 0), FAIL (≥10% — exit 1). research/run_matador_v5_johansen.py agora emite portfolio_v5_summary.json após cada run com pnl_brl_gross+pnl_brl_net por leg/portfólio (matador_ops grava gross; backtest grava net; reconcile compara ambos lados em paralelo). Convenção de saída unificada: backtest realiza pts_favor real do bar (igual core/trade_engine.py:352), não TP/-SL/0 hardcoded — fix do medium #2 do codex round-9. AC #15 marcado done (slippage 5pts/lado + B3 R$1/contrato/RT + rollover discard via 5σ heuristic). **AC #16 fica BLOCKED até paper history acumular**: matador_ops tem 0 closed trades em 2026-05-07; reconcile reporta BLOCKED com exit 0 e a metodologia está em docs/PARAM_PROFILE.md §4. Re-rodar o script após algumas semanas de uptime do paper engine. Slice 6c desbloqueia slice 7 (lint frontend AC #8) e slice 8 (review final AC #12).
<!-- SECTION:NOTES:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 Sem avanço para TASK-2 até esta task estar Done ou explicitamente aprovada como exceção.
- [ ] #2 Notas finais resumem o que foi corrigido, o que ficou pendente e o risco residual.
<!-- DOD:END -->
