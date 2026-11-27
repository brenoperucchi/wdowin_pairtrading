// Entradas do card do Instagram para um (ativo, data), sem depender do painel.
// Reproduz a derivação que o IntradayCompassPanel faz para alimentar o InstagramCardModal:
//   bars        = série M5 oficial da sessão (sem o dia anterior)
//   walls       = all_walls do payload
//   divergences = engine_divs_v32 pré-calculado, ou resposta do motor (POST /api/compass/divergencias_motor)
// Diferenças deliberadas em relação ao painel: nada aqui depende de toggles, zoom ou janela visível, então o card
// nunca sai vazio por causa da interface nem com barras de uma data e rótulo de outra.
import { filterSignalsForHost } from "../../utils/signalFilters.js";

export const DIV_ENGINE = "v3.2";
export const MIN_BARS = 5;

const isoDay = (v) => String(v || "").slice(0, 10);

/** Extrai do payload de um ativo (etapa1[ativo]) o que o card precisa. */
export function extractCardBase(payload, asset) {
    const ca = (payload && payload.caminho_a) || {};
    const series = Array.isArray(ca.m5_dealer_vs_flow_series) ? ca.m5_dealer_vs_flow_series : [];
    const bars = series.filter((pt) => pt && !pt.is_prev_day && pt.time);
    const walls = Array.isArray(payload?.all_walls) ? payload.all_walls : [];
    const signalsLog = filterSignalsForHost(ca.signals_log || [], true);
    const sessionDate = isoDay(payload?.session_date || ca.ref_date);
    const precomputed = Array.isArray(ca.engine_divs_v32) ? ca.engine_divs_v32 : null;
    return { asset: asset === "WDO" ? "WDO" : "WIN", bars, walls, signalsLog, sessionDate, precomputed };
}

/** Corpo do POST do motor de divergências (idêntico ao do painel). */
export function buildEngineRequest(base) {
    const trades = base.signalsLog
        .filter((s) => s && !s.is_prev_day && s.time)
        .map((s) => ({ strategy_id: s.strategy_id, time: String(s.time).slice(0, 5), direction: s.direction }));
    return {
        asset: base.asset,
        engine: DIV_ENGINE,
        bars: base.bars.map((pt) => ({
            time: String(pt.time).slice(0, 5),
            open: Number(pt.open),
            high: Number(pt.high),
            low: Number(pt.low),
            close: Number(pt.close),
            wave: Number(pt.smart_swing_wave || 0),
        })),
        walls: base.walls.map((w) => ({ type: w.type, price: Number(w.price) })),
        trades,
    };
}

/** Lista do motor -> divergências no formato que buildInstagramSignals e o card esperam. */
export function mapEngineDivergences(list) {
    return (list || []).map((d) => ({
        type: d.dir === 1 ? "BULL_DIV" : "BEAR_DIV",
        prevTime: d.f1_time,
        prevPrice: Number(d.f1_px),
        prevWave: Number(d.f1_wave),
        currTime: d.f2_time,
        currPrice: Number(d.f2_px),
        currWave: Number(d.f2_wave),
        confTime: d.conf_time,
        triggerTime: d.trigger_time,
        triggerKind: d.trigger_kind,
        nearWall: String(d.anchor || "").includes("WALL"),
        anchor: d.anchor,
        isPendingTrigger: false,
    }));
}

/**
 * Carrega as entradas completas do card.
 * @param {object} args
 * @param {object} args.etapa1   resposta de /api/compass/etapa1?date_str=...
 * @param {"WIN"|"WDO"} args.asset
 * @param {(body: object) => Promise<object>} args.fetchDivs  faz o POST do motor e devolve o JSON
 */
export async function loadCardInputs({ etapa1, asset, fetchDivs }) {
    const base = extractCardBase(etapa1?.[asset], asset);
    if (base.bars.length < MIN_BARS) {
        return { ...base, divergences: [], engineList: [], status: "sem_barras" };
    }
    let list = base.precomputed && base.precomputed.length > 0 ? base.precomputed : null;
    let status = list ? "pre_calculado" : "motor";
    if (!list) {
        let reply = null;
        for (let attempt = 0; attempt < 2 && reply === null; attempt += 1) {
            try {
                reply = await fetchDivs(buildEngineRequest(base));
            } catch {
                reply = null;
            }
        }
        const fromApi = reply && reply.ok && Array.isArray(reply.divergences) ? reply.divergences : [];
        list = fromApi;
        status = reply === null ? "erro_motor" : "motor";
    }
    return { ...base, engineList: list, divergences: mapEngineDivergences(list), status };
}
