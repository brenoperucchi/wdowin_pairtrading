import { useEffect, useState } from "react";
import { call } from "./marketingApi";
import { countOpenPosts } from "./postState";

// Evento que a página de Marketing dispara ao atualizar a lista, para a barra de navegação acompanhar sem esperar o próximo ciclo.
export const OPEN_POSTS_EVENT = "mw-open-posts";

/** Quantos posts de marketing estão em aberto (rascunho, aprovado, publicando, falhou). `enabled` só para admin. */
export function useOpenPostCount(enabled) {
    const [total, setTotal] = useState(0);
    useEffect(() => {
        if (!enabled) return undefined;
        let off = false;
        const load = () =>
            call("/posts")
                .then((r) => { if (!off) setTotal(countOpenPosts(r.posts).total); })
                .catch(() => {});
        load();
        const timer = setInterval(load, 60000);
        const onEvent = (e) => setTotal(Number(e.detail?.total) || 0);
        window.addEventListener(OPEN_POSTS_EVENT, onEvent);
        return () => {
            off = true;
            clearInterval(timer);
            window.removeEventListener(OPEN_POSTS_EVENT, onEvent);
        };
    }, [enabled]);
    return total;
}
