# PLANO MESTRE — Divergências no modelo e setups operáveis (11/11/2026)

Status: **somente planejamento**. Nada foi rodado em backtest/otimização. Único código novo: `research/div_master/inspect_today.py`
(inspeção read-only do pregão de hoje via `GET http://localhost:8080/api/compass/etapa2` + Walls do dia).

Motivo: as 7 frentes de hoje (`div_gate`, `div_entry`, `audit_5176`, `sniper2`, `sniper_add`, `sniper_direct`, `div3m`) otimizaram
setups **em cima de detectores que não marcam as divergências que o usuário vê**. Antes de qualquer otimização, este plano
(0) cria uma ferramenta de rotulagem fácil para o usuário, (1) inventaria os detectores, (2) mede o que eles marcaram hoje contra o gabarito do usuário, (3) define a taxonomia de
divergências, (4) define contexto na Wall, (5) cataloga setups e (6) fixa um protocolo de validação que começa por rotulagem manual.

Referência visual: print do painel 5176 enviado pelo usuário em 11/11 (WIN M5; painel de cima = preço + Walls + NWE; painel de
baixo = "Fluxo Smart Money"). Destino previsto: `research/div_master/ref_20261111.jpg` — **o arquivo não foi encontrado no box no
momento da cópia; copiar manualmente** quando disponível. A definição operacional do usuário é: **divergência = preço × curva
"Fluxo Smart Money" (`smart_swing_wave`) do painel 5176**, lida no contexto da Wall.

---

## 1. Inventário — o que já existe no código

### 1.1 Detectores de divergência (preço × onda smart money)
| # | Detector | Arquivo / função | TF | Dados | Como define | Limitações encontradas |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| A | Divergência do motor (HUD/3 motores) | `core/gex_live_dealer_engine.py` L1795-1915 (campo `swing_divergence`, BULL_DIV/BEAR_DIV) | M5 | barras do motor ao vivo (`m5_enriched`) | fundo local (≤ 2 barras anteriores **e ≤ barra seguinte**), pavio/fechamento a favor, força/onda a favor; F1 = 1º pivô para trás em até 16 barras; onda(F2) > onda(F1) + 1.800 (WIN) / 320 (WDO); ext ≤ 360 / 8,5; `price_tol` 40 / 1,0 | **lê a barra i+1** (`m5_enriched[i_e + 1]`) → barra do futuro; **repinta** (apaga a divergência anterior se surgir fundo mais baixo em ≤ 6 barras); `near_wall` só informativo; **nunca foi backtestado** como sinal |
| B | Sniper 5176 "visual" | `research/flow_window_asg/inject_unified_div_opt2.py` `detect_visual_swing_divergences` L110; cópia ao vivo `gex_live_dealer_engine._detect_causal_visual_swing_divs` L3202; cópia no front `regime-dashboard/src/components/IntradayCompassPanel.jsx` L625-855 | M5 | cache externo `C:\Users\ryzen\.gemini\...\cached_214_{WIN,WDO}.json` (fora do repo) ou `build_profit_session_payload` | F1 = **fundo mais baixo** (não o de fluxo mais fraco) entre i-16 e i-3; onda mínima de 3 barras > onda(F1) + max(1.500, 18%) (WIN) / max(180, 18%) (WDO) ou troca de sinal; exaustão de volume/lote; cooldown 6 | `near_wall` calculado (raio 130 / 3) **mas não filtra** (29% fora da Wall, `audit_5176`); filtro ao vivo `(pos_in-3) <= si <= pos_in` inclui a barra da entrada (barra do futuro); **no 5176 a linha só é desenhada se houver trade de setup até 3 barras depois** (L763) — o painel não mostra todas as divergências; barra de abertura nunca é F1 (j ≥ 1 e exige pivô) |
| C | 3 motores | `inject_unified_div_opt2.py` L226-283; ao vivo `check_bar_3motor` L3368 | M5 | idem B | OR de condições de força/Wyckoff/impulso | aprova 99-100% das divergências (`sniper_direct`, `div3m`) → não filtra nada |
| D | div_wall v1 | `core/div_wall_signal.py` `detect_signals` L245 | M5/M1 | `.min` Profit via `research/div_wall/build_dataset*.py` (dataset congelado com hash) | pivôs L2/R1; F1 = pivô mais extremo 3-20 barras; ext ≤ 400 / 10; onda(F2)-onda(F1) > k × mediana causal de \|onda\|; Wall ≤ R | F1-F2 limitado a 20 barras; onda no pivô = pior valor de (j-1, j) — mata divergências quando a barra anterior ao fundo teve onda baixa |
| E | divergência v2 | `core/div_wall_signal.py` `detect_divergences_v2` L353 | M5 | idem D | F1 = pivô de **onda mínima do pregão inteiro**; sem limite de distância/extensão; "perto" da Wall ou "furou e voltou"; PIVO / FECHA_WALL | sem cooldown → repete sinais (hoje 8 vendas com o mesmo F1 10:25); F1 fica "preso" no pico de fluxo do dia → qualquer topo posterior vira divergência; confirmação "furou" chega tarde (até 12 barras) |
| F | Spring/upthrust | `core/div_wall_signal.py` `detect_springs` L455 | M1 (desenhado) | `div_wall_m1_v1` | furo da Wall entre `pierce_min` e `pierce_max` e fechamento de volta | não é divergência; sem leitura de rompimento real (furo > `pierce_max` é ignorado) |
| G | Divergência de 1 barra (front) | `IntradayCompassPanel.jsx` L545-596 (BULL_DIV/BEAR_DIV/FOMO/SWEEP por barra) | M5 | payload do motor | delta/inst/varejo/Wyckoff da barra contra o preço | só no front; **oculta no modo 5176** (L692-697) |

