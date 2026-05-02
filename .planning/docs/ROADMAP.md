# Roadmap — WIN×WDO Pair Trading System

**Última atualização**: Abril 2026

---

## ✅ Fase 1: MVP — Monitoramento de Regime (Concluída)

> *"Conseguir enxergar a oportunidade em tempo real"*

- [x] Conexão live com MetaTrader 5
- [x] Cálculo de Z-Score rolling (OLS, janela 40)
- [x] Dashboard React com gráfico intraday
- [x] Classificação de sinais (COMPRA/VENDA/NEUTRO/ANOMALIA)
- [x] Monitoramento de correlação ρ
- [x] Alerta sonoro ao cruzar zona de trade

---

## ✅ Fase 2: Inteligência — HMM + Kalman (Concluída)

> *"Filtrar entradas com IA e melhorar estimativa de beta"*

- [x] Filtro de Kalman para beta adaptativo em tempo real
- [x] Endpoint V2 com dual z-score (Kalman BUY + OLS SELL)
- [x] HMM 3-estados (BULL/BEAR/CHOP) em background thread M30
- [x] Bloqueio automático de entrada em regime BULL
- [x] Teste de cointegração Engle-Granger horário

---

## ✅ Fase 3: Validação — Backtest + Setup Matador (Concluída)

> *"Provar que funciona em 5 anos de dados antes de operar"*

- [x] Backtest completo 2021-2026 em dados M1 (~93MB)
- [x] Otimização de SL/TP por direção (grid search)
- [x] Otimização de Break-Even (heatmap ativação × lock)
- [x] Otimização de horário de operação
- [x] Validação do filtro HMM no backtest
- [x] Trade Engine com parâmetros assimétricos validados
- [x] Persistência SQLite por trade

---

## ✅ Fase 4: Engenharia — Reorganização (Concluída)

> *"Código de produção não pode ser monolítico"*

- [x] Decomposição do server.py (911 → 480 linhas)
- [x] Módulos `core/` (config, signals, mt5_client, hmm, kalman, trade_engine)
- [x] Decomposição do App.jsx (677 → 460 linhas + 5 componentes)
- [x] Suite de 24 testes automatizados
- [x] Organização: root limpo, `research/`, `data/`, `docs/`
- [x] Documentação: PRD, SPEC, Roadmap, Decision Log

---

## 🔄 Fase 5: Reavaliação Estratégica (Próxima)

> *"O Setup Matador continua performando ou existe algo melhor?"*

- [ ] Atualizar CSVs históricos com dados recentes (Abr 2026+)
- [ ] Re-rodar backtests com janela atualizada
- [ ] Comparar performance Setup Matador vs novas variantes:
  - [ ] Z-Score threshold sensitivity (1.5 vs 1.8 vs 2.0)
  - [ ] Janela de z-score (30 vs 40 vs 50)
  - [ ] Asymmetric vs symmetric SL/TP
  - [ ] HMM filter vs sem filtro (quantificar alpha)
- [ ] Walk-Forward Analysis (WFA) para robustez temporal
- [ ] Relatório comparativo final
- [ ] Decisão: manter, ajustar ou substituir Setup Matador

---

## 📋 Fase 6: Automação (Futuro)

> *"Tirar o humano do loop"*

- [ ] Execução real de ordens via MT5 (send_order)
- [ ] Gerenciamento de posição automático
- [ ] Notificações Telegram/Discord
- [ ] Logging estruturado para auditoria
- [ ] Painel de risk management (drawdown, max loss diário)
- [ ] Monitoramento de saúde do sistema (uptime, latência)

---

## 🔮 Fase 7: Escala (Futuro Distante)

> *"Expandir o universo de pares e estratégias"*

- [ ] Pairs trading em outros ativos B3 (PETR4×VALE3, etc.)
- [ ] Multi-timeframe analysis (M5 + M15 + H1)
- [ ] Ensemble de modelos (HMM + LSTM + XGBoost)
- [ ] Dashboard multi-par
- [ ] Cloud deployment (VPS com MT5 headless)
