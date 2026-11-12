# 📐 SPEC TÉCNICA — Dois Especialistas de Divergência para o Painel `5176`
**(`ESP_DIV_WALL` & `ESP_DIV_EXTREMO_DIA` · Gatilho Opção C · Motores `v3`, `v2.1` e `v3.1 Fusão`)**

> **Data:** 11/11/2026  
> **Objetivo:** Construir e validar dois setups especialistas independentes e 100% causais para o painel `5176`, substituindo a dependência das entradas dos EAs antigos por gatilhos próprios de **retomada de nível no fechamento (Opção C)** ancorados em **Wall/MidWall** e em **Máxima/Mínima do Dia**, comparando lado a lado três motores de divergência (`v3`, `v2.1` e a `Fusão v3.1`).

> **Revisão 2 (11/11/2026):** amarra a janela do gatilho Opção C à confirmação do pivô (§3.0), congela os parâmetros que tinham duas leituras, e acrescenta o protocolo de seleção e validação (§5), os pré-requisitos de dado (§6) e as decisões pendentes (§7).

> **✅ MODELO FINAL (12/11/2026, decisão do usuário):** o motor de divergência oficial da 5176 é o **v3.2 sem módulo de abertura** (`modulo.engine_v32` com `V32_PROD`; resultados em `v32/RESULTADOS.md`).
> - **Regras:** F1 no pivô de fluxo mais extremo da perna, sem reset, extensão só com extremo de preço novo; pivôs só do ZigZag 1,2×ATR14, sem o 0,8×ATR, o L2/R1 e a semente da abertura.
> - **Onde roda:** o mesmo motor alimenta o filtro do Sniper (WIN/WDO), o especialista `ESP_DIV_V22_WIN` (o ID ficou por compatibilidade) e o desenho no painel.
> - **Painel:** só o V3.2 (botão liga/desliga) e o Canal Gauss (NWE100).
> - **Paridade:** pesquisa = core = ao vivo, em `carteira_v22/paridade_v32.py`.
> - **Carteira 5176 (02/01–11/11, dentro da amostra):** 520 trades · PF 1,96 · R$ 16.889 · DD R$ 664 · Ret/DD 25,4 · 11/11 meses positivos. Os motores v2.1, v2.2, v3 e v3.1 ficam só como referência de pesquisa.

---

## 0. Ponto de Partida — o que os testes de 11/11 já mostraram

- **Entrar em toda divergência não deu lucro.** `sniper_direct`: PF cai para `1,1` e o DD triplica. `div_v3` etapa A: vantagem bruta negativa em `Jan–Jul`. `div_v3` etapas C/E e `div3m`: aprovados em `Jan–Jul`, reprovados em `Ago–Nov`.
- **A vantagem medida do Sniper corrigido** (`287` trades, PF `1,95`, Ret/DD `14,2`) vem de **entrada de setup + divergência como filtro**, não da divergência sozinha.
- **Hipótese específica desta SPEC:** o **gatilho Opção C** é o que transforma a divergência em entrada operável. Por isso o teste central é **Opção C × a mesma divergência sem Opção C** (entrada na confirmação do pivô) — §5.
- **A âncora Extremo do Dia dá cobertura, não precisão:** `61,4%` das divergências válidas rotuladas têm `F2` em nova máxima/mínima do pregão, mas "extremo do dia **ou** Wall" também cobre `87,2%` das falsas (`engine_v2_1/RESULTADOS.md`). A separação tem de vir do gatilho.

---

## 1. Arquitetura Geral dos Dois Especialistas

Em vez de um único setup genérico tentando operar qualquer divergência, separamos a física do mercado em **dois especialistas com âncoras, gatilhos de confirmação e alvos próprios**:

| Dimensão | 🧱 Especialista 1: `ESP_DIV_WALL` | 🏔️ Especialista 2: `ESP_DIV_EXTREMO_DIA` |
| :--- | :--- | :--- |
| **Tese Institucional** | Defesa passiva institucional + Market Makers (`Gamma`) absorvendo agressão na `MagicWall` ou `MidWall` GEX. | Armadilha de liquidez intradiária (*Stop Hunt / Failed Auction*): rompe o topo/fundo do dia para estopar varejo sem confirmação do Fluxo Smart Money. |
| **Onde Opera (Âncora `F2`/`T2`)** | Extremo do pivô `F2`/`T2` a **`≤ 150 pts` (WIN)** / **`≤ 3,5 pts` (WDO)** de uma `Wall`/`MidWall`, ou que **furou a Wall** em até `220 pts` (WIN) / `6,0 pts` (WDO). | A partir das **`09:30`** (após formar o range inicial de 30 min), `F2`/`T2` faz **Nova Mínima ou Nova Máxima do Pregão** (ou testa a `≤ 30 pts` WIN / `1,0 pt` WDO do extremo do dia). |
| **Gatilho Opção C (Confirmação)** | Barra `i` (`1 a 3` barras após o pivô, nunca antes de o motor confirmar o pivô — §3.0) **fecha retomando o lado defendido da Wall** (devolvendo o furo ou superando o fechamento/corpo do ataque na Wall). | Barra `i` (`1 a 3` barras após o pivô, nunca antes de o motor confirmar o pivô — §3.0) **fecha devolvendo a máxima/mínima anterior do dia** que havia sido rompida pelo `F2`/`T2`. |
| **Regra de Super-Confluência** | Quando o `F2`/`T2` é **simultaneamente** Wall e Extremo do Dia: na pesquisa individual ambos contabilizam o trade; na carteira combinada, o trade é deduplicado (1 entrada) com tag `SUPER_CONFLUENCIA`. | Idem (permite medir isoladamente quanto cada especialista soma e quanto a interseção entrega). |

---

## 2. Especificação dos 3 Motores de Divergência (`v3`, `v2.1` e `v3.1 Fusão`)

Todos os 3 motores leem a mesma curva **`smart_swing_wave`** (`core/div_wall_signal.py`) e obedecem à **Causalidade Estrita**: na barra `i`, o detector só enxerga `bars[0..i]`.

### 2.1. Motor 1 — `v3` (Base Pivô Curto + Abertura + Reset)
- **Pivôs:** `pivot_left = 2`, `pivot_right = 1` (confirma 1 barra após o extremo `j = i - 1`), mais a **barra `0` (`09:00`)** sempre elegível como `F1/T1`.
- **Leitura da Onda em `F1`:** extremo da onda na janela `k-1 .. k+1` (`f1_win = 1`).
- **Pareamento e Reset:** `F1` é o pivô de onda mais extrema desde o último sinal (`anchor[d]` reinicia em `j` a cada sinal emitido, `reset_f1 = True`), exigindo `min_dist = 3` barras e extremo novo caso repita na mesma estrutura.
- **Limiar de Fluxo:** `(wave[F2] - wave[F1]) * d > 0,50 × mediana_causal(|wave[0..i]|)`.

### 2.2. Motor 2 — `v2.1` (Base ZigZag Adaptativo por ATR + Sem Leque)
- **Pivô Evidente (ZigZag Causal):** Um topo ou fundo `j` só é confirmado na barra `confirm = i` quando o preço reverte pelo menos `R = max(1,2 × ATR14_causal(i), piso)` a partir do extremo (`piso = 80 pts` no WIN / `2,5 pts` no WDO).
- **Pareamento Sem Leque (1-para-1):** `F1` é o pivô ZigZag anterior do mesmo lado (entre `2` e `48` barras atrás) que ainda não foi usado como `F1` (`used_f1`).
- **Estrutura de Preço e Onda:** `px(F2) <= px(F1) + price_tol` na compra (`60 pts` WIN / `2,0 pts` WDO) e `(wave[F2] - wave[F1]) * d > 0,15 × mediana_causal(|wave[0..i]|)`.

### 2.3. Motor 3 — `v3.1 Fusão` (O Melhor do `v2.1` + O Melhor do `v3`)
1. **Semente de Abertura (`Herança v3`):** A barra `0` (`09:00`) e o primeiro extremo local das `09:00–09:20` entram como `F1/T1` elegíveis sem exigir recuo prévio de `1,2 × ATR14`; até `09:35`, `F2` confirma com reversão reduzida (`0,8 × ATR14` ou pivô `L2/R1` com candle a favor).
2. **Filtro de Pivô Evidente no Pregão (`Herança v2.1`):** Após os primeiros 30 minutos, todo pivô exige a reversão de **ZigZag causal de `1,2 × ATR14`** (piso `80 pts` WIN / `2,5 pts` WDO — o mesmo valor calibrado no `v2.1`), barrando micro-pivôs no meio do ruído. `1,0 × ATR14` fica como única variação registrada.
3. **Onda de `F1` com Tolerância `k ± 1` (`Herança v3`):** `w1 = min(wave[k-1 .. k+1])` na compra (`max` na venda).
4. **Ancoragem Dinâmica sem Leque (`Fusão v2.1 + v3`):** Cada `F1` gera no máximo 1 sinal (`used_f1`), `anchor[d]` avança para `F2` após o disparo (`reset_f1 = True`), e novo sinal no mesmo sentido exige renovação de extremo.
5. **Qualidade Microestrutural no `F2`:** Exige na janela `j..i` defesa institucional/Wyckoff ativa (`wyckoff_abs * d > 0` ou `inst_pass_delta * d > 0` ou `force * d > 0`). **Checagem obrigatória na Etapa 1:** medir quantos `F2` este item aprova. O filtro "3 motores" do Sniper, que também é um OU de condições de força, aprova `99–100%` e não filtra nada; se este aprovar `≥ 90%`, sai do motor (parâmetro morto). Depende ainda do pré-requisito de dado do §6.
   **Resultado da Etapa 1 (12/11/2026): aprova `93,4%` (WIN) e `97,5%` (WDO) em `Jan–Jul` → removido. O `v3.1` segue sem o item 5** (`especialistas/ETAPA1.md` §4.1).