### 1.2 A curva "Fluxo Smart Money" (o que o usuário olha)
- Fórmula única em 3 lugares: `core/div_wall_signal.py` `compute_flow` L79, `inject_unified_div_opt2.compute_causal_3motor_bars` L47,
  motor `gex_live_dealer_engine.py` L1745-1792 (`smart_swing_wave`). Hoje os três dão o mesmo valor (conferido barra a barra no WIN).
- `força = 0,45·Wyckoff + 0,25·porte + 0,30·institucional`; `onda = 0,55·(EMA2 − EMA10 do acumulado) + 0,45·impulso de 3 barras`.
- **Atenção:** o termo Wyckoff (45%) é volume × forma do candle (posição do fechamento e pavios). Parte da "onda" é price action
  do próprio candle — a divergência preço × onda é parcialmente preço × preço. Isso não invalida a leitura do usuário, mas explica por
  que trocar a onda por CVD não mudou nada em `div_wall` e precisa ser medido (seção 3, D1 vs D2).

### 1.3 Fluxo, players e absorção
| Medida | Onde | O que mede | Dados / disponibilidade |
| :-- | :-- | :-- | :-- |
| Decomposição inst/varejo do `.min` | `core/profit_min_decomp.py` `decompose_min_bars`; `core/profit_wall_players_engine.py` `_build_from_profit_min_m1_m5` L780 | `inst_aggr`, `inst_pass`, `ret_delta` | **sintético**: pesos por lote médio e fração passiva por pavio. Não é split real por corretora. Histórico 2026 completo (M1/M5) |
| Players reais | `profit_wall_players_engine._build_from_profit_trd` L441, `classify_wall_player_signature` L283 (absorção inst, sweep, armadilha varejo/RLP, giro HFT) | assinatura dos 4 players na Wall | real só com `.trd` (Times & Trades). No disco há poucos dias (ex.: `WINZ26 ... 20261109.trd`, `20261110.trd`); o resto é sintético |
| Absorção por janela | `core/profit_mt5_flow_engine.py` `compute_window_metrics` L733 | delta ≥ 10% do volume com preço parado (≤ 2 ticks) = ABSORCAO; preço andando + inst a favor = AGRESSAO | ao vivo (ticks); sem histórico gravado (hipótese — verificar) |
| Status da Wall | `profit_mt5_flow_engine.analyze_nearby_walls` L816 | ABSORCAO / ROMPIMENTO / DISPUTA na zona, janela 5 min | ao vivo |
| Score composto | `profit_mt5_flow_engine.compute_composite_flow_score` L889 | inst 45% + agressão 30% + absorção 25%; `div_bonus` = inst × varejo em 15 min | ao vivo |
| Eventos da Wall | `gex_live_dealer_engine.py` L480-597 | DEFENDEU / VIOLINADA ("Absorveu") / ROMPEU / VIROU por Wall, com pavio, `inst_delta_bar`, `cvd_inst` 15 min; `live_verdict` | função pura das barras M5 → **recomputável no histórico** (bom candidato a rotulador de contexto) |
| Dealer / GEX | `gex_live_dealer_engine.AssetGexCurveModel` (`evaluate_local_gex` L152, `compute_dealer_hedge_flow` L210, `get_dominant_gamma_magnets` L256); campos `dealer_hedge_bar`, `cum_dealer_hedge`, `gex_magnet_*` | hedge esperado do dealer por barra | modelado a partir das Walls D-1 |
| Walls | `mt5/Files/jumba_gex_{win,wdo}_history.csv` (221/217 sessões), `..._daily.csv`, `gex/data/b3_gex_history_2026.csv` (flip/min/max) | Wall/MidWall Black-76, D-1 OI | histórico 2026 completo |
| NWE | `core/div_wall_signal.nwe_series` L47 (100/8/3), `core/signals.calc_nwe_with_bands`; `nwe30_*` no payload | envelope causal | completo |
| Opções | `core/options_live_radar_engine.py` | fluxo de opções BOVA11 | só ao vivo (hipótese) |
| WIN × WDO | `core/kalman_filter.py`, `core/signals.calc_zscore` | spread/z-score | MT5 M5 completo |

