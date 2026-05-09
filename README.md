# WIN × WDO — Advanced Regime Monitor

Um dashboard profissional em tempo real para operações de **Statistical Arbitrage (Long/Short)** focado no par Mini Índice (WIN) e Mini Dólar (WDO) da B3. Esta versão avançada introduz **Cálculo Dinâmico de Beta (OLS)** e monitoramento rigoroso de **Saúde da Relação (Regime Health)** para evitar armadilhas de cointegração quebrada.

![Dashboard Preview](./regime-dashboard/public/preview.png) 

---

### 1. Painel de Saúde da Relação (Regime Health) Multi-Pilar
O *Z-score* só tem utilidade se a relação matemática entre as duas pontas (WIN e WDO) for estacionária. O dashboard agora implementa classificações severas baseadas na saúde dessa relação e no consenso de múltiplos modelos:
- **Correlação de Pearson (ρ)**: O indicador mais rápido de quebra. Classificado em *Forte (≤ -0.70)*, *Atenção*, *Fraca* e *Quebrada (> -0.40)*.
- **Delta Beta (Δβ)**: Mede o desvio (em %) do beta de curto prazo em relação ao referencial de 20 dias. Classificado como *Estável (< 5%)*, *Derivando*, *Instável* e *Breakdown (> 25%)*.
- **Múltiplos Motores de Sinal (Kalman, OLS, DI)**: O sistema analisa o Z-Score utilizando Filtro de Kalman, Regressão OLS Clássica e prêmio de risco do DI1, gerando um mapa de calor de Consenso de Sinais.

**`safe_to_trade`**: O sinal de entrada só é valido e visualmente liberado se tanto a correlação quanto a derivação do beta estiverem dentro das margens seguras (bandas verde ou amarela), e houver consenso entre os motores de sinal.

### 2. Sincronização Inteligente de Histórico e Fuso Horário
- O gráfico visual "limpa" automaticamente os resquícios do último pregão **todos os dias a partir das 08:50 (hora de Brasília)**.
- Implementação de offset de fuso horário (+3 horas) para acomodar os servidores MetaTrader 5 internacionais com o horário oficial da B3, garantindo que as marcações do gráfico e da sessão ocorram corretamente.

### 3. Gestão de Risco e Sinais Sonoros 
- **Position Sizing Dinâmico:** O sistema deixou de ser estático. Com base na volatilidade momentânea do desvio padrão do Spread (σ), o `server.py` determina e te sugere lotes matematicamente escalonados de Índice x Dólar buscando financeiro alvo.
- **Engle-Granger Cointegração:** Teste estatístico rigoroso (`statsmodels`) rodado ao vivo todo pregão as `08:45` que valida (p-value < 0.05) se os ativos continuam engrenados ou se a cointegração diária espalhou. 
- **Meia-Vida (Half-Life AR1):** Cálculo automático da taxa de reversão para você saber quanto tempo o trade pode ou não demorar em barras.
- **Alertas Auditivos:** Via Web Audio API, um sintetizador avisa o trader com um *beep* direto no navegador assim que um sinal for triggado verde/seguro, dispensando ficar colado na tela.

### 4. Banco de Dados e Dashboard de Performance Acumulada 
- O motor de trading agora loga as entradas, desvios, betas e preços da cotação B3 direto num arquivo `trades.db` (SQLite3).
- O robô auto-calcula os pontos baseando-se nas réguas de mercado (WDO = R$10 / WIN = R$0,20).
- O Frontend importa o endpoint e re-renderiza sob demanda um **Dashboard Estático Operacional** incluindo **Win Rate**, Tempo Médio até ser Target, **Histórico de Sinais em Tabela** expansível com motivo da saída e **Resultado Acumulado PnL BRL**.

---

## 🛠 Arquitetura e Estrutura

O projeto é dividido em um Backend rápido em Python e um Frontend imersivo em React.

```text
/
├── server.py                   # Backend: FastAPI, MetaTrader 5 Bridge, Numpy, Math
├── README.md                   # Documentação técnica
└── regime-dashboard/           # Frontend
    ├── package.json            # Dependências NPM (React, Recharts, Vite)
    └── src/
        └── App.jsx             # Motor de UI, Polling Server-Side e Fallback Simulado
```

### O Backend (`server.py`)
Atua como um adaptador *Headless* e como motor operacional. Um poller interno roda a cada **2.5 segundos** independentemente do dashboard/Firebase, chama `/api/v2/regime` internamente, conversa com o MT5, avalia entradas/saidas e persiste a timeline. Chamadas HTTP ao mesmo endpoint continuam disponíveis para o dashboard, mas não são mais o gatilho exclusivo do motor.

