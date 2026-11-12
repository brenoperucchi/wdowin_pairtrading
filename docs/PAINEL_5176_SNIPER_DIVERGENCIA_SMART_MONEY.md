# 🎯 Documentação Oficial — Painel `5176` · Sniper de Divergência na Wall & Fluxo Smart Money

> **Última atualização:** 11/11/2026  
> **Escopo:** Operacional, matemática de fluxo, unificação da Janela de Fluxo Smart Money (`V5b` em `WIN` e `WDO`), auditoria histórica (212 pregões de 2026), arquitetura visual minimalista do painel `http://localhost:5176` e roadmap das próximas fases de pesquisa de fluxo (Absorção Filtrada na Wall e estratégias em `M1`).

---

## 1. Arquitetura Dual dos Painéis (`5174` vs `5176`)

O repositório opera **dois painéis independentes** sobre a mesma base React/FastAPI, isolados automaticamente pela função `isWallsFlowLocalhost()`:

| Porta / URL | Papel no Ecossistema | Estratégias Exibidas | Visual do Gráfico |
| :--- | :--- | :--- | :--- |
| **`http://localhost:5174`** | **Painel Robôs MT5 (`PROPOSTA A`)** — acompanhamento da carteira automatizada M5 executada via Expert Advisors com **Janela de Fluxo Smart Money Unificada (`V5b`)**. | **8 Estratégias M5** (`EST_04`, `EST_07`, `EST_13`, `EST_14`, `EST_15`, `WDO_01`, `WDO_05`, `WDO_07`) — **`+R$ 32.309`** (`11/11` meses +, `WIN Ret/DD 15,31x` com `Max DD -R$ 1.083` e `WDO 10/11 M+`). | Tradicional colorido (candles verdes/vermelhos, eventos de Wall, controles completos). |
| **`http://localhost:5176`** | **Painel Sniper de Divergência & Fluxo Smart Money** — leitura limpa institucional focada 100% em divergência na Wall + aba `STAT-ARB` preservada. | **2 Estratégias Sniper 1:1** (`WIN_DIV_WALL` 2c Mix + `WDO_DIV_WALL` 1c MidWall) — **`+R$ 12.827` líquidos (`Ret/DD 33,76x`, `11/11` meses +)**. | **Monocromático Minimalista + Visão Dupla Padrão (`WIN + WDO`)**: Walls brancas/cinzas, candles neutros e cor viva apenas nas divergências e nas caixas de trade. |
| **`http://localhost:8080`** | **Backend Unificado FastAPI (`server.py`)** — alimenta simultaneamente a `5174`, a `5176` e a aba `STAT-ARB` (`WINFUT × WDOFUT × DIFUT`). | Ambas as carteiras servidas sem conflito via `portfolio_4_sistematicas` e `signals_log`. | API REST JSON + SQLite + Profit RTD/DB + MT5 single-thread. |

- **Alta Disponibilidade Local (`keep_dashboards_alive.py`):** O processo residente `pythonw.exe keep_dashboards_alive.py` monitora continuamente as portas `8080`, `5174` e `5176`, subindo o Vite em modo **dual-stack IPv4 + IPv6 (`--host ::`)** para garantir resposta imediata tanto em `http://localhost:5176` (`[::1]`) quanto em `http://127.0.0.1:5176`.

---

## 2. O Que Aprendemos na Pesquisa de Fluxo nas Walls (Lições Críticas)

Durante a bateria de testes nos **212 pregões de 2026 (`02/01/2026` a `06/11/2026`)**, testamos desde motores multi-gatilho de absorção até divergências puras. Os aprendizados fundamentais que moldaram o operacional atual foram:

1. **Absorção simples na Wall opera de forma excessiva quando sem filtros rígidos:**
   - Quando o motor disparava entradas em qualquer barra M5 que tocasse uma Wall com absorção passiva ou agressão institucional isolada, surgiam **muito mais trades na tela do que divergências reais** (`6` a `9` entradas num mesmo pregão, muitas contra o movimento estrutural).
   - **Conclusão prática:** A absorção na Wall é uma tese excelente, mas **não pode ser operada indiscriminadamente** em todo toque de nível — ela exige filtros fortes de contexto, exaustão e microestrutura (que serão desenvolvidos em fase própria, inclusive no `M1`).

