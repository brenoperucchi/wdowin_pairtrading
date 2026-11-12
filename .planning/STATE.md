# Project State

## Project Reference

See: [`STATARB_2026_KNOWLEDGE.md`](../STATARB_2026_KNOWLEDGE.md), [`docs/PAINEL_5176_SNIPER_DIVERGENCIA_SMART_MONEY.md`](../docs/PAINEL_5176_SNIPER_DIVERGENCIA_SMART_MONEY.md) & [`.planning/PROJECT.md`](PROJECT.md). Documento de estado atualizado em 10/11/2026.

**Core value:** Arquitetura dual de painéis em produção local: **`5174`** (Carteira Top 8 EAs M5 com fluxo para robôs MT5), **`5176`** (Painel minimalista Sniper 1:1 de Divergência `F1➔F2 / T1➔T2` na Wall + `Fluxo Smart Money` + `Visão Dupla` padrão) e Aba 3 **`STAT_ARB`** (`WIN × WDO × DI`) preservada em ambos.
**Current focus:** Operação ao vivo do Sniper de Divergência na `5176` (`2c WIN Mix + 1c WDO MidWall`) e preparação da próxima fase de pesquisa de fluxo (Absorção na Wall com filtros rigorosos de seletividade + estratégias no timeframe `M1`).

## Current Position

Status: **Em Produção Local Dual-Stack (`5174`, `5176`, `8080` via `keep_dashboards_alive.py`)**
Last activity: **10/11/2026** — Consolidação completa do **Painel `5176` Sniper de Divergência na Wall & Fluxo Smart Money** (`WIN_DIV_WALL` 2c Mix `[L1 NWE30 Din + L2 750p]` + `WDO_DIV_WALL` 1c MidWall, com sobreposição permitida, filtro de horário `s/ 12h WIN` e `s/ 11h WDO` e Meta Diária causal `+R$ 180` / `+R$ 120` ➔ **`+R$ 12.827` líquidos em 212 pregões, `WR 70,0%`, `PF 2,49`, `MDD R$ 380`, `Ret/DD 33,76x`, `11/11` meses +**); redesign visual monocromático na `5176` (`Visão Dupla` padrão, Walls brancas/cinzas, candles neutros, sub-painel `2. FLUXO SMART MONEY` apenas com linha azul e cor viva restrita às divergências e caixas de trade); watchdog ajustado para dual-stack IPv4+IPv6 (`--host ::`); `5174` mantida 100% intacta.

**Em andamento (não commitado):** saldo em lotes de RLP/HFT no cockpit — `regime-dashboard/src/components/IntradayCompassPanel.jsx` e os motores `core/gex_live_dealer_engine.py`, `core/profit_mt5_flow_engine.py` e `core/profit_wall_players_engine.py`. Riscos em aberto: `importlib.reload` de `profit_wall_players_engine` em `profit_mt5_flow_engine.py` (hot-reload no caminho de produção) e fallbacks inconsistentes de `rlp_delta` entre engine e UI.

**Execução real MT5:** ainda não implementada — não existe `core/mt5_executor.py` e não há chamada a `mt5.order_send()` no backend.

## Key Decisions (Consolidated 10/11/2026)

- **Manutenção do Sistema Atual de Saída (`BE +150/200p → +15p` + Alvo Wall/Z-Rev):** Entregou `+R$ 10.135` (`+25.338 pts`), Max DD `R$ 764` e `Ret/DD = 13,27x` nos 212 pregões de 2026 (488 trades).
- **Stop Loss Sempre Atrás da Wall Anterior:** `calc_wall_tp_sl` posiciona o stop `30 pts` atrás da Wall anterior (mín. `200 pts`, máx. `300 pts`). Se a Wall exigir `> 300 pts`, o setup é abortado (nunca truncado para antes da Wall).
- **Sinais Sem Repintura:** Barras M5 fechadas têm seus sinais (`sig_wdo`, `sig_di`, `sig_cons`) congelados no SQLite (`bar_history`).
- **Isolamento de Abas:** Aba 1 exclusiva para Cockpit GEX + 4 sistemáticas (`WIN_1` / `WIN_2` / `WDO_1` / `WDO_2`) e o calendário das carteiras 11 EAs (com filtro de fluxo) e 8 EAs (sem filtro), perfis MT5 XP (`LiveTradingCalendar.jsx`); Aba 3 exclusiva para Arbitragem `WIN × WDO × DI`. As antigas “6 Estratégias Campeãs” foram substituídas por esse recorte no código e nos commits de 05/11 e 10/11/2026.
- **Blindagem MT5:** Toda comunicação com a DLL do MetaTrader 5 roda em thread única de SO (`_single_mt5_executor` + `core.mt5_client.mt5_lock`). Isso serializa chamadas à DLL; não é execução real de ordens.
