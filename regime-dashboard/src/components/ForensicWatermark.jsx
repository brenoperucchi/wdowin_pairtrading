// Camada 3 Anti-Rateio: Watermark Forense diagonal sutil sobre toda a área de gráfico.
// Invisível para operar (opacity 0.04), identifica imediatamente quem gravar tela ou retransmitir.

export default function ForensicWatermark({ label }) {
    if (!label) return null;
    const safeText = String(label).slice(0, 72);

    return (
        <div
            data-testid="forensic-watermark"
            aria-hidden="true"
            style={{
                position: "fixed",
                inset: 0,
                zIndex: 40,
                pointerEvents: "none",
                userSelect: "none",
                overflow: "hidden",
            }}
        >
            <svg width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
                <defs>
                    <pattern
                        id="mw-forensic-pattern"
                        width="420"
                        height="240"
                        patternUnits="userSpaceOnUse"
                        patternTransform="rotate(-26)"
                    >
                        <text
                            x="16"
                            y="95"
                            fill="#eef0f5"
                            fillOpacity="0.04"
                            fontSize="13"
                            fontWeight="500"
                            fontFamily="'IBM Plex Mono', ui-monospace, monospace"
                            letterSpacing="0.04em"
                        >
                            {safeText}
                        </text>
                        <text
                            x="160"
                            y="210"
                            fill="#38bdf8"
                            fillOpacity="0.04"
                            fontSize="12"
                            fontWeight="500"
                            fontFamily="'IBM Plex Mono', ui-monospace, monospace"
                            letterSpacing="0.04em"
                        >
                            {`Magic Walls · ${safeText}`}
                        </text>
                    </pattern>
                </defs>
                <rect width="100%" height="100%" fill="url(#mw-forensic-pattern)" />
            </svg>
        </div>
    );
}