2. **Sincronia 1:1 entre o Olho Humano e o Sinal (`1 Divergência na Wall = 1 Trade`):**
   - Ao restringir o gatilho exclusivamente às **Divergências Estruturais de Topo e Fundo (`F1 ➔ F2` na compra e `T1 ➔ T2` na venda)** entre o **Preço** e a **Onda de Fluxo Smart Money**, ancoradas sobre uma `MagicWall` ou `MidWall` GEX, o ruído desapareceu:
   - A taxa de acerto saltou para **`74,2%` no WIN** e **`67,8%` no WDO** (**`70,0%` combinado**), com média enxuta de **`1,8` operação por dia** somando os dois ativos.

3. **Sobreposição Permitida > Trava Artificial de 1 Posição:**
   - Como o Lote 2 do `WIN` busca alvo longo (`750 pts`) já protegido no Breakeven (`+20 pts` após andar `+180 pts`), bloquear novas divergências legítimas na Wall enquanto o runner ainda estava aberto escondia sinais válidos e reduzia o resultado. Permitir **sobreposição causal** aumentou a consistência e alinhou perfeitamente o gráfico (`cada divergência válida na Wall gera sua operação correspondente`).

4. **Filtros de Horário Institucional eliminam os dois piores focos de violinada da B3:**
   - **No `WDO`: pular `11:00–11:55`** (choque da abertura de NY à vista + formação da janela PTAX, onde o dólar rompe níveis técnicos por fluxo cambial exógeno).
   - **No `WIN`: pular `12:00–12:55`** (buraco de liquidez do almoço, onde falsos rompimentos de fundo/topo ocorrem com book raso) e encerrar novas entradas após `16:45`.

5. **Meta Diária Causal protege o capital ganho na manhã/início da tarde:**
   - Parar de abrir novas entradas no ativo assim que os trades **já encerrados** (`exit_time <= barra_atual`, 100% causal sem *look-ahead*) atingem **`+R$ 180` no WIN (2 contratos)** ou **`+R$ 120` no WDO (1 contrato)** cortou a devolução de fim de pregão, reduzindo o Drawdown Máximo combinado para apenas **`R$ 380`** em 11 meses (**`Ret/DD = 33,76x`** e **`11/11` meses positivos**).

---

## 3. Motor `"Fluxo Smart Money"` e Regra Exata da Divergência

### 3.1. Construção da Onda Azul (`smartSwingWave`)
Diferente do CVD acumulado puro (que sofre deriva direcional desde as `09:00` e impede comparar topos/fundos da tarde), o indicador **`2. FLUXO SMART MONEY`** calcula um oscilador de onda sem deriva (`EMA_3 - EMA_10` do esforço efetivo acumulado) alimentado por **3 motores institucionais** extraídos do Profit 4-Players:

1. **Absorção Oculta Wyckoff na Pedra (`wyckoffAbs`):** mede o esforço de agressão total versus o deslocamento líquido da barra M5 combinado ao saldo passivo institucional (`inst_pass_delta`). Se o mercado agride venda pesada na Wall, mas o candle não desloca para baixo (ou fecha defendendo) porque o institucional absorveu na pedra, a força resultante é compradora.
2. **Urgência e Porte de Lote Institucional (`lotUrgency`):** pondera a agressão institucional (`inst_aggr_delta`) pelo porte médio da boleta institucional frente ao varejo.
3. **Saldo Não-Varejo (`smartInst`):** soma a atuação direcional institucional (`Agressor + Passivo`) descontando a armadilha do varejo (`ret_delta_bar`), isolando o giro neutro de `HFT` e `RLP`.

### 3.2. Detecção Causal de `F1 ➔ F2` (Compra) e `T1 ➔ T2` (Venda) na Wall
Em cada barra M5 fechada $i$ (distância entre pivôs de `3` a `16` barras M5, *cooldown* mínimo de `6` barras entre divergências da mesma direção):

- **Divergência Compradora de Fundo (`BULL_DIV` — `F1 ➔ F2`):**
  1. **Preço faz fundo menor ou fundo duplo:** mínima atual $L_2 \le L_1 + \text{tol}$ (com tolerância de `45 pts` no WIN / `1,5 pt` no WDO e extensão máxima de `550 pts` WIN / `18 pts` WDO).
  2. **Onda Smart Money faz fundo mais alto (`Higher Low`):** vale da onda em $F_2$ sobe ao menos `+1.500` lotes equivalentes no WIN (`+180` no WDO) ou `18%` acima do vale $F_1$ (ou vira de negativo em $F_1$ para positivo em $F_2$).
  3. **Exaustão vendedora / defesa:** volume vendedor menor que em $F_1$ (`< 90%`) ou absorção Wyckoff compradora ativa.
  4. **Ancoragem na Wall GEX:** o fundo $L_2$ (ou fechamento) ocorre a até **`130 pts` no WIN** ou **`4,5 pts` no WDO** de uma `MagicWall` ou `MidWall` oficial do dia.
  5. **Gatilho de confirmação (`0` a `2` barras após o pivô):** barra fecha confirmando rejeição/fluxo a favor antes da entrada.

