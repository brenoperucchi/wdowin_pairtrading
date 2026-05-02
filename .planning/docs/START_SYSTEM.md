---
description: Inicializa o sistema completo (Backend FastAPI + Dashboard React) nas portas corretas
---

# Inicialização do Sistema WIN×WDO Regime Monitor

## Configurações Fixas do Projeto

| Componente | Porta | Comando | Diretório |
|---|---|---|---|
| Backend (FastAPI/Uvicorn) | **8080** | `python server.py` | `wdo win pair trading/` |
| Frontend (Vite/React) | **5174** | `npm run dev` | `wdo win pair trading/regime-dashboard/` |

- **MT5 Path**: `C:/Program Files/MetaTrader 5 Terminal/terminal64.exe` (definido em `core/config.py`)
- **vite.config.js** já tem `server.port: 5174` configurado

## Estrutura do Projeto

```
wdo win pair trading/
├── core/               # Módulos de produção
│   ├── config.py       # Configurações centralizadas
│   ├── signals.py      # Funções de sinal e classificação
│   ├── mt5_client.py   # Conexão MT5 e beta state machine
│   ├── hmm_background.py  # Thread HMM M30
│   ├── kalman_filter.py    # Filtro Kalman beta
│   └── trade_engine.py     # Motor de execução Setup Matador
├── research/           # Scripts de backtest e otimização
├── data/               # Outputs gerados (heatmaps, CSVs, reports)
├── regime-dashboard/   # Frontend React
├── tests/              # Testes automatizados
├── server.py           # Thin controller FastAPI (~480 linhas)
└── trades.db           # Database SQLite
```

## Pré-requisitos

1. O MetaTrader 5 **DEVE** estar aberto e logado antes de iniciar o backend.

## Passos para Iniciar

### 1. Verificar/liberar processos antigos nas portas

```powershell
netstat -ano | findstr ":8080 " | findstr LISTENING
netstat -ano | findstr ":5174 " | findstr LISTENING
# Se houver, matar com: taskkill /PID <PID> /F
```

// turbo
### 2. Iniciar o Backend (FastAPI) na porta 8080

```powershell
cd "c:\Users\ryzen\Downloads\Antigravity\wdo win pair trading"
python server.py
```

// turbo
### 3. Iniciar o Frontend (Vite/React) na porta 5174

```powershell
cd "c:\Users\ryzen\Downloads\Antigravity\wdo win pair trading\regime-dashboard"
npm run dev
```

### 4. Verificar Conectividade

Abrir no navegador: **http://localhost:5174/**

## Troubleshooting

| Problema | Causa | Solução |
|---|---|---|
| Dashboard sem dados | MT5 não está aberto | Abrir MetaTrader 5 Terminal e fazer login |
| Backend travado | MT5_PATH errado | Verificar `core/config.py`: `C:/Program Files/MetaTrader 5 Terminal/terminal64.exe` |
| Vite na porta errada | Config | Verificar `regime-dashboard/vite.config.js` tem `port: 5174` |
