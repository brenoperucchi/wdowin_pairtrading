# Magic Walls — Manual Compacto da Marca (Flip Strata · Ink Azul)

## 1. A marca e o conceito

- **Ideia central:** Três estratos horizontais de liquidez com chanfros internos a `45°` em simetria invertida de `180°` — representando **Call Wall** (topo), **FlipWall** (eixo central) e **Put Wall** (base). Evolui a `WallsMark` original eliminando a leitura ambígua de menu hambúrguer.
- **Versões principais:** Horizontal (primária), Empilhada (capas/cartões/selos), Símbolo isolado, Wordmark isolado e Tile para favicon/app.
- **Arquivos mestres (`docs/brand/magic-walls/kit/`):**
  - `masters/` — SVGs vetoriais puros em `<path>` (sem `<text>`, filtros ou raster): variantes `-dark` (fundo escuro) e `-light` (fundo claro/impressão), além de `-small` (otimizado para `16–24 px`) e `-tile-dark`.
  - `variants/` — Exportações em SVG e PNG (`512 px`, `1024 px`, `1200 px`) nas versões colorida, preta, branca invertida e monocromáticas (`#38bdf8`, `#0284c7`, `#0e1118`).
  - `web-icons/` — `favicon.svg`, `favicon.ico` (`16/32/48 px`), `apple-touch-icon.png` (`180 px`), `icon-192.png`, `icon-512.png`, `maskable-512.png`, `site.webmanifest` e `head-snippet.html`.
  - `presentation/` — Prancha completa em HTML (`board.html`) e slides PNG (`slides/`).

---

## 2. Área de respiro (Clear Space)

Mantenha uma zona livre mínima de **`1 × h`** em todos os lados da marca, onde **`h`** é a altura de uma barra do símbolo **Flip Strata** (`36u` no mestre escuro / `38u` no mestre claro; aproximadamente `20%` da altura total do símbolo). A zona escala proporcionalmente com o tamanho aplicado.

---

## 3. Tamanho mínimo de reprodução

| Versão | Tela (Digital) | Impressão | Arquivo recomendado |
|---|---|---|---|
| **Lockup Horizontal** | `96 px` de largura | `25 mm` de largura | `magic-walls-horizontal-*.svg` |
| **Lockup Empilhado** | `88 px` de largura | `24 mm` de largura | `magic-walls-stacked-*.svg` |
| **Símbolo isolado** | `16 px` | `6 mm` | `magic-walls-symbol-small-*.svg` (até `24 px`) |
| **Favicon / App Tile** | `16 px` | — | `web-icons/favicon.svg` ou `favicon.ico` |

---

## 4. Paleta oficial (calibrada para `www.magicwalls.com.br`)

| Nome / Papel | HEX | RGB | CMYK (aprox.) | Pantone (aprox.)* | Contraste verificado |
|---|---|---|---|---|---|
| **Chrome / Tile** (`--mw-chrome`) | `#0a0c12` | `10, 12, 18` | `44, 33, 0, 93` | `Black 6 C` | Base de navbar e tile |
| **Ink Base** (`--mw-bg`) | `#0e1118` | `14, 17, 24` | `42, 29, 0, 91` | `433 C` | `18.9:1` em `#ffffff` |
| **Chalk / Call Wall** (`--mw-text-1`) | `#eef0f5` | `238, 240, 245` | `3, 2, 0, 4` | `Cool Gray 1 C` | `17.3:1` em `#0a0c12` |
| **Cyan FlipWall** (`--mw-accent`) | `#38bdf8` | `56, 189, 248` | `77, 24, 0, 3` | `298 C` | `9.3:1` em `#0a0c12` |
| **Cyan Light / Print** | `#0284c7` | `2, 132, 199` | `99, 34, 0, 22` | `2925 C` | `4.0:1` em `#ffffff` |
| **Slate / Put Wall** (`--mw-text-3`) | `#848da2` | `132, 141, 162` | `19, 13, 0, 36` | `7544 C` | `5.7:1` em `#0a0c12` · `3.3:1` em `#ffffff` |