- **Divergência Vendedora de Topo (`BEAR_DIV` — `T1 ➔ T2`):**
  - Simétrica: máxima $H_2 \ge H_1 - \text{tol}$ na região da `Wall`/`MidWall`, enquanto a **Onda Smart Money faz topo mais baixo (`Lower High`)** com exaustão compradora e confirmação de fluxo vendedor.

### 3.3. Fórmula Unificada da Janela de Fluxo Smart Money (`V5b` · `WIN` e `WDO` na `5174`)
Para unificar a física de fluxo entre `5176` e `5174` sem usar preço (`0% Preço`) e sem *overfitting* por ativo, a mesma fórmula estrutural de **Janela de Fluxo Smart Money (`V5b`)** governa as janelas compradoras/vendedoras (`window_dir` / `flow_hist`) tanto no **Índice (`WIN`)** quanto no **Dólar (`WDO`)** em [`research/flow_window_asg/flow_filters.py`](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/research/flow_window_asg/flow_filters.py) e [`core/gex_live_dealer_engine.py`](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/core/gex_live_dealer_engine.py):

- **3 Motores Físicos da Fita (`0% Preço`):**
  $$\text{bar\_force} = 0{,}12 \cdot \phi_{\text{wyckoff}} + 0{,}18 \cdot \phi_{\text{porte}} + 0{,}70 \cdot \bigl(0{,}90 \cdot \text{inst\_aggr} + 0{,}75 \cdot \text{inst\_pass} - 0{,}25 \cdot \text{ret\_delta}\bigr)$$
- **Memória Estrutural (`EMA 4 / 20`):**
  $$\text{smart\_wave} = 0{,}92 \cdot \bigl(\text{EMA}_4(\text{cum\_eff}) - \text{EMA}_{20}(\text{cum\_eff})\bigr) + 0{,}08 \cdot \text{impulso}_{3\text{b}}$$
- **Histerese de Janela:** escala adaptativa `EMA 7` do passo de fluxo e trava de virada `flip_thr = ±11,0` (`4,22` viradas/dia no `WIN` e `4,59` viradas/dia no `WDO`).

| Ativo (212 Pregões Auditados) | Antigo `A.S.G` (`85% CVD Agr + 15% Preço`) | **Smart Money Unificado (`V5b` · `0% Preço`)** | Evolução de Robustez |
| :--- | :---: | :---: | :--- |
| **🇧🇷 `TOP 5 WIN` (`5174`)** | `+R$ 16.058` · `DD -R$ 1.360` · `Ret/DD 11,81x` · `11/11 M+` | **`+R$ 16.579` · `DD -R$ 1.083` · `Ret/DD 15,31x` · `11/11 M+`** | **`+R$ 521` lucro / `-20,4%` de Drawdown** |
| **💵 `TOP 3 WDO` (`5174`)** | `+R$ 16.988` · `DD -R$ 1.155` · `Ret/DD 14,71x` · `9/11 M+` | **`+R$ 15.730` · `DD -R$ 1.240` · `Ret/DD 12,69x` · `10/11 M+`** | **Sobe de `9/11` para `10/11` meses positivos (`WDO_07 Ret/DD 9,93x`)** |
| **🏆 Carteira `TOP 8` (`5174`)** | `3.005 tr` · `PF 1,39` · `+R$ 33.046` · `11/11 M+` | **`3.048 tr` · `PF 1,38` · `+R$ 32.309` · `Ret/DD 19,70x` · `11/11 M+`** | **100% guiada por fluxo institucional puro nos 2 ativos** |

---

## 4. Regras Operacionais e Resultados Auditados (Modo Base: `2c WIN + 1c WDO`)

Auditoria completa em **212 pregões (`02/01/2026` a `06/11/2026`)**, líquida de custos operacionais B3 (**`R$ 2,00`/contrato no WIN** e **`R$ 5,00`/contrato no WDO**):

### 4.1. Configuração Exata de Execução e Gestão de Risco

