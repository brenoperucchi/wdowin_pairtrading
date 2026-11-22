---
name: mw-ig-dm-conversion
description: Conduz atendimento consultivo e qualificação em comentários e Direct do Instagram (Comment-to-DM) para leads da MagicWalls, indicando o plano ideal (Canal 08h30, Passe 7d, CORE, PRO ou QUANT) sem violar a CVM 20. Usar na gestão de Directs.
example-prompt: Crie as respostas personalizadas para os 12 comentários "MAPA" do Reels de hoje e o fluxo consultivo de Direct para qualificar quem opera WIN/WDO e direcionar para o Passe 7 Dias ou plano PRO.
---

# Conversão Consultiva no Direct do Instagram (`mw-ig-dm-conversion`)

## Objetivo
Converter comentários e mensagens no Direct do Instagram em assinantes qualificados da MagicWalls usando diagnóstico consultivo em 4 passos, com zero pressão e 100% dentro da CVM 20.

## Entradas Obrigatórias
- Lista de interações/DMs do dia e palavras-chave ativas (`"MAPA"`, `"WALL"`, `"PASS"`, `"PRO"`)
- `openbot-team/BRAND_BIBLE_CVM.md` (preços vigentes e tabela de termos permitidos)

## Procedimento Passo a Passo
1. **Abertura Comment-to-DM (Rápida e Pessoal):** Responder publicamente no comentário (*"Te chamei no Direct com o link do mapa!"*) e iniciar DM entregando imediatamente o prometido (ex.: resumo 08h30 ou explicação rápida).
2. **Diagnóstico em 4 Perguntas (1 por mensagem):**
   - P1: *"Você opera mais WIN, WDO ou os dois? Usa ProfitChart, TradingView ou MT5?"*
   - P2: *"Opera manual no gráfico ou também tem interesse em execução sistemática/robôs?"*
   - P3: *"Qual seu maior desafio hoje: achar onde os Market Makers defendem ou filtrar horários de violinada?"*
3. **Prescrição do Plano Certo (Nunca empurrar o errado):**
   - Só níveis manuais + Profit/TV → **CORE (`R$ 197/mês`)** ou **Passe 7 Dias (`R$ 29,90`)** para testar antes.
   - Leitura institucional completa (`5176` Sniper, divergências `F1➔F2`, Replay, GEX Global) → **PRO (`R$ 347–397/mês`)**.
   - Robôs MT5 com trava de lote + acompanhamento → **QUANT / Desk**.
4. **Quebra Segura de Objeções:**
   - *"Funciona no meu celular/Profit?"* → Explicar painel web responsivo + exportador Profit/TV em 1 clique.
   - *"Dá sinal de compra/venda?"* → Explicar que é software analítico quantitativo (CVM 20) com níveis GEX e leitura de fluxo institucional.
5. **Handoff para Recuperação:** Se o lead receber o link e não finalizar em 2h, registrar em `Shared/magicwalls/recuperacao/YYYY-MM-DD_dm-pipeline-handoff_06-social.md`.

## Guardrails e Restrições
- Nunca enviar mensagens automáticas não aprovadas ou dar recomendações de operação ao vivo.
- Nunca inventar descontos fora das ofertas oficiais registradas na `BRAND_BIBLE_CVM.md`.

## Checklist de Verificação
- [ ] Scripts validados pelo `02-brand-compliance`.
- [ ] Handoff de links não pagos enviado ao `07-recovery-retention`.
- [ ] Top objeções anotadas para o relatório de sexta-feira.