---

## 2. Diagnóstico de 11/11 (WIN M5) — gabarito do usuário × detectores

**Decisões do usuário (11/11, 14:35):** horários/preços dos 4 eventos confirmados; F1 do evento 1 = barra de abertura 09:00;
rompimento vale após o reteste (**entrada 10:10**, aceitação), não no 1º fechamento das 09:55; "na Wall" = até **150 pts no WIN**;
**MidWall conta como Wall**; divergência = **só preço × onda Smart Money** (CVD, inst × varejo, WDO etc. viram variações
secundárias/controles); entradas: testar as 3 (fechamento da barra de sinal, rompimento da barra de sinal, limite na Wall); alvo
inicial: próxima Wall/MidWall, centro da NWE ou banda da NWE. Ferramenta de rotulagem aprovada e implementada (seção 6.1).

Dados disponíveis: **sim**. 64 barras M5 do motor (09:00-14:15, 63 fechadas), M1 em `/api/compass/m1_series` (565 barras; última
marcada 18:24 às 14:17 — conferir), `.min` M5 `WINZ26` atualizado às 11:30 (intraday parcial), Walls do dia em
`mt5/Files/jumba_gex_win_daily.csv` (ref OI 10/11). Walls na faixa: Wall 172.891 · MidWall 173.397 · **Wall 173.902** ·
**MidWall 174.408** · **Wall 174.913**. Saída completa: `python research/div_master/inspect_today.py WIN`.

### 2.1 Os 4 eventos do print localizados nos dados
| # | Evento do usuário | Nos dados | Wall | Depois (descritivo, não é BT) |
| :-- | :-- | :-- | :-- | :-- |
| 1 | COMPRA 09:00-09:15: fundo descendente na Wall de baixo, SM subindo | fundos 09:00 **173.370** (onda −42.285) → 09:15 173.380 (−32.651) → 09:25 173.310 (−16.333) → 09:35 **173.300** (−23.222) | MidWall 173.397 (furou ~90-97 e voltou) | máxima 174.750 às 10:45 |
| 2 | ROMPIMENTO 09:50-10:05 da Wall do meio com SM a favor (entrada do usuário: **10:10**, após o reteste) | 09:50 máx 173.925 / fecha 173.835; **09:55 1º fechamento acima (173.950)**; 10:05 reteste mín 173.600 fecha 173.870 (abaixo); **10:10 fecha 174.145**; onda 16.928 → 49.304 → 85.768; 10:20 rompe também MidWall 174.408 (fecha 174.535) | Wall 173.902 | sem volta abaixo de 173.902 até 11:30 |
| 3 | VENDA 11:00-11:50: topo plano na Wall de cima, SM caindo | topos 10:45 174.750 (36.091) · 11:10 174.685 (22.766) · **11:25 174.765 (3.050)** · 11:40 174.670 (12.971) | Wall 174.913 a −150/−230 (não tocou); MidWall 174.408 abaixo | 11:30 mín 173.960 (−800 do topo), depois volta |
| 4 | VENDA 12:05-12:25: topo mais alto testando a Wall de cima, SM não confirma | 12:00 174.815 (43.796) → **12:20 174.850 (35.226)** | Wall 174.913 a −63 (rejeição sem tocar) | 13:20 mín 174.085 |

