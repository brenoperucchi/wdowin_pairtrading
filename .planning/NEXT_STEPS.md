# Próximos Passos — Ecossistema MagicWalls & Quant B3

## 1. Pesquisa de Novas Estratégias via Fluxo (Painel `5176` — Absorção Seletiva na Wall & `M1`)
Referência completa: [`docs/PAINEL_5176_SNIPER_DIVERGENCIA_SMART_MONEY.md`](../docs/PAINEL_5176_SNIPER_DIVERGENCIA_SMART_MONEY.md) e [`research/flow_ablation/RESULTADOS.md`](../research/flow_ablation/RESULTADOS.md)

- **1.1. Estratégia de Absorção na Wall com Filtros Rigorosos (Alta Seletividade):**
  - *Aprendizado consolidado:* operar absorção simples na Wall de forma indiscriminada gera excesso de operações e ruído contra tendência. Além disso, a ablação de 16/11/2026 (`research/flow_ablation/RESULTADOS.md`) mostrou que no WIN atual a maior parte do sinal da onda vinha da geometria do candle (parcela Wyckoff) e não do volume puro — reforçando a necessidade de validar separadamente o valor preditivo da microestrutura real (Tape/livro) antes de adicionar novas estratégias na `5176`.
  - Critérios para novos candidatos:
    - Exigir assimetria extrema **Esforço × Resultado** com dados reais de microestrutura (`Tape` / agressão × deslocamento).
    - Filtrar por **regime GEX favorável (`Gamma Positivo` na defesa)** e "frescor" do nível (priorizar 1º/2º toque da sessão).
    - Aplicar desde a origem **filtro de horário** + **trava causal** + validação estrita OOS / nulo embaralhado.
- **1.2. Expansão da Pesquisa para o Timeframe `M1` (Microestrutura Fina):**
  - Combinar a ancoragem macro das `MagicWalls`/`MidWalls` GEX com gatilhos no `M1` (absorção + 1ª barra de ignição, *Spring / Upthrust* em `1–3` barras `M1`, Stop Loss técnico atrás da defesa real do `M1`).

---

## 2. Onda 2 — SaaS Resiliente (`app.magicwalls.com.br` / `api.magicwalls.com.br`)
Referência técnica: [`cloud_saas/README_DEPLOY.md`](../cloud_saas/README_DEPLOY.md) e [`docs/PLANO_COMERCIAL_SAAS_MAGICWALLS.md`](../docs/PLANO_COMERCIAL_SAAS_MAGICWALLS.md)

- **2.1. Produtor Hot Standby (Zero SPOF do PC Local):**
  - Provisionar instância secundária (`scripts/cloud_publisher.py --role standby --producer-id ...`) em VPS Windows dedicada (ou máquina backup com MT5/Profit sincronizados) para assumir automaticamente a publicação de snapshots `core`/`pro` caso o produtor primário (`pc-local-01`) caia durante o pregão.
- **2.2. Monitoramento Externo de `feed_age` e SLA:**
  - Configurar verificação externa independente (uptime monitor / cron externo) consultando `GET https://api.magicwalls.com.br/api/v1/feed/status` (e `/health`) durante o horário de pregão B3 (`08:55–17:30`), alertando em Telegram/webhook se `feed_age` ultrapassar o limiar de SLA (`> 15s` / `> 60s`).
  - Garantir `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` configurados em `cloud_saas/.env` para ativação completa dos alertas nativos do `HeartbeatMonitor` em `scripts/cloud_publisher.py`.
- **2.3. Backup e Recuperação do Supabase:**
  - Implantar rotina automática de backup lógico/exportação das 6 tabelas (`profiles`, `subscriptions`, `active_sessions`, `terms_acceptance`, `audit_logs`, `producer_heartbeats`) e testar procedimento de *restore* em projeto de homologação.
- **2.4. Governança de Custos e Conformidade LGPD:**
  - Monitorar mensalmente consumo e faixas de custo (Railway `api.magicwalls.com.br`, Upstash Redis REST, Supabase PostgreSQL e Cloudflare Pages/túneis) contra a receita por assinante.
  - Consolidar fluxo operacional de atendimento aos direitos do titular (LGPD: exportação/anonimização via `audit_logs`, versionamento de aceite clickwrap `MW_TERMS_VERSION` e retenção mínima de logs).

---

## 3. Onda 3 — Estratégico & Evolução de Arquitetura
- **3.1. Decisão Pós-30 Pregões de Paper Trading (`ESP_DIV_V22_WIN` + Carteira V3.2):**
  - Avaliar após **30 pregões completos** em paper trading no painel `5176` a aderência live vs backtest de `ESP_DIV_V22_WIN` (`core/especialista_v22.py`) e dos 4 robôs da Carteira V3.2 (`C1a_BRK_WIN`, `V1a_DIV_WDO`, `SYM_DIV_WIN`, `SYM_DIV_WDO`), além de acompanhar os relatórios diários da carteira MT5 Top 10 (`scripts/reconcile_mt5_vs_bt.py`), antes de decidir qualquer alteração de alocação ou automação adicional.
- **3.2. Coleta de Base Robusta de Tape Diário (`35–40` Pregões `WIN + WDO`):**
  - Acumular **35–40 pregões completos** de Tape tick-a-tick (`WIN` e `WDO`) para eliminar limitação de poder estatístico (observada com apenas 4–15 pregões na ablação de fluxo) e permitir validação OOS rigorosa de sinais baseados em player, apregoação e agressão líquida real.
- **3.3. Modularização Progressiva do Monólito (`server.py` e `gex_live_dealer_engine.py`):**
  - Quebrar `server.py` (~2.935 linhas) em roteadores FastAPI coesos por domínio (`routers/regime.py`, `routers/compass.py`, `routers/flow.py`, `routers/live_calendar.py`) e decompor `core/gex_live_dealer_engine.py` (~4.620 linhas) em módulos menores (cálculo GEX/NWE, replay histórico, integração paper V22/V3.2), mantendo contratos JSON e cobertura de testes (`pytest`).
