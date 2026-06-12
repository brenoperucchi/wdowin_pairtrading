# Phase 1: Indicador e Gráfico de Fluxo Sintético - Research

**Researched:** 2026-06-12
**Domain:** Real-time B3 Order Flow calculations in Python FastAPI + React Lightweight Charts
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** O cálculo do indicador sintético de fluxo institucional ocorrerá inteiramente no backend em Python (`server.py`).
- **D-02:** O backend manterá um cache em memória (`collections.deque` de tamanho máximo 720) para registrar o histórico de ticks a cada 5 segundos dos últimos 60 minutos.
- **D-03:** O score de fluxo será ponderado conforme as três janelas recomendadas:
  $$\text{ScoreFinal} = 0.50 \cdot \text{Score}_{5\text{s}} + 0.30 \cdot \text{Score}_{15\text{s}} + 0.20 \cdot \text{Score}_{60\text{s}}$$
- **D-04:** Para o cálculo de persistência ($\text{PERS}_t$) e concentração ($\text{CONC}_t$), serão usadas as regras definidas na especificação técnica.
- **D-05:** Criação da rota `GET /api/flow/realtime` que retorna os dados prontos no formato exigido pela biblioteca `lightweight-charts` do frontend (timestamp, valor e cor).
- D-06: O frontend renderizará uma linha única contínua usando `lightweight-charts` no componente `FlowScoreChart.jsx`.
- **D-07:** A linha do gráfico mudará de cor dinamicamente com base na pontuação: Verde ($\ge +40$), Vermelho ($\le -40$), ou Amarelo (entre $-40$ e $+40$).
- **D-08:** O gráfico será inserido na pilha vertical abaixo do `FlowDeltaChart` no arquivo `App.jsx`.

### the agent's Discretion
- Método exato para suavização de valores brutos se necessário.
- Margens, preenchimento e estilo estético fino do gráfico de linha única.

### Deferred Ideas (OUT OF SCOPE)
- Expansão do cálculo e gráfico de fluxo para o WDO — Backlog.
- Alertas visuais e sonoros de absorção no próprio gráfico de fluxo — Backlog.

</user_constraints>

<research_summary>
## Summary

A especificação exige um cálculo de alta frequência (a cada 5 segundos) de um indicador sintético consolidando cinco fatores do fluxo institucional (direção, persistência, concentração, absorção e aceleração) no backend em Python, com posterior exibição em tempo real de linha única em um gráfico React.

Após analisar o ecossistema existente, constatou-se que a melhor estratégia é implementar um coletor assíncrono em `server.py` que rode a cada 5 segundos. Esse coletor agregará as agressões atuais recebidas do Profit RTD, comparando com snapshots anteriores armazenados em um `collections.deque` de tamanho máximo 720 (para manter exatamente 60 minutos de dados). 

No frontend, utilizaremos a biblioteca `lightweight-charts` da TradingView, que já está em uso na aplicação. A plotagem usará timestamps UNIX inteiros estritamente crescentes para evitar erros de renderização na escala temporal do gráfico de tempo real.

**Primary recommendation:** Implementar uma classe gerenciadora `RealTimeFlowTracker` em Python para encapsular o cache de deques, o loop de captura assíncrono e a fórmula do score, expondo o resultado em um endpoint `/api/flow/realtime` no FastAPI. No React, criar o componente correspondente reusando os hooks e propriedades de sincronização de eixos já presentes em `IndexChart` e `FlowDeltaChart`.

</research_summary>

<standard_stack>
## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| lightweight-charts | ^4.1.0 | Renderização do gráfico | Performance nativa em Canvas para alta frequência |
| fastapi | ^0.100.0 | Exposição dos dados | Servidor API rápido e assíncrono |
| numpy | ^1.24.0 | Cálculos estatísticos (médias, desvios) | Eficiência em computações matemáticas vetoriais |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| collections.deque | pandas.DataFrame em memória | Deque é muito mais rápido para inserções/remoções circulares rápidas e consome menos memória no loop de 5s |
| lightweight-charts | Chart.js / Recharts | lightweight-charts é focado em séries temporais financeiras e lida muito melhor com scroll, zoom e sincronização de múltiplos eixos temporais |

</standard_stack>

<architecture_patterns>
## Architecture Patterns

### Recommended Project Structure
* O código do backend será adicionado a `server.py` (e em `core/` se for necessário criar uma classe separada).
* O frontend terá o novo arquivo `regime-dashboard/src/components/FlowScoreChart.jsx` e modificações em `App.jsx`.

### Pattern 1: Cache Circular com Deque em Python
```python
import time
from collections import deque

class FlowSnapshot:
    def __init__(self, timestamp, win_price, broker_flow_data):
        self.timestamp = timestamp
        self.win_price = win_price
        self.flow = broker_flow_data # dict {broker: {net, buy, sell}}

# Mantendo os últimos 720 pontos
flow_history_5s = deque(maxlen=720)
```