Obs.: no evento 4 a onda vinha subindo desde 11:25 (3.050 → 43.796); a "não confirmação" é T1 12:00 → T2 12:20.

### 2.2 O que cada detector marcou hoje
| # | A motor (`swing_divergence`) | B Sniper 5176 | D v1 | E v2 (k 0,5-1,5) | F spring (M5) | Setups do dia |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| 1 COMPRA | **sim** 09:15→09:35, near_wall, "absorção Wyckoff" | **não** | não | não | COMPRA 09:15 (MidWall 173.397) | EST_04 **VENDEU** 09:35 @173.400 → stop −250 |
| 2 ROMPIMENTO | não existe detector | não existe | não | não | **VENDA** 09:50 (upthrust na 173.902 — direção errada) | nenhum (EST_07 Ignição não disparou) |
| 3 VENDA | **sim** 10:25→10:45 e 11:10→11:25 | **sim** 10:40 e 11:25, mas `near_wall=False` (raio 130; Wall a 148-193) | não | sim, só às **11:30** ("furou 174.408"), 3 vezes, F1 = 10:25 | não | EST_01/EST_16 **COMPRARAM** 11:10/11:30 @174.410 → stops |
| 4 VENDA | **sim** 12:00→12:20 | **não** | não | **sim** 12:05 / 12:25 ("perto 174.913") | não | — |

Resumo: **o detector que bate com o olho do usuário é o A (motor), 4 de 4 nas reversões (1, 3, 4)** — e é justamente o único que
nunca foi testado (e tem barra do futuro + repintura). O B (base de toda a pesquisa do Sniper) pegou 1 de 3; v1 0 de 3; v2 2 de 3
(um atrasado). Nenhum detector existe para o evento 2 (rompimento com fluxo a favor). No painel 5176 o B só desenha divergência
quando há trade de setup em até 3 barras — hoje os setups foram **contra** as divergências, então o painel não mostrou nenhuma.

### 2.3 Por que falharam (causas objetivas)
- **Evento 1 / B, D, E:** o F1 do usuário é a **barra de abertura 09:00** (173.370, onda −42.285). Os detectores exigem pivô com 2
  barras à esquerda ou j ≥ 1 → 09:00 nunca é F1. Com F1 = 09:15, a onda do F2 é medida como o **pior valor de (j-1, j)**
  (09:35 → min(−23.222, −32.583) = −32.583 ≈ −32.651 do F1): diferença de 68, abaixo de qualquer limiar. F2 09:25 está a 2 barras
  de 09:15 (< `min_dist` 3).
- **Evento 3 / B:** marcou, mas raio de Wall 130 → `near_wall=False`. Com a zona definida pelo usuário (150 pts), o topo de 11:25
  (174.765, a 148 da Wall 174.913) entra; os de 10:45 (163) e 11:10 (228) ficam fora — a rotulagem dirá qual F2 é o válido.
- **Evento 4 / B:** limiar de 18% × 43.796 = 7.883 e a onda máxima das 3 barras inclui 12:15 (45.892) → falha. A diferença real
  (43.796 → 35.226 = −8.570) é pequena perto do limiar relativo.
- **v2:** F1 sempre 10:25 (onda 113.718 = pico do dia) → marca qualquer topo depois; confirma tarde.
- **Rompimento:** não há definição de aceitação; o spring lê o furo como armadilha.

