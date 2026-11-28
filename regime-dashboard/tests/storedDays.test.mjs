import test from "node:test";
import assert from "node:assert/strict";
import { decideDay } from "../src/utils/storedDays.js";

const dates = ["2026-11-26", "2026-11-25", "2026-11-24"];

test("sem feed ao vivo abre o último pregão guardado", () => {
    assert.deepEqual(decideDay({ live: false, dates, selectedDate: "", autoDay: "" }), { selectedDate: "2026-11-26", autoDay: "2026-11-26" });
});
test("sem feed e sem dias guardados fica em ao vivo (sem inventar data)", () => {
    assert.deepEqual(decideDay({ live: false, dates: [], selectedDate: "", autoDay: "" }), { selectedDate: "", autoDay: "" });
});
test("com feed ao vivo não troca de dia", () => {
    assert.deepEqual(decideDay({ live: true, dates, selectedDate: "", autoDay: "" }), { selectedDate: "", autoDay: "" });
});
test("escolha manual do usuário nunca é trocada, com ou sem feed", () => {
    assert.deepEqual(decideDay({ live: false, dates, selectedDate: "2026-11-24", autoDay: "" }), { selectedDate: "2026-11-24", autoDay: "" });
    assert.deepEqual(decideDay({ live: true, dates, selectedDate: "2026-11-24", autoDay: "" }), { selectedDate: "2026-11-24", autoDay: "" });
});
test("produtor volta: sai do dia que o painel abriu sozinho", () => {
    assert.deepEqual(decideDay({ live: true, dates, selectedDate: "2026-11-26", autoDay: "2026-11-26" }), { selectedDate: "", autoDay: "" });
});
test("produtor volta mas o usuário já tinha escolhido outro dia: mantém", () => {
    assert.deepEqual(decideDay({ live: true, dates, selectedDate: "2026-11-24", autoDay: "2026-11-26" }), { selectedDate: "2026-11-24", autoDay: "" });
});
