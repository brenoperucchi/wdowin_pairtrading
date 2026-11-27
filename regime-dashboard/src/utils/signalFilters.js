// Quais estratégias aparecem no painel Walls & Fluxo (e no card do Instagram). Fonte única: o painel e o
// estúdio de marketing importam daqui, para o card nunca divergir do que o painel mostra.
export const WALLS_FLOW_6_IDS = [
    "WIN_DIV_WALL",
    "WDO_DIV_WALL",
    "ESP_DIV_V22_WIN",
    "C1a_BRK_WIN",
    "V1a_DIV_WDO",
    "SYM_DIV_WIN",
    "SYM_DIV_WDO",
];
export const WALLS_FLOW_6_SET = new Set(WALLS_FLOW_6_IDS);
export const MT5_TOP6_IDS = ["EST_04", "EST_07", "EST_13", "EST_14", "EST_15", "WDO_01", "WDO_05", "WDO_07"];
export const MT5_TOP6_SET = new Set(MT5_TOP6_IDS);

export function filterSignalsForHost(signalsLog = [], isWallsFlow = false) {
    if (!Array.isArray(signalsLog)) return [];
    if (isWallsFlow) {
        return signalsLog.filter((s) => s && WALLS_FLOW_6_SET.has(String(s.strategy_id || "")));
    }
    return signalsLog.filter((s) => s && MT5_TOP6_SET.has(String(s.strategy_id || "")));
}