*\*Nota: equivalências CMYK e Pantone são aproximações numéricas — valide sempre contra catálogo físico Pantone antes de produção gráfica em offset ou serigrafia.*

### Combinações aprovadas de fundo e marca
- **Dark UI (padrão web / terminal / vídeo):** versão `-dark` (`#eef0f5` + `#38bdf8` + `#848da2`) ou monocromática branca (`-white`) sobre `#0a0c12`, `#0e1118` ou `#131720`.
- **Light UI / Impressão clara:** versão `-light` (`#0e1118` + `#0284c7` + `#848da2`) ou monocromática preta/`#0e1118` sobre `#ffffff` ou `#f6f8fb`. Nunca aplicar `#38bdf8` diretamente em texto ou barra central sobre papel branco (contraste cai para `2.1:1`).
- **Fotos / fundos complexos:** usar o tile `-tile-dark` (`#0a0c12`) ou a versão monocromática branca sobre área escura e calma.

---

## 5. Tipografia

- **Wordmark:** `IBM Plex Sans` **SemiBold (`600`)**, em *Title Case* (`Magic Walls`), com kerning óptico aplicado e já convertido em curvas `<path>` nos arquivos finais.
- **Interface e UI:** `IBM Plex Sans` (`400`, `500`, `600`) para rótulos e leitura.
- **Dados e cotações:** `IBM Plex Mono` (`400`, `500`, `600`) com `tabular-nums`.
- **Licença:** `IBM Plex` é distribuída sob licença aberta **SIL Open Font License 1.1 (OFL)**, livre para uso comercial e incorporação em marcas.

---

## 6. Proibições (Anti-Slop Ink Azul)

- **Não** esticar, inclinar ou alterar a proporção dos chanfros de `45°` do símbolo.
- **Não** adicionar brilho (`glow`), sombras (`box-shadow` / `shadowBlur`), gradientes, bordas neon ou `backdrop-filter: blur`.
- **Não** usar pesos tipográficos `700`, `800` ou `900` nem recriar o wordmark digitando texto solto fora dos arquivos em curvas.
- **Não** usar cantos arredondados (`rx`) no novo símbolo **Flip Strata** nem reordenar as cores fora da hierarquia Topo `#eef0f5` / Centro `#38bdf8` / Base `#848da2`.

---

## 7. Snippets prontos para integração no site (quando desejar aplicar)

### React SVG inline (`20×20` para Topbar `#0a0c12` — corte óptico pequeno)
```jsx
function WallsMark({ size = 20 }) {
    return (
        <svg width={size} height={size} viewBox="0 0 256 256" fill="none" aria-hidden="true">
            <path fill="#eef0f5" d="M24 28 H178 L134 72 H24 Z" />
            <path fill="#38bdf8" d="M24 106 H232 V150 H24 Z" />
            <path fill="#848da2" d="M122 184 H232 V228 H78 Z" />
        </svg>
    );
}
```

### HTML `<head>` (`web-icons/head-snippet.html`)
```html
<link rel="icon" href="/favicon.ico" sizes="48x48">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<meta name="theme-color" content="#0a0c12">
```

---

## 8. Notas de entrega (Handover)

- **Ajustes ópticos aplicados:** versão `-dark` afinada de `38u → 36u` (ganho de respiro de `37u → 39u`) para compensar irradiação óptica do claro sobre escuro; corte `-small` engrossado para `44u` (`2.75 px` a `16 px`) garantindo nitidez em favicons e topbars; variante clara utiliza `#0284c7` na barra central para manter contraste acessível em papel e fundo branco.
- **Auditoria automatizada (`svg_audit.py`):** símbolos mestres com **100/100** (`0` avisos) e lockups/wordmarks com **91/100** (`0 FAIL`, sem `<text>` vivo, sem rasters/filtros e sem erros de contraste nos testes com `--bg "#0a0c12"` e `--bg "#ffffff"`).
- **Registro:** este kit não substitui consulta formal de anterioridade no INPI ou busca reversa de imagem antes de registro de marca.