### 2.4 Alerta de dado ao vivo (hipótese a confirmar antes de rotular com dado do motor)
A partir de **10:05** os campos `inst_aggr_delta` / `inst_pass_delta` do WIN caem para perto de zero (09:00 = 54.248; 10:05 = 80;
10:10 = 336), enquanto `cvd_inst` continua variando. Hipótese: troca de fonte no meio do pregão (`.trd` de hoje não está no disco;
último é 20261110) → depois das 10h a onda ao vivo fica dominada pelo termo Wyckoff. **A curva do print pode não ser igual à
que o `.min` reconstrói depois do pregão.** Ação: comparar a onda ao vivo de hoje com a onda reconstruída do `.min` à noite.

WDO hoje (referência): A marcou 4, B 7, v1 1, v2 9 (com repetições). Sem gabarito do usuário no WDO.

---

## 3. Taxonomia — todas as formas computáveis de divergência
Notação: barra i fechada; sinal no fechamento de i, entrada na abertura de i+1. Pivô = extremo local confirmado com R barras à direita
(R ≥ 1 é atraso obrigatório). "Fluxo" X = série acumulada ou onda.

| Cód. | Tipo | Definição objetiva | Parâmetros | Dados | Disponível? |
| :-- | :-- | :-- | :-- | :-- | :-- |
| D1 | Preço × onda SM (regular) | F2 ≤ F1 + tol (compra) e onda(F2) − onda(F1) ≥ θ; venda simétrica | tol, θ (abs. ou × mediana \|onda\| ou × ATR da onda), distância F1-F2 [m, M], **F1 pode ser a 1ª barra**, valor da onda no pivô (no pivô / pior de 2 / melhor de 2) | `.min` M5/M1 | sim (2026 inteiro) |
| D2 | Preço × CVD total | idem com Σ(buy_vol − sell_vol) do dia | idem | `.min` (agressão real) | sim |
| D3 | Preço × CVD institucional | idem com Σ(inst_aggr + inst_pass) | idem | sintético `.min`; real só `.trd` | sim (proxy) |
| D4 | Institucional × varejo | em janela N: Δinst > a e Δvarejo < −b (ou sinal oposto) com preço parado/contra | N, a, b | idem D3 | proxy |
| D5 | Esforço × resultado (1 barra / janela curta) | \|delta\| ou volume ≥ pct p do dia/horário e \|Δpreço\| ≤ t ticks (absorção) | p, t, janela 1-3 barras | `.min` | sim |
| D6 | Preço × porte de lote | preço faz novo extremo e lote médio do agressor cai (ou do lado oposto sobe) | lookback | `.min` (buy_qty/buy_trd) | sim |
| D7 | Preço × dealer/GEX | preço anda contra o hedge esperado (`dealer_hedge_bar`) ou contra o ímã (`gex_magnet_wall`) | limiar de hedge | Walls D-1 + modelo | sim (modelado) |
| D8 | WIN × WDO | WIN faz novo fundo e WDO **não** faz nova máxima no mesmo intervalo (ou z do spread Kalman extremo) | janela, z | MT5 M5 dos dois | sim |
| D9 | Oculta (continuação) | compra: preço faz fundo **mais alto** e onda fundo **mais baixo** (pullback em tendência/pós-rompimento) | idem D1 | idem | sim — **não implementada** |
| D10 | Pivô × janela rolante | preço faz extremo de N barras e o fluxo não faz extremo de N barras (sem pivô) | N | idem | sim |
| D11 | Multi-timeframe | contexto/pivô em M5 + divergência D1/D2 em M1 dentro da barra de toque | TF par | `div_wall_m1_v1` (211/207 dias) | sim |
| D12 | Volume/exaustão | 2º teste com volume do agressor ≤ x × 1º teste (o `sell_exhausted` do A) | x | `.min` | sim |
| D13 | Na Wall × fora | modificador: F2 a ≤ R de Wall/MidWall, ou furou-e-voltou | R por ativo, tipos de nível | Walls | sim |
| D14 | Rompimento confirmado por fluxo (não-divergência, controle) | fechamento além da Wall com onda/CVD fazendo novo extremo junto | ver seção 4 | idem | sim |

Regra para todos: cada tipo vira **uma função causal** `detect_<tipo>(bars[:i+1], walls, params) -> sinais`, num único módulo,
com teste de paridade (lote = barra a barra) como `research/div_wall/parity_test.py`.

---

