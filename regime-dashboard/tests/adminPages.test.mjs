import test from "node:test";
import assert from "node:assert/strict";
import { ADMIN_PAGES, visibleAdminPages, pageKeyFromSearch, hrefForPage, isAdminUser } from "../src/admin/adminPages.js";

test("administrador vê Gráficos, Marketing e Logins", () => {
    const pages = visibleAdminPages({ saasEnabled: true, user: { plan: "admin" } });
    assert.deepEqual(pages.map((p) => p.key), ["charts", "marketing", "logins"]);
});

test("usuário comum, sem login ou plano vazio não vê nenhuma página administrativa", () => {
    for (const user of [{ plan: "core" }, { plan: "pro" }, { plan: "trial" }, { plan: "" }, {}, null, undefined]) {
        assert.deepEqual(visibleAdminPages({ saasEnabled: true, user }), [], JSON.stringify(user));
    }
});

test("sem o modo SaaS a barra não aparece, mesmo com plano admin", () => {
    assert.deepEqual(visibleAdminPages({ saasEnabled: false, user: { plan: "admin" } }), []);
});

test("plano admin é reconhecido sem depender de caixa ou espaços", () => {
    assert.equal(isAdminUser({ plan: " ADMIN " }), true);
    assert.equal(isAdminUser({ plan: "administrador" }), false);
});

test("a página atual vem do parâmetro mode; desconhecido cai em Gráficos", () => {
    assert.equal(pageKeyFromSearch("?mode=marketing"), "marketing");
    assert.equal(pageKeyFromSearch("?mode=admin"), "logins");
    assert.equal(pageKeyFromSearch(""), "charts");
    assert.equal(pageKeyFromSearch("?mode=qualquer"), "charts");
});

test("endereços: Gráficos volta ao caminho limpo, as outras usam ?mode=", () => {
    const [charts, marketing, logins] = ADMIN_PAGES;
    assert.equal(hrefForPage(charts, "/app/"), "/app/");
    assert.equal(hrefForPage(marketing, "/app/"), "/app/?mode=marketing");
    assert.equal(hrefForPage(logins, "/"), "/?mode=admin");
});
