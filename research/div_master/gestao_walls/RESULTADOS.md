# Gestão pelas Walls: SL atrás da Wall, BE ao cruzar a Wall, TP na Wall (12/11/2026)

Os detalhes estão em `teste.py`, `results/grade.csv` e `results/estresse.csv`.

## Como foi testado
- **Execução:** tick a tick em M1, 2 contratos, uma posição por vez.
- **Grade:** 281 gestões, combinando estas opções:
  - **Stop:** fixo de 200, atrás da Wall da entrada, atrás da Wall além do F2 (−20/40/60) ou no extremo do F2 −30.
  - **Alvo:** sem alvo, na próxima Wall (W1), na segunda Wall (W2), um lote em cada (W1+W2) ou W1 com o outro lote no tempo.
  - **BE:** o atual, ao cruzar a W1 ou em escada de Walls.
  - **Tempo:** 12 ou 24 barras.
- **Sinais:** os do especialista (252), "sem super · 10–16h" (385) e todos os gatilhos (704).
- **Referência:** a gestão atual reproduz o especialista (252 tr · R$ 9.214 · Ret/DD 14,05, sendo 7,50 em jan–jul e 9,99 em ago–nov).

## Resultado (sinais do especialista)
| Peça | Melhor resultado | Comparado à gestão atual |
| :-- | :-- | :-- |
| **SL atrás da Wall além do F2 (−20)** | Ret/DD 14,52 (7,82 / 9,99), R$ 9.314 | praticamente igual |
| SL atrás da Wall da entrada | mediana da grade pior que o SL fixo | pior |
| **TP na próxima Wall (W1)** | mediana do Ret/DD de 2,2 | muito pior: corta os ganhadores |
| TP na 2ª Wall (W2) | 11,4–13,0, com ago–nov caindo para 4,8–5,8 | pior |
| **BE ao cruzar a W1** | mediana de 4,6 | pior: as Walls são retestadas e o BE estopa cedo |
| BE em escada de Walls | mediana de 1,7 | o pior de todos |

- **Sinais mais largos:** a gestão por Walls também não libera mais trades.
  - Sem super · 10–16h: o melhor é 7,68, com ago–nov em 1,20.
  - Todos os gatilhos: o melhor é 2,93.
- **Único ganho:** veio de um stop que não é de Wall, o **extremo do F2 −30 (teto de 300) com 24 barras**.
  - No período completo dá Ret/DD 15,16 e R$ 10.488.
  - Melhora jan–jul (9,93 contra 7,50) e piora ago–nov (7,20 contra 9,99).
  - É mais resistente aos estresses de execução: 10,8 contra 8,2 com tudo junto.
  - É um resultado misto, não uma melhora clara.

## Conclusão
- Usar as Walls como referência para SL, BE e TP não melhora o especialista.
- O stop atrás da Wall dá o mesmo resultado do stop de 200, porque cai numa distância parecida.
- O alvo e o BE nas Walls pioram o resultado. Quando a divergência funciona, o preço costuma passar da próxima Wall, e as Walls são retestadas antes disso.
- Candidato para acompanhar ao vivo (sem trocar a produção): stop no extremo do F2 −30 com 24 barras.
