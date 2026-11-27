// Legenda final de um post: texto gerado pelo estúdio + avisos fixos. O servidor recusa legenda sem o aviso.
export const DISCLAIMER = "Conteúdo educacional. Sem recomendação de investimento.";
const PAST_NOTICE = "Resultado passado não garante resultado futuro.";
const RESULT_NOTICE =
    "Este resumo mostra as entradas sinalizadas pelas Walls, não o resultado de uma conta ou de um robô. " +
    "Os pontos positivos são o MÁXIMO que o preço andou a favor depois do sinal. " +
    "Os stops aparecem com o valor que de fato saiu. Mostramos o dia inteiro.";

function stripPanelDisclaimer(text) {
    return String(text || "")
        .replace(/\n?⚠️?\s*Conteúdo educacional[^\n]*$/u, "")
        .trim();
}

export function finalCaption(raw, kind, asset) {
    const body = stripPanelDisclaimer(raw);
    const tags = ["#MagicWalls", asset && /^[A-Z0-9]+$/.test(asset) ? `#${asset}` : "", "#B3"].filter(Boolean).join(" ");
    if (kind === "end_of_day") {
        return `${body}\n\n${RESULT_NOTICE}\n\n${DISCLAIMER} ${PAST_NOTICE}\n${tags}`;
    }
    const hasNotice = body.includes(DISCLAIMER);
    return hasNotice ? body : `${body}\n\n${DISCLAIMER}\n${tags}`;
}

/** Corpo editável da legenda: tudo antes dos avisos fixos (que o código anexa de novo depois). */
export function captionBody(caption) {
    const text = String(caption || "");
    const cuts = [RESULT_NOTICE.slice(0, 30), DISCLAIMER, "⚠️ Conteúdo educacional", "⚠ Conteúdo educacional"]
        .map((marker) => text.indexOf(marker))
        .filter((i) => i >= 0);
    return (cuts.length ? text.slice(0, Math.min(...cuts)) : text).trim();
}
