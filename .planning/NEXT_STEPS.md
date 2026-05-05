# Próximos Passos — WDO×WIN Pair Trading

## 1. Firebase Hosting (Dashboard público)
- Criar projeto Firebase 
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
