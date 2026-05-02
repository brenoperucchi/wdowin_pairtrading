# Decision Log — WIN×WDO Pair Trading System

Registro de decisões técnicas e aprendizados do projeto.  
Cada entrada documenta **o quê**, **por quê**, e **o que aprendemos**.

---

## Decisões Estratégicas

### D001 — Dual Z-Score Routing (BUY≠SELL)
**Data**: Mar 2026  
**Decisão**: Usar Kalman z-score para BUY e OLS z-score para SELL.

**Contexto**: O backtest mostrou que o filtro Kalman captura reversões mais rápido no lado de compra, mas gera mais falsos positivos no lado de venda. O OLS com janela fixa é mais conservador para vendas.

**Resultado**: Melhora de ~12% no win rate de vendas vs usar Kalman para ambos.

**Aprendizado**: Não existe um modelo único que seja ótimo para todas as direções. A assimetria do mercado (BULL tende ser gradual, BEAR tende ser abrupto) exige tratamento diferenciado.

---

### D002 — SL/TP Assimétrico por Direção
**Data**: Mar 2026  
**Decisão**: Parâmetros diferentes para BUY e SELL:

| Param | BUY | SELL | Razão |
|---|---|---|---|
| SL | 350 pts | 300 pts | Compra precisa de mais espaço |
| TP | 500 pts | 1400 pts | Venda captura movimentos maiores |
| BE Act | 400 pts | 800 pts | Venda precisa de mais confirmação |
| BE Lock | 50 pts | 200 pts | Venda trava mais profit |

**Contexto**: Otimizados via grid search exaustivo em 5 anos de dados M1 (~2.5M barras). Os heatmaps mostraram clusters claros de parâmetros ótimos.

**Aprendizado**: O mercado brasileiro tem assimetria forte — os movimentos de queda no índice são mais rápidos e violentos que os de alta. Operar com SL/TP simétrico ignora essa realidade.

---

### D003 — HMM como Filtro (não como Gerador de Sinais)
**Data**: Mar 2026  
**Decisão**: O HMM M30 serve apenas para **bloquear** entradas em regime BULL, não para gerar sinais de compra/venda.

**Contexto**: Tentamos usar o HMM para gerar sinais diretos (compra se BEAR) mas os resultados foram instáveis — muitos whipsaws na transição de regimes. Usar como filtro binário (BULL = não entra) foi mais robusto.

**Aprendizado**: Modelos de regime funcionam melhor como filtros conservadores do que como geradores de sinais. A inércia do HMM (transition matrix com diagonal forte) garante que ele só bloqueia em tendências claras.

---

### D004 — Operar Apenas WIN (não WDO)
**Data**: Mar 2026  
**Decisão**: O Setup Matador opera apenas contratos de WIN, ignorando WDO.

**Contexto**: O backtest original operava o par (WIN + WDO), mas a execução simultânea de dois ativos com spreads diferentes adicionava complexidade e slippage. O z-score captura a relação — operar apenas WIN simplifica a execução.

**Aprendizado**: Em pairs trading, nem sempre é necessário operar ambas as "pernas" do par. Se a relação é o sinal, um único instrumento pode ser suficiente para capturar o alpha.

---

### D005 — Beta Discreto (State Machine) vs Contínuo
**Data**: Fev 2026  
**Decisão**: Recalcular beta OLS apenas em intervalos de 1 hora (09:30, 10:30, ..., 17:30).

**Contexto**: Recalcular beta a cada barra de 5 min (tick-by-tick) gerava instabilidade — variações de 5-10% em poucos minutos poluíam os sinais. A state machine horária suaviza sem perder responsividade.

**Aprendizado**: Parâmetros de calibragem (como β) precisam de estabilidade. Atualizar rápido demais introduz ruído; lento demais perde a adaptação. O intervalo horário durante o pregão foi o sweet spot.

---

### D006 — Threshold ρ ≤ -0.40 para Bloqueio
**Data**: Mar 2026  
**Decisão**: Parar de operar quando correlação sobe acima de -0.40.

**Contexto**: O pairs trading assume correlação estável. ρ > -0.40 indica descorrelação — o z-score perde significado estatístico. Testar com ρ > -0.55 foi conservador demais (perdeu muitas oportunidades).

**Aprendizado**: -0.40 é o ponto onde a correlação é tão fraca que o z-score pode estar medindo ruído puro. Abaixo de -0.55 é confortável, entre -0.55 e -0.40 opera com sizing menor.

---

## Decisões de Engenharia

### E001 — FastAPI + React (não streamlit/dash)
**Decisão**: Backend FastAPI com frontend React separado.

**Por quê**: Streamlit e Dash são convenientes mas limitam customização visual e performance de polling. A separação permite dashboard de grau profissional com UI financeira.

---

### E002 — SQLite (não Postgres)
**Decisão**: Usar SQLite para persistência de trades.

**Por quê**: Operação local, single-user, poucos trades/dia. SQLite é zero-config, portátil, e mais que suficiente. Quando/se migrar para VPS, considerar Postgres.