| Parâmetro | 🇧🇷 `WIN_DIV_WALL` (`WIN Sniper · 2c Mix`) | 💵 `WDO_DIV_WALL` (`WDO Sniper · 1c MidWall`) |
| :--- | :--- | :--- |
| **Lote Base** | **2 mini-contratos** (`Lote 1` parcial + `Lote 2` runner) | **1 mini-contrato** |
| **Janela de Horário** | **`09:05` às `16:45`**, **pulando `12:00–12:55`** (almoço) | **`09:00` às `17:00`**, **pulando `11:00–11:55`** (NY / PTAX) |
| **Meta Diária Causal (Gain Cap)** | Bloqueia novas entradas no dia ao atingir **`>= +R$ 180`** realizados | Bloqueia novas entradas no dia ao atingir **`>= +R$ 120`** realizados |
| **Sobreposição** | Permitida (toda divergência válida na Wall dentro do horário e antes da meta opera) | Permitida (toda divergência válida na Wall dentro do horário e antes da meta opera) |
| **Alvo (`Take Profit`)** | **Lote 1:** Banda Oposta Dinâmica do Envelope **`NWE30`** ($L=30, bw=3{,}0, mult=1{,}6$)<br/>**Lote 2:** Alvo estrutural fixo de **`750 pts`** | **Lote Único:** Próxima **`MidWall` / `Wall` GEX** estrutural na direção do trade (mín. `5,5p`, teto `14,0p`) |
| **Stop Loss Inicial** | Atrás da estrutura/Wall (`240` a `260 pts`) | Atrás da Wall defendida (`~9,5` a `10,5 pts`) |
| **Proteção de Breakeven (`BE`)** | Ao andar **`+180 pts`** a favor (ou tocar `TP1`), trava stop em **`+20 pts`** | Escudo na metade do caminho até a `MidWall` (`+3,5p ➔ +1,0p`) |
| **Time-Stop / Encerramento** | Máx. `24` barras M5 (`120 min`) ou fechamento intradiário | Máx. `24` barras M5 (`120 min`) ou fechamento intradiário |

### 4.2. Desempenho Histórico Auditado (Jan–Nov/2026 · 212 Pregões)

| Estratégia / Carteira | Contratos | Trades (`ops/dia`) | Assertividade (`WR`) | Profit Factor (`PF`) | Lucro Líquido (pós-custos) | Drawdown Máx (`MDD`) | Relação `Ret/DD` | Meses Positivos |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`WIN_DIV_WALL`** | `2 ct WIN` | `128` (`0,6/d`) | **`74,2%`** | **`2,71`** | **`+R$ 5.662`** | `-R$ 360` | **`15,73x`** | `10 / 11` |
| **`WDO_DIV_WALL`** | `1 ct WDO` | `245` (`1,2/d`) | **`67,8%`** | **`2,36`** | **`+R$ 7.165`** | `-R$ 345` | **`20,77x`** | `10 / 11` |
| **🏆 `PORTFOLIO_DIV_OPT2` (Total)** | **`2c WIN + 1c WDO`** | **`373` (`1,8/d`)** | **`70,0%`** | **`2,49`** | **`+R$ 12.827`** | **`-R$ 380`** | **`33,76x`** | **`11 / 11` (`100%`)** |

---

## 5. Identidade Visual Minimalista do Painel `5176`

O painel da porta `5176` foi redesenhado para eliminar toda poluição visual (sem legendas escritas sobre as Walls, sem modos Cabo de Guerra/Oscilador expostos e sem barras coloridas redundantes):

1. **Abertura Padrão na `Visão Dupla` (`WIN + WDO` juntos):**
   - Ao abrir `http://localhost:5176`, o Cockpit já carrega o **Cartão Combinado do Dia (`WIN + WDO`)** seguido dos gráficos completos de **Índice (`WIN`)** e **Dólar (`WDO`)** na mesma tela, permitindo acompanhar a carteira inteira sem trocar de aba.
2. **Painel 1 — Preço Monocromático (Foco Total no Gatilho e no Risco/Retorno):**
   - **`Walls` principais em branco (`#f1f5f9`)** e **`MidWalls` tracejadas em cinza (`#8b9bb0`)**, com apenas a etiqueta limpa de preço na escala direita.
   - **Candles M5 neutros** em cinza/prata institucional (`#cbd5e1` barra de alta e `#475569` barra de baixa) + envelope `NWE30` sutil em cinza (`#94a3b8`).
   - **Uso exclusivo de cor viva (`#00e87a` verde e `#ff3860` vermelho):** aparece **unicamente** nos **conectores/pílulas de Divergência na Wall** (`🟢 DIV. COMPRA NA WALL · Fluxo ↑`, `🔴 DIV. VENDA NA WALL · Fluxo ↓`, ou amarelo `⏳ Aguard. Gatilho` quando uma divergência acabou de se formar nas últimas 2 barras) e nas **caixas de projeção de `TP / SL` dos trades**.
   - **Sincronia Visual 1:1:** divergências fora de Wall, fora do horário operacional, sem gatilho confirmado ou após a Meta Diária atingida são ocultadas na `5176`, garantindo que **toda divergência plotada corresponde a uma operação real (ou a um gatilho ao vivo iminente)**.
