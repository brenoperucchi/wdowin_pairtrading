import test from "node:test";
import assert from "node:assert/strict";
import { ADMIN_PAGES, visibleAdminPages, pageKeyFromPathname, pageForPathname, hrefForPage, isAdminUser } from "../src/admin/adminPages.js";
import { ROUTE_PATHS } from "../src/routes.js";

test("administrador vê Gráficos, Marketing e Logins", () => {
    const pages = visibleAdminPages({ saasEnabled: true, user: { plan: "admin" } });
    assert.deepEqual(pages.map((p) => p.key), ["charts", "marketing", "users"]);
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

test("a página atual vem do caminho da URL; /admin, /manual e desconhecido não destacam nada", () => {
    assert.equal(pageKeyFromPathname("/admin/marketing"), "marketing");
    assert.equal(pageKeyFromPathname("/admin/users"), "users");
    assert.equal(pageKeyFromPathname("/admin/users/"), "users");
    assert.equal(pageKeyFromPathname("/"), "charts");
    assert.equal(pageKeyFromPathname("/admin"), "");
    assert.equal(pageKeyFromPathname("/manual"), "");
    assert.equal(pageKeyFromPathname("/qualquer"), "");
    assert.equal(pageForPathname("/admin/marketing").label, "Marketing");
});

test("endereços: cada página é o caminho dela, sem ?mode= nem outro parâmetro", () => {
    const [charts, marketing, users] = ADMIN_PAGES;
    assert.equal(hrefForPage(charts), "/");
    assert.equal(hrefForPage(marketing), "/admin/marketing");
    assert.equal(hrefForPage(users), "/admin/users");
    for (const p of ADMIN_PAGES) assert.ok(!hrefForPage(p).includes("?"), p.key);
});

test("registro: chaves e rotas são únicas, toda rota existe e as de admin ficam sob /admin", () => {
    const keys = ADMIN_PAGES.map((p) => p.key), routes = ADMIN_PAGES.map((p) => p.route);
    assert.equal(new Set(keys).size, keys.length);
    assert.equal(new Set(routes).size, routes.length);
    for (const p of ADMIN_PAGES) {
        assert.ok(p.label && typeof p.label === "string");
        assert.ok(ROUTE_PATHS[p.route] !== undefined, `rota inexistente: ${p.route}`);
        if (p.key !== "charts") assert.ok(ROUTE_PATHS[p.route].startsWith("/admin/"), p.key);
    }
});
