// Helpers puros usados pelo desenho do card (movidos de InstagramCardModal.jsx sem alterações).

export function formatDuration(mins) {
    const m = Math.round(Number(mins || 0));
    if (m <= 0) return "—";
    if (m < 60) return `${m}m`;
    const h = Math.floor(m / 60);
    const rem = m % 60;
    return rem > 0 ? `${h}h${String(rem).padStart(2, "0")}` : `${h}h`;
}

export function getNweValues(pt) {
    const line = Number(pt?.nwe100_line ?? pt?.nwe30_line ?? pt?.nwe_line ?? 0);
    const upper = Number(pt?.nwe100_upper ?? pt?.nwe30_upper ?? pt?.nwe_upper ?? 0);
    const lower = Number(pt?.nwe100_lower ?? pt?.nwe30_lower ?? pt?.nwe_lower ?? 0);
    return { line, upper, lower };
}
