# Engenharia Reversa: Algoritmo Jumba Walls

## Resumo

O Jumba Walls NAO e um simples "top N por GEX". E um **Grid completo** de
strikes convertidos, com 3 camadas de informacao:

---

## Camada 1: Walls (8 linhas verdes solidas)

Cada strike IBOV com intervalo de **1.000 pontos**, convertido para WIN:

```
K_WIN = K_IBOV x (F_WIN / S_IBOV)
```

Onde:
- `F_WIN` = Preco atual do contrato futuro WIN (ex: WINM26)
- `S_IBOV` = Preco spot do indice IBOVESPA

O fator tipicamente fica entre **1.005 e 1.040** (custo de carregamento).

**Width** atribuido pelo |GEX| relativo do strike:
- Width 3 = Wall principal (maior concentracao de OI/GEX)
- Width 2 = Secundaria
- Width 1 = Terciarias

## Camada 2: MidWalls (7 linhas cinzas tracejadas)

Exatamente o **ponto medio** entre cada par de Walls consecutivas.
Equivalem a strikes de 500 em 500 do IBOV.

```
MidWall[i] = (Wall[i] + Wall[i+1]) / 2
```

## Camada 3: Niveis Derivados (Market Gamma Curve)

Calculados varrendo a funcao GEX_total(S_hyp) de 0.80*F ate 1.20*F:

- **MaxGamma** (verde, espessa): S_hyp onde GEX_total e maximo (positivo)
- **MinGamma** (vermelho, espessa): S_hyp onde GEX_total e minimo (negativo)
- **GammaFlip** (amarelo): S_hyp onde GEX_total cruza zero

O GammaFlip e particularmente importante:
- Acima do Flip: dealers estao "long gamma" (hedgeiam vendendo rallies -> amortece volatilidade)
- Abaixo do Flip: dealers estao "short gamma" (hedgeiam comprando quedas -> amplifica volatilidade)

---

## Validacao Numerica

Comparacao com output real do Jumba Trader (mesmo dia/hora):

| Strike IBOV | Jumba Real  | Nosso Engine | Erro   |
|-------------|-------------|-------------|--------|
| 184.000     | 186.870,81  | 186.870,80  | 0,01   |
| 185.000     | 187.886,41  | 187.886,40  | 0,01   |
| 186.000     | 188.902,02  | 188.902,00  | 0,02   |
| 187.000     | 189.917,62  | 189.917,60  | 0,02   |
| 188.000     | 190.933,21  | 190.933,20  | 0,01   |
| 189.000     | 191.948,81  | 191.948,81  | 0,00   |
| 190.000     | 192.964,42  | 192.964,41  | 0,01   |
| 191.000     | 193.980,02  | 193.980,01  | 0,01   |

**Erro maximo: 0,02 pts** (arredondamento de ponto flutuante).

---

## Mapeamento de Cores (MQL5)

| Variavel      | Cor MQL5  | Hex       | Uso                          |
|--------------|-----------|-----------|------------------------------|
| clWall       | clLime    | #00FF00   | Walls principais             |
| clMidWall    | clGray    | #808080   | MidWalls                     |
| clMaxGamma   | clGreen   | #00FF00   | Pico de gamma positivo       |
| clMinGamma   | clRed     | #FF0000   | Pico de gamma negativo       |
| clFlip       | clYellow  | #FFFF00   | Ponto de cruzamento do GEX   |

---

## Formato de Output (MQL5 BEGIN...END)

O Jumba exporta no formato compativel com indicadores MQL5:

```
line{N} := {valor_K_futuro};
line{N}Color := {cor};
line{N}Width := {1|2|3};
line{N}Style := 0;
```

Nosso engine publica via Firebase em JSON equivalente.
