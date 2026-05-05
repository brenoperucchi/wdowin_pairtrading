# Coding Conventions

## Python (Backend)
- **Typing:** Type hints limitados. O projeto usa duck typing e formatação padrão sem uso obrigatório de ferramentas agressivas como `black` ou `mypy`.
- **Imports:** Imports absolutos com base na raiz da pasta (`from core.config import ...`).
- **Data:** Utilização intensiva de vetores `numpy` primitivos convertidos a partir de `pandas.DataFrame` para máxima performance de loop.
- **Log Errors:** O sistema mascara propositalmente exceptions em threads de polling contínuo (ex: `try: ... except Exception: pass`) para evitar logs poluídos, apesar desta prática precisar de reestruturação.

## JavaScript / React (Frontend)
- Componentes funcionais e Hooks.
- Estilização majoritariamente por object literals em `style={{...}}`.
- Não usa CSS-in-JS ou SCSS avançado; conta com um `index.css` master.
