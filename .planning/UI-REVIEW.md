# Standalone UI Review — WDO×WIN Pair Trading Dashboard

**Audited:** 2026-04-30
**Baseline:** Abstract 6-pillar standards (No UI-SPEC.md)
**Screenshots:** Not captured (code-only audit)

---

## Pillar Scores

| Pillar | Score | Key Finding |
|--------|-------|-------------|
| 1. Copywriting | 3/4 | Boa clareza financeira, sem botões genéricos, mas há mistura de PT/EN em rótulos. |
| 2. Visuals | 4/4 | Dashboard com grid limpo, hierarquia bem definida e bom uso de gráficos. |
| 3. Color | 3/4 | Paleta de dark mode consistente, porém utiliza hardcoded hex codes. |
| 4. Typography | 2/4 | Muitos tamanhos de fonte hardcoded (inline styles), sem escala tipográfica padrão. |
| 5. Spacing | 2/4 | Margens e paddings fixos inline. Dificulta manutenção e responsividade. |
| 6. Experience Design | 3/4 | Modo "fallback" (offline) bem implementado, mas falta indicação visual clara de "carregando" inicial. |

**Overall: 17/24**

---

## Top 3 Priority Fixes

1. **Escala de Espaçamento e Tipografia Inline** — Difícil manter e gera inconsistência visual — **Mover estilos de tipografia e espaçamento para classes CSS globais (ex: no `index.css`) ou adotar TailwindCSS em refatoração futura.**
2. **Mistura de Idiomas (PT/EN)** — Pode confundir usuários (ex: "WIN RATE" junto com "STATUS OPERACIONAL") — **Padronizar todo o dashboard para Português (Taxa de Acerto, Resultado Acumulado, etc).**
3. **Falta de Estado de Carregamento (Skeleton/Spinner)** — A tela surge "vazia" até o primeiro poll da API — **Adicionar um skeleton loader no `App.jsx` enquanto os dados da API ainda não responderam a primeira vez.**

---

## Detailed Findings

### Pillar 1: Copywriting (3/4)
- **Positivo:** Os rótulos de performance são precisos para o nicho (PnL, TRADES, SINAIS). Não há botões genéricos vazios.
- **Atenção:** Termos em inglês ("WIN RATE", "BUY", "SELL", "TARGET") estão misturados com termos em português ("STATUS OPERACIONAL", "AGUARDANDO", "CONSENSO"). Recomenda-se padronizar.

### Pillar 2: Visuals (4/4)
- **Positivo:** A interface possui forte distinção visual. O `PerformancePanel` e o `SignalHistogram` fornecem pontos focais imediatos.
- **Positivo:** O uso do layout escuro com grids (`gridTemplateColumns: "repeat(5, 1fr)"`) mantém os dados alinhados e fáceis de escanear.

### Pillar 3: Color (3/4)
- **Positivo:** O sistema de cores financeiras é claro: `#00e87a` para lucros/compras, `#ff3860` para perdas/vendas.
- **Atenção:** Uso excessivo de hardcoded colors diretamente nas tags (ex: `color: "#4a6070"`). Criar variáveis CSS seria o ideal para evitar inconsistências em futuras expansões.

### Pillar 4: Typography (2/4)
- **Negativo:** O painel possui inúmeras variações de tamanhos soltos (8, 9, 10, 12, 14, 16, 18, 22). 
- **Correção:** Estabelecer uma escala de pelo menos 5 tamanhos de fonte base e remover as definições inline arbitrárias.

### Pillar 5: Spacing (2/4)
- **Negativo:** O sistema usa valores aleatórios (ex: `padding: "10px 14px"`, `marginBottom: 6`, `gap: 14`).
- **Correção:** Adotar uma escala fixa (base 4 ou 8px) para paddings e margins, mantendo a consistência em componentes novos.

### Pillar 6: Experience Design (3/4)
- **Positivo:** Resiliência da interface. O `status === "fallback"` simula dados se a API Python cair, evitando a tela branca da morte.
- **Atenção:** O painel poderia incluir dicas (tooltips) explicando o que é o "MOTOR" (Z_SOURCE) ou o "Zw/Zd", pois são jargões técnicos.

---

## Files Audited
- `regime-dashboard/src/App.jsx`
- `regime-dashboard/src/components/PerformancePanel.jsx`
- `regime-dashboard/src/components/SignalHistogram.jsx`
- `regime-dashboard/src/components/IndexChart.jsx`
