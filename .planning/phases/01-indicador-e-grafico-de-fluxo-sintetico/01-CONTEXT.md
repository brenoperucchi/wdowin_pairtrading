# Phase 1: Indicador e Gráfico de Fluxo Sintético - Context

**Gathered:** 2026-06-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Desenvolvimento do indicador sintético de fluxo institucional em tempo real de alta frequência para o WIN, abrangendo a infraestrutura de cache do backend, lógica do score sintético ponderado (janelas de 5s, 15s e 60s) e a plotagem de linha dinâmica de 60 minutos (resolução de 5s) no dashboard React.

</domain>

<decisions>
## Implementation Decisions

### Processamento do Score Sintético
- **D-01:** O cálculo do indicador sintético de fluxo institucional ocorrerá inteiramente no backend em Python (`server.py`).
- **D-02:** O backend manterá um cache em memória (`collections.deque` de tamanho máximo 720) para registrar o histórico de ticks a cada 5 segundos dos últimos 60 minutos.
- **D-03:** O score de fluxo será ponderado conforme as três janelas recomendadas:
  $$\text{ScoreFinal} = 0.50 \cdot \text{Score}_{5\text{s}} + 0.30 \cdot \text{Score}_{15\text{s}} + 0.20 \cdot \text{Score}_{60\text{s}}$$
- **D-04:** Para o cálculo de persistência ($\text{PERS}_t$) e concentração ($\text{CONC}_t$), serão usadas as regras definidas na especificação técnica.

### Rota e API do Backend
- **D-05:** Criação da rota `GET /api/flow/realtime` que retorna os dados prontos no formato exigido pela biblioteca `lightweight-charts` do frontend (timestamp, valor e cor).

### Visualização e Gráfico (React)
- **D-06:** O frontend renderizará uma linha única contínua usando `lightweight-charts` no componente `FlowScoreChart.jsx`.
- **D-07:** A linha do gráfico mudará de cor dinamicamente com base na pontuação: Verde ($\ge +40$), Vermelho ($\le -40$), ou Amarelo (entre $-40$ e $+40$).
- **D-08:** O gráfico será inserido na pilha vertical abaixo do `FlowDeltaChart` no arquivo `App.jsx`.

### the agent's Discretion
- Método exato para suavização de valores brutos se necessário.
- Margens, preenchimento e estilo estético fino do gráfico de linha única.

</decisions>

<canonical_refs>
## Canonical References

### Especificação do Fluxo
- `RTD/Spec_Indicador_Sintetico_Fluxo_Institucional.docx` — Especificação técnica do indicador sintético de fluxo institucional.
- `.planning/notes/fluxo_sintetico_design.md` — Decisões de design e fórmulas do indicador.
- `.planning/todos/pending/implementar_fluxo_sintetico.md` — Lista de tarefas de implementação do fluxo.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `BrokerFlowPanel` e `FlowDeltaChart` no React contêm a lógica de processamento e renderização do fluxo do WIN que podem ser usadas como referência para assinar ou ler dados de fluxo.
- `lightweight-charts` já está configurada e inicializada em `IndexChart.jsx` e `FlowDeltaChart.jsx`, servindo de modelo exato para a criação do `FlowScoreChart.jsx`.

### Established Patterns
- Polling no React a cada 250ms/2500ms para pegar dados live.
- Sincronização de cursor (Crosshairs) e visibilidade horizontal (`timeScale().subscribeVisibleLogicalRangeChange`) entre gráficos.

### Integration Points
- `server.py`: loop assíncrono que gera snapshots de fluxo.
- `App.jsx`: inclusão do novo gráfico na pilha e passagem da referência do chart para sincronização.

</code_context>

<deferred>
## Deferred Ideas

- Expansão do cálculo e gráfico de fluxo para o WDO — Backlog.
- Alertas visuais e sonoros de absorção no próprio gráfico de fluxo — Backlog.

</deferred>

---

*Phase: 01-indicador-e-grafico-de-fluxo-sintetico*
*Context gathered: 2026-06-12*
