// A URL é o estado da página. Leitura e escrita de parâmetros da query (filtro, aba, data...) em um lugar só.
// Quem usa o hook não guarda o estado em memória: o valor vem da URL e a mudança escreve na URL, então colar o
// endereço em outro navegador reproduz a tela e os botões voltar/avançar funcionam.
import { useCallback, useSyncExternalStore } from "react";

const URL_EVENT = "mw-url-changed";

/** Valor de um parâmetro de `search` ("" quando ausente). */
export function readParam(search, name) {
    return new URLSearchParams(search || "").get(name) || "";
}

/** Novo `search` com os parâmetros trocados; valor vazio ou null remove o parâmetro. Mantém os demais. */
export function withParams(search, patch) {
    const qs = new URLSearchParams(search || "");
    for (const [k, v] of Object.entries(patch)) {
        if (v === null || v === undefined || v === "") qs.delete(k);
        else qs.set(k, String(v));
    }
    const s = qs.toString();
    return s ? `?${s}` : "";
}

/** Aceita só valores conhecidos; qualquer outra coisa vira o padrão (URL editada à mão nunca quebra a tela). */
export function parseEnum(value, allowed, fallback) {
    return allowed.includes(value) ? value : fallback;
}

/** Aceita só AAAA-MM-DD; outra coisa vira "". */
export function parseIsoDate(value) {
    return /^\d{4}-\d{2}-\d{2}$/.test(String(value || "")) ? String(value) : "";
}

/** Escreve parâmetros na URL atual sem recarregar. `replace`: troca a entrada do histórico em vez de empilhar. */
export function writeParams(patch, { replace = false } = {}) {
    if (typeof window === "undefined") return;
    const { pathname, search, hash } = window.location;
    const next = withParams(search, patch);
    if (next === search) return;
    window.history[replace ? "replaceState" : "pushState"](window.history.state, "", `${pathname}${next}${hash}`);
    window.dispatchEvent(new Event(URL_EVENT));
}

function subscribe(cb) {
    window.addEventListener("popstate", cb);
    window.addEventListener(URL_EVENT, cb);
    return () => {
        window.removeEventListener("popstate", cb);
        window.removeEventListener(URL_EVENT, cb);
    };
}

const getSearch = () => window.location.search;
const getServerSearch = () => "";

/** [valor, definir]: o valor é o parâmetro da URL ("" se ausente); definir("") remove o parâmetro. */
export function useUrlParam(name) {
    const search = useSyncExternalStore(subscribe, getSearch, getServerSearch);
    const set = useCallback((value, opts) => writeParams({ [name]: value }, opts), [name]);
    return [readParam(search, name), set];
}
