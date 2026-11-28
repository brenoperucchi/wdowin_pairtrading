// Prova que o motor novo reproduz o card do painel. Referência real: print do Card IG de WIN em 26/11/2026
// (3 sinais, 1 stop, melhor +1.325 pts; #2 stop -250; #3 +255). Dados congelados capturados do ks4.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadCardInputs, buildEngineRequest, extractCardBase } from "../src/marketing/studio/cardInputs.js";
import { buildInstagramSignals, buildInstagramCaption, SIGNAL_RULES, describeSignalRule } from "../src/utils/instagramSignalMetrics.js";

const FIX = path.join(path.dirname(fileURLToPath(import.meta.url)), "fixtures");
const read = (n) => JSON.parse(fs.readFileSync(path.join(FIX, n), "utf8"));
const has = (n) => fs.existsSync(path.join(FIX, n));

test("extractCardBase tira o dia anterior e filtra as estratégias do painel", () => {
    const base = extractCardBase({
        session_date: "2026-11-26T00:00",
        all_walls: [{ type: "Wall", price: 1 }],
        caminho_a: {
            m5_dealer_vs_flow_series: [{ time: "09:00", is_prev_day: true }, { time: "09:05" }, { is_prev_day: false }],
            signals_log: [{ strategy_id: "SYM_DIV_WIN" }, { strategy_id: "EST_04" }],
        },
    }, "WIN");
    assert.equal(base.bars.length, 1);
    assert.equal(base.sessionDate, "2026-11-26");
    assert.deepEqual(base.signalsLog.map((s) => s.strategy_id), ["SYM_DIV_WIN"]);
});

test("sem barras suficientes devolve vazio sem chamar o motor", async () => {
    let calls = 0;
    const r = await loadCardInputs({ etapa1: { WIN: { caminho_a: { m5_dealer_vs_flow_series: [{ time: "09:00" }] } } }, asset: "WIN", fetchDivs: async () => { calls += 1; return {}; } });
    assert.equal(r.status, "sem_barras");
    assert.equal(calls, 0);
});

test("pré-calculado dispensa o motor; vazio chama o motor uma vez", async () => {
    const bars = Array.from({ length: 6 }, (_, i) => ({ time: `09:${10 + i}`, open: 1, high: 2, low: 0, close: 1 }));
    const pre = [{ dir: 1, f1_time: "09:10", f1_px: 1, f1_wave: 1, f2_time: "09:15", f2_px: 2, f2_wave: 1, anchor: "WALL" }];
    let calls = 0;
    const etapa1 = (divs) => ({ WIN: { caminho_a: { m5_dealer_vs_flow_series: bars, engine_divs_v32: divs, signals_log: [] } } });
    const a = await loadCardInputs({ etapa1: etapa1(pre), asset: "WIN", fetchDivs: async () => { calls += 1; return {}; } });
    assert.equal((a.status, calls), 0); assert.equal(a.status, "pre_calculado"); assert.equal(a.divergences[0].type, "BULL_DIV");
    const b = await loadCardInputs({ etapa1: etapa1(null), asset: "WIN", fetchDivs: async () => { calls += 1; return { ok: true, divergences: pre }; } });
    assert.equal(calls, 1); assert.equal(b.status, "motor"); assert.equal(b.divergences.length, 1);
});

test("falha de rede tenta duas vezes e acaba em erro_motor sem quebrar", async () => {
    const bars = Array.from({ length: 6 }, (_, i) => ({ time: `09:${10 + i}`, open: 1, high: 2, low: 0, close: 1 }));
    let calls = 0;
    const r = await loadCardInputs({ etapa1: { WIN: { caminho_a: { m5_dealer_vs_flow_series: bars, signals_log: [] } } }, asset: "WIN", fetchDivs: async () => { calls += 1; throw new Error("rede"); } });
    assert.equal(calls, 2); assert.equal(r.status, "erro_motor"); assert.deepEqual(r.divergences, []);
});

async function build(date, asset) {
    const etapa1 = read(`etapa1_${date}.json`);
    const motor = read(`divs_${asset}_${date}.json`);
    const inputs = await loadCardInputs({ etapa1, asset, fetchDivs: async () => motor });
    const built = buildInstagramSignals(inputs.bars, inputs.divergences, asset, null);
    return { inputs, built, sig: built.allSignals.map((x) => ({ n: x.num, lado: x.directionLabel, hora: x.entryTime, status: x.status, pts: x.resultPts })) };
}

