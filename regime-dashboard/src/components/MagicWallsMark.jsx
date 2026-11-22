// Símbolo oficial Magic Walls — Flip Strata (docs/brand/magic-walls/kit/BRAND_GUIDELINES.md)
// Três estratos horizontais com chanfros internos de 45° em simetria invertida de 180°:
// Topo (#eef0f5 Call Wall) · Centro (#38bdf8 FlipWall) · Base (#848da2 Put Wall).
// Sem rx, sem glow e sem filtros; corte óptico "small" (44u) para 16–24 px e "master" (36u) acima de 24 px.

export default function MagicWallsMark({ size = 20, variant, className, style }) {
    const useSmall = variant ? variant === "small" : size <= 24;
    return (
        <svg
            width={size}
            height={size}
            viewBox="0 0 256 256"
            fill="none"
            aria-hidden="true"
            className={className}
            style={{ display: "block", flexShrink: 0, ...style }}
        >
            {useSmall ? (
                <>
                    <path fill="#eef0f5" d="M24 28 H178 L134 72 H24 Z" />
                    <path fill="#38bdf8" d="M24 106 H232 V150 H24 Z" />
                    <path fill="#848da2" d="M122 184 H232 V228 H78 Z" />
                </>
            ) : (
                <>
                    <path fill="#eef0f5" d="M28 35 H175 L139 71 H28 Z" />
                    <path fill="#38bdf8" d="M28 110 H228 V146 H28 Z" />
                    <path fill="#848da2" d="M117 185 H228 V221 H81 Z" />
                </>
            )}
        </svg>
    );
}
