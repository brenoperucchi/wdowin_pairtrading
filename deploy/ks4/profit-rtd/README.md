# Clipboards do Profit (ks4), RTD

Os `.tsv` abaixo ficam so na maquina (estao no `.gitignore`: sao negocios reais com codigo de corretora).

Guardados em 25/11/2026, lidos do display :99 do container `profit-wine` com
`podman exec -e DISPLAY=:99 profit-wine xclip -selection clipboard -o -t UTF8_STRING`.

- `clipboard-rtd-campos-ativo.tsv`: planilha de RTD por ativo (WDOZ26, WINZ26). Campos de preço, volume,
  agressão (AGRVOL*, AGRNEG*, AGRSALDO*) e os códigos numéricos 184/103/98/100/99. É o que o `rtdmin` grava por
  minuto. Reconstruída a partir do que o clipboard mostrou; as fórmulas são as mesmas.
- `clipboard-times-and-trades-T&T0.tsv`: tabela `T&T0` (Times & Trades), cópia exata do clipboard. Por negócio:
  DAT, QUL (quantidade), PRE (valor), ACP (corretora compradora), AVD (corretora vendedora), AGR (agressor).
  Linhas 0 a 19 (janela das últimas 20 negociações). `INFO ATV` = ativo da janela, `INFO TAB` = tabela.

Limite conhecido: a janela gira (WIN faz ~50 mil negócios/min na abertura), então polling não captura tudo.
Cobertura precisa ser medida contra o aumento do campo NEG.

## rtdmw (cliente RTD único), 25/11/2026

O servidor RTD do Profit só aceita uma sessão: um segundo cliente derruba o primeiro
(log do Profit: `TRtdServer.ServerStart: sessão anterior não finalizada`). Por isso `rtdmw.exe` substitui o
`rtdmin.exe` (mesmo CSV por minuto e mesmo `status.json`) e soma o Times & Trades.

- Fonte: `rtdmw.cpp` (base: `rtdmin.cpp` do vps-12). Compila no host ks4:
  `x86_64-w64-mingw32-g++ -O2 -municode -static -o rtdmw.exe rtdmw.cpp -lole32 -loleaut32 -luuid`.
- Loop: `rtdmw-loop.sh` (container profit-wine, `/home/mt5/.mt5/rtd/`), chamado pelo `start-profit.sh`
  (backup `start-profit.sh.bak4`). `rtdmin.exe` e `rtdmin-loop.sh` ficam no disco, sem uso.
- Saídas em `/home/app/profit-wine/prefix/rtd-csv/` (container: `/home/mt5/.mt5/rtd-csv/`):
  `<ATIVO>_min_DD_MM_YYYY.csv`, `status.json` (agora com bloco `tt`: trades, gaps, neg_delta, coverage) e
  `tt_<ATIVO>_DD_MM_YYYY.csv` (`HH:MM:SS;qtd;preço;compradora;vendedora;agressor`, uma linha por negócio, mais antigo primeiro;
  linha `GAP;;;;;` marca perda de sobreposição da janela).
- Cobertura medida (10:18 a 10:20, 500 linhas): WIN 99,4%, WDO 94%. Watchdog: sai se `hor` não avançar por 60 s em pregão.
- Regra: não rodar nenhum outro cliente RTD junto (derruba a sessão).
