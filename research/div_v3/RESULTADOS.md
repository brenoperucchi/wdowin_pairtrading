# Divergência v3 — etapa A, só jan–jul (11/11/2026)

**Fonte dos sinais:** `detect_divergences_v3`, a definição aprovada pelo usuário. Ela roda sobre o dataset congelado
`div_wall_v1` (barras do Profit e Walls do dia).

**Simulação:** a mesma do `research/div3m`: tick a tick em M1, regras MT5, custos WIN 10 pts e WDO 0,5 pt. Foram
testadas 4 entradas × 120 saídas × 2 modos de gestão × com/sem meta diária, sem filtros. Ago–nov não foi lido.

- Scripts: `sinais.py` e `bt_v3_is.py`.
- Saídas: `results/grid_is_sem_filtro_{WIN,WDO}.csv`, `results/sinais_is_*.csv` e `results/etapa_a.log`.

**Paridade com o painel:** batem 18 de 19 sinais em 05–06/11. A diferença é um sinal no limite, causado por pequenas
diferenças nos campos de fluxo entre o dataset e o cache do painel.

## Volume
| | Sinais jan–jul | Por dia | Detector antigo do Sniper |
| :-- | --: | --: | --: |
| WIN | 727 | 5,1 | 730 (5,1/dia) |
| WDO | 708 | 5,0 | 988 (6,9/dia) |

## Vantagem bruta (pontos 12 barras depois da entrada, sem custo)
| | jan–abr | mai–jul | Acerto |
| :-- | --: | --: | --: |
| WIN | −17 | −46 | 49% / 45% |
| WDO | −0,3 | −0,4 | 49% / 45% |

## Entrando em toda divergência (jan–jul)
| Entrada | WIN: PF entre as 120 saídas | WDO: PF entre as 120 saídas |
| :-- | :-- | :-- |
| Abertura da barra seguinte | 0,78–0,94 (nenhuma saída com lucro) | 0,78–0,93 (nenhuma) |
| Rompimento da barra do sinal | 0,71–0,92 (nenhuma) | 0,63–0,85 (nenhuma) |
| Limite no meio da barra do sinal | 0,78–1,04 | 0,83–1,14 |
| Confirmação (barra seguinte fecha a favor) | 0,83–1,05 | 0,73–0,93 |

Melhores configurações com pelo menos 150 trades e lucro nas duas metades:
- **WIN:** confirmação, SL pivô+30, alvo 750, 24 barras. PF 1,09, R$ 1.087, DD R$ 2.263, Ret/DD 0,5.
- **WDO:** limite no meio da barra do sinal, SL 10,5, alvo no centro da NWE50, 48 barras. PF 1,14, R$ 2.023,
  DD R$ 1.055, Ret/DD 1,9, acerto 78%.

## Por tipo de sinal (entrada na abertura, PF mediano entre as saídas)
| | WIN | WDO |
| :-- | :-- | :-- |
| F2 perto da Wall | 0,89 | 0,94 |
| F2 furou e voltou | 0,84 | 0,73 |
| 09h | 0,70 | 0,67 |
| 11h | 1,02 | 0,87 |
| 14h | 0,94 | 1,19 |
| 16h | 0,63 | 1,38 |
| 1ª do dia no sentido | 0,93 | 0,79 |
| Demais | 0,78 | 0,89 |

## Conclusão da etapa A
Com a definição certa, entrar em toda divergência ainda não dá lucro em jan–jul. Só o WDO com entrada limite e alvo no
centro da NWE50 fica levemente positivo (PF 1,14). O tipo "perto da Wall" é melhor que "furou e voltou" nos dois ativos.
As divergências das 9h foram as piores nos dois ativos.

# Etapa B: absorção rápida na Wall + divergência v3 (só jan–jul)
Script: `bt_abs_v3_is.py`. Log: `results/abs_v3.log`. Grade: `results/grid_is_abs_v3.csv.gz` (1.920 configurações por variante).

A absorção é a de `research/div_entry`: uma barra que encosta numa Wall ou MidWall e fecha do lado defendido, com
Wyckoff a favor, institucional passivo a favor e varejo contra. Entra quando ela aparece até N barras depois de uma
divergência v3 no mesmo sentido. A absorção sozinha serve de controle.

"Aprováveis" são as configurações com pelo menos 150 trades e lucro nas duas metades de jan–jul.

| Ativo | Variante | Sinais/dia | PF mediano | Melhor PF (≥150 tr) | Melhor Ret/DD | Aprováveis |
| :-- | :-- | --: | --: | --: | --: | --: |
| WIN | absorção até 12 barras após div v3, raio 100 | 2,2 | **1,01** | **1,70** | 3,9 | **433**/1.920 |
| WIN | absorção até 6 barras após div v3, raio 100 | 1,4 | 0,88 | 1,29 | 0,9 | 0 |
| WIN | absorção sozinha, raio 100 | 7,2 | 0,93 | 1,29 | 2,6 | 202 |
| WIN | absorção sozinha, raio 40 | 3,0 | 0,95 | 1,46 | 5,1 | 283 |
| WDO | absorção até 12 barras após div v3, raio 1,5 | 2,3 | 0,75 | 1,24 | 2,8 | 113 |
| WDO | absorção sozinha, raio 1,5 | 7,1 | 0,80 | 1,21 | 5,7 | 131 |

As variantes com janela de 0 ou 3 barras dão menos de 1 sinal por dia.

