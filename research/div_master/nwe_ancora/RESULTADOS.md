# Divergência na média da NWE50 como 3ª âncora (12/11/2026)

**Pergunta:** operar também a divergência cujo F2 está na média da NWE50 aumenta o número de trades e o Ret/DD?

## Como foi testado
- **Script:** `teste.py`; os resultados estão em `results/grade.csv`.
- **Período:** WIN, 02/01–11/11, 213 pregões.
- **Âncora NWE:** vale só para as divergências que **não** têm âncora na Wall nem no extremo do dia, porque essas o especialista já opera.
  - **Compra:** a mínima do F2 fica entre a média − furo e a média + tolerância. A venda é o espelho.
- **Grade:**
  - tolerância: 40, 80 ou 120 pts;
  - furo: 80 ou 150 pts;
  - gatilho RETOMADA: fecha além da média + 20, com corpo a favor e além do fechamento do pivô;
  - gatilho DUPLO: fecha além da máxima ou mínima do pivô;
  - contexto NWE50: ligado ou desligado.
- **Filtros e saída:** iguais aos do especialista.
- **Referência:** o especialista atual é reproduzido exatamente (252 tr · R$ 9.214 · Ret/DD 14,05, sendo 7,50 em jan–jul e 9,99 em ago–nov).

## Resultado
- **Poucas divergências novas:** são 87 a 214 no período (0,4 a 1 por pregão). A maioria das divergências do motor já tem âncora na Wall ou no extremo do dia.
- **Âncora NWE sozinha:** 19 a 87 trades, de perto do zero a negativa. A melhor combinação (DUPLO, contexto ligado) fez 19 tr, PF 1,69 e R$ 476, mas perde em ago–nov (Ret/DD −0,45). Com furo de 150, todas perdem.
- **Como estratégia separada:** a carteira cai de Ret/DD 14,05 para 8,5–13,1.
- **No mesmo livro do especialista** (sequência do dia e um trade por vez compartilhados):
  - o melhor caso (DUPLO, sem contexto, tolerância ≥ 80, furo 80) chega a 262 tr, R$ 9.650 e Ret/DD 14,71;
  - são +10 trades e +R$ 436, mas ago–nov piora (9,02 contra 9,99);
  - é ruído, não melhora.

## Conclusão
Não vale incluir. A média da NWE não é um ponto de divergência com vantagem própria: acrescenta poucos trades, e eles não pagam.