### 2.4. Ressalva sobre o `v3.1`
É o motor com mais parâmetros (semente de abertura, dois regimes de reversão, janela `k ± 1`, item 5) e foi desenhado olhando os mesmos 9 pregões rotulados usados para calibrar o `v2.1`. Só substitui o `v2.1` se ganhar **fora** desses pregões (hold-out, leave-one-session-out ou pregões novos rotulados) — §5, Etapa 2.

---

## 3. Especificação Matemática do Gatilho Opção C (*Reclaim / Devolução no Fechamento*)

### 3.0. Regra comum da janela do gatilho (vale para os dois especialistas e os três motores)
- `j` = barra do pivô `F2`/`T2`. `conf` = barra em que o motor **confirma** o pivô: `j+1` no `v3` (pivô `L2/R1`); a barra da reversão do ZigZag no `v2.1` e no `v3.1`.
- O gatilho dispara na **primeira** barra `i` com `max(j+1, conf) <= i <= j+3` cuja condição de fechamento (§3.1 / §3.2) é verdadeira **no fechamento da própria barra `i`**. Um gatilho por `F2`.
- Se `conf > j+3`, o sinal é **descartado** (não se espera a confirmação tardia). Medido no `v2.1` (WIN, 16 pregões, 144 detecções de `engine_v2_1/detections.json`): confirmação na própria barra `j` em `37,5%`, até `j+1` em `71,5%`, até `j+3` em `95,8%`; `4,2%` seriam descartados.
- `i = j` não vale. No `v3` o pivô só é conhecido em `j+1`; no ZigZag, confirmar na própria barra supõe que a mínima veio antes da máxima dentro do candle, o que o M5 não informa.
- **Entrada:** abertura de `i+1` no backtest; fechamento de `i` ao vivo.

> **Pendente após a Etapa 1 (12/11/2026):** como está escrita abaixo, a Opção C dispara em `65–85%` dos candidatos com âncora. Em `57–76%` dos C1 a barra do pivô já tinha fechado retomada (o furo foi só pavio). As alternativas (a) C1/violação só com fechamento além, (b) `C_t` além de `C_j` em todos os subcasos, ou (c) manter estão em `especialistas/ETAPA1.md` §4.2. Decisão do usuário antes da Etapa 3.

### 3.1. Gatilho Opção C no Especialista 1 (`ESP_DIV_WALL`)
- **Subcaso C1 — Violinada na Wall (*Pierce & Reclaim*):** `F2` furou a Wall ($L_j < W$ na compra / $H_j > W$ na venda, até `220p` WIN / `6,0p` WDO) e a barra `i` (janela do §3.0) **fecha retomando a Wall para o lado defendido** ($C_i > W + \text{buf}$ na compra / $C_i < W - \text{buf}$ na venda). `buf = 20 pts` (WIN) / `0,5 pt` (WDO) — valor proposto, §7.
- **Subcaso C2 — Defesa na Zona da Wall (*Touch & Reject*):** `F2` tocou a zona da Wall sem fechar além ($|P_2 - W| \le 150\text{p}$ WIN / $3{,}5\text{p}$ WDO) e a barra `i` **fecha do lado defendido de $W$, a favor da operação ($C_i > O_i$ na compra / $C_i < O_i$ na venda) e além do fechamento da barra do pivô** ($C_i > C_j$ na compra / $C_i < C_j$ na venda), na janela do §3.0. "Além da metade da barra do pivô" fica como única variação registrada.

