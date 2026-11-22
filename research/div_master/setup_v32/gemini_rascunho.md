# Plano de Pesquisa: Setup Aditivo de Extremos e Confluência (Motor V3.2)

## 1. Premissas e Escopo Operacional

- **Natureza aditiva (Add-on):** O especialista atual em produção (`ESP_DIV_V22_WIN`, rotulado no painel 5176 como *"WIN Especialista V3.2"*, implementado em [especialista_v22.py](file:///C:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/core/especialista_v22.py)) é **imutável** neste plano. Suas regras, filtros, janelas e dimensionamento (2 contratos) permanecem intactos.
- **Papel do Motor V3.2:** O motor oficial da carteira desde 12/11/2026 (`engine_v32` com `V32_PROD` em [modulo.py](file:///C:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/research/div_master/especialistas/modulo.py#L478-L565)) entra como **filtro/contexto de zona e estrutura**, nunca como ordem automática em toda marcação. A pesquisa anterior (`sniper_direct`, `div_v3`) já demonstrou que operar toda divergência isolada não tem expectativa positiva; o edge reside na combinação de **contexto + divergência como filtro + gatilho de confirmação**.
- **Orçamento enxuto e ceticismo estatístico:** A rodada de 12/11 testou ~20 mil combinações (`I1`–`I5`, `V1a`, `flow_breakout`) e mostrou que buscas massivas geram artefatos de seleção (`I3` reprovado na validação independente; `I5` com expectativa real próxima de Ret/DD ~1 contra 5,46 de vitrine). Este plano restringe o espaço de busca a **poucas hipóteses estruturais (~15 a 30 configurações no total)**, escolhidas exclusivamente na amostra de treino (IS: jan–jul).

---

## 2. O que já está em produção: Motor V3.2 e Especialista WIN

### 2.1. Motor Oficial V3.2 (`V32_PROD`)
Implementado em [modulo.py](file:///C:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/research/div_master/especialistas/modulo.py#L478-L565) e exposto visualmente por `core/div_engines_view.py` (`POST /api/compass/divergencias_motor`):
- **Geometria de pivôs:** Exclusivamente ZigZag causal de `1,2 × ATR(14)` (piso de 80 pts no WIN / 2,5 pts no WDO), **sem módulo de abertura** (`open_module=False`: sem ZigZag `0,8 × ATR`, sem pivô curto L2/R1 até 09:35 e sem semente até 09:20).
- **Pareamento F1 → F2:**
  - `F1`: pivô anterior da mesma perna com a onda (*Fluxo Smart Money*) **mais extrema** da própria barra (`f1="flow"`), respeitando distância entre 2 e 48 barras e tolerância de preço (`tol_v21`: 60 pts WIN / 2,0 pts WDO).
  - `F2`: último extremo de preço confirmado pelo ZigZag, com perda de força no fluxo (`d * (w2 - w1) > 0,15 × mediana_causal(|onda|)`).
  - **Sem reset (`reset=False`, `used=False`) e com extensão (`rep=True`):** Um mesmo `F1` pode ancorar sucessivos `F2` desde que o preço renove o extremo anterior (extensão da divergência na mesma perna). No painel visual, apenas a última extensão de cada `F1` é desenhada (1 linha por perna).
- **Elegibilidade (`elig="common"`):** O pivô `F2` deve ocorrer a ≤ 150 pts (WIN) / 3,5 pts (WDO) de uma `Wall` ou `MidWall` (furo máximo de 220 pts / 6,0 pts) **OU** configurar extremo do dia a partir das 09:30 (`day_tol` de 30 pts / 1,0 pt).

### 2.2. O Especialista WIN (`ESP_DIV_V22_WIN`)
Implementado em [especialista_v22.py](file:///C:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/core/especialista_v22.py#L73-L142):
- **Métricas históricas de produção (02/01–11/11, 2 contratos):** 252 trades, lucro líquido R$ 9.214, DD R$ 656, Ret/DD 14,05 (IS jan–jul: Ret/DD 7,50; OOS ago–nov: Ret/DD 9,99). *(Nota: a variante de pesquisa "E22" com 266 trades e Ret/DD 15,08 difere porque descarta duplicatas antes de incrementar `seq`; a referência oficial é a de 252 trades).*
- **Filtros restritivos que definem seu perfil defensivo:**
  1. Gatilho Opção C `(a)+(b)` (`WALL C1/C2` ou `EXTREMO VIOL/DUPLO`) entre `max(j+1, conf)` e `j+3`.
  2. **Descarte de super-confluência (`r["super"] == True`):** Se `F2` tem simultaneamente âncora de `Wall/MidWall` **e** `Extremo do Dia`, o trade é bloqueado ([especialista_v22.py](file:///C:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/core/especialista_v22.py#L111)).
  3. **Limite de sequência (`seq <= 1`):** Aceita apenas o 1º e o 2º gatilho do dia por direção; a partir do 3º (`seq >= 2`), ignora. No código de produção, gatilhos de `WALL` e `EXTREMO` do mesmo pivô incrementam `seq` separadamente.
  4. **Janela e Contexto:** Entrada entre 10:00 e 15:55; filtro NWE50 (`bw=8, mult=3`) exigindo `ext50 > -0,5` e `slope50 > -0,5`.
  5. **Saída:** Stop Loss de 200 pts, sem alvo fixo, Break-Even de `+180 → +20` pts, saída por tempo na abertura da 13ª barra (`tmax=12`) ou às 17:25.

---

## 3. Diagnóstico de 13/11/2026: Onde está o "buraco"

Em 13/11, todas as estratégias sistemáticas Sniper fizeram **0 trades** (`portfolio_4_live_days.json`), e o especialista WIN fez apenas **1 trade** (11:15, saída no BE +20). Contudo, o motor `V32_PROD` cravou visualmente as máximas do WIN e a mínima e as máximas do WDO.

A reconstrução barra a barra mostra que **o problema não é de detecção do motor V3.2, mas de descarte pelos filtros de entrada do especialista (no WIN) e ausência de regra em produção (no WDO)**:

### 3.1. WIN (WINZ26) em 13/11
| # | Direção | Par F1 → F2 (conf) | Preço F2 | Âncora | Gatilho Opção C | O que aconteceu no Especialista (`ESP_DIV_V22_WIN`) |
| :-: | :-: | :-- | --: | :-- | :-- | :-- |
| **1** | VENDA | `10:45 → 11:05` (conf `11:10`) | 173.825 | `WALL` | `WALL/C2` (11:10 → in 11:15) | **Executado (`seq=0`).** Entrada a 173.425, saída 11:30 no BE (+20 pts brutos / +10 pts líq., R$ 2). |
| **2a** | VENDA | `10:35 → 11:55` (extensão) | 174.390 | `WALL + EXTREMO` (`XW▲`) | `WALL/C1` (12:00 → in 12:05) | **Recusado por `super=True`** (super-confluência Wall + Extremo do dia) e consumiu `seq=1`. |
| **2b** | VENDA | `10:35 → 13:10` (conf `13:20`) | **174.430 (Máxima do dia)** | `EXTREMO DO DIA` (`X▼`) | `EXTREMO/DUPLO` (13:20 → in 13:25) | **Recusado por `seq=2`** (3º gatilho de venda do dia). NWE50 em 13:25 passaria (`ext=0,03`, `slope=-0,22`). |
| **3** | COMPRA | `15:45 → 16:00` (conf `16:05`) | 173.595 | `WALL` (`W▲`) | `WALL` (16:05 → in 16:10) | **Recusado por horário** (`16:10 >= 16:00`). Não era mínima do dia. |

- **Sobre a mínima do WIN (172.495 às 09:00):** O motor oficial (`open_module=False`) não marcou divergência de compra ali, e a onda das 09:15/09:20 afundou no recuo — não havia divergência clara de fluxo no fundo da abertura.
- **A ironia estrutural na máxima do WIN:** A perna que culminou na máxima do dia (174.430) gerou dois gatilhos válidos com NWE favorável: o primeiro às 12:00 foi vetado porque tinha **dupla âncora** (`super=True`, Wall + Extremo do dia); o segundo às 13:20 (na máxima cravada) foi vetado porque as extensões anteriores da mesma perna já haviam esgotado a cota `seq <= 1`. *(Ressalva de pesquisador: um único pregão ao vivo ilustra o mecanismo do filtro, mas não invalida sozinho a estatística histórica que levou ao descarte de `super` no E22 — isso precisa ser testado em jan–jul com gatilho e gestão adequados).*

### 3.2. WDO em 13/11
| # | Direção | Par F1 → F2 (conf) | Preço F2 | Âncora | Gatilho Opção C | Diagnóstico |
| :-: | :-: | :-- | --: | :-- | :-- | :-- |
| **1** | VENDA | `10:05 → 11:10` (conf `11:15`) | 5.683,5 | `EXTREMO DO DIA` | `EXTREMO/DUPLO` (11:15 → in 11:20) | Máxima até então. Não operado por **ausência de especialista WDO em produção**. |
| **2** | COMPRA | `12:10 → 13:10` (conf `13:10`) | **5.647,5 (Mínima do dia)** | `WALL + EXTREMO` | `WALL/C2` (13:20 → in 13:25) | Mínima cravada do dia (`super=True`). Sem especialista WDO. |
| **3** | VENDA | `14:20 → 18:15` (conf `18:20`) | **5.688,5 (Máxima do dia)** | `EXTREMO DO DIA` | Sem barra seguinte útil | Fim do pregão (18:20), fora de qualquer janela operacional. |

---

## 4. Teses e Setups Candidatos (Add-on V3.2)

Em vez de reabrir uma grade combinatória aberta, propomos **3 teses operacionais enxutas** (2 para WIN e 1 estudo separado para WDO), sempre exigindo candidato prévio do motor `V32_PROD` (`elig="common"`).

### Tese 1 — `ADD_WIN_EXT_REC` (Recaptura de Extremo / Super-Confluência por Extensão V3.2)
- **Problema que ataca:** No motor V3.2 (`rep=True, reset=False`), uma tendência forte faz extensões do mesmo `F1`. As primeiras tentativas na Wall costumam acionar `seq=0` e `seq=1` (ou são descartadas por `super=True`), e quando o preço finalmente crava o extremo definitivo da perna (como às 13:20 em 13/11, ou na confluência `XW▲` das 12:00), o especialista está bloqueado.
- **Filtro de Contexto (Motor V3.2):**
  - Candidato `V32_PROD` com âncora `EXTREMO DO DIA` (`day is not None`), permitindo `super=True` (confluência `Wall + Extremo` é aceita).
  - Opera **apenas os sinais que o `ESP_DIV_V22_WIN` descartou por regra de filtro estrutural**: isto é, candidatos onde `super == True` **OU** onde a perna é uma extensão (`ext == True` / `seq >= 2` causado por consumo prévio do mesmo `F1`).
  - Limite próprio: no máximo **1 trade executado por direção por dia** neste add-on (evita metralhadora em dia direcional sem fundo/topo).
- **Variantes de Gatilho a testar (em `t ∈ [conf, j+3]`, entrada na abertura de `t+1`):**
  - **G1 (Opção C padrão destravada):** Mesmo gatilho `WALL C1/C2` ou `EXTREMO VIOL/DUPLO`, mais filtro NWE50 (`ext50 > -0,5`, `slope50 > -0,5`). Testa puramente se a trava `super` / `seq` por extensão está deixando dinheiro na mesa com o motor V3.2.
  - **G2 (Rompimento da Barra de Sinal / Confirmação + Fluxo):** Fechamento de `t` rompe a mínima (na venda) ou máxima (na compra) da barra do pivô `j` (`close[t] < low[j]` ou `close[t] > high[j]`) **E** a onda (*Fluxo Smart Money*) vira a favor do trade (`d * (wave[t] - wave[t-1]) > 0`).

### Tese 2 — `ADD_WIN_REJ_NWE` (Filtro V3.2 + Gatilho Alternativo de Rejeição / Banda NWE)
- **Problema que ataca:** Casos em que o motor V3.2 confirma a divergência na Wall ou no Extremo do Dia, mas o gatilho Opção C (`DUPLO` / `VIOL` / `C1` / `C2`) não dispara ou exige esperar demais, enquanto o preço deixa rejeição explícita na zona ou devolve um excesso fora da banda da NWE50.
- **Filtro de Contexto (Motor V3.2):**
  - Candidato `V32_PROD` (`elig="common"`, Wall ou Extremo do Dia após 09:30) que **não** tenha gerado entrada simultânea no `ESP_DIV_V22_WIN`.
- **Variantes de Gatilho a testar (em `t ∈ [conf, j+3]`, entrada na abertura de `t+1`):**
  - **G3 (Rejeição na Wall + Virada de Fluxo):** Barra `t` (ou a própria barra `conf`) testa a zona da Wall/Extremo, deixa pavio contra o extremo ≥ 40% do range da barra (`(high - max(open, close)) / range >= 0,40` na venda; análogo na compra), fecha a favor da reversão (`d * (close - open) > 0`) com desaceleração/virada da onda (`d * (wave[t] - wave[j]) > 0`).
  - **G4 (Retorno de Exaustão da Banda NWE50):** O extremo do pivô `j` (ou `t-1`) violou ou tocou a banda externa da NWE50 (`ext50 <= -0,8`, isto é, preço próximo ou além de `nwe50_upper` na venda / `nwe50_lower` na compra) e a barra `t` fecha de volta para dentro da banda com `d * (close[t] - close[j]) > 0`. *(Nota: enquanto o E22 usa `ext50 > -0,5` para não operar contra tendência esticada demais, o G4 testa especificamente o retorno à média quando a divergência V3.2 ocorre na banda externa da NWE).*

### Tese 3 — `ADD_WDO_V32_CORE` (Estudo Separado de WDO Puro V3.2, Sem Módulo de Abertura)
- **Diagnóstico prévio:** O candidato `V1a` de WDO estudado em 12/11 dependia do módulo de abertura (`open_module=True`) e teve Ret/DD em walk-forward reduzido para ~3–4 (contra ~7 de vitrine), sendo recomendado apenas para sombra. Como o motor oficial `V32_PROD` **não tem módulo de abertura**, qualquer setup de WDO precisa se sustentar apenas com o ZigZag `1,2 × ATR` a partir das 10:00 (como foram os sinais das 11:15 e 13:20 em 13/11).
- **Regra em teste:**
  - Sinal `V32_PROD` no WDO (`elig="common"`), janela 10:00–15:55, 1 contrato.
  - Testar 2 combinações de âncora: (A) apenas `WALL` (onde a validação de 12/11 apontou existir efeito real contra Walls deslocadas) vs. (B) `WALL` + `EXTREMO` (incluindo `super=True`, que capturaria a mínima de 13/11 às 13:25).
  - Gatilhos: Opção C padrão (G1) vs. Rompimento + Virada de Fluxo (G2).

---

## 5. Regras de Coexistência com o Especialista (`ESP_DIV_V22_WIN`)

Para garantir que o add-on seja estritamente complementar e nunca desconfigure o perfil de risco da carteira 5176:

1. **Prioridade Absoluta do Especialista:** Se na mesma barra `t` o `ESP_DIV_V22_WIN` e o Add-on dispararem entrada na mesma direção, **apenas o `ESP_DIV_V22_WIN` entra**. O Add-on é suprimido naquela barra.
2. **Posição já aberta na mesma direção (Sobreposição):**
   - **Regra padrão (conservadora):** Se o `ESP_DIV_V22_WIN` já está posicionado na direção `d`, o Add-on **não abre** nova posição na mesma direção `d` (bloqueio de piramidação). Ele só atua quando o especialista está *flat* (como às 12:05 e 13:25 de 13/11, pois o trade das 11:15 já havia saído no BE às 11:30).
   - *(Variante secundária a medir na avaliação de carteira: permitir +1 contrato do Add-on somente se o especialista já estiver com o stop movido para o Break-Even `+20`).*
3. **Sinais Opostos:** Se o `ESP_DIV_V22_WIN` está comprado e o Add-on gera venda (ou vice-versa), o Add-on é **bloqueado** (não faz hedge interno nem zera o especialista). O especialista governa sua própria saída até o SL, BE, 12 barras ou 17:25.
4. **Tamanho e Exposição Máxima:**
   - `ESP_DIV_V22_WIN`: **2 contratos** (atual, inalterado).
   - `Add-on WIN`: **1 contrato** (metade da mão do especialista).
   - `Add-on WDO` (se aprovado para sombra): **1 contrato**.
   - **Limite no Add-on:** 1 trade aberto por vez no Add-on; máximo de **2 trades executados por dia** no Add-on WIN (máx. 1 por direção na Tese 1).
5. **Janela de Horário:**
   - Entrada: **10:00 às 15:55** (mesma janela do especialista — evita o ruído da abertura das 09:00–09:55 sem módulo de abertura e evita entradas tardias como a das 16:10 em 13/11).
   - Encerramento compulsório: **17:25** (`eod=1045`).

---

## 6. Stops, Alvos e Grade Limitada de Teste

Para não repetir o sobreajuste de stops/alvos, os parâmetros de saída são congelados nos defaults já validados do especialista e nas respostas do usuário de 11/11:

### 6.1. Saídas em Teste (Apenas 2 perfis por ativo — sem otimização fina)
- **Perfil S1 (Padrão Especialista — Tempo/BE, sem alvo fixo):**
  - **WIN:** SL `200 pts`, BE `+180 → +20 pts`, sem alvo fixo, saída por tempo em `12 barras` (abertura da 13ª) ou `17:25`.
  - **WDO:** SL `7,0 pts`, BE `+6,0 → +1,0 pt`, saída por tempo em `12 barras` ou `17:25`.
- **Perfil S2 (Alvo Estrutural do Usuário — Banda/Linha NWE50 ou Próxima Wall):**
  - Mesmo SL e BE do Perfil S1, mas com realização na abertura/toque de:
    - **S2a:** Linha central da `NWE50` (`nwe50_line`) se a entrada ocorreu fora de `0,5 × meia-banda`, ou banda oposta da `NWE50`.
    - **S2b:** Próxima `Wall` / `MidWall` a favor do trade (desde que ofereça razão retorno/risco mínima de `>= 1,0 × SL`).

### 6.2. Orçamento Total da Grade (Máximo ~24 combinações)
- **WIN:** 2 Teses × 2 Gatilhos por tese (G1, G2 na Tese 1; G3, G4 na Tese 2) × 3 Saídas (S1, S2a, S2b) = **12 configurações**. (Avaliadas em modo *standalone* e em modo *bloqueado quando E22 posicionado* = 24 execuções).
- **WDO:** 1 Tese × 2 Âncoras (`WALL` vs `WALL+EXTREMO`) × 2 Gatilhos (G1, G2) × 2 Saídas (S1, S2a) = **8 configurações**.
- **Premissas estritas de execução e custos (100% causais):**
  - Sinal apurado no fechamento da barra M5 `t`; entrada a mercado na **abertura da barra `t+1`**.
  - Simulação intrabar conservadora: Abertura → Extremo Contra → Extremo a Favor → Fechamento (na dúvida entre stop e alvo na mesma barra, **o stop é acionado primeiro**).
  - Custos e derrapagem:
    - **WIN:** 10 pts por contrato de custo + 1 tick (5 pts) de slippage em stops acionados fora da abertura; R$ 0,20/pt; 1 contrato no teste-base.
    - **WDO:** 0,5 pt por contrato de custo + 1 tick (0,5 pt) de slippage em stops fora da abertura; R$ 10,00/pt; 1 contrato no teste-base.

---

## 7. Protocolo de Validação Honesto e Critérios de Aceitação

### 7.1. Partição Temporal e Blindagem contra OOS Contaminado
- **IS (In-Sample — Escolha e Ajuste):** **02/01/2026 a 31/07/2026 (jan–jul).** Toda escolha de tese, gatilho (G1–G4) e perfil de saída (S1/S2) é feita **exclusivamente** olhando jan–jul.
- **Walk-Forward Interno no IS:** Divisão em `jan–abr` (treino) vs `mai–jul` (validação interna) para descartar configurações que concentram todo o resultado em um único trimestre.
- **OOS Histórico (ago–nov: 01/08/2026 a 11/11/2026):** Como este período já foi inspecionado repetidas vezes nas baterias anteriores de 12/11, ele está **estatisticamente contaminado para seleção**. Será **reportado com transparência**, mas **não pode ser usado para escolher qual variante vence**.
- **Pregões ao vivo recentes (12/11 e 13/11):** Usados apenas como **teste de sanidade mecânica** (verificar se o código reproduz exatamente a leitura visual do dia 13/11), nunca como métrica de aprovação.

### 7.2. Testes de Placebo (Controles Negativos Obrigatórios em jan–jul)
Para provar que o edge vem da combinação *Divergência V3.2 + Zona + Gatilho* e não de um viés direcional ou do gatilho sozinho:
1. **Placebo P1 (Sem Divergência):** Aplicar exatamente o mesmo gatilho (G1–G4) e filtro NWE em pivôs do ZigZag `1,2 × ATR` na Wall/Extremo do dia onde **não há divergência V3.2**. O candidato só é válido se superar P1 com folga em PF e Ret/DD.
2. **Placebo P2 (Direção Invertida):** Entrar na direção oposta ao sinal (mesmo stop/alvo simétrico antes de custos). Deve apresentar expectativa negativa.
3. **Placebo P3 (Walls Deslocadas / Falsas):** Para variantes que usam âncora de `Wall`, deslocar os níveis de Wall em `+250 pts` (WIN) / `+5,0 pts` (WDO) ou permutar as Walls entre dias. (Lembrando que o `I3` foi reprovado em 12/11 justamente porque mantinha o resultado com Walls falsas).

### 7.3. Métricas Reportadas e Teste de Estresse
- **Métricas individuais (1 contrato, IS jan–jul, WF mai–jul e OOS ago–nov):** Número de trades (`N`), Win Rate (`WR%`), Profit Factor (`PF`), Lucro Líquido (R$), Max Drawdown (`DD`), `Ret/DD`, consistência mensal (% de meses positivos), estabilidade `H1/H2`.
- **Métricas de Carteira Incremental (`ESP_DIV_V22_WIN [2 ct] + Add-on [1 ct]`):**
  - Correlação do PnL diário com o `ESP_DIV_V22_WIN` de produção (252 trades).
  - Taxa de sobreposição temporal (% de barras posicionadas simultaneamente).
  - Ganho marginal no `Ret/DD` e variação do `DD` máximo da dupla em `jan–jul`.
- **Estresse de Custo/Slippage:** Rodar com custo dobrado (`20 pts` no WIN / `1,0 pt` no WDO + 2 ticks de slip no stop). A estratégia deve permanecer lucrativa (`PF > 1,10`) no cenário de estresse.

### 7.4. Critérios Objetivos de Aceitação (Portão para Sombra / Paper Live)
Um candidato da grade só avança para acompanhamento em **Sombra (Paper Live)** se cumprir **simultaneamente em IS (jan–jul)**:
1. **Amostra mínima:** `N >= 40` trades em `jan–jul` (pelo menos ~6 trades/mês adicionados ao especialista).
2. **Qualidade standalone (IS jan–jul):** `PF >= 1,35`, `Ret/DD >= 4,0`, ambos os subperíodos (`jan–abr` e `mai–jul`) positivos, e pelo menos 5 dos 7 meses de `jan–jul` no azul.
3. **Superação dos Placebos:** `Ret/DD` e `PF` superiores ao Placebo Sem Divergência (P1) e ao Placebo de Walls Deslocadas (P3).
4. **Valor Aditivo na Carteira (`E22 Prod + Add-on` em jan–jul):**
   - Correlação diária com `ESP_DIV_V22_WIN` `<= 0,35`.
   - Não aumentar o Drawdown máximo do `ESP_DIV_V22_WIN` em mais de **15%** (em R$), **ou** elevar o `Ret/DD` combinado de `jan–jul` acima dos **7,50** atuais do especialista isolado.
5. **Estágio Final (Validação Real):** Nenhum candidato entra operando ordens reais direto do backtest. O vencedor aprovado no portão acima entra em **Sombra / Paper Live por no mínimo 20 pregões**, exatamente como recomendado para `I5` e `V1a` em 12/11.

---

## 8. O que NÃO Fazer (Guardrails Explícitos)

1. **NÃO alterar nem reotimizar o `ESP_DIV_V22_WIN`:** A regra de 252 trades (`core/especialista_v22.py`) é o pilar da carteira e não será modificada.
2. **NÃO ativar o complementar `I3`:** Já foi auditado e reprovado em [VALIDACAO.md](file:///C:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/research/div_master/especialistas/win_especialista/VALIDACAO.md) (degrada ago–nov da carteira e falha no teste de Walls falsas).
3. **NÃO tratar números de vitrine de `I5` (Ret/DD 5,46), `V1a` (Ret/DD 7,0) ou `B_dw_ex10` (Ret/DD 8,96) como prontos para produção:** `I5` e `V1a` já tiveram seu desconto de seleção medido na validação independente, e `B_dw_ex10` (`flow_breakout`) ainda não passou por auditoria independente de placebos.
4. **NÃO reativar o módulo de abertura (`open_module=True`) por trás dos panos:** O motor oficial é `V32_PROD` (`open_module=False`). Qualquer add-on deve usar exatamente os candidatos que o usuário enxerga no painel 5176.
5. **NÃO usar 13/11 (nem ago–nov) para calibrar parâmetros:** 13/11 serve para diagnosticar por que a máxima das 13:20 e a super-confluência das 12:00 foram ignoradas, mas a decisão de destravá-las depende da estatística em `jan–jul`.

---

## 9. Riscos Técnicos e Operacionais

- **Armadilha da Super-Confluência (`super=True`):** Em 13/11, a super-confluência (`Wall + Extremo`) às 12:00 no WIN e às 13:20 no WDO funcionou muito bem. Porém, na construção original do especialista, descartar `super=True` melhorou o Ret/DD histórico porque muitas vezes o rompimento do extremo do dia junto de uma Wall indica *breakout* direcional forte (o mercado atropela a Wall). Se a Tese 1 (`G1`) mostrar em `jan–jul` que `super=True` puro degrada a expectativa, o gatilho mais exigente (`G2` — rompimento da barra + virada de fluxo) será essencial para filtrar os atropelos.
- **Ausência do Módulo de Abertura no WDO:** Sem `open_module`, o ZigZag `1,2 × ATR` precisa de uma perna prévia formada no dia para ter `F1`. Isso reduz naturalmente o número de sinais entre 09:30 e 10:15 no WDO.
- **Fidelidade da Onda (*Fluxo Smart Money*) ao vivo vs. histórico:** No backtest, `sig_bars` vem do histórico exportado; ao vivo no painel 5176, `smart_swing_wave` é alimentada em tempo real. Qualquer gatilho que dependa de `wave[t] - wave[t-1]` (como `G2` e `G3`) deve ser verificado quanto à estabilidade da onda no fechamento da barra M5.

---

## 10. Ordem de Trabalho Proposta (Somente em `research/`, após aprovação)

Quando você autorizar a execução da pesquisa, o trabalho será feito **exclusivamente** dentro de um diretório isolado `research/div_master/setup_v32/` (zero alteração em `core/`, dashboard ou configs):

1. **Etapa 1 — Sanidade e Auditoria de Descarte (`diagnostico_descartes.py`):**
   - Contabilizar em `jan–jul` (e separar `ago–nov` apenas informativo) todos os candidatos gerados por `V32_PROD` que o `ESP_DIV_V22_WIN` recusou, classificando o motivo exato do descarte (`super=True`, `seq > 1` por extensão do mesmo `F1`, `seq > 1` de novo `F1`, filtro `NWE50`, ou janela de horário). Verificar também a reprodução exata do dia 13/11.
2. **Etapa 2 — Implementação dos Gatilhos e Simulador Coexistente (`motor_addon.py`):**
   - Implementar as funções causais para as Teses 1, 2 e 3 (`G1` a `G4`, saídas `S1`, `S2a`, `S2b`) acopladas ao estado de posição do `core/especialista_v22.run` (respeitando bloqueio de sobreposição e sinais opostos).
3. **Etapa 3 — Execução da Grade Enxuta em IS (`jan–jul`) + Placebos (`avaliar_is.py`):**
   - Rodar as 12 configurações de WIN e 8 de WDO em `jan–jul`, calcular walk-forward interno (`jan–abr` / `mai–jul`), rodar os 3 placebos (`P1`, `P2`, `P3`) e o estresse de custo dobrado.
4. **Etapa 4 — Relatório Cético (`research/div_master/setup_v32/RESULTADOS.md`):**
   - Consolidar a tabela comparativa (IS, WF interno, placebos, correlação com `ESP_DIV_V22_WIN` de 252 trades e leitura informativa de `ago–nov` + `12–13/11`). Se nenhuma variante passar nos critérios da Seção 7.4, a recomendação será manter apenas o especialista atual.

---

## 11. Perguntas para Decisão do Usuário (com Defaults Sugeridos)

Para destravar o início da Etapa 1 de pesquisa, confirme ou ajuste os 4 pontos abaixo:

1. **Escopo de Ativos (WIN apenas vs. WIN + WDO):**
   - *Pergunta:* Você quer que a pesquisa priorize apenas o **Add-on de WIN** (complementando o `ESP_DIV_V22_WIN`) ou devemos rodar em paralelo a **Tese 3 de WDO** (ciente de que no WDO usamos o `V32_PROD` sem módulo de abertura)?
   - *Default sugerido:* **Testar ambos em separado** (prioridade 1 para o Add-on WIN; Tese 3 de WDO avaliada à parte, com exigência de passar no placebo de Walls deslocadas).
2. **Regra de Coexistência na Mesma Direção (Quando o Especialista já está posicionado):**
   - *Pergunta:* Se o `ESP_DIV_V22_WIN` (2 contratos) já estiver em um trade aberto e surgir um novo sinal válido do Add-on na mesma direção, você prefere bloquear totalmente a nova entrada ou permitir adicionar 1 contrato caso o especialista já esteja protegido no Break-Even (`+20 pts`)?
   - *Default sugerido:* **Bloquear totalmente enquanto o especialista estiver posicionado**, permitindo que o Add-on opere apenas quando o especialista estiver *flat* (menor risco de cauda; medimos a variante "permitir após BE" apenas como comparação secundária).
3. **Alvo Preferencial do Add-on (Perfil S1 vs. Perfil S2):**
   - *Pergunta:* No Add-on, você prefere manter a mesma filosofia de saída do especialista (S1: sem alvo fixo, saindo por BE `+180→+20` ou tempo de 12 barras) ou prefere que o Add-on realize lucro no toque da linha/banda da `NWE50` ou próxima `Wall` (S2)?
   - *Default sugerido:* **Testar S1 vs. S2a (NWE50) vs. S2b (próxima Wall)** dentro da grade enxuta em `jan–jul`, pois trades de recaptura de extremo do dia costumam devolver até a média (`NWE50`).
4. **Relação com os candidatos da rodada de 12/11 (`I5` e `flow_breakout`):**
   - *Pergunta:* Deseja manter `I5` e `B_dw_ex10` fora deste estudo para focar exclusivamente nas marcações de topo/fundo do motor `V32_PROD` (Teses 1, 2 e 3), ou quer incluí-los na mesma tabela comparativa como linha de base?
   - *Default sugerido:* **Focar nas Teses 1, 2 e 3 (reversão nos extremos marcados pelo V3.2)** e usar os números já conhecidos do `ESP_DIV_V22_WIN` (252 trades) como única linha de base obrigatória.

---

## 12. Próximo Passo

Aguardo sua validação deste plano e das 4 respostas (ou aprovação dos defaults sugeridos). **Nenhum arquivo foi criado ou modificado.** Assim que autorizado, iniciaremos pela **Etapa 1** em `research/div_master/setup_v32/`.
