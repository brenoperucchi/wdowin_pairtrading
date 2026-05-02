---
created: 2026-04-09T15:34:09.166Z
title: Avaliar resultados modelos ML e validar abordagem direcional
area: research
files:
  - .planning/docs/SPEC_ML_DIRECTION.md
---

## Problem

Os modelos de Machine Learning (HMM, LSTM, XGBoost) foram rodados e o grid search foi executado conforme especificado em `.planning/docs/SPEC_ML_DIRECTION.md`. No entanto, o relato foi de que "ainda não cheguei num veredicto de que estamos fazendo a coisa certa". 

Falta confiança na tomada de decisão sobre os outputs. Precisamos rever os dados frios, comparar criticamente contra o baseline original (Setup Matador puro) e provar — ou desprovar — se a complexidade do ML Direcional de fato traz benefício prático e estatístico.

## Solution

TBD. (Como próximo passo provável: revisar metodicamente os resultados extraídos de `research/compare_models.py`, levantar métricas de significância e tomar a "Reavaliação Estratégica" citada no ROADMAP de forma orientada a dados para darmos um Go/No-Go nesta SPEC.)