## 4. Contexto na Wall — definições objetivas
Zona: \|preço − W\| ≤ R, Wall **ou MidWall**. **WIN R = 150 (decisão do usuário)**; variação de controle {100, 200}.
WDO: R a definir (proposta inicial 3,0; controles {1,5, 4,5}). Lado de origem = média dos 3 fechamentos antes do 1º toque.
Rompimento (decisão do usuário): a entrada é na **aceitação após o reteste** (regra "b"), não no 1º fechamento além.

| Contexto | Definição | Combina com |
| :-- | :-- | :-- |
| **Rejeição** | toque na zona vindo de um lado e fechamento de volta do mesmo lado sem fechar além de W ± b em até N barras; pavio na direção da Wall ≥ w% (b WIN 20-40; N 1-3) | D1/D2/D5 regulares → reversão (eventos 3 e 4) |
| **Absorção** | na zona, barra(s) com volume/delta agressor contra ≥ pct p e progresso ≤ t ticks (D5); pode furar W até `pierce_max` e voltar (violinada) | D1 regular + D5 → reversão (evento 1) |
| **Rompimento / aceitação** | fechamento além de W ± b e (a) m barras seguintes sem fechar de volta, ou (b) reteste que fura no máx. r e fecha além. Com fluxo: onda/CVD em novo extremo no rompimento (D14) | D14 a favor = continuação; D9 oculta no reteste (evento 2) |
| **Falha de rompimento** | fechamento além e volta para dentro em ≤ N barras, com fluxo divergente no rompimento | D1 regular → fade |

Hoje a escolha de regra muda o rótulo: na 173.902 o reteste das 10:05 furou 302 e fechou abaixo (regra "a" = falha; regra "b" com r ≥ 302 = aceitação).
Por isso o contexto também passa pela rotulagem (fase 0).

---

## 5. Catálogo de setups candidatos (7 + controles)
Custos WIN 10 pts / WDO 0,5 pt + 1 tick de slippage em stop; 1 contrato; regras MT5 (stop antes do alvo, gap na abertura).

**Sinal principal de todos os setups: D1 (preço × onda Smart Money).** D2-D14 só entram como variação secundária ou controle.
**Entradas (as 3 testadas em todo setup):** E0 = abertura após o fechamento da barra de sinal · E1 = stop 1 tick além da
máxima/mínima da barra de sinal (vale 2 barras) · E2 = limite na Wall/MidWall (preço da Wall ± 1 tick, vale 3 barras).
**Alvos iniciais (os 3):** T1 próxima Wall/MidWall (front-run 15 / 0,5) · T2 centro da NWE · T3 banda oposta da NWE.
| Setup | Gatilho | Entrada | Stop | Alvo | Gestão | Ativo | Exemplo hoje |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| S1 Rejeição + Div | D1 regular com T2/F2 a ≤ 150 da Wall/MidWall + rejeição | E0 · E1 · E2 | além do pivô F2 + buffer (WIN 30, faixa 100-300; WDO 1, faixa 3-10) | T1 · T2 · T3 | BE em 1R; tempo 24-48 barras; fecha 17:25 | WIN, depois WDO | evento 4 (e 3 com R=250) |
| S2 Absorção + Div | D1 regular na zona + absorção (D5 como contexto; furo ≤ `pierce_max`) | E0 · E1 · E2 | além do extremo da absorção | T1 · T2 · T3 | BE 1R | WIN, WDO | evento 1 |
| S3 Rompimento + aceitação pós-reteste | rompimento com onda SM a favor, reteste da Wall rompida e fechamento de aceitação (hoje 10:10) | E0 · E1 · E2 (limite na Wall rompida) | W − R (WIN) | T1 (hoje 174.408 → 174.913) · T2 · T3 | BE 1R, trailing na Wall seguinte | WIN | evento 2 (reteste 10:05) |
| S4 Ignição com fluxo (controle do S3) | 1º fechamento além da Wall com onda em novo extremo do dia | E0 | dentro da Wall − R | próxima Wall | tempo curto (12 barras) | WIN | evento 2 (09:55 / 10:10) — comparar com EST_07 |
| S5 Falha de rompimento + Div | rompimento com fluxo divergente e volta para dentro em ≤ N barras | abertura após o fechamento de volta | extremo do furo + buffer | Wall oposta / centro NWE | BE 1R | WIN, WDO | 11:30 (perde 174.408) |
| S6 Confluência 2 motores | D1 **e** D2 (ou D3) regulares no mesmo pivô na zona | como S1 | como S1 | como S1 | como S1 | WIN, WDO | a medir |
| S7 Cross-asset | D1 no WIN na Wall + D8 (WDO não confirma) | como S1 | como S1 | como S1 | como S1 | WIN | a medir |
| Controles | mesma entrada/saída em (a) pivôs quaisquer na zona, (b) toques sorteados, (c) direção invertida | — | — | — | — | — | — |