### 3.2. Gatilho Opção C no Especialista 2 (`ESP_DIV_EXTREMO_DIA`)
- Após `09:30`, `F2` renova ou testa o extremo anterior do dia $E_{\text{prev}} = \min_{t \le j-2} L_t$ (ou $\max_{t \le j-2} H_t$ na venda).
- **Disparo Opção C (janela do §3.0):** A barra `i` **fecha devolvendo o rompimento para dentro do range anterior do dia** ($C_i > E_{\text{prev}}$ e $C_i > O_i$ na compra; $C_i < E_{\text{prev}}$ e $C_i < O_i$ na venda; ou, em fundo/topo duplo exato sem violação de $E_{\text{prev}}$, fecha superando a máxima/mínima da barra $j$).

---

## 4. Saídas e Plano de Execução (Etapas 1 a 5)
1. **Saída A (Sniper 5176):** WIN `2c Mix (L1 NWE30 + L2 750p + BE 180→20, SL 240/260)` · WDO `1c MidWall/NWE30 (SL 10p + BE 3,5→1,0p)`.
2. **Saída B (Técnica Estrutural):** Stop atrás do pivô `F2/T2` + buffer (`30p` WIN / `1,0p` WDO) e alvo na próxima `Wall/MidWall` (saindo `15 pts` WIN / `0,5 pt` WDO antes do nível). A banda oposta da `NWE50` fica como única variação registrada de alvo. **Teto de risco:** se o stop ficar a mais de `300 pts` (WIN) / `10,5 pts` (WDO) da entrada, o trade é abortado, nunca truncado (no WIN é a regra já usada no `calc_wall_tp_sl`; o valor do WDO é proposto, §7).
3. **Execução (detalhada no §5):** Etapa 1 (Módulo unificado + paridade causal) ➔ Etapa 2 (Confronto contra `labels.csv` + `11/11`) ➔ Etapa 3 (Anatomia & Backtest M1 em `Jan–Jul/2026` + Placebo) ➔ Etapa 4 (Carteira Combinada & checagem única em `Ago–Nov/2026`, que já não é período limpo) ➔ Etapa 5 (Sombra ao vivo).

---

## 5. Protocolo de Seleção e Validação

Sem este protocolo a SPEC abre `3 motores × 2 especialistas × 2 saídas × 2 ativos = 24` células antes de qualquer parâmetro. Com ele, um motor é escolhido **antes** de olhar lucro e sobram `2 especialistas × 2 saídas = 4` células por ativo.

| Etapa | O que decide | Critério | Dados |
| :--- | :--- | :--- | :--- |
| **1. Módulo + paridade** | Se os três motores e os dois gatilhos são causais | Paridade lote × barra a barra em `100%`. Mede sinais/dia por motor × especialista e a taxa de aprovação do item 5 do `v3.1`. Sem P&L. | `Jan–Jul/2026` |
| **2. Escolha do motor** | Qual **um** motor segue | Cobertura, precisão e atraso contra `labels.csv` (44 divergências válidas, 9 pregões WIN), **sem P&L**. Comparação em hold-out / leave-one-session-out e, de preferência, em pregões novos rotulados (meta do `PLANO_MESTRE`: 15 pregões de `Jan–Jul`). Referência hoje: `v2.1` cobre `72,7%` com precisão `38,6%`; `v3` cobre `40%` das válidas e `25%` das falsas. Critério proposto: cobertura `≥ 70%` e precisão `≥ 40%`; em empate, o motor com menos parâmetros. | Pregões rotulados |
| **3. Estudo em `Jan–Jul`** | Se cada especialista tem vantagem | (a) Retorno bruto em 6/12/24 barras contra placebo, antes de qualquer saída. (b) Backtest das 4 células. **Controle central:** mesma divergência sem Opção C. Aprovação: `≥ 80` trades no WIN, lucro nas duas metades (`Jan–Abr`, `Mai–Jul`), placebo `p < 0,10` e platô (vizinhas de 1 parâmetro também positivas). | `Jan–Jul/2026` |
| **4. `Ago–Nov`** | Nada — é checagem | Rodado **uma vez**, com trava (`oos_log.json`). Esse período já foi usado pelo menos 5 vezes em 11/11; um resultado bom aqui não aprova, um resultado ruim reprova. | `Ago–6/Nov/2026` |
| **5. Sombra ao vivo** | Aprovação final | Regras congeladas (hash do módulo), sinais gravados no momento em que nascem, `≥ 20` pregões e `≥ 40` trades por ativo. | A partir da data de congelamento |

