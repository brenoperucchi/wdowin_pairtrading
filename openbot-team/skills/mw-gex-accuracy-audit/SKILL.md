---
name: mw-gex-accuracy-audit
description: Extrai com precisão factual os dados do /api/morning-brief e relatórios GEX às 07h50 e audita o comportamento real do mercado sobre as MagicWalls às 17h05 para alimentar o conteúdo Antes×Depois do Instagram sem alucinações.
example-prompt: Rode a auditoria matinal das 07h50 lendo o /api/morning-brief e os relatórios DAILY_REPORT para gerar o briefing factual do vídeo 08h30 de hoje.
---

# Auditoria Factual Pré & Pós-Pregão GEX (`mw-gex-accuracy-audit`)

## Objetivo
Garantir **100% de integridade numérica** em tudo o que a MagicWalls publica no Instagram às 08h30 e às 17h15, separando fatos observados de suposições.

## Entradas Oficiais (Somente-Leitura)
- `GET http://127.0.0.1:8080/api/morning-brief`
- `GET http://127.0.0.1:8080/api/compass/etapa1?lite=1` (no fechamento 17h)
- `gex/docs/DAILY_REPORT.txt`, `gex/docs/DAILY_REPORT_DOL.txt`, `gex/docs/DAILY_ECONOMIC_CALENDAR.txt`
- `gex/data/win_walls_cache.json` e `gex/data/usd_brl_walls_cache.json`

## Procedimento Passo a Passo
1. **Auditoria Pré-Pregão (`07:50 BRT`):**
   - Consultar `/api/morning-brief` e validar se `ref_date` e `updated_at` correspondem ao pregão de hoje/último fechamento útil válido. Se não corresponder, marcar `[BLOQUEIO_DATA_DESATUALIZADA]`.
   - Extrair exatamente: preço de referência, `Gamma Flip`, regime (`POSITIVE` vs `NEGATIVE`), Resistência Imediata, Suporte Imediato, Grande Muralha / Ímã (`★★★`) e top 4 horários macro do calendário econômico.
   - Gravar em `Shared/magicwalls/briefs/YYYY-MM-DD_morning-data_08-analytics.md`.
2. **Auditoria Pós-Pregão (`17:05 BRT`):**
   - Consultar `/api/compass/etapa1?lite=1` e o briefing das 07h50.
   - Listar os horários exatos em que `WIN` e `WDO` testaram as `MagicWalls`/`MidWalls` do dia e as divergências `F1➔F2 / T1➔T2` registradas na sessão.
   - Indicar quais níveis cravaram reação e quais foram rompidos (transparência completa!).
   - Gravar em `Shared/magicwalls/briefs/YYYY-MM-DD_closing-audit_08-analytics.md`.

## Guardrails e Restrições
- Nunca inventar números, arredondar para melhorar narrativa nem esconder dias de stop/rompimento.
- Se qualquer fonte estiver offline ou incompleta, registrar `[DADO_INDISPONIVEL]` e notificar `01-ceo-magicwalls`.

## Checklist de Verificação
- [ ] `ref_date` verificado antes de liberar o turno da manhã.
- [ ] Todos os preços e horários copiados diretamente dos arquivos/API oficiais.
- [ ] Pareamento Antes (08:30) × Depois (17:00) documentado objetivamente.
