// Qual pregão o painel abre. Com produtor ao vivo, "" (hoje). Sem ele, o último pregão guardado no servidor,
// para o usuário nunca ficar numa tela de espera. Escolha manual do usuário nunca é trocada.
//   live: o servidor tem snapshot ao vivo | dates: pregões guardados (mais novo primeiro)
//   selectedDate: dia aberto agora ("" = ao vivo) | autoDay: dia que o painel abriu sozinho (ou "")
export function decideDay({ live, dates, selectedDate, autoDay }) {
    const list = Array.isArray(dates) ? dates : [];
    if (live) {
        // produtor voltou: sai do dia aberto automaticamente, mas só se foi o painel que abriu
        if (autoDay && selectedDate === autoDay) return { selectedDate: "", autoDay: "" };
        return { selectedDate, autoDay: selectedDate === autoDay ? autoDay : "" };
    }
    if (!selectedDate && list.length > 0) return { selectedDate: list[0], autoDay: list[0] };
    return { selectedDate, autoDay: selectedDate === autoDay ? autoDay : "" };
}
