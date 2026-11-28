import test from "node:test";
import assert from "node:assert/strict";
import { appBasePath, hrefForRoute, routeKeyFromPathname, routePathFromPathname, ROUTE_PATHS } from "../src/routes.js";
import { parseEnum, parseIsoDate, readParam, withParams } from "../src/utils/urlState.js";

test("cada rota tem um caminho em inglês e a leitura volta à mesma chave", () => {
    for (const [key, path] of Object.entries(ROUTE_PATHS)) {
        assert.match(path, /^\/[a-z-]*(\/[a-z-]+)*$/, `${key}: ${path}`);
        assert.equal(routeKeyFromPathname(path, ""), key);
    }
    assert.deepEqual(Object.values(ROUTE_PATHS).sort(), ["/", "/admin", "/admin/marketing", "/admin/users", "/manual", "/morning-video"].sort());
});

test("barra final, index.html e prefixo do túnel não mudam a rota; caminho desconhecido é notFound", () => {
    assert.equal(routeKeyFromPathname("/admin/marketing/", ""), "adminMarketing");
    assert.equal(routeKeyFromPathname("/index.html", ""), "charts");
    assert.equal(routeKeyFromPathname("/magicwall", ""), "charts");
    assert.equal(routeKeyFromPathname("/magicwall/manual", ""), "manual");
    assert.equal(routeKeyFromPathname("/admin/logins", ""), "notFound");
    assert.equal(routeKeyFromPathname("/qualquer-coisa", ""), "notFound");
});

test("o prefixo de implantação vem do base do build e é descontado em um lugar só", () => {
    assert.equal(appBasePath("/"), "");
    assert.equal(appBasePath("./"), "");
    assert.equal(appBasePath(undefined), "");
    assert.equal(appBasePath("/app/"), "/app");
    assert.equal(routeKeyFromPathname("/app/admin/users", "/app"), "adminUsers");
    assert.equal(routeKeyFromPathname("/app", "/app"), "charts");
    assert.equal(routePathFromPathname("/app/admin", "/app"), "/admin");
    assert.equal(hrefForRoute("adminUsers", {}, "/app"), "/app/admin/users");
    assert.equal(hrefForRoute("charts", {}, "/app"), "/app/");
    assert.equal(hrefForRoute("charts", {}, ""), "/");
});

test("hrefForRoute: só filtro e aba na query; vazio é omitido; rota desconhecida falha", () => {
    assert.equal(hrefForRoute("adminMarketing", { tab: "history" }, ""), "/admin/marketing?tab=history");
    assert.equal(hrefForRoute("charts", { date: "2026-11-26", tf: "m1", tab: "" }, ""), "/?date=2026-11-26&tf=m1");
    assert.throws(() => hrefForRoute("nope"));
});

test("withParams troca, remove e preserva os demais parâmetros", () => {
    assert.equal(withParams("?date=2026-11-26&tf=m1", { tf: "" }), "?date=2026-11-26");
    assert.equal(withParams("", { tab: "wdo" }), "?tab=wdo");
    assert.equal(withParams("?tab=wdo", { tab: null }), "");
    assert.equal(withParams("?a=1", { b: "2" }), "?a=1&b=2");
    assert.equal(readParam("?tab=wdo", "tab"), "wdo");
    assert.equal(readParam("", "tab"), "");
});

test("URL editada à mão nunca quebra: enum e data inválidos caem no padrão", () => {
    assert.equal(parseEnum("m1", ["m1"], ""), "m1");
    assert.equal(parseEnum("xx", ["m1"], ""), "");
    assert.equal(parseIsoDate("2026-11-26"), "2026-11-26");
    assert.equal(parseIsoDate("26/11/2026"), "");
    assert.equal(parseIsoDate("<script>"), "");
});