Volume de variações por setup: **≤ 48 combinações**, fixadas antes de rodar (seção 6).

---

## 6. Protocolo de validação (corrige os erros de hoje)
**Fase 0 — Rotulagem manual com ferramenta facilitada (antes de otimizar qualquer coisa)**
1. Gabarito de hoje: os 4 eventos da seção 2.1 (confirmados pelo usuário).
2. Usuário rotula **15 pregões completos do IS (jan-jul)**, sorteados com seed fixa e estratificados por mês (~10 min por pregão,
   ~2,5 h no total), com a ferramenta da seção 6.1, marcando também as divergências que nenhum candidato pegou.
3. Medida por detector (A causal, B, D, E e os novos D1-D14): **recall** = rótulos com sinal da mesma direção a ≤ 2 barras do F2/
   confirmação; **precisão** = sinais do detector nos dias rotulados que batem com rótulo; atraso médio em barras.
   Critério para seguir (hipótese, usuário decide): recall ≥ 70% e precisão ≥ 40%.
4. Calibração de parâmetros do detector **só nos dias rotulados**, depois congelar (hash do módulo + dataset).
   Dias rotulados não são reutilizados como evidência de lucro.

### 6.1 Ferramenta de rotulagem (aprovada em 11/11; implementação em `research/div_master/labeler/`)
**Objetivo:** o usuário só valida candidatos; não precisa desenhar nada nem abrir planilha.

| Item | Especificação |
| :-- | :-- |
| Onde | `research/div_master/labeler/` — servidor próprio (Python stdlib) em **127.0.0.1:5180**. Não toca 5174/5176/5177/8080, `server.py`, `core/`, `regime-dashboard/` nem o túnel. Sem túnel público |
| Dados | JSON pré-calculado por pregão em `labeler/data/` a partir do `.min` do Profit (`profit_min_decomp` + `compute_flow`, mesma onda do 5176) e das Walls de `mt5/Files/jumba_gex_win_history.csv`; 11/11 vem do GET da API 8080 (motor ao vivo). Nada do cache `.gemini` |
| Layout | como o painel 5176: em cima candles M5 + Walls/MidWalls + NWE (centro e bandas); embaixo a onda "Fluxo Smart Money"; eixo de tempo comum; responsivo (celular) |
| Pré-marcação | **união** dos detectores com recall alto (A causal, B, v1, v2, D1 frouxo, BRK). Sem leque: cada pivô é F1 de no máximo um candidato (o swing novo casa com o anterior do mesmo lado, ou com o anterior mais relevante). Rejeição/absorção a ≤150 pts de Wall/MidWall ou nova máxima do pregão (venda) / nova mínima (compra), causal, mesmo fora da zona; rompimentos ficam à parte, também deduplicados. Sinais do mesmo lado a poucas barras (≤3) viram um só (fica o mais forte; fontes e contexto wall/midwall/day_high/day_low vão só para `candidate_sources.json`). Teto de **11 candidatos por pregão**, por força. Marcado só na barra em que o sinal já seria conhecido (sem barra do futuro). O detector de origem **não aparece** na tela (rotulagem cega). Pregões já rotulados não são regenerados |
| Ações | por candidato: **Válida / Falsa**, tipo **Rejeição / Absorção / Rompimento / Outro**, direção (corrigível) |
| Marcação nova | toque na barra F1 e depois na F2 → escolhe direção e tipo |
| Progresso | contador por pregão (revisados / candidatos) e geral |
| Saída | `research/div_master/labels/labels.csv` (append, com timestamp); **desfazer** grava uma linha de anulação (o CSV nunca é reescrito) |
| Tempo alvo | ~10 min por pregão |

