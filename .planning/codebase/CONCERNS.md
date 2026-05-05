# Areas of Concern / Technical Debt

## 1. Concorrência e Event Loop Blocking (FastAPI)
- `server.py` possui funções de sincronização síncrona com MT5 sendo chamadas por uma task do `asyncio`. Se o terminal MetaTrader 5 tiver um atraso pontual de tick, a API Web irá enfileirar conexões ou travar.

## 2. Disk Thrashing do SQLite
- `TradeEngine` invoca `sqlite3.connect` por volta de ~5 vezes a cada loop de avaliação, que ocorre a cada 2.5s. Em discos mecânicos ou VDI, isso criará lock da database e degradará o tempo de resposta do endpoint.

## 3. Acoplamento de Lógica Front/Back
- `App.jsx` está iterando arrays de 1500+ registros (`mergedSignals`) em um loop no próprio Client-Side para calcular o Envelope de Nadaraya-Watson (NWE), tarefa pesada que já está presente e é feita na API.

## 4. Legado da API V1
- Existem variáveis, caches e rotas (`/api/regime`) do setup V1 OLS que ainda figuram ativamente, quando poderiam ser limpos já que a estratégia v4 usa apenas Filtro de Kalman.
