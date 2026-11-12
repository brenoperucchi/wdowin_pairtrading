# Pré-registro — quais versões somar ao Sniper 5176 (11/11/2026)

Pergunta: alguma das versões de `research/div_gate/versions.py` que hoje **não** entra no Sniper 5176 melhora a
carteira (e aumenta o número de trades) se passar pelo **mesmo** filtro do Sniper?

## Base (fica igual)
Sniper 5176 corrigido (auditoria, versão B, sem barra do futuro): `research/audit_5176/audit_sniper.py`.
- WIN: trades dos setups do JSON (EST_01/04/07/13/14/15/16, WIN_E2) → filtro **3 motores** da barra anterior →
  divergência visual F1→F2/T1→T2 (`detect_visual_swing_divergences`, tol 2, só até a barra anterior) →
  saída 2 lotes (NWE30 260–750 + 750, BE +180→+20) → 09:05–16:45, sem 12:00–12:55, meta R$ 180.
- WDO: WDO_01/05/07/10 → divergência visual (tol 2) → saída original → 09:00–17:00, sem 11:00–11:55, meta R$ 120.
  (O 5176 não aplica o 3 motores no WDO; aqui também não.)

## Candidatas a somar (48)
Trades do runner (regras MT5) em `research/sniper2/results/pool_*.csv`:
- versões que não estão na base: WIN EST_07_EA, WIN_S02/S04/S05/S06/S09/S10/S11/S16; WDO WDO_02, WDO_09,
  WDO_S04/S06/S08/S09/S11/S13/S15 — cada uma **com** e **sem** o filtro de fluxo próprio (36);
- versões que já estão na base, na variante **sem** filtro de fluxo (só as entradas a mais) (12).
Cada candidata entra como mais uma fonte de entradas, sem duplicar (data, horário, direção) já existentes, e passa
exatamente pelo mesmo caminho da base (3 motores no WIN, divergência, saída, horário, meta).

## Regras (congeladas)
1. Seleção só em jan–jul (IS). Métrica = carteira inteira (WIN 2 contratos + WDO 1), Ret/DD trade a trade.
2. Uma candidata só pode entrar se as entradas que ela acrescenta tiverem no IS: ≥ 15 trades, PF ≥ 1,3 e lucro > 0
   nas duas metades (jan–abr e mai–jul).
3. Seleção gulosa: a cada rodada entra a candidata elegível que mais sobe o Ret/DD do IS, desde que o lucro
   também suba; para quando nenhuma sobe o Ret/DD.
4. OOS ago–6/nov uma vez, base vs base + escolhidas. Aprovação: as entradas acrescentadas com lucro > 0 e PF ≥ 1,3
   no OOS, e Ret/DD da carteira no OOS não pior que o da base.
5. Ressalva: as regras da base (tol, horários, meta) foram ajustadas no ano todo; o teste limpo é o do acréscimo.