**Fase 1 — Estudo de evento (IS)**: retorno à frente 6/12/24 barras, MFE/MAE por contexto, com placebo (pivôs sorteados na mesma zona,
mesma quantidade por mês × direção) e invertido. Só setups com sinal bruto acima do custo seguem.

**Fase 2 — Backtest dos setups (IS jan-jul)**
- Sem barra do futuro: sinal no fechamento, entrada na abertura seguinte; detector A reescrito sem `i+1` e sem repintura; teste de
  paridade barra a barra obrigatório (100%).
- Dados só do repositório (`.min` → `profit_min_decomp`), **sem o cache `.gemini`**; manifesto com hash.
- Execução M1 (caminho tick do `research/div3m/bt_div3m.py`), custos e slippage, DD **trade a trade**.
- Orçamento de variações: ≤ 48 por setup, registradas em `variations_log.csv` (conta tudo o que foi tentado).
- Platô (mediana da config e vizinhas de 1 parâmetro), mínimo de trades (WIN ≥ 80 no IS), lucro nas 2 metades (jan-abr, mai-jul),
  placebo p < 0,10 e invertido sem a mesma marca. Horário, meta diária e almoço **não** são escolhidos olhando o resultado.

**Fase 3 — Fora da amostra**
- ago-6/nov rodado **uma vez** com trava `oos_log.json`. **Ressalva:** esse período já foi usado hoje 5 vezes (div_gate,
  div_entry, sniper2, sniper_direct, div3m) — não é mais limpo para escolher entrada.
- Validação decisiva: **papel ao vivo a partir de 12/11**, regras congeladas, ≥ 20 pregões / ≥ 40 trades por ativo.
- Opcional (hipótese): hold-out 2025 se as Walls de 2025 puderem ser reconstruídas (há `.min` WINQ25/V25/Z25 no disco).

---

## 7. Ordem sugerida e esforço (estimativas, hipótese)
| Etapa | Entrega | Esforço |
| :-- | :-- | :-- |
| 0 | ~~Confirmar os 4 eventos e responder às perguntas~~ (feito 11/11); checar o alerta 2.4 (onda ao vivo × `.min` à noite) | 0,5 dia |
| 1 | ~~Ferramenta de rotulagem (seção 6.1)~~ (feita 11/11) + usuário rotula 15 pregões IS + 11/11 | ~2,5 h do usuário |
| 2 | Módulo único de detectores D1-D14 + detector A causal + paridade | 1-1,5 dia |
| 3 | Relatório recall/precisão/atraso por detector; calibrar e congelar | 0,5 dia |
| 4 | Estudo de evento por contexto (IS) | 0,5-1 dia |
| 5 | BT S1-S7 + controles (IS, M1) | 1-2 dias |
| 6 | OOS uma vez + papel ao vivo | 20 pregões |

**Primeiro passo recomendado:** usuário rotula os 16 pregões na ferramenta (`http://127.0.0.1:5180`) antes de qualquer otimização.

## 8. Perguntas em aberto para o usuário
Respondidas em 11/11 (14:35): eventos/horários (sim; F1 = 09:00), rompimento (entra 10:10, após o reteste), zona (150 pts WIN;
MidWall = Wall), tipo de divergência (só preço × Smart Money), entradas (as 3) e alvos (próxima Wall / centro NWE / banda NWE),
rotulagem (ferramenta facilitada, aprovada).

Restam:
1. Horário: a 9h entra? (o `div3m` achou 9h e 1ª divergência do dia ruins no WIN, mas o evento 1 de hoje é exatamente isso.)
2. Só WIN por enquanto, ou rotular WDO também? Se WDO, qual distância conta como "na Wall" (proposta 3,0 pts)?
3. M5 só, ou você confirma em M1 em algum caso?
4. Validação final: aceita o papel ao vivo a partir de 12/11 como teste decisivo (ago-nov já foi muito usado)?
5. Quer abrir a ferramenta no celular? Hoje ela só escuta em 127.0.0.1 (só no PC); liberar na rede local exige sua aprovação.
