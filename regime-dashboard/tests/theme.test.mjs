import test from "node:test";
import assert from "node:assert/strict";
import { normalizeTheme, nextTheme } from "../src/utils/theme.js";

test("só 'light' é claro; qualquer outro valor cai no escuro", () => {
    assert.equal(normalizeTheme("light"), "light");
    for (const v of ["dark", "", null, undefined, "azul"]) assert.equal(normalizeTheme(v), "dark");
});
test("alternar vai de um para o outro", () => {
    assert.equal(nextTheme("dark"), "light");
    assert.equal(nextTheme("light"), "dark");
    assert.equal(nextTheme(undefined), "light");
});
