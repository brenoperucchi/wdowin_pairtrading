---
name: mw-brand-cvm-guard
description: Audita roteiros, legendas, overlays de vídeo, scripts de DM, anúncios Meta Ads e réguas de cobrança contra a Brand Bible da MagicWalls, Resolução CVM 20/2021 e políticas financeiras da Meta. Usar antes de aprovar qualquer peça externa.
example-prompt: Audite este roteiro de Reels 08h30, a legenda e o texto de anúncio do Passe 7 Dias usando a BRAND_BIBLE_CVM.md e emita o parecer oficial com substituições se algo infringir CVM 20 ou Meta Ads.
---

# Gate de Marca & Compliance CVM 20 / Meta Ads (`mw-brand-cvm-guard`)

## Objetivo
Garantir 100% de conformidade visual, regulatória (CVM 20) e de política publicitária (Meta Ads) em toda comunicação da MagicWalls, emitindo parecer binário `[APROVADO_BRAND]` ou `[REPROVADO_AJUSTAR]`.

## Entradas Obrigatórias
- `openbot-team/BRAND_BIBLE_CVM.md`
- Peça submetida em `Shared/magicwalls/producao/`, `ads/` ou `recuperacao/`
- Dados factuais do pregão em `Shared/magicwalls/briefs/` (para checar veracidade dos números)

## Procedimento Passo a Passo
1. **Varredura CVM 20 (Anti-Call):** Buscar verbos imperativos operacionais ("compre", "venda", "entre agora", "stop garantido", "call ao vivo"). Substituir por linguagem de software analítico ("zona de defesa GEX", "absorção institucional observada", "sinalização algorítmica educacional").
2. **Varredura Meta Ads (Anti-Bloqueio):** Bloquear promessas de retorno financeiro ("ganhe R\$ X/dia", "consistência garantida", "renda extra rápida", "nunca mais perca").
3. **Conferência Factual:** Comparar data, preço de referência WIN/WDO, `Gamma Flip`, `Ímã GEX` e horários macro citados na peça com os dados reais de `briefs/`. Divergência numérica = reprovação imediata.
4. **Checagem de Disclaimers:** Confirmar disclaimer curto dentro de vídeos/cards/Stories e disclaimer completo na legenda, LP ou anúncio.
5. **Auditoria Visual (se houver mídia):** Conferir paleta Obsidian (`#050911`), Cyan (`#38bdf8`), Emerald (`#34d399`), Rose (`#f43f5e`), Gold (`#fbbf24`), fontes `Inter`/`JetBrains Mono` e safe zones Reels `9:16` (`96px` topo, `170px` base, `56px` laterais).
6. **Emitir Parecer Oficial:** Gravar em `Shared/magicwalls/aprovacao/YYYY-MM-DD_<peca>_02-brand-parecer.md` com veredito `[APROVADO_BRAND]` ou `[REPROVADO_AJUSTAR]` + reescrita pronta das frases reprovadas.

## Guardrails e Restrições
- Não suavizar violações por pressa de horário; corrigir e devolver texto pronto em menos de 5 minutos.
- Não publicar nem editar arquivos originais do produto; registrar apenas o parecer na pasta `aprovacao/`.

## Checklist de Verificação
- [ ] Zero imperativos de compra/venda ou promessa de lucro.
- [ ] Números 100% compatíveis com o relatório GEX real do dia.
- [ ] Disclaimer adequado ao formato presente.
- [ ] Veredito binário gravado em `Shared/magicwalls/aprovacao/`.
