// Estado de um post para a interface. Funções puras (sem rede), testáveis em node.
//
// "Em aberto" = começou e não terminou: rascunho, aprovado e ainda não enviado, publicando agora ou que falhou.
// Terminado = publicado (acabou) ou rejeitado (cancelado). Só o que está em aberto é retomado ao abrir o Marketing.

export const OPEN_STATUSES = ["draft", "approved", "publishing", "failed"];

export function isOpenPost(post) {
    return Boolean(post) && OPEN_STATUSES.includes(post.status);
}

/** Etapa em que o post está: 1 Criar, 2 Aprovar, 3 Enviar. */
export function stepOfPost(post) {
    if (!post) return 1;
    if (post.status === "draft" || post.status === "rejected") return 2;
    return 3;
}

const isEndOfDay = (p, asset, refDate) => p.kind === "end_of_day" && p.asset === asset && p.ref_date === refDate;

/**
 * O post que o estúdio deve mostrar para um ativo e dia: o que está EM ABERTO.
 * Sem ele, o estúdio abre um formulário novo (etapa 1). `viewPostId` é só para quando a pessoa pede, pelo Histórico,
 * para ver um post específico (inclusive um já publicado); fora isso o último publicado nunca toma a tela.
 */
export function findStudioPost(posts, asset, refDate, viewPostId = "") {
    const list = posts || [];
    const viewed = viewPostId ? list.find((p) => p.id === viewPostId && isEndOfDay(p, asset, refDate)) : null;
    return viewed || list.find((p) => isEndOfDay(p, asset, refDate) && isOpenPost(p)) || null;
}

/** O post já publicado para o ativo e dia (o servidor não aceita um segundo post do mesmo dia: POST_EXISTS). */
export function findPublishedPost(posts, asset, refDate) {
    return (posts || []).find((p) => isEndOfDay(p, asset, refDate) && p.status === "published") || null;
}

/** Quantos posts em aberto há, no total e por ativo (WIN, WDO). */
export function countOpenPosts(posts) {
    const out = { total: 0, WIN: 0, WDO: 0 };
    for (const p of posts || []) {
        if (!isOpenPost(p)) continue;
        out.total += 1;
        if (p.asset === "WIN" || p.asset === "WDO") out[p.asset] += 1;
    }
    return out;
}

/** Texto do selo de um post em aberto: o que ainda falta (nada disso foi publicado). */
export function openPostBadgeText(post) {
    switch (post?.status) {
        case "draft":
            return "Rascunho em aberto: falta aprovar e enviar";
        case "approved":
            return "Aprovado, ainda não enviado: falta enviar";
        case "publishing":
            return "Publicando agora";
        case "failed":
            return "Falhou ao enviar: tente de novo ou cancele";
        default:
            return "";
    }
}
