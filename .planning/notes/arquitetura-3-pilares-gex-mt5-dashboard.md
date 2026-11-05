---
title: "Arquitetura em 3 Pilares: Cálculo GEX, Robôs Walls MT5 e Dashboard Operacional"
date: "2026-11-04"
context: "Organização estrutural da documentação e mapeamento dos 3 subsistemas do projeto"
---

# Arquitetura em 3 Pilares do Projeto

Documentação mestre consolidada em `docs/MAPA_GERAL_DO_PROJETO.md`:

1. **Pilar 1 — Motor de Cálculo de GEX (`gex/`)**:
   - `gex/engine/`: `main.py` (WIN), `main_dol.py` (WDO), `black76.py`, `walls_calculator.py`, `mt5_prices.py`, `mt5_exporter.py`, `profit_exporter.py`, `tradingview_exporter.py`.
   - `gex/data/`: Caches diários (`win_walls_cache.json`, `usd_brl_walls_cache.json`) e históricos (`jumba_gex_win_history.json`, `jumba_gex_wdo_history.json`).
   - `gex/docs/`: Códigos gerados para TradingView (`jumba_tradingview.pine`) e ProfitChart (`jumba_neologica`, `MagicWallManual.nts`) + relatórios diários (`DAILY_REPORT.txt`, `DAILY_REPORT_DOL.txt`).

2. **Pilar 2 — Arquivos e Robôs (EAs) de Walls no MT5 (`mt5/`)**:
   - `mt5/Include/`: `Jumba_SafetyGuard.mqh` (trava rígida de 1 mini-contrato por EA, sem multiplicador/piramidação), `Jumba_GEX_NWE_Core.mqh` e `Jumba_WDO_GEX_NWE_Core.mqh`.
   - `mt5/Files/` + `Common\Files`: CSVs e JSONs lidos pelos EAs (`jumba_gex_win_daily.csv`, `jumba_gex_wdo_daily.csv`, `jumba_gex_win_history.csv`, `jumba_gex_wdo_history.csv`).
   - `mt5/Experts/` + `mt5/Profiles/Charts/`: EAs individuais e Perfil `Jumba_18_WF_100TR_MONITOR` auditados.

3. **Pilar 3 — Dashboard Web e Operacional das 6 Estratégias (`core/` + `regime-dashboard/` + `server.py`)**:
   - `core/gex_live_dealer_engine.py` + `core/profit_mt5_flow_engine.py`: Motores intraday com Janela de Fluxo A.S.G **Campeã Conjunta** (WIN `5/18, 85/15, 0.45, ±11` | WDO `4/22, 85/15, 0.60, ±11`), GEX Makers Opção 1 (Hedge Acumulado) e Opção 3 (Mapa de Atração/Ímã) e as **6 Estratégias Sistemáticas** (`EST_01`, `EST_07`, `EST_13`, `WDO_09`, `WDO_11`, `WDO_S2`) com 6/6 meses positivos (`Ret/DD = 40,04x`).
   - `regime-dashboard/src/components/IntradayCompassPanel.jsx`: Interface do Cockpit limpo com gráfico de 4 andares e curva de capital do dia.