### Pattern 2: Renderização de Cores Dinâmicas em Linha Única (Lightweight Charts)
Para mudar a cor de uma linha dinamicamente na biblioteca `lightweight-charts`, a série de linha principal pode aceitar cores individuais por ponto usando a propriedade `color` em cada elemento do array de dados (compatível com a API de dados da linha).

```javascript
// Exemplo no frontend
const data = [
  { time: 1718181800, value: 45, color: '#00e87a' },
  { time: 1718181805, value: 10, color: '#f5a623' },
  { time: 1718181810, value: -52, color: '#ff3860' },
];
lineSeries.setData(data);
```

### Anti-Patterns to Avoid
- **Divisão por Zero:** Ao calcular `FLN = FL / VA` ou `PERS = SOMA(FL) / SOMA(|FL|)`, tratar o caso quando o volume agressor (`VA`) ou o saldo líquido absoluto acumulado for igual a zero para evitar erros `ZeroDivisionError` no backend.
- **Timestamps Duplicados:** lightweight-charts lança um erro fatal se dois pontos tiverem o mesmo timestamp. A geração do timestamp no backend deve garantir valores únicos e estritamente crescentes.

</architecture_patterns>

<dont_hand_roll>
## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Sincronização de cursor (crosshair) | Script manual de mouse | `chart.subscribeCrosshairMove` | lightweight-charts já expõe hooks nativos para ler e espelhar posições de crosshair |
| Operações matemáticas estatísticas | Loops manuais de desvio padrão | `numpy.std` / `numpy.mean` | Velocidade, precisão numérica e tratamento automático de vetores |

</dont_hand_roll>

<common_pitfalls>
## Common Pitfalls

### Pitfall 1: Bloqueio do loop de eventos (Event Loop Blocking)
**What goes wrong:** O backend FastAPI fica lento ou deixa de responder a requisições HTTP enquanto processa o loop de 5s.
**Why it happens:** Execução de operações síncronas bloqueantes dentro do loop assíncrono (ex: consultas lentas a bancos de dados).
**How to avoid:** Utilizar conexões assíncronas ou isolar operações de banco em threads. O cálculo em memória no deque é extremamente rápido, então o loop será leve se não contiver I/O síncrono pesado.

### Pitfall 2: Falta de dados iniciais (Cold Start)
**What goes wrong:** Nas primeiras requisições do dia, o cache circular está vazio e o score retorna zero ou erro.
**Why it happens:** O deque é preenchido incrementalmente a cada 5s.
**How to avoid:** O backend deve lidar graciosamente com deques que têm menos de $12$ elementos (60 segundos), calculando apenas com o histórico disponível sem falhar.

</common_pitfalls>

<code_examples>
## Code Examples

### Lógica de Cálculo do Score Ponderado (Backend)
```python
def calculate_synthetic_score_for_window(snapshots, window_seconds):
    # window_seconds = 5, 15 ou 60
    periods = window_seconds // 5
    if len(snapshots) < 2:
        return 0.0
        
    slice_data = list(snapshots)[-periods:]
    if len(slice_data) < 2:
        return 0.0
        
    first = slice_data[0]
    last = slice_data[-1]
    
    # 1. Direção / Fluxo Líquido Normalizado
    # Coletamos o delta de agressão do WIN nesse período
    buy_sum = 0
    sell_sum = 0
    for b in _broker_list:
        buy_sum += (last.flow[b]["buy"] - first.flow[b]["buy"])
        sell_sum += (last.flow[b]["sell"] - first.flow[b]["sell"])
        
    va = buy_sum + sell_sum
    fl = buy_sum - sell_sum
    fln = (fl / va) if va > 0 else 0.0
    
    # 2. Persistência (Janela de 10 períodos da janela atual)
    # PERS_t = SOMA(FL) / SOMA(ABS(FL))
    # Para simplificar, acumulamos os deltas das subjanelas
    # ... Lógica de Persistência ...
    
    # 3. Concentração Top 3
    # ... Lógica de Concentração ...
    
    # 4. Absorção
    # ... Lógica de Absorção ...
    
    # Score da janela
    score = 100 * (0.40 * fln + 0.30 * pers + 0.20 * conc_dir + 0.10 * abs_dir)
    return score
```

</code_examples>

<sources>
## Sources

### Primary (HIGH confidence)
- `lightweight-charts` API documentation — Custom coloring, Series APIs.
- FastAPI documentation — Startup events, background tasks.
- Spec_Indicador_Sintetico_Fluxo_Institucional.docx — Fórmulas e pesos de cálculo.

</sources>

<metadata>
## Metadata

**Research scope:**
- Core technology: Python FastAPI, React Lightweight Charts
- Patterns: deque caching, high frequency updates
- Pitfalls: zero division, event loop blocking

**Confidence breakdown:**
- Standard stack: HIGH
- Architecture: HIGH
- Pitfalls: HIGH
- Code examples: HIGH

**Research date:** 2026-06-12
**Valid until:** 2026-07-12
</metadata>

---

*Phase: 01-indicador-e-grafico-de-fluxo-sintetico*
*Research completed: 2026-06-12*
*Ready for planning: yes*
