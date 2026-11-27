import test from "node:test";
import assert from "node:assert/strict";
import { captionBody, finalCaption, DISCLAIMER } from "../src/utils/marketingCaption.js";

const RAW = "Magic Walls — Resumo do pregão · Mini-Índice (WIN) (Qui, 26/11/2026)\n\n• #1 · 11:35 · X Venda (175.105) → +1.325 pts\n\nTotal: 1 sinais.";

test("captionBody devolve o corpo sem os avisos fixos (fim do dia)", () => {
    const full = finalCaption(RAW, "end_of_day", "WIN");
    assert.ok(full.includes(DISCLAIMER) && full.includes("#MagicWalls"));
    assert.equal(captionBody(full), RAW);
});

test("finalCaption(captionBody(x)) reproduz x: sem aviso duplicado", () => {
    const full = finalCaption(RAW, "end_of_day", "WDO");
    assert.equal(finalCaption(captionBody(full), "end_of_day", "WDO"), full);
    assert.equal(full.split(DISCLAIMER).length - 1, 1);
});

test("captionBody tira o aviso com emoji do painel e aceita texto sem aviso", () => {
    assert.equal(captionBody(`${RAW}\n⚠️ Conteúdo educacional. Sem recomendação de investimento.`), RAW);
    assert.equal(captionBody(RAW), RAW);
    assert.equal(captionBody(""), "");
    assert.equal(captionBody(null), "");
});

test("legenda de outro tipo (manhã) também volta ao corpo", () => {
    const full = finalCaption("Walls de hoje no WIN.", "morning", "WIN");
    assert.equal(captionBody(full), "Walls de hoje no WIN.");
});