3. **Painel 2 — `2. FLUXO SMART MONEY`:**
   - Exibe **apenas a linha azul contínua (`#00d4ff`)** sobre a linha `ZERO` tracejada, acompanhada exclusivamente dos segmentos de divergência **`F1➔F2 ↗`** (verde) e **`T1➔T2 ↘`** (vermelho) conectados verticalmente ao gráfico de preço.
4. **Painel Lateral de Capital Retrátil (`Wide Mode` para `WIN` e `WDO`):**
   - Na `5176`, a coluna lateral direita (`CAPITAL DAS OPERAÇÕES DO DIA` + `HUD`) inicia **recuada por padrão** em uma guia vertical compacta de `44px` na borda direita (exibindo o saldo líquido do dia em R\$, pontos, placar `✅/❌` e atalho `📋`), fazendo com que o gráfico de **Preço + `2. FLUXO SMART MONEY`** ocupe praticamente **100% da largura da tela (`width = 1240`)** tanto no **Índice (`WIN`)** quanto no **Dólar (`WDO`)**.
   - Pode ser expandida ou recuada a qualquer momento com 1 clique na guia vertical direita (`◀ Expandir Capital`), no botão `💰 ... ◀ Capital / Recuar ▶` na barra superior do gráfico ou no botão `Recuar ▶` dentro do próprio card `CAPITAL DAS OPERAÇÕES DO DIA`.
5. **Escalas Variáveis e Navegação Interativa estilo TradingView (`Preço` + `Fluxo Smart Money`):**
   - **Auto-ajuste dinâmico (`Auto` / botão `A`) por barras visíveis** independente no **Painel 1 (Preço)** e no **Painel 2 (`2. FLUXO SMART MONEY`)** — a onda azul não fica mais presa simetricamente ao zero, aproveitando toda a altura útil do painel.
   - **Esticar/Comprimir cada Escala Y:** arraste verticalmente (ou gire a roda do mouse) sobre a escala direita do **Preço** ou sobre a escala direita do **Fluxo Smart Money** de forma independente.
   - **Pan 2D Livre (Horizontal + Vertical):** ao destravar o botão **`A`** (ou segurando `Shift` / após ajustar a escala Y), arrastar dentro do gráfico move livremente no tempo e na vertical; clique em **`A`** ou dê **duplo-clique na escala** para voltar ao modo automático.
   - **Divisória Redimensionável (`Splitter ↕`):** arraste a barra central entre o Preço e o `2. FLUXO SMART MONEY` para aumentar ou diminuir a altura de cada janela ao vivo, além de zoom horizontal ancorado no cursor com a roda do mouse (após clicar no gráfico ou sobre o eixo de tempo).
6. **Aba `3. STAT-ARB & Z-SCORE` mantida 100% preservada** na barra superior.

---

## 6. Mapa Técnico dos Arquivos do Painel `5176`

