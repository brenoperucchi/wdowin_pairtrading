# Planejamento — Setup Divergência 3 Motores (11/11/2026)

Base da ideia: `INVESTIGACAO.md` (só jan–jul). Sinal = divergência F1→F2 / T1→T2 do Sniper 5176 (barras do
Profit, onda dos 3 motores, `detect_visual_swing_divergences`), sem precisar de entrada de setup.

## 1. Filtros (hipóteses fechadas; níveis fixos, sem otimizar limiar)
| Código | WIN | WDO |
| :-- | :-- | :-- |
| NWE | NWE80 entre 0,10 e 0,41 da meia-banda, do lado contra o trade | NWE80 ≥ 0,25 |
| TEND | não operar contra NWE50 com inclinação ≤ −1 ATR em 6 barras | idem |
| PA | pavio de rejeição ≥ 0,46 da barra e barra ≤ 1,2 ATR | corpo da barra do sinal contra o trade |
| PERSEG | entrada até 1 ATR do pivô F2 | idem |
| FLUXO | institucional e varejo da barra fora do quartil mais a favor | varejo contra (ret ≤ −34) |
| HORA | sem 09h | sem 09h |
| SEQ | não operar a 1ª divergência do dia na mesma direção | idem |

## 2. Entradas
E0 abertura da barra seguinte · E1 stop 1 tick além da máxima/mínima da barra do sinal, vale 2 barras ·
E2 limite no meio da barra do sinal, vale 3 barras · E3 barra seguinte fecha a favor → entra na abertura da próxima.

## 3. Saídas (regras MT5: stop antes do alvo na mesma barra; gap preenche na abertura; na barra de entrada só conta
o stop; BE só se a abertura seguinte passar; fecha 17:25; custos WIN 10 pts, WDO 0,5 pt por contrato)
| | WIN | WDO |
| :-- | :-- | :-- |
| Stop | fixo 200 · fixo 260 · pivô F2 + 30 (entre 100 e 300) | fixo 8 · fixo 10,5 · pivô F2 + 1 (entre 3 e 12) |
| Alvo | centro NWE50 (dinâmico) · banda oposta NWE50 · fixo 450 · fixo 750 · 2 lotes (centro NWE50 + 750) | centro NWE50 · banda oposta NWE50 · fixo 10 · fixo 16 · 2 lotes (centro + 16) |
| Proteção | BE {não, em 1R → +custo} · trailing {não, stop na banda NWE30 do lado do trade} | idem |
| Tempo | máx. 24 ou 48 barras | idem |

## 4. Gestão
Posição {LIVRE, UM_POR_VEZ} · meta diária causal {não, WIN R$ 90/contrato, WDO R$ 120/contrato}.

## 5. Protocolo (jan–jul já foi usado para descobrir as hipóteses)
1. Grade só em jan–jul: combinações de até 3 dos 7 filtros (64) × 4 entradas × saídas × gestão, por ativo.
   Score = Ret/DD trade a trade com ≥ 150 trades e lucro > 0, e lucro nas duas metades (jan–abr, mai–jul).
2. Platô = mediana da config e das vizinhas (tirar/pôr um filtro, trocar o stop, trocar o tempo). Fica a de maior platô.
3. Placebo, exigindo p < 0,10 nos dois: (a) divergências sorteadas na mesma quantidade por (mês, direção) → mede
   o filtro; (b) barras quaisquer sorteadas → mede a divergência.
4. Ago–6/nov uma vez (trava `results/oos_log.json`). Ressalva: esse período já foi visto uma vez para a entrada direta
   sem filtro; os filtros são novos, mas é a segunda vez que se usa o período.
   Aprovação: PF ≥ 1,3, lucro > 0, ≥ 3 de 4 meses positivos.
5. Se aprovar: papel ao vivo com regras congeladas a partir de 12/11, até 60 trades por ativo (≈ 4–6 semanas).
   Para seguir: PF ≥ 1,2 no papel.
6. Relatório: sozinho, comparado ao Sniper 5176 corrigido, e os dois juntos (correlação, DD, meses).

## 6. Volume esperado
Pelas combinações da investigação: WIN ~1,4–1,9 e WDO ~1,8–2,7 trades por dia (sobra 30–40% das divergências),
contra ~2 por dia do Sniper 5176 (os dois ativos somados).
