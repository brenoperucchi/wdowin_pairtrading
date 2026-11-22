# Magic Walls — Padrão Visual Oficial (Ink Azul)

Sistema de design oficial do projeto **Magic Walls** (`WIN × WDO`, painel web público/SaaS, gráficos intraday, posts/stories do Instagram e vídeos pré-pregão 08h30).

Baseado nos princípios editoriais de contenção, hierarquia tipográfica e ausência de ornamento artificial do guia [`heydamir/unslop`](https://github.com/heydamir/unslop) (Damir Sokolovsky, `@heydamir`, CC BY 4.0), adaptado para a identidade azul institucional do Magic Walls (**Ink Azul**).

---

## 1. Direção (5 Linhas)

- **Domínio**: Terminal quantitativo de Gamma Exposure (GEX), Walls e Fluxo Smart Money para mini-índice (`WIN`) e mini-dólar (`WDO`) na B3.
- **Atmosfera**: Calmo, preciso e silencioso até o dado pedir atenção — superfície escura fosca (*Ink Dark*) com sotaque azul contido (`#38bdf8`) preservando a identidade visual da marca.
- **Tipografia**: `IBM Plex Sans` para interface e textos corridos + `IBM Plex Mono` com `tabular-nums` para cotações, horários, contratos, deltas e distâncias em pontos. Pesos limitados a `400`, `500` e `600` (nunca `700`/`800`/`900`).
- **Cor**: Quase monocromático na estrutura; cor semântica aparece apenas nos momentos de dado (ativo/fluxo em azul, compra/suporte/gain em verde suave, venda/resistência/stop em vermelho sóbrio, FlipWall/destaque em âmbar quente).
- **Assinatura**: Marca plana de 3 barras horizontais (*Walls Mark*), trilho esquerdo semântico de `2px` nos cabeçalhos de ativo e marcadores numerados (`1, 2, 3…`) sem linhas poluindo o gráfico de preço por padrão.

---

## 2. Tokens de Cor (Ink Azul)

Definidos em `regime-dashboard/src/index.css` (`:root`) e replicados nos geradores SVG/Canvas:

| Token CSS | Hex / RGBA | Papel |
|---|---|---|
| `--mw-chrome` | `#0a0c12` | Topbar, trilhas de progresso, fundo de selects e controles embutidos |
| `--mw-bg` | `#0e1118` | Fundo principal da página, área de plotagem de gráficos e palco do vídeo |
| `--mw-card` | `#131720` | Superfície de cards, painéis de ativo, cartões de KPI e slots da escada GEX |
| `--mw-raised` | `#1b212e` | Item ativo em segmented controls, pills de metadados, hover de controles |
| `--mw-hairline` | `rgba(238, 240, 245, 0.08)` | Bordas estruturais de 1px (`#232836` em SVG/Canvas opaco) |
| `--mw-hairline-strong` | `rgba(238, 240, 245, 0.14)` | Bordas em foco, hover e contornos de badges neutros |
| `--mw-text-1` | `#eef0f5` | Títulos, preços, valores principais e rótulos ativos |
| `--mw-text-2` | `#a3a9b8` | Subtítulos, métricas secundárias, textos explicativos |
| `--mw-text-3` | `#848da2` | Rótulos de eixo, timestamps, notas de rodapé e metadados terciários |
| `--mw-accent` | `#38bdf8` | Identidade Magic Walls, Fluxo Smart Money, barra central do logo, CTA sólido |
| `--mw-accent-ink` | `#7dd3fc` | Texto azul sobre superfície escura (alto contraste) |
| `--mw-accent-soft` | `rgba(56, 189, 248, 0.12)` | Fundo suave de badges/controles ativos |
| `--mw-on-accent` | `#070a10` | Texto escuro sobre botões/pills sólidos `#38bdf8` (contraste > 9:1) |
| `--mw-pos` | `#4cc38a` | Compra, suporte, ganho, regime Gamma Positivo |
| `--mw-pos-soft` | `#10231b` | Fundo de badge positivo |
| `--mw-neg` | `#e5484d` | Venda, resistência, stop, regime Gamma Negativo |
| `--mw-neg-soft` | `#261316` | Fundo de badge negativo |
| `--mw-flip` | `#d4a259` | FlipWall (Gamma Flip), régua de melhor movimento, destaque da melhor pernada |
| `--mw-flip-soft` | `#211d17` | Fundo de badge FlipWall / destaque |

### Regras de Uso de Cor
- **Máximo de 3 papéis de texto** (`#eef0f5`, `#a3a9b8`, `#848da2`) — não inventar cinzas intermediários avulsos.
- **Nunca usar branco puro (`#ffffff`)** em textos grandes ou bordas; usar `#eef0f5`.
- **Nunca usar amarelo neon (`#ffd600`) ou laranja saturado (`#fb923c`)** em gráficos/cards; usar `#d4a259` para FlipWall/destaque e `#e5484d` para venda/resistência/stop.
- **Botão ou pill sólido azul (`#38bdf8`)** deve sempre levar texto escuro `#070a10`, nunca branco.

---

## 3. Tipografia

- **UI / Prose**: `"IBM Plex Sans", system-ui, -apple-system, sans-serif`
- **Dados / Monospace**: `"IBM Plex Mono", ui-monospace, SFMono-Regular, monospace`
- **Pesos permitidos**: `400` (regular), `500` (medium) e `600` (semibold para preços e cabeçalhos). **Proibido** `700`, `800` e `900`.
- **Caixa**: *Sentence case* em toda interface, cards e vídeo (`Resumo do pregão`, `Fluxo Smart Money`, `Mapa de liquidez`, `Dinâmica dos market makers`). Exceções restritas a siglas de mercado (`WIN`, `WDO`, `VWAP`, `GEX`, `BRT`, `M5`, `M1`, `B3`, `USD`, `BRL`).
- **Espaçamento de letras (`letter-spacing`)**: `0` abaixo de `16px`; `-0.02em` apenas em grandes numerais de destaque (`>= 28px`). **Proibido** `uppercase` com `letter-spacing` largo (`>= 0.08em`).
- **Alinhamento numérico**: `font-variant-numeric: tabular-nums` obrigatório em qualquer preço, horário, delta, percentual, contador e tabela.

---

## 4. Layout, Espaçamento, Bordas e Ícones

- **Grade de espaçamento**: múltiplos de `4px` (`4, 8, 12, 16, 20, 24, 32`).
- **Raio aninhado**: `radius_interno = radius_externo - padding` (ex.: card `10px`, botões/chips internos `6px`).
- **Superfícies opacas**: **Proibido** `backdrop-filter: blur(...)`, transparências leitosas ou gradientes de fundo em cards e topbars.
- **Sombras e brilhos**: **Proibido** `box-shadow` luminoso/glow, `shadowBlur` em Canvas, halos pulsantes ou bordas neon. A elevação vem apenas da escada de luminância (`#0a0c12 → #0e1118 → #131720 → #1b212e`) + hairline de `1px`.
- **Ícones**: Apenas SVGs vetoriais planos no estilo **Lucide** (`15–16px`, `stroke-width: 1.5`, `stroke-linecap: round`). **Proibido** emojis (`📸`, `🎬`, `🛡️`, `⚡`, `⏱️`, `★`, `🚀`, `📊`) na interface, nos cards SVG ou nos quadros de vídeo.
- **Marca (Flip Strata — Logo Kit oficial)**: Utilizar exclusivamente o símbolo **Flip Strata** de [`docs/brand/magic-walls/kit/BRAND_GUIDELINES.md`](brand/magic-walls/kit/BRAND_GUIDELINES.md) (componente `MagicWallsMark.jsx`): três estratos horizontais com chanfros internos de `45°` em simetria invertida de `180°` — topo `#eef0f5` (Call Wall), centro `#38bdf8` (FlipWall) e base `#848da2` (Put Wall) — sem cantos arredondados (`rx`), sem brilho e sem gradiente. Usar o corte óptico `small` (`44u`) em `16–24px` (topbar/favicon) e `master` (`36u`) acima de `24px`. Web icons oficiais ficam em `regime-dashboard/public/` (`favicon.ico`, `favicon.svg`, `apple-touch-icon.png`, `site.webmanifest`).

---

## 5. Padrão de Gráficos e Painel Intraday (`walls.css-pro.com.br`)

1. **Topbar única**: Uma única linha sólida (`#0a0c12`) contendo marca, seletor `Dupla | WIN | WDO`, `Empilhado | Lado a lado`, seletor de pregão com atalhos rápidos e badge de status honesto (`Ao vivo`, `Replay`, `Sem pregão`, `Offline`).
2. **Cabeçalho do ativo unificado**: Trilho esquerdo de `2px` refletindo o regime (`#4cc38a` compra / `#e5484d` venda / `#848da2` neutro), chip do contrato, preço `28px` tabular, delta vs VWAP, janela institucional e resumo `Sup · Res · FlipWall`.
3. **Sinais numerados sem poluição**:
   - Divergências renderizadas como marcadores circulares numerados (`1, 2, 3…`) com detecção de colisão (estilo Card IG), ordenação estável pelo pregão inteiro.
   - **Linhas de divergência sobre os candles ficam desligadas por padrão** (`Linhas div.` off); hover ou clique em um número destaca apenas aquele sinal e mostra resumo OHLC + pontos.
   - No painel `Fluxo Smart Money`, pins `#1..#N` têm proteção anticolisão e espaçamento horizontal automático.
4. **Timeframe `M1` legível**: Ao alternar para `M1`, abrir automaticamente em janela de `2h` (`120` barras) com navegação `◀ HH:MM–HH:MM ▶ | 1h | 2h | 3h` e arrasto (*drag-pan*). **Não usar** modos arbitrários como `Foco (48b)`.
5. **Responsividade e honestidade**:
   - SVG com `viewBox` 1:1 sincronizado com a largura real do contêiner (evita texto distorcido ou cortado no mobile).
   - Ocultar etiquetas de preço das Walls no eixo Y quando colidirem com o botão `[A]` de autoescala.
   - Em fins de semana/feriados ou sem candles, exibir estado vazio explícito (`Sem pregão em DD/MM/AAAA`) — nunca simular status `LIVE`.

---

## 6. Padrão para Instagram (Feed 4:5, Stories 9:16 e Carrossel 1/2 & 2/2)

Aplica-se a `regime-dashboard/src/components/InstagramCardModal.jsx`:

- **Fundo e estrutura**: Retângulo fosco `#0e1118` (zero gradiente vertical, zero brilho radial no topo). Seções separadas por cards `#131720` com hairline `1px` (`#232836`).
- **Cabeçalho**: Walls Mark (3 barras planas) + `Magic Walls` (`600`) + `Resumo do pregão · Dia, DD/MM/AAAA` em sentence case, com chip do contrato (`WINZ26` / `WDOZ26`) à direita.
- **Faixa de 3 KPIs**: `Sinais no dia`, `Melhor pernada`, `Saldo máx. a favor` em cards `#131720` silenciosos com hairline neutra e `2px` de destaque superior apenas na cor semântica do dado — sem bordas neon, sem estrelas `★`, sem peso `900`.
- **Gráfico**: Candles sóbrios (alta `#9aa5b6` ou `#4cc38a` discreto, baixa `#475266`), Walls horizontais finas, FlipWall tracejada `#d4a259`, marcadores circulares numerados `1..N` (`#4cc38a` compra, `#e5484d` venda, anel `#d4a259` na melhor pernada, marcador vazado `#261316`/`#e5484d` em stop), `Linhas div.` desligado por padrão, régua da melhor pernada em `#d4a259` limpo e subpainel `Fluxo Smart Money` em `#38bdf8`.
- **Tabela de entradas**: Linhas `#131720` com trilho esquerdo de `2px`, tag direcional limpa (`F▲ Compra` / `F▼ Venda`), horário + entrada em `IBM Plex Mono`, detalhe de pico ou stop, barra de magnitude de `4px` (trilha `#1b212e`) e badge `Melhor` (`#211d17`/`#d4a259`) ou `Stop` (`#261316`/`#e5484d`).
- **Rodapé**: Linha hairline `1px`, `@magicwallsb3` à esquerda e nota educacional discreta (`#848da2`) à direita.

---

## 7. Padrão para Vídeo Pré-Pregão 08h30 (Reels 9:16 & YouTube 16:9)

Aplica-se a `regime-dashboard/src/utils/morningVideoRenderer.js` e `MorningWallsVideoModal.jsx`:

- **Palco**: `#0e1118` fosco limpo. **Proibido** gradiente de fundo, halo radial, grade tática móvel, linha de radar varrendo a tela, partículas flutuantes, anéis concêntricos, ponto verde piscando ou laser com `shadowBlur`.
- **Barra de progresso superior**: 5 segmentos finos (`3px`) no topo (`#1b212e` inativo, `#38bdf8` ativo), acompanhados pela Walls Mark plana, indicador do ato (`1/5 Abertura` … `5/5 Fechamento`) e data.
- **Movimento (Motion)**:
  - Curva única `easeOutCubic` / `easeOutQuart` — **proibido** `easeOutBack` (efeito mola/carimbo quicando).
  - Deslocamentos curtos (`12–20px`), fade suave e preenchimento linear das barras GEX sem gloss/gradiente.
- **5 Atos**:
  1. **Abertura**: Walls Mark plana, pill estática `Pré-pregão · 08:30 BRT`, título `Mapa de liquidez` / `WIN × WDO`, e cards resumidos WIN e WDO lado a lado com trilho de regime de `2px`.
  2. **WIN (Escada GEX)** & 3. **WDO (Escada GEX)**: Cabeçalho do ativo + escada vertical sem sobreposição (7 níveis com barra de força GEX de `4px` e indicador geométrico de 1–3 níveis em vez de `★★★`) + linha de `Preço ref.` em `#38bdf8` nítido (sem glow) + 3 cards táticos (`Resistência imediata`, `Suporte imediato`, `Ímã GEX`) + bloco `Dinâmica dos market makers`.
  4. **Radar Macro**: Comparativo WIN × WDO + lista de `Horários de liquidez · Agenda BRT` com pills `HH:MM` e `BRL`/`USD` + faixa discreta de ativos globais (`SP500 ES`, `NASDAQ NQ`, `GOLD XAU`, `BTC USD`).
  5. **Fechamento & CTA**: Pill estática `Publicado antes da abertura · DD/MM/AAAA` com check vetorial `#4cc38a`, chamada `Salve este mapa e confira` / `no fechamento às 17h`, e card CTA com botão plano `#38bdf8` + texto escuro `#070a10` (`walls.css-pro.com.br`) e `@magicwallsb3`.

---

## 8. Checklist Anti-Slop (Obrigatório Antes de Publicar)

- [ ] Nenhum peso tipográfico `700`, `800` ou `900`.
- [ ] Nenhum texto com `uppercase` + `letter-spacing >= 0.08em`.
- [ ] Zero emojis em UI, gráficos, cards SVG ou Canvas de vídeo.
- [ ] Zero `backdrop-filter: blur`, `box-shadow` luminoso, `shadowBlur`, gradientes de fundo ou partículas/radar.
- [ ] Zero animações em loop (`animate-pulse`, `animate-bounce`, pulso contínuo de opacidade).
- [ ] Todos os números em `IBM Plex Mono` com `tabular-nums`.
- [ ] Contraste validado (texto escuro `#070a10` sobre `#38bdf8`).
- [ ] Estados vazios e status de pregão sempre honestos (sem falso `LIVE` fora de horário).

---

*Crédito de referência: princípios editoriais adaptados de [`heydamir/unslop`](https://github.com/heydamir/unslop) por Damir Sokolovsky (`@heydamir`), sob licença CC BY 4.0.*