**Regras fixas do backtest (Etapas 3 e 4):**
- **Orçamento:** no máximo `48` variações por especialista × ativo, todas registradas em `variations_log.csv` (conta tudo o que foi tentado). As variações já registradas nesta SPEC: reversão `1,0 × ATR14`, C2 pela metade da barra, alvo `NWE50` na Saída B.
- **Execução em M1**, stop antes do alvo na mesma barra, stop rompido em gap preenchido na abertura. Em `div3m` a mesma configuração do WIN deu `R$ 2.894` com M1 e `R$ 258` com a regra M5.
- **Custos:** WIN `10 pts` / WDO `0,5 pt` por trade, mais 1 tick de slippage em stop. DD medido trade a trade.
- **Placebos:** mesma entrada e saída em (a) pivôs na zona sem divergência, (b) barras sorteadas, mesma quantidade por mês × direção, (c) direção invertida.
- **Horários pulados e meta diária do Sniper não entram no teste-base.** Foram escolhidos olhando o ano inteiro (`audit_5176/AUDITORIA.md`, ponto 3); aparecem como linha separada no relatório. O balde das `09h` é reportado à parte, sem ser cortado pelo resultado.
- **Dados só do repositório** (`.min` → `profit_min_decomp`), com manifesto e hash. Nada do cache `.gemini`.

---

## 6. Pré-requisitos de Dado

1. **Onda ao vivo × onda reconstruída (alerta 2.4 do `PLANO_MESTRE`, ainda sem conferência registrada).** Em 11/11, `inst_aggr_delta` / `inst_pass_delta` do WIN caíram para perto de zero a partir das `10:05` no motor ao vivo. Antes da Etapa 5, comparar barra a barra a onda gravada ao vivo com a reconstruída do `.min` à noite, em pelo menos 3 pregões. Se divergirem, o que foi validado no histórico não é o que o painel calcula, e o item 5 do `v3.1` (que lê `inst_pass_delta`) não pode rodar ao vivo.
2. **WDO sem gabarito.** Os 9 pregões rotulados são só WIN. Os limiares do WDO nesta SPEC (`3,5` / `6,0` / `1,0 pt`, piso `2,5 pts`, tolerância `2,0 pts`) são **provisórios**. O WDO só passa da Etapa 1 depois de ter rótulos próprios ou de uma regra de escala fixada de antemão (por exemplo, razão das medianas de ATR14 M5 WDO/WIN em `Jan–Jul`).

---

## 7. Decisões Pendentes (suas)

| # | Decisão | Valor proposto nesta revisão |
| :--- | :--- | :--- |
| 1 | `buf` do subcaso C1 (não tinha valor) | `20 pts` WIN / `0,5 pt` WDO |
| 2 | C2: fechar além do **fechamento** ou da **metade** da barra do pivô | Fechamento (metade vira variação) |
| 3 | Alvo principal da Saída B, e qual leitura da `NWE50` | Próxima `Wall/MidWall`; `NWE50` = banda oposta, como variação |
| 4 | Teto de risco do WDO na Saída B | `10,5 pts` |
| 5 | WDO entra já com limiares provisórios, ou só depois de rotulado | Só depois (WIN primeiro) |
| 6 | Critério de escolha do motor na Etapa 2 | Cobertura `≥ 70%`, precisão `≥ 40%` |

---

## 8. Resultado da busca no período completo (12/11/2026)

O usuário pediu: gatilho (a)+(b), período completo e busca até achar Ret/DD > 10. Isso substituiu as Etapas 2–4 do §5. Detalhe em `especialistas/RESULTADOS.md`.

- **A SPEC como está não funciona:** as 54 combinações (motor × especialista × Saída A/B × ativo) ficaram com Ret/DD < 2.
- **Regra encontrada (`ESP_DIV_V21_WIN`):**
  - WIN, motor `v2.1`, sem super-confluência, até o 2º gatilho do dia por direção;
  - entrada entre 10:00 e 15:55, com `ext50 > −0,5` e `slope50 > −0,5`;
  - SL 200, sem alvo, saída em 12 barras, BE +180→+20, um trade por vez.
  - Período completo: 319 trades, PF 1,77, R$ 4.703 (1 contrato), DD R$ 399, **Ret/DD 11,8**, 11/11 meses. Jan–jul 5,9; ago–nov 11,1. Platô 9,9.
- **Placebo de barras com os mesmos filtros:** p = 0,003. Sem divergência, Ret/DD 5,6.
- **Sem Opção C: Ret/DD 11,8.** O gatilho não acrescenta; a hipótese do §0 não se confirmou.
- **WDO:** sem vantagem em nenhum motor.
- **Seleção feita no período completo**, com 77.828 configurações registradas: só o papel ao vivo valida.
