// Exportação do card SVG para PNG (movido de InstagramCardModal.jsx sem alterações de comportamento).
import { INK } from "./theme";

const FONT_CSS_URL =
    "https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap";

let fontCssPromise = null;

function bufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let bin = "";
    for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
    return btoa(bin);
}

/** CSS @font-face da IBM Plex (subconjunto latin, com acentos do português) com os arquivos embutidos em base64.
 *  Vem do mesmo Google Fonts que o index.html já usa; guarda em memória. Se a rede falhar devolve "" (o PNG sai com a
 *  fonte do sistema, como antes) e tenta de novo na próxima exportação. */
export function loadEmbeddedFontCss() {
    if (!fontCssPromise) {
        fontCssPromise = (async () => {
            const css = await (await fetch(FONT_CSS_URL)).text();
            const blocks = [...css.matchAll(/\/\*\s*([\w-]+)\s*\*\/\s*(@font-face\s*\{[^}]*\})/g)]
                .filter((m) => m[1] === "latin")
                .map((m) => m[2]);
            if (!blocks.length) throw new Error("sem blocos latin");
            const out = await Promise.all(
                blocks.map(async (block) => {
                    const url = block.match(/url\(([^)]+)\)/)?.[1]?.replace(/['"]/g, "");
                    if (!url) throw new Error("fonte sem url");
                    const buf = await (await fetch(url)).arrayBuffer();
                    return block.replace(/url\([^)]+\)/, `url(data:font/woff2;base64,${bufferToBase64(buf)})`);
                })
            );
            return out.join("\n");
        })().catch(() => {
            fontCssPromise = null;
            return "";
        });
    }
    return fontCssPromise;
}

/** `embedFonts: true` embute a IBM Plex no PNG (sem isso a imagem usa a fonte do sistema de quem exporta). */
export async function svgElementToPngBlob(svgEl, width, height, { embedFonts = false } = {}) {
    if (!svgEl) throw new Error("SVG não encontrado para exportação.");
    const clone = svgEl.cloneNode(true);
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    clone.setAttribute("width", String(width));
    clone.setAttribute("height", String(height));
    clone.setAttribute("viewBox", `0 0 ${width} ${height}`);

    if (embedFonts) {
        const fontCss = await loadEmbeddedFontCss();
        if (fontCss) {
            const style = document.createElementNS("http://www.w3.org/2000/svg", "style");
            style.textContent = fontCss;
            const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
            defs.appendChild(style);
            clone.insertBefore(defs, clone.firstChild);
        }
    }
    const xml = new XMLSerializer().serializeToString(clone);
    const svgBlob = new Blob([`<?xml version="1.0" encoding="UTF-8"?>\n${xml}`], {
        type: "image/svg+xml;charset=utf-8",
    });
    const url = URL.createObjectURL(svgBlob);

    try {
        const img = await new Promise((resolve, reject) => {
            const image = new Image();
            image.decoding = "sync";
            image.onload = () => resolve(image);
            image.onerror = (err) => reject(err || new Error("Falha ao rasterizar SVG."));
            image.src = url;
        });

        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = INK.bg;
        ctx.fillRect(0, 0, width, height);
        ctx.drawImage(img, 0, 0, width, height);

        const pngBlob = await new Promise((resolve, reject) => {
            canvas.toBlob((blob) => {
                if (blob) resolve(blob);
                else reject(new Error("Falha ao gerar PNG."));
            }, "image/png", 1.0);
        });
        return pngBlob;
    } finally {
        URL.revokeObjectURL(url);
    }
}

export function triggerBlobDownload(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1500);
}