### O Frontend (`App.jsx`)
Usa `React` puro com `Recharts` sem dependência de complexas *store libraries* (ex: Redux). Realiza polling de HTTP Long-polling a cada **2.5 segundos** (frequência ideal para setups gráficos sem sobrecarregar a bridge do MT5). Possui também um gerador de série temporal Gaussiana (Simulador Fallback) autônomo, ativado quando o servidor ou mercado está fechado, perfeito para testar layouts.

---

## ⚙️ Configuração e Inicialização

### Pré-requisitos
1. **Windows OS** (Necessário para a biblioteca oficial do `MetaTrader5`).
2. **MetaTrader 5** devidamente instalado e **Ativo/Logado na conta da Corretora B3**.
3. **Python 3.10+**.
4. **Node.js 18+**.

### 1. Instalação do Python (Backend)

No diretório raiz do projeto:

```bash
pip install fastapi uvicorn MetaTrader5 numpy pandas statsmodels
```

*Verifique se o seu terminal MT5 está em execução. Se ele foi instalado em um local não padrão, atualize a variável `MT5_PATH` na linha 32 do arquivo `server.py`.*

Rodando o servidor:

```bash
python server.py
```

O Uvicorn iniciará e o console exibirá `[REGIME] Dia selecionado para o gráfico...` e informações de sync do pregão.

### 2. Inicialização do React (Dashboard)

Em um segundo terminal, entre na pasta do front-end e instale:

```bash
cd regime-dashboard
npm install
npm install recharts
```

Rodando o sistema via **PM2** (Recomendado para 24/7):

```bash
# Iniciar backend e frontend e monitorar falhas
pm2 start ecosystem.config.js
pm2 save

# Para ver os logs:
pm2 logs
```

Alternativamente (Modo Dev Manual):

```bash
# Terminal 1 (Backend)
uvicorn server:app --host 0.0.0.0 --port 8080 --reload

# Terminal 2 (Frontend)
npm run dev
```
Acesse `http://localhost:5174` (A porta pode variar).

---

## 🧠 Guia Operacional Baseado no Painel

O dashboard cruza sinais probabilísticos com regras duras de regime estacionário. Veja como interpretar a leitura gráfica:

1. **Aguarde a Saúde do Regime (Regime Health)**:
   - Certifique-se de que a `Correlação ρ` não seja listada como *Fraca* / *Quebrada*.
   - A barra `Δ BETA (20d)` informa o quão anormal é o comportamento elástico da relação hoje frente ao comum. Se estiver categorizado em *Instável* / *Breakdown*, o sistema emitirá um alerta banner 🚨 pulsante se instruindo a ignorar a entrada.
2. **Ponto de Entrada**:
   - As entradas ideais (Compra WIN/Vende WDO ou Compra WDO/Vende WIN) surgem quando o `Z-Score` cruza **+/- 2.0σ**.
   - O gráfico de área ajudará a vizualizar a anomalia do desvio padrão antes e no ato da formação das velas.
3. **Trajetória e Targets**:
   - Retornos à média (Z=0.5σ ou zero). O Target recomendado em caso de arbitragens de volatilidade intraday (não carry-over posições do par para o overnight caso não tenha garantias na corretora).
4. **Anomalias Extremas**: 
   - Se os ativos desviarem além de `|z| > 4.5σ`, a cointegração falhou fatalmente perante uma notícia atípica, por favor zere as posições preventivamente.

---

## 🚨 Troubleshooting Frequente

| Sintoma Visualizado | Causa Comum e Solução |
| :--- | :--- |
| **Gráfico exibe "Simulado" ou Status Amarelo** | O FastAPI não conectou com o Terminal MT5 no Desktop. |
| **Erro "No data for WIN$N"** | Ticker WIN expirado (Data Rollover). Mude de `WIN$N` pelo ticker correspondente do mês atual (Ex: `WINM25`) no inicio do `server.py`. |
| **Linha do tempo (Eixo X) vazia ou com uma linha reta** | O horário do computador difere massivamente da timezone da sua corretora no MT5. Acesse `server.py`, verifique a variável constante `TIME_OFFSET = 3 * 3600`. Altere para o offset correspondente (positivos ou negativos) testando. |
| **Falha no NPM Install Recharts** | Se existirem arquivos legados bloqueando, apague a folha `package-lock.json` ou use `--force`. |

---

## 📚 Documentação Adicional
Consulte também [Motor de Compra/Venda e Fluxo de Dados](docs/MOTOR_E_FLUXO_DE_DADOS.md) para entender o funil operacional entre MT5, backend, `TradeEngine`, SQLite e dashboard.

Consulte a pasta `.planning/` para documentação extensa:
- [Estrutura do Projeto](.planning/codebase/STRUCTURE.md)
- [Regras de Arquitetura](.planning/codebase/ARCHITECTURE.md)
- [Log de Decisões](.planning/docs/DECISIONS.md)
- [Especificações do Sistema](.planning/docs/SPEC.md)

---
**Build:** v2.4.0 · **Stack:** FastAPI, React, Recharts, MT5 API, PM2
