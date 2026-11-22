---
description: Padrão visual oficial Magic Walls (Ink Azul / unslop) para web, gráficos intraday, posts/stories do Instagram e vídeos pré-pregão 08h30
---

# Padrão Visual Oficial — Magic Walls (Ink Azul)

Ao criar ou editar qualquer interface em `regime-dashboard/` (painel público/SaaS, gráficos intraday, cards/posts do Instagram e renderizador de vídeo pré-pregão), siga rigorosamente a especificação completa em [`docs/DESIGN_SYSTEM_MAGIC_WALLS.md`](../../docs/DESIGN_SYSTEM_MAGIC_WALLS.md).

## 1. Paleta Ink Azul (Obrigatória)
- **Superfícies foscas (sem gradiente e sem blur)**:
  - Chrome / trilhas: `#0a0c12` (`--mw-chrome`)
  - Fundo de página / plot / vídeo: `#0e1118` (`--mw-bg`)
  - Cards / painéis / linhas: `#131720` (`--mw-card`)
  - Controles ativos / pills: `#1b212e` (`--mw-raised`)
  - Hairlines: `rgba(238, 240, 245, 0.08)` (ou `#232836` opaco) e `rgba(238, 240, 245, 0.14)` em foco.
- **Hierarquia de texto (apenas 3 tons)**: `#eef0f5` (primário), `#a3a9b8` (secundário), `#848da2` (terciário). Nunca usar `#ffffff` puro em texto longo.
- **Cor semântica (apenas no dado)**:
  - Marca / Fluxo / Ação: `#38bdf8` (`#7dd3fc` ink, `rgba(56,189,248,0.12)` soft, texto `#070a10` sobre fundo sólido `#38bdf8`).
  - Compra / Suporte / Gain / Gamma+: `#4cc38a` (fundo `#10231b`).
  - Venda / Resistência / Stop / Gamma-: `#e5484d` (fundo `#261316`).
  - FlipWall / Melhor pernada / Destaque: `#d4a259` (fundo `#211d17`).

## 2. Tipografia e Ícones
- **Fontes**: `IBM Plex Sans` (UI) + `IBM Plex Mono` (`tabular-nums` em preços, horários, contratos e pontos).
- **Pesos**: apenas `400`, `500` e `600`. **Nunca** usar `700`, `800` ou `900`.
- **Caixa**: *Sentence case* (exceto siglas de mercado como `WIN`, `WDO`, `GEX`, `VWAP`, `BRT`, `M5`, `M1`, `B3`). `letter-spacing: 0` abaixo de `16px`; `-0.02em` apenas em grandes numerais (`>= 28px`).
- **Ícones**: SVGs vetoriais planos estilo Lucide (`15–16px`, `stroke-width: 1.5`). **Proibido** emojis em UI, gráficos, cards SVG ou quadros de vídeo.
- **Marca (Flip Strata)**: Usar o símbolo oficial **Flip Strata** (`regime-dashboard/src/components/MagicWallsMark.jsx`, baseado em `docs/brand/magic-walls/kit/BRAND_GUIDELINES.md`) com chanfros de `45°`, zero `rx`, hierarquia `#eef0f5` / `#38bdf8` / `#848da2` (corte `small` em `16–24px`, `master` acima de `24px`) + trilho esquerdo semântico de `2px` apenas em cabeçalhos de ativo/regime.

## 3. Regras Anti-Slop (Zero Exceções)
- **Proibido**: `backdrop-filter: blur`, `box-shadow` luminoso, `shadowBlur` no Canvas, gradientes de fundo, bordas neon, amarelo `#ffd600`, partículas flutuantes, anéis/varredura de radar, `animate-pulse` ou `easeOutBack` quicando.
- **Gráficos**: Marcadores numerados (`1, 2, 3…`) com `Linhas div.` desligadas por padrão; `M1` sempre em janela navegável de `2h` (`1h | 2h | 3h`), sem modo `Foco 48b`; status honesto (`Sem pregão`, `Replay`, `Ao vivo`, `Offline`).
- **Motion (vídeo 08h30)**: Apenas `easeOutCubic` / `easeOutQuart`, barra de progresso superior em 5 segmentos de `3px` e barras GEX foscas sem gloss.
- **Build público**: Após alterações em `regime-dashboard/`, executar `node build-publico.mjs` para atualizar `regime-dashboard/dist-publico/`.

*Referência editorial baseada em `heydamir/unslop` (Damir Sokolovsky, `@heydamir`, CC BY 4.0).*