| Arquivo | Função Técnica no Operacional `5176` |
| :--- | :--- |
| [`core/gex_live_dealer_engine.py`](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/core/gex_live_dealer_engine.py) | Calcula a onda `smart_swing_wave`, detecta causalmente as divergências `_detect_causal_visual_swing_divs()`, gera os sinais ao vivo `_append_live_unified_divergence_signals()` (`WIN_DIV_WALL` e `WDO_DIV_WALL` com filtro de horário + meta diária causal) e atualiza os `live_days` (`sniper_v2`). |
| [`research/flow_window_asg/inject_unified_div_opt2.py`](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/research/flow_window_asg/inject_unified_div_opt2.py) | Script oficial que audita os 212 pregões e injeta aditivamente `WIN_DIV_WALL`, `WDO_DIV_WALL` e `PORTFOLIO_DIV_OPT2` no JSON de curvas históricas sem tocar nas 8 estratégias MT5 da `5174`. |
| [`data/processed/portfolio_4_sistematicas_equity_v1.json`](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/data/processed/portfolio_4_sistematicas_equity_v1.json) | Base auditada de curvas de capital, métricas de `Ret/DD`, lucros mensais e histórico diário consumida tanto pela `5174` quanto pela `5176`. |
| [`regime-dashboard/src/components/IntradayCompassPanel.jsx`](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/regime-dashboard/src/components/IntradayCompassPanel.jsx) | Renderiza o Cockpit da `5176` (`Visão Dupla` padrão, gráfico monocromático, `2. FLUXO SMART MONEY`, sincronia 1:1 de divergências e painel da carteira Sniper). |
| [`regime-dashboard/src/components/LiveTradingCalendar.jsx`](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/regime-dashboard/src/components/LiveTradingCalendar.jsx) | Calendário financeiro mensal/diário sincronizado na `5176` para consolidar os resultados de `WIN_DIV_WALL` (2c) + `WDO_DIV_WALL` (1c). |
| [`keep_dashboards_alive.py`](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/keep_dashboards_alive.py) | Watchdog de sistema operacional que mantém `8080`, `5174` e `5176` ativos em dual-stack (`--host ::`). |

---

## 7. Próximos Passos do Projeto — Novas Estratégias de Fluxo (Absorção Filtrada & `M1`)

O Sniper de Divergência `F1➔F2 / T1➔T2` na Wall provou que **menos operações com filtragem institucional rigorosa superam largamente setups de alta frequência sem filtro**. A partir dessa base consolidada, as próximas fases de pesquisa e evolução do painel `5176` seguirão duas frentes principais:

### Fase A — Estratégia de Absorção na Wall com Alta Seletividade (Multi-Filtro)
A ideia central de operar **Absorção Institucional na Wall** permanece altamente promissora, desde que deixe de operar de forma indiscriminada em qualquer toque e passe a exigir **confluência estrita**:
1. **Assimetria Extrema de Esforço × Resultado (Wyckoff Puro):** exigir volume agressor contrário acima de percentil elevado (ex.: top `15%` da sessão) batendo exatamente na zona da Wall enquanto o corpo/fechamento da barra trava (deslocamento líquido próximo de zero ou pavio de rejeição dominante).
2. **Defesa Institucional Passiva Real vs. Varejo Preso:** confirmar saldo positivo relevante de `inst_pass_delta` (absorção na pedra por corretoras institucionais) simultâneo à agressão do varejo do lado errado (`ret_delta` oposto), descartando barras dominadas apenas por giro de `HFT`.
3. **Filtro de Regime GEX e "Frescor" da Wall:** diferenciar **1º/2º teste** de uma `MagicWall` em regime **`Gamma Positivo`** (onde os Market Makers defendem junto com o institucional passivo) de paredes já exauridas/testadas repetidas vezes ou em regime de *Squeeze* (`Gamma Negativo`).
4. **Governança Operacional Já Comprovada:** aplicar desde o nascimento da estratégia os filtros de horário (`sem 11h no WDO` e `sem 12h no WIN`) e trava de Meta Diária / limite de tentativas por Wall.

### Fase B — Descer para o Timeframe `M1` (Microestrutura Fina & Stops Curtos)
Expandir o laboratório de pesquisa para dados de **1 minuto (`M1`)** combinados às Walls GEX diárias e ao fluxo de corretoras do Profit:
1. **Ancoragem Macro (`Walls GEX` + `M5`) com Gatilho Fino no `M1`:** usar o toque na `MagicWall`/`MidWall` como zona de alerta e exigir no **`M1`** o padrão microestrutural exato de virada (absorção pesada seguida da primeira barra `M1` de ignição institucional a favor, ou micro-divergência `F1➔F2` dentro de `3` a `8` minutos).
2. **Captura de Violinadas Rápidas (*Spring / Upthrust* na Wall em `M1`):** detectar em `1` a `3` barras de `M1` o rompimento falso da Wall que estopa o varejo com exaustão imediata de agressão e retomada para dentro do nível — movimento que muitas vezes já andou `150–250 pts` no `WIN` (`4–6 pts` no `WDO`) se esperarmos o fechamento de uma vela inteira de `M5`.
3. **Melhora Drástica de Assimetria `Risco : Retorno`:** entrar pelo `M1` colado na defesa institucional permite trabalhar com stops técnicos muito mais curtos atrás da mínima/máxima da absorção real, elevando o `Profit Factor` e a relação `Retorno / Drawdown` de novos setups complementares ao Sniper M5.
