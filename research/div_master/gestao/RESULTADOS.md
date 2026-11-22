# Gestão sobre todas as marcações V3.2 (12/11/2026)

O usuário perguntou se outra gestão de risco deixaria o especialista operar todas as 716 marcações V3.2 do WIN (02/01–11/11), ou quase todas. Hoje ele opera 222. Foram testadas as duas ideias dele:
- **(A) 3 contratos:** stop curto; o lote 1 sai rápido e leva os outros para o zero; o lote 2 sai na próxima Wall; o lote 3 é conduzido.
- **(B) preço médio:** 1 contrato na entrada, o 2º entra se o preço andar contra, com stop maior.

## Como foi testado
- **Fonte:** `explorar.py`, `analise.py` e `robustez.py`, com resultados em `results/`.
- **Entradas:**
  - `CONF`: a mercado na barra seguinte à confirmação da divergência; toda marcação tem.
  - `OPC`: no gatilho Opção C, como hoje.
- **Execução:** tick a tick em M1; custo de 10 pts por contrato; stop preenche 1 tick pior; uma posição por vez; saída às 17:25.
- **Referência:** a gestão atual reproduz exatamente o especialista (252 tr · R$ 9.214 · DD R$ 656).
- **Grade:** 145 gestões × 6 filtros × 2 entradas.
- **Seleção:** a escolha é feita em jan–jul e conferida em ago–nov. Ago–nov já foi muito usado, então não é um teste fora da amostra limpo.

## Resultado

### 1. Preço médio (B): descartado
Perde em todos os subconjuntos, inclusive no da regra atual. A melhor combinação dentro da amostra fica com PF 1,18 e perde dinheiro em ago–nov. Colocar mais um contrato contra a divergência aumenta o prejuízo das marcações que falham, e não recupera nada.

### 2. Três lotes (A): só funciona com alvo de 30 pts, e isso não sobrevive ao realismo de execução

Na simulação base, com todas as marcações e entrada na confirmação, a melhor gestão é:
- stop no extremo do F2 + 30, com teto de 150 pts;
- lote 1 com alvo +30, levando os outros para +20;
- lote 2 na próxima Wall;
- lote 3 com alvo de +600.

Ela dá **1.113 tr · R$ 8.659 · DD R$ 757 · Ret/DD 11,4**. Mas o alvo de +30 e o zero em +20 ficam a 2 ticks um do outro, e a M1 não mostra a ordem dos negócios dentro do minuto.

Estresses de execução (`robustez.py`):

| Gestão / filtro | Base | Alvo +1 tick | Stop 2 ticks | Caminho M1 contra | Entrada 1 tick pior | Tudo junto |
| :-- | --: | --: | --: | --: | --: | --: |
| 3L T1 30 · todas | 11,4 | 5,4 | 7,1 | **−0,5** | 2,9 | **−1,0** |
| 3L T1 60 · todas | 3,6 | 1,9 | 1,9 | −0,1 | 0,1 | −1,0 |
| 3L T1 30 · sem super 10–16h | 11,7 | 6,1 | 8,9 | **0,0** | 3,9 | **−1,0** |
| **Atual 2c · regra atual** | **14,1** | **14,1** | **12,9** | **14,1** | **9,0** | **8,2** |

(Ret/DD no período completo.)

**Leitura:**
- O ganho dos 3 lotes vem da ordem dos preços dentro do minuto. Com o caminho M1 desfavorável, ele desaparece. Com alvo de 60 ou 100 pts, a grade já não paga nem na simulação base.
- A gestão atual é a que aguenta todos os estresses, com Ret/DD 8,2 no pior caso. Ela não usa alvo curto, e o BE de +180 fica longe do preço.
- Na simulação base, os lotes 2 e 3 dão o resultado e o lote 1 fica negativo. A ideia de conduzir parte da posição tem algum mérito, mas não com um stop curto e um zero colado.

### 3. Por que nem toda marcação vira entrada: os filtros separam marcações boas de ruins
Os números abaixo usam a entrada na confirmação, com cada grupo inteiro e sem nenhum outro filtro:

| Grupo | Gestão atual 2c | 3 lotes (T1 60) |
| :-- | --: | --: |
| Com gatilho Opção C (1º/2º do dia) | 476 tr · PF 1,69 · +R$ 11.240 | PF 2,06 · +R$ 9.939 |
| 3º gatilho em diante | PF 1,08 · +R$ 668 | PF 1,35 · +R$ 1.769 |
| **Sem gatilho Opção C** | **285 tr · PF 0,19 · −R$ 15.224** | **PF 0,38 · −R$ 6.532** |
| Super-confluência | PF 0,78 · −R$ 4.130 | PF 1,21 · +R$ 2.175 |
| 16h em diante | PF 0,43 · −R$ 1.532 | PF 0,74 · −R$ 385 |
| Compra / venda | PF 0,78 / 1,09 | PF 1,08 / 1,34 |

- **Gatilho Opção C:** é o que separa as marcações boas das ruins. As marcações que nunca têm a retomada do nível perdem em qualquer gestão.
- **Causalidade:** "ter gatilho" só é conhecido depois da confirmação. Por isso, na entrada `CONF`, ele não pode ser usado como filtro (seria olhar o futuro). Os grupos acima servem para diagnóstico.
- **Quantidade × qualidade:** dá para operar mais relaxando filtros com a gestão atual, mas cada relaxamento derruba a qualidade:

| Filtros aplicados (gestão atual) | Trades | Ret/DD |
| :-- | --: | --: |
| Regra atual | 252 | 14,1 |
| Sem os filtros NWE50 e 3º gatilho | 385 | 6,7 |
| Só tirar a super-confluência | 413 | 5,2 |
| Todas com gatilho | 704 | 1,6 |

## Conclusão
- **Operar todas:** nenhuma gestão testada faz todas as marcações virarem uma estratégia robusta.
- **Preço médio:** está descartado.
- **3 lotes:** só parece bom com alvo de 30 pts, e esse resultado depende da ordem dos preços dentro do minuto.
- **Validação com ticks:** o único jeito de confirmar ou descartar de vez os 3 lotes com alvo curto é testar com ticks reais (`.trd` do Profit). O modo de ticks reais do MT5 está quebrado.
- **Especialista atual:** opera pouco porque o gatilho Opção C e os filtros cortam justamente as marcações que perdem. Ele continua sendo a melhor e a mais robusta configuração.