// Referência (regra do Miqueias, commit 2bf56ca: stop atrás do pivô): WIN 26/11, #1 Venda 11:35 +1.325; #2 Compra 13:10 stop -445.
// O print antigo do painel (stop na Wall oposta, #2 = -250) vale só para a regra anterior.
// O dado congelado é posterior ao fechamento; nele o motor recalcula o 3º sinal (o SELL de 17:35 some e vira um
// sinal neutro às 18:00). Por isso só os dois primeiros são comparados com o print.
test("WIN 26/11: sinais 1 e 2 seguem a regra de stop do pivô; total e stops idênticos",
    { skip: !has("divs_WIN_2026-11-26.json") }, async () => {
    const { built, sig } = await build("2026-11-26", "WIN");
    assert.equal(built.summary.totalSignals, 3);
    assert.equal(built.summary.stopCount, 1);
    assert.deepEqual(sig[0], { n: 1, lado: "VENDA", hora: "11:35", status: "PROTECTED", pts: 1325 });
    assert.deepEqual(sig[1], { n: 2, lado: "COMPRA", hora: "13:10", status: "STOP", pts: -445 });
});

// Valores de referência do motor novo (trava regressões); NÃO são prova de igualdade com o painel.
const GOLDEN = {
    "2026-11-26|WIN": { total: 3, stops: 1, bruto: 1325, liquido: 880 },
    "2026-11-26|WDO": { total: 4, stops: 1, bruto: 30, liquido: 25 },
    "2026-11-25|WIN": { total: 5, stops: 1, bruto: 1335, liquido: 755 },
    "2026-11-25|WDO": { total: 3, stops: 0, bruto: 147.5, liquido: 147.5 },
};
for (const [key, want] of Object.entries(GOLDEN)) {
    const [date, asset] = key.split("|");
    test(`referência fixa ${asset} ${date}`, { skip: !has(`divs_${asset}_${date}.json`) }, async () => {
        const { built } = await build(date, asset);
        const s = built.summary;
        assert.deepEqual({ total: s.totalSignals, stops: s.stopCount, bruto: s.grossMfePts, liquido: s.netPts }, want);
    });
}

// Uma regra só: o texto da legenda e os rótulos nascem de SIGNAL_RULES, nunca de números digitados em outro lugar.
test("legenda e rótulos acompanham SIGNAL_RULES (mudar a regra muda o texto sozinho)", () => {
    const antes = SIGNAL_RULES.WIN.protectPts;
    const base = { symKey: "WIN", dateInfo: { short: "26/11/2026", weekday: "Qui" }, activeSignals: [], summary: {} };
    try {
        SIGNAL_RULES.WIN.protectPts = 222;
        assert.match(describeSignalRule("WIN").ruleTxt, /222 pts/);
        assert.match(describeSignalRule("WIN").ruleTxt, /pivô/);
        assert.doesNotMatch(describeSignalRule("WIN").ruleTxt, /Wall oposta/);
        const sig = [{ num: 1, isBull: true, isStopped: false, entryTime: "10:00", anchorCode: "W", entryPrice: 1, mfePts: 300, isBest: true }];
        const cap = buildInstagramCaption({ ...base, activeSignals: sig, summary: { totalSignals: 1, winCount: 1, stopCount: 0, netPts: 300, totalStopPts: 0, bestSignal: null } });
        assert.match(cap, /≥222 pts/);
        assert.match(cap, /proteção após \+222 pts/);
    } finally {
        SIGNAL_RULES.WIN.protectPts = antes;
    }
});

import { buildInstagramSignals as _build, buildInstagramCaption as _caption } from "../src/utils/instagramSignalMetrics.js";
test("legenda: protegido no singular e sinal sem desfecho contado à parte (não vira 'protegido')", () => {
    // 3 barras; compra com stop tocado, venda protegida, venda na última barra (sem desfecho)
    const bars = [
        { time: "10:00", open: 1000, high: 1010, low: 990, close: 1000 },
        { time: "10:05", open: 1000, high: 1005, low: 700, close: 750 },
        { time: "10:10", open: 750, high: 760, low: 740, close: 750 },
        { time: "10:15", open: 750, high: 755, low: 745, close: 750 },
    ];
    const divs = [
        { type: "BEAR_DIV", confTime: "10:00", currTime: "10:00", prevTime: "10:00", currPrice: 1010, prevPrice: 1000, anchor: "EXTREMO DO DIA" },
        { type: "BEAR_DIV", confTime: "10:15", currTime: "10:15", prevTime: "10:10", currPrice: 755, prevPrice: 750, anchor: "EXTREMO DO DIA" },
    ];
    const r = _build(bars, divs, "WIN");
    assert.equal(r.summary.winCount, 1);
    assert.equal(r.summary.neutralCount, 1);
    const cap = _caption({ symKey: "WIN", dateInfo: { short: "26/11/2026", weekday: "Qui" }, activeSignals: r.activeSignals, summary: r.summary, handle: "@x" });
    assert.match(cap, /1 protegido ≥/);
    assert.doesNotMatch(cap, /1 protegidos/);
    assert.match(cap, /1 sem desfecho/);
});