---

### E003 — Monolito → core/ (Abr 2026)
**Decisão**: Decompor server.py de 911 linhas em 6 módulos core/.

**Por quê**: O monolito misturava I/O (MT5), computação (sinais), threading (HMM) e HTTP (FastAPI) no mesmo arquivo. Impossível testar sem MT5 conectado. Com `core/signals.py` isolado, podemos testar funções puras com dados sintéticos.

**Resultado**: 24 testes passando em 0.3s sem MT5.

---

### E004 — V1/V2 Toggle Removido (Abr 2026)
**Decisão**: Remover toggle V1/V2 do frontend, fixar no V2 (Kalman).

**Por quê**: O V2 já inclui ambos os z-scores (Kalman + OLS dashed). O toggle era útil na fase de desenvolvimento para comparação, mas confuso em produção. A linha OLS permanece como referência visual no gráfico.

---

### E005 — Process Manager PM2 (Abr 2026)
**Decisão**: Substituir o script em lote local por gerenciamento via `pm2` para o backend FastAPI e frontend Vite.

**Por quê**: A operação em 24/7 do monitor exige ressuscitação automática em caso de crashes no backend (ex: desconexões do MT5) e inicialização silenciosa em background. O PM2 fornece logs unificados e restart automático, aumentando drasticamente a estabilidade do sistema.

---

### E006 — Prevenção de Memory Leaks no React (Abr 2026)
**Decisão**: Limitar o array de histórico (`fullHistory`) e implementar memoização rigorosa (`useMemo`, limpeza de `setTimeout` e reuso de `AudioContext`).

**Por quê**: O polling de 2.5 segundos somado ao re-render contínuo dos gráficos do Recharts e clonagem de arrays via map/spread exauria a memória do navegador após horas rodando. Componentes como `SignalHistogram` e o alerta sonoro recriavam instâncias caras a cada ciclo. A memoização e o teto máximo de barras garantem estabilidade infinita para uma aba deixada aberta dias a fio.

---

## Aprendizados Gerais

### L001 — Cointegração Não é Estável
A relação WIN×WDO é cointegrada na maioria do tempo, mas **quebra** em eventos macro (Copom, intervenção BC, crise política). O teste Engle-Granger horário detecta isso, mas com lag. O ρ rolling é um indicador mais precoce de instabilidade.

### L002 — Backtest ≠ Trading Real
Os resultados de backtest são otimistas por natureza (sem slippage, sem latência, sem emoção). Manter margem de segurança nos parâmetros. O SL de 350 pts em BUY provavelmente precisa ser 400+ em produção real.

### L003 — HMM Precisa de Regularização
O GaussianHMM com `transmat_prior = I + eye*5` funciona melhor que sem prior. Sem o prior, os regimes flip muito rápido (3-5 barras), gerando whipsaws. Com o prior, o modelo fica "pegajoso" — muda de regime apenas com evidência forte.

### L004 — Break-Even é Mais Importante que SL/TP
A otimização mostrou que o break-even tem mais impacto no resultado final do que ajustes finos de SL e TP. Ativar BE cedo demais (< 200 pts) gera muitas saídas prematuras. O ponto ótimo é ~400 pts para BUY e ~800 pts para SELL.

### L005 — Organização do Código Importa
Com 20+ scripts na raiz, ficava impossível saber o que era produção e o que era experimento. A separação `core/` vs `research/` vs `data/` clarificou o que roda em produção e o que é descartável.

### L006 — NWE No Frontend Precisa Ser Causal (Mai 2026)
A implementação original do `calcNWE()` no frontend (`IndexChart.jsx`) usava **todas as barras da série** no kernel Gaussian (incluindo dados futuros). Isso criava um NWE suavizado "perfeito" — visualmente bonito mas impossível em tempo real. O backend (`core/signals.py`) usava corretamente apenas **lookback=95 barras para trás** (causal).

**Impacto direto:** O `isUp` (direção do NWE) flippava constantemente no histograma do dashboard, porque a direção calculada com lookahead é completamente diferente da direção causal. Isso invalidava toda a filtragem NWE no painel.

**Aprendizado:** Ao portar lógica matemática do backend (Python) para o frontend (JS), a garantia de **causalidade** é tão importante quanto os parâmetros. Um NWE com lookahead é um indicador *pintado* — útil para análise retroativa, inútil para trading em tempo real.

### L007 — Filtros Visuais Devem Espelhar o Setup (Mai 2026)
Botões de toggle (Filtro NWE, Filtro Estatístico) no dashboard permitiam o usuário ligar/desligar filtros que já estavam embutidos na definição de cada setup. Isso criava confusão: o histograma mostrava sinais que não existiam no trade engine, ou escondia sinais válidos.

**Decisão:** Cada row do histograma agora representa *exatamente* um setup com suas regras fixas. "WDO NWE" sempre aplica NWE, "DI NWE" sempre aplica NWE, e "WDO DI" (Consenso) nunca aplica NWE. Os toggles foram removidos.
