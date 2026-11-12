# Motor v3.2 (12/11/2026)

O pedido saiu das marcações do usuário no WIN em 05/11. Ele marcou três divergências:
- venda: T1 09:00 → T2 11:25;
- compra: F1 09:15 → F2 09:40;
- compra: F1 12:15 → F2 14:00.

Em todas, o F1 é o pivô da perna com o fluxo mais extremo, o F2 é o último extremo de preço, e há uma divergência por perna.

## Regras

O v3.2 é o v3.1 (`modulo.engine_v32`) com três mudanças:
1. **F1:** é o pivô com a onda mais extrema da própria barra, entre os que passam no preço e no limiar. O v3.1 usa o mais recente.
2. **Sem reset do F1 depois de um sinal.** A regra de repetição do v3 continua valendo: com o mesmo F1, só vale um extremo de preço novo, e isso é uma **extensão** da mesma divergência.
3. **No painel:** das extensões do mesmo F1, aparece só a última, uma por perna. Ao vivo, a linha se estende quando o preço renova o extremo.

Garantia: com as opções do v3.1 (`f1="recent"`, `reset=True`, `used=True`), o v3.2 reproduz o v3.1.

## Resultado (`teste.py` → `results/variantes.csv`)

| Variante | Marcações de 05/11 | Linhas em 05/11 | Cobertura dos rótulos (bruta / 1 por perna) | Especialista | Sniper | Carteira Ret/DD (jan–jul) | Lucro | DD |
| :-- | :-: | --: | :-- | --: | --: | :-- | --: | --: |
| v2.2 (produção) | 2/3 | 18 | 77% | 9,9 | 23,5 | **23,9 (15,9)** | R$ 21.950 | R$ 918 |
| v3.1 | 1/3 | 8 | 57% | 11,6 | 9,8 | 13,7 (9,0) | R$ 16.201 | R$ 1.184 |
| **v3.2** | **3/3** | **4** | 59% / 32% | 5,8 | 18,1 | 19,0 (13,7) | R$ 14.502 | R$ 762 |
| v3.2 F1 k±1 | 2/3 | 4 | 59% / 30% | 8,0 | 13,5 | 12,5 (8,6) | R$ 16.029 | R$ 1.278 |
| v3.2 sem módulo de abertura | 2/3 | 3 | 59% / 36% | **14,2** | 15,0 | **25,4 (14,7)** | R$ 16.869 | **R$ 664** |
| v3.2 com reset | 2/3 | 6 | 52% | 9,6 | 13,4 | 16,7 (11,8) | R$ 14.710 | R$ 880 |

## Leitura

- **Visualmente**, o v3.2 é o mais limpo (cerca de 4 divergências por pregão) e o único que bate as 3 marcações de 05/11.
- **Rótulos antigos:** uma linha por perna derruba a cobertura (32%), porque nas sessões de rotulagem o usuário validou também as divergências intermediárias da mesma perna.
- **Para operar**, o v2.2 continua na frente em lucro e em jan–jul.
  - O v3.2 sem o módulo de abertura tem o melhor Ret/DD no período completo (25,4) e o menor DD, mas lucra R$ 5 mil a menos.
  - Em jan–jul ele empata com o v2.2 pelo critério (diferença abaixo de 10%), e o desempate pelos rótulos favorece o v2.2.
- **Decisão pendente:** unificar no v3.2 trocaria a carteira em produção. Por enquanto, o v3.2 está só no seletor do painel, para comparação visual.
