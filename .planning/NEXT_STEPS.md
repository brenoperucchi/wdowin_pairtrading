# Próximos Passos — WDO×WIN Pair Trading

## 1. Firebase Hosting (Dashboard público)
- Criar projeto Firebase (ou reusar `rastromacro`)
- Backend pusha dados para Firebase RTDB (como IRAI faz)
- Frontend consome RTDB em produção, localhost em dev
- `firebase.json` + `.env.production` + `vite build` + `firebase deploy`
- Referência: `rastro_irado/frontend/` já tem setup completo

## 2. Integração MT5 — Envio de Ordens
- Usar `mt5.order_send()` para despachar ordens reais
- Trade engine atual é signal-only + paper tracking → converter para execução
- Criar módulo `core/mt5_executor.py` com order_send/position_close
- SL/TP/BE via ordens pendentes ou gestão interna
- Kill switch manual no dashboard
- **ATENÇÃO**: dinheiro real, exige testes exaustivos em conta demo primeiro

## 3. Auditoria Painel ↔ Trade Engine ↔ Setup Matador (Mai 2026)
- Alinhar eixo X dos 3 gráficos (ZScore, Histograma NWE, Preço) — recharts Bar vs Line
- Implementar lógica de **proximidade NWE** no frontend (preço próximo à banda superior/inferior)
- Verificar que cada row do histograma espelha exatamente o setup do trade engine
- Corrigir `inject_day_trades.py` (z_in errado para DI, TIME_OFFSET, PnL)
- **Ref:** `.planning/todos/pending/2026-05-01-auditoria-completa-setup-matador-painel-histograma.md`