**Conclusão da etapa B:**
- **WIN:** a divergência v3 faz diferença. A absorção até 12 barras depois da divergência é a única variante com PF mediano
  acima de 1 entre as 1.920 saídas, e a que tem mais configurações aprováveis. Melhor configuração: entrada no rompimento,
  SL 200, alvo na banda oposta da NWE50, um trade por vez. Ela dá 165 trades, PF 1,61, R$ 2.651, DD R$ 672 e Ret/DD 3,9,
  com lucro nas duas metades.
- **WDO:** somar a divergência não acrescenta nada à absorção sozinha.

# Etapa C: validação do WIN absorção + v3 (`valida_abs_v3.py`, trava `results/oos_abs_v3.json`)
**Configuração escolhida em jan–jul pelo platô:**
- sinal: absorção na Wall até 12 barras depois de uma divergência v3;
- entrada: rompimento da barra de absorção;
- saída: SL 200, alvo 450, trailing NWE30, máximo de 24 barras;
- gestão: um trade por vez, meta diária R$ 90.

Platô 3,18 (322 de 1.920 configurações com platô > 0). Placebos: absorção sem divergência p 0,025; barras quaisquer
p 0,020. Passou nas duas etapas de jan–jul.

| Período | Trades | Acerto | PF | Lucro R$ | DD R$ | Ret/DD | Meses + |
| :-- | --: | --: | --: | --: | --: | --: | :-: |
| jan–jul | 172 | — | 1,33 | 1.369 | 365 | 3,76 | 6/7 |
| ago–6/nov | 66 | 33% | 0,93 | −133 | 516 | −0,26 | 2/4 |
| completo | 238 | 39% | 1,21 | 1.237 | 516 | 2,4 | 8/11 |

**Não aprovado.** Em ago–nov, a vantagem que existia em jan–jul (inclusive acima dos placebos) não se manteve.

# Etapa D: rompimento da Wall com o maior fluxo do dia (definição do usuário; só jan–jul)
**Sinal:** o fechamento atravessa uma Wall/MidWall (a barra anterior fechou do outro lado), e o fluxo da barra no sentido
do rompimento é o maior do dia até ali. Um sinal por nível e sentido no dia. Função: `sinais.breakouts`.

- **Fluxo "onda":** a onda smart money no maior valor do dia. Pega 5 dos 8 rompimentos que o usuário marcou como válidos
  e 3 dos 12 falsos.
- **Fluxo "força":** a força da barra (Wyckoff + porte + institucional) no maior valor do dia. Pega 3 de 8.
- **Controle:** rompimento sem condição de fluxo.

Script: `bt_rom_is.py`. Log: `results/rom.log`. Grade: `results/grid_is_rom.csv.gz` (1.920 configurações por variante).

| Ativo | Fluxo | Sinais/dia | Bruto 12 barras (jan–abr / mai–jul) | PF mediano | Melhor PF (≥150 tr) | Aprováveis |
| :-- | :-- | --: | :-- | --: | --: | --: |
| WIN | onda | 2,8 | +11 / −75 pts | 0,91 | 1,27 | 143 |
| WIN | **força** | 1,9 | **+94 / +8 pts** | **1,12** | **1,45** | **435** |
| WIN | sem fluxo (controle) | 8,4 | +15 / −16 pts | 0,95 | 1,19 | 223 |
| WDO | onda | 1,5 | ≈0 | 0,68 | 1,30 | 12 |
| WDO | força | 1,2 | ≈0 | 0,73 | 0,87 | 0 |
| WDO | sem fluxo (controle) | 5,2 | ≈0 | 0,75 | 1,28 | 66 |

**WIN com força**, melhor configuração em jan–jul:
- regras: entrada na abertura seguinte, SL 200, alvo na banda oposta da NWE50, 24 barras;
- resultado: 277 trades, PF 1,44, R$ 2.974, DD R$ 576, Ret/DD 5,2;
- ressalva: R$ 2.601 vieram de jan–abr e só R$ 373 de mai–jul.

**WDO:** a condição de fluxo não acrescenta nada ao rompimento.

# Etapa E: validação do WIN rompimento com força (`valida_rom.py`, trava `results/oos_rom.json`)
**Configuração escolhida em jan–jul pelo platô:**
- entrada: abertura seguinte;
- saída: SL 200, alvo na banda oposta da NWE50, sem BE, sem trailing, máximo de 24 barras;
- gestão: livre, sem meta.

Platô 3,99 (443 de 1.920 configurações com platô > 0). Placebos: rompimento sem fluxo p 0,010; barras quaisquer p 0,010.

| Período | Trades | Acerto | PF | Lucro R$ | DD R$ | Ret/DD | Meses + |
| :-- | --: | --: | --: | --: | --: | --: | :-: |
| jan–jul | 277 | 41% | 1,44 | 2.974 | 576 | 5,2 | 6/7 |
| ago–6/nov | 140 | 33% | 0,69 | −1.230 | 1.307 | −0,9 | 2/4 |
| completo | 417 | 39% | 1,16 | 1.744 | 1.331 | 1,3 | 8/11 |

Mensal (R$): jan 987 · fev 653 · mar 833 · abr 128 · mai 408 · jun −152 · jul 117 · ago 45 · set 13 · out −820 · nov −468.

**Não aprovado.** A vantagem existia no começo do ano e foi desaparecendo mês a mês.
