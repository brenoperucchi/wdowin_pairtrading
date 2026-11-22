# Validação independente do setup WDO "V1a" (12/11/2026)

A regra foi reescrita do zero a partir da descrição trazida pelo usuário, sem o script que a encontrou. Os scripts são `validar.py` e `detalhe.py`, e a grade está em `results/grade.csv`. O período é 02/01–11/11 (211 pregões), com 1 contrato, custo de 0,5 pt e stop 1 tick pior.

## 1. Reprodução
| Variante | Informado | Reproduzido aqui |
| :-- | :-- | :-- |
| TP fixo 12 | 190 tr · R$ 3.985 · DD 580 · Ret/DD 6,87 · 11/11 | **190 tr · R$ 3.985 · DD 580 · Ret/DD 6,87 · 11/11 (idêntico)** |
| ProxWall, lido ao pé da letra (aborta se a próxima Wall está a < 2,5) | 184 tr · R$ 4.498 · 7,62 | 165 tr · R$ 3.475 · 5,99 |
| ProxWall ignorando as Walls a < 3 pts e mirando a seguinte | 184 tr · R$ 4.498 · 7,62 | 188 tr · R$ 4.560 · 7,86 (quase igual) |
| Wall + MidWall | 179 tr · Ret/DD 7,49 | **267 tr · Ret/DD 1,13 (não reproduz)** |

## 2. O efeito é real
- **Placebo de Walls** (os mesmos níveis deslocados, 10 sorteios): Ret/DD mediano −0,40, máximo 1,58. O real fica em 6,0–6,9. Sem as Walls verdadeiras, não funciona.
- **Direção invertida:** −R$ 4.205 (Ret/DD −0,95).
- **Execução** (o alvo é uma ordem limite):

| Variante | Alvo só passando 1 tick | + custo 2× e stop 2 ticks |
| :-- | :-- | :-- |
| ProxWall | Ret/DD 6,82 | 4,39 |
| TP 12 | Ret/DD 5,67 | 3,38 |

  A entrada é a mercado, então o problema da fila que derrubou a ordem limite na Wall não se aplica aqui.

## 3. O número de vitrine está inflado pela escolha
- **Grade:** 528 vizinhos com ≥ 100 trades (SL, alvo máximo, zona, ext30, tempo).
  - o Ret/DD mediano é 0,74;
  - só 2 combinações chegam a ≥ 7;
  - o V1a está no **percentil 99**.
- **Walk-forward** (escolhe em jan–jul, mede em ago–nov):
  - o melhor de jan–jul faz Ret/DD 3,01 em ago–nov;
  - os 20 melhores de jan–jul ficam com Ret/DD mediano de **2,9** em ago–nov, todos positivos.
- **ago–nov favoreceu a família inteira:** as 528 combinações são positivas nesse período (mediana 1,86).
  - Só jan–jul, o V1a faz 2,9–4,7 (ProxWall) e 4,15 (TP 12).
  - **Expectativa realista: Ret/DD de 3 a 4, não 7,6.**

## 4. Depende de três escolhas
| Sem… | Ret/DD |
| :-- | --: |
| módulo de abertura (o motor oficial da carteira) | **0,92** |
| filtro ext30 > 0 | 1,52 |
| pular a hora 11 | 2,17 |

- **Horário:** o lucro está concentrado nas entradas das 9h e 10h (R$ 3.380 de R$ 3.985 no TP 12).
- **Módulo de abertura:** 64 trades só existem com ele, sendo 53 deles às 9h (+R$ 2.460). Isso é justamente o módulo que foi retirado do motor oficial em 12/11.
- **Hora 11:** o corte já existia no Sniper WDO (s/ 11h NY/PTAX), então não é uma escolha nova.
- **ext30 e módulo de abertura:** vieram da busca.

## Veredito
- **Validado em parte.** As Walls, a direção e o tratamento da fila confirmam um efeito real e não aleatório no dólar.
- **Ret/DD de 7,6 não é a expectativa:** é o melhor de uma grade grande. O walk-forward indica cerca de 3.
- **Fragilidade:** o resultado depende do módulo de abertura (o setup vive das divergências da abertura) e de dois filtros.
- **Recomendação:** congelar a regra como está (TP 12, que reproduz exatamente, ou ProxWall) e acompanhar ao vivo, em sombra, por ≥ 20 pregões antes de entrar na carteira.
- **Na carteira:** o WDO precisaria rodar o motor V3.2 **com** o módulo de abertura, separado do motor oficial.
