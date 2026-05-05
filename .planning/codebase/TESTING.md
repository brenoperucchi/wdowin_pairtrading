# Testing Framework

## Automação
Atualmente, o projeto WDO×WIN não possui uma suíte ativa de Test-Driven Development (TDD) via Pytest ou Jest integrada em CI/CD.

## Backtesting (Pesquisa)
- Os testes do modelo preditivo ocorrem na pasta `research/` ou usando bibliotecas matemáticas (ex: XGBoost, HmmLearn) exportando dados `Parquet`.
- Validação "Walk Forward Analysis" (OOS). 

## Validação de Tela
- Foi deixado intencionalmente um método de fallback `genFallback()` em `App.jsx` que gera Z-scores espúrios para simular UI quando a API do `server.py` está morta.
