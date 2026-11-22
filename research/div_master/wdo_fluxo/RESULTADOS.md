# Dólar: o problema é a Wall ou o fluxo? (12/11/2026)

O script é `teste.py` e os resultados estão em `results/fluxos.csv`. Testa a mesma máquina do especialista V3.2 no WDO (02/01–11/11), trocando só a série de fluxo que define a divergência.

## O que foi testado
- **Séries de fluxo (10):**
  - atual;
  - componentes isolados: Wyckoff, porte, institucional, delta/CVD, institucional agressor, institucional passivo, varejo invertido;
  - dois placebos: fluxo **aleatório** e **SÓ WALL**, sem nenhuma condição de fluxo (todo pivô na Wall que passa pela regra de preço vira sinal).
- **Âncora:** Wall/MidWall ou extremo do dia, e só Wall/MidWall.
- **Filtros:** a regra do especialista, ou solto (todos os gatilhos).
- **Saídas:** 24 combinações por série.
  - SL de 5, 7 ou 10 pts;
  - alvo na próxima Wall ou sem alvo;
  - BE de 4→0,5 ou sem BE;
  - tempo de 12 ou 24 barras.

## Resultado
- **Com custo de 0,5 pt:** 940 combinações e só 5 positivas. Nenhuma série de fluxo bate o placebo aleatório.

| Série | PF mediano (regra / solto) | Melhor caso escolhido em jan–jul |
| :-- | :-- | :-- |
| atual | 0,68 / 0,73 | −R$ 615 a −R$ 2.488 |
| delta (CVD) | 0,69 / 0,78 | +R$ 1.930, mas com Ret/DD de 0,02 em jan–jul |
| **aleatório (placebo)** | 0,76 / **0,84** | +R$ 1.072 |
| **SÓ WALL (sem fluxo)** | 0,64 / 0,81 | −R$ 1.005 a −R$ 3.275 |

- **Sem custo nenhum:** o PF mediano fica entre 0,72 e 0,97. O "SÓ WALL" fica em 0,72–0,94, e o aleatório ainda fica à frente (0,85–0,97).
- **Leitura:**
  - A entrada de **reversão na Wall**, com retomada do nível no fechamento, não tem vantagem no dólar nem antes dos custos, com ou sem fluxo.
  - O que falha não é o fluxo, é a ideia de entrar contra o movimento na Wall.
  - O custo do WDO também pesa mais: 0,5 pt é cerca de 12% da amplitude típica de uma barra de 5 minutos, contra cerca de 4% no WIN.

## Onde as Walls do dólar funcionam
- **No Sniper WDO (PF 1,55):** a Wall é usada como **alvo** a partir das entradas dos setups (WDO_01/05/07/10). O preço é atraído até a Wall, mas virar nela não paga.
- **Próximo teste sugerido:** usar a Wall do dólar como ímã ou alvo, com entradas a favor do movimento em direção à próxima Wall e rompimentos, em vez de reversão.
