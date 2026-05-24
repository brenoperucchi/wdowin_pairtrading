---
status: pending
area: gex
created: 2026-05-07
---

# Aprimorar Calculo de IV (Newton-Raphson)

## Objetivo
Atualmente, o calculo do GEX utiliza uma Volatilidade Implicita (IV) fixa de 20% para todos os strikes, pois o CSV de "Posicoes em aberto" da B3 fornece apenas o Open Interest e nao os premios das opcoes.

O objetivo e implementar o metodo de Newton-Raphson para descobrir a IV real (Volatility Smile) de cada strike, garantindo precisao milimetrica nas linhas de MaxGamma, MinGamma e GammaFlip.

## Requisitos
1. Obter os premios (precos de fechamento/mercado) das opcoes IBOV.
   - Alternativa A: Buscar `IBOVK186` e afins diretamente no MT5.
   - Alternativa B: Processar o "Boletim Diario" ou "Cadastro de Instrumentos" da B3 para cruzar o prêmio com o OI.
2. Implementar a funcao `implied_volatility` em `black76.py` baseada em Newton-Raphson.
3. Atualizar `walls_calculator.py` para calcular o Gamma de cada strike usando sua IV especifica em vez de `iv=0.20`.
