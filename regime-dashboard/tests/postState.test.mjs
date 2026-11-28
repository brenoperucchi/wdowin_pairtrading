import test from "node:test";
import assert from "node:assert/strict";
import { countOpenPosts, findPublishedPost, findStudioPost, isOpenPost, openPostBadgeText, stepOfPost } from "../src/marketing/postState.js";

const post = (id, status, over = {}) => ({ id, status, kind: "end_of_day", asset: "WIN", ref_date: "2026-11-26", ...over });

test("só rascunho, aprovado, publicando e falhou estão em aberto; publicado e rejeitado terminaram", () => {
    for (const s of ["draft", "approved", "publishing", "failed"]) assert.equal(isOpenPost(post("a", s)), true, s);
    for (const s of ["published", "rejected"]) assert.equal(isOpenPost(post("a", s)), false, s);
    assert.equal(isOpenPost(null), false);
});

test("o estúdio NÃO reabre o último post publicado: sem post em aberto vem formulário novo (etapa 1)", () => {
    const posts = [post("p1", "published")];
    assert.equal(findStudioPost(posts, "WIN", "2026-11-26"), null);
    assert.equal(stepOfPost(findStudioPost(posts, "WIN", "2026-11-26")), 1);
});

test("post cancelado (rejeitado) também não toma a tela", () => {
    assert.equal(findStudioPost([post("p1", "rejected")], "WIN", "2026-11-26"), null);
});

test("post em aberto é retomado, na etapa certa", () => {
    assert.equal(findStudioPost([post("p1", "draft")], "WIN", "2026-11-26").id, "p1");
    assert.equal(stepOfPost(post("p1", "draft")), 2);
    assert.equal(stepOfPost(post("p1", "approved")), 3);
    assert.equal(stepOfPost(post("p1", "failed")), 3);
});

test("com um publicado e um aberto no mesmo dia, o aberto é o que aparece", () => {
    const posts = [post("old", "published"), post("new", "draft")];
    assert.equal(findStudioPost(posts, "WIN", "2026-11-26").id, "new");
});

test("não mistura ativo, dia nem tipo", () => {
    const posts = [post("a", "draft", { asset: "WDO" }), post("b", "draft", { ref_date: "2026-11-25" }), post("c", "draft", { kind: "morning" })];
    assert.equal(findStudioPost(posts, "WIN", "2026-11-26"), null);
});

test("pedido explícito do Histórico (viewPostId) mostra aquele post, mesmo publicado, e só ele", () => {
    const posts = [post("p1", "published")];
    assert.equal(findStudioPost(posts, "WIN", "2026-11-26", "p1").id, "p1");
    assert.equal(findStudioPost(posts, "WIN", "2026-11-25", "p1"), null);
    assert.equal(findStudioPost(posts, "WDO", "2026-11-26", "p1"), null);
});

test("publicado do mesmo dia é achado à parte (o servidor barra um segundo post do dia)", () => {
    assert.equal(findPublishedPost([post("p1", "published")], "WIN", "2026-11-26").id, "p1");
    assert.equal(findPublishedPost([post("p1", "draft")], "WIN", "2026-11-26"), null);
});

test("contagem de em aberto, total e por ativo", () => {
    const posts = [post("1", "draft"), post("2", "approved", { asset: "WDO" }), post("3", "published"), post("4", "rejected"), post("5", "failed", { kind: "other", asset: "" })];
    assert.deepEqual(countOpenPosts(posts), { total: 3, WIN: 1, WDO: 1 });
    assert.deepEqual(countOpenPosts(null), { total: 0, WIN: 0, WDO: 0 });
});

test("selo diz o que falta e nunca sugere que já foi publicado", () => {
    for (const s of ["draft", "approved", "publishing", "failed"]) {
        const t = openPostBadgeText(post("a", s));
        assert.ok(t.length > 0, s);
        assert.ok(!/publicado/i.test(t), t);
    }
    assert.equal(openPostBadgeText(post("a", "published")), "");
});
