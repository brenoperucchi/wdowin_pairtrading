# GEX Engine — Jumba Walls Replicator
## Guia de Operacao Diaria

---

### Pre-Requisitos (ja configurados)

- [x] Python 3.x com `scipy`, `pandas`, `numpy`, `firebase-admin`, `MetaTrader5`
- [x] Arquivo `serviceAccountKey.json` na raiz do projeto
- [x] MetaTrader 5 instalado e com login ativo (para buscar precos)
- [x] Frontend React rodando (`npm run dev` na pasta `regime-dashboard`)

---

### Quando Executar

Executar **antes da abertura do mercado** (antes das 9:00 BRT) ou assim que a B3 liberar o arquivo.
O engine usa dados sincronizados do **último pregão às 17h00**:
- Preços (F_WIN, S_IBOV): Vela `M5` das `16:55` (cujo fechamento é a fotografia exata do fechamento do IBOV à vista às 17:00).
- Open Interest: CSV da B3 (posições em aberto correspondentes).

---

### Passo a Passo Diário

#### 1. Baixar o boletim da B3

Acesse a página de **Posições em Aberto** da B3:
```
https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/consultas/boletim-diario/boletim-diario-do-mercado/
```

Baixe o arquivo CSV do dia (geralmente disponível após **18h BRT**).

#### 2. Colocar o arquivo na pasta `gex/data/`

Copie o CSV para:
```
wdo win pair trading/gex/data/
```

O parser detecta automaticamente o arquivo mais recente.
Não precisa renomear nada. 

#### 3. Rodar a Automação Diária (Recomendado)

Basta dar um duplo clique no arquivo `GEX_DAILY.bat` na raiz do projeto.
Isso fará tudo automaticamente:
1. Conecta ao MT5 e busca os **preços das 17h00** (`M5` das `16:55`) para sincronia de F_WIN e IBOV.
2. Lê o CSV mais recente da B3.
3. Calcula GEX via Black-76 para cada strike.
4. Gera as 34 linhas (Jumba Walls) e publica no Firebase.
5. Faz o **commit no Git** salvando o histórico da versão diária.

#### Modo Python Manual (fallback)

Se o MT5 nao estiver aberto, passe os valores manualmente:
```powershell
python -m gex.engine.main <F_WIN> <S_IBOV>
```

Exemplo:
```powershell
python -m gex.engine.main 186610 183852
```

#### 4. Verificar no Dashboard

O dashboard React atualiza **automaticamente** (listener Firebase).
De um F5 se necessario. Voce vera:

- Walls (lime, solidas): Grid de strikes a cada 1000 pts do IBOV
  - Linha mais grossa = maior concentracao de GEX
- MidWalls (cinza, tracejadas): Ponto medio entre Walls
- MAX G (verde, grossa): Preco de maximo gamma positivo
- MIN G (vermelho, grossa): Preco de maximo gamma negativo
- G FLIP (amarelo): Onde o GEX net cruza zero

---

### Troubleshooting

| Problema | Solucao |
|----------|---------|
| "Nenhum arquivo encontrado" | Colocar CSV em `gex/data/` ou raiz do projeto |
| Walls em posicao errada | Verificar se F_WIN e S_IBOV estao corretos |
| MT5 retorna 0 | Verificar se o terminal esta aberto com login |
| IBOV nao disponivel | Normal — usa fallback F_WIN / 1.015 |
| MaxGamma/MinGamma deslocados | Normal com IV fixa 20%. Futuro: calibrar IV |
| Firebase 404 | Verificar `serviceAccountKey.json` |

---

### Estrutura da Pasta gex/

```
gex/
|-- __init__.py
|-- engine/
|   |-- __init__.py
|   |-- main.py              <- Orquestrador (CLI + auto MT5)
|   |-- mt5_prices.py        <- Busca precos do fechamento D-1
|   |-- b3_parser.py         <- Parser do CSV da B3
|   |-- black76.py           <- Motor matematico (Gamma)
|   |-- walls_calculator.py  <- Grid + MidWalls + Market Gamma Curve
|   +-- firebase_publisher.py <- Publica no Firebase
|
|-- data/
|   +-- (CSVs da B3 aqui)
|
+-- docs/
    |-- RUNBOOK.md            <- Este arquivo
    +-- REVERSE_ENGINEERING.md <- Eng. reversa do Jumba
```

---

### Comando Resumido

```powershell
# Modo automatico (MT5 busca precos)
python -m gex.engine.main

# Modo manual
python -m gex.engine.main 186610 183852
```
