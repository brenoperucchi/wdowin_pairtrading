# Próximos Passos — WDO×WIN Pair Trading & Fluxo nas Walls

## 1. Pesquisa de Novas Estratégias via Fluxo (Painel `5176` — Absorção Seletiva na Wall & `M1`)
Referência completa: [`docs/PAINEL_5176_SNIPER_DIVERGENCIA_SMART_MONEY.md`](../docs/PAINEL_5176_SNIPER_DIVERGENCIA_SMART_MONEY.md)

- **1.1. Estratégia de Absorção na Wall com Filtros Rigorosos (Alta Seletividade):**
  - *Aprendizado consolidado:* operar absorção simples na Wall de forma indiscriminada gera excesso de operações e ruído contra tendência. A ideia estrutural de absorção na Wall é excelente, mas precisa de **filtros estritos de confluência** antes de entrar no portfólio da `5176`:
    - Exigir assimetria extrema **Esforço × Resultado (Wyckoff)** (alto percentil de agressão contrária batendo na Wall sem deslocamento real de preço / pavio de defesa).
    - Exigir **absorção passiva institucional real (`inst_pass_delta`)** combinada com varejo preso na agressão oposta (`ret_delta`), filtrando falsos sinais dominados por giro de `HFT`.
    - Filtrar por **regime GEX favorável (`Gamma Positivo` na defesa)** e "frescor" do nível (priorizar 1º/2º toque da sessão em vez de Wall já desgastada).
    - Aplicar desde a origem a governança comprovada no Sniper: **filtro de horário (`s/ 11h WDO` e `s/ 12h WIN`)** + **trava de Meta Diária causal**.
- **1.2. Expansão da Pesquisa para o Timeframe `M1` (Microestrutura Fina):**
  - Combinar a ancoragem macro das `MagicWalls`/`MidWalls` GEX com **gatilhos cirúrgicos no `M1`**:
    - Capturar **absorção na pedra + 1ª barra `M1` de ignição institucional** logo no toque da Wall (sem precisar esperar 5 minutos inteiros quando o movimento já andou).
    - Capturar **violinadas rápidas (*Spring / Upthrust* em `1–3` barras `M1`)** com exaustão imediata do agressor e retomada do nível.
    - Reduzir drasticamente o tamanho do **Stop Loss técnico** posicionando-o atrás da defesa real do `M1`, aumentando `Profit Factor` e `Retorno / Drawdown` de setups complementares ao Sniper M5.

## 2. Firebase Hosting (Dashboard público)
- Projeto Firebase `wdo-win-dashboard` já existe (`.firebaserc`, `firebase.json` apontando para `regime-dashboard/dist`, `regime-dashboard/.env.production`)
- Confirmar o deploy público do Hosting e registrar a URL
- Ligar a publicação do backend para o Firebase RTDB e fazer o frontend consumir o RTDB em produção (localhost em dev)
- Referência: `rastro_irado/frontend/` já tem setup completo

## 3. Integração MT5 — Envio de Ordens
- Ainda não implementado: não existe `core/mt5_executor.py` e não há `mt5.order_send()` no backend (`core/*.py`, `server.py`)
- Usar `mt5.order_send()` para despachar ordens reais
- Trade engine atual é signal-only + paper tracking → converter para execução
- Criar módulo `core/mt5_executor.py` com order_send/position_close
- SL/TP/BE via ordens pendentes ou gestão interna
- Kill switch manual no dashboard
- **ATENÇÃO**: dinheiro real, exige testes exaustivos em conta demo primeiro
