---
name: mw-ig-editorial-engine
description: Cria pautas, ganchos de 3s, roteiros de Reels, carrosséis educacionais, sequências de Stories e legendas CVM-safe para o Instagram da MagicWalls, com CTA por palavra-chave para Direct. Usar na rotina diária e no planejamento semanal do IG.
example-prompt: Gere o roteiro e a legenda do Reels pré-pregão de hoje e um carrossel salvável explicando Gamma Negativo com base no briefing de 08h00 e na BRAND_BIBLE_CVM.md.
---

# Motor Editorial de Instagram MagicWalls (`mw-ig-editorial-engine`)

## Objetivo
Produzir copy de alta retenção e salvamento para o Instagram da MagicWalls (Reels, Carrosséis, Stories e Legendas) mantendo tom de mesa quantitativa e integração direta com o funil de Direct.

## Entradas Obrigatórias
- Briefing factual do dia (`Shared/magicwalls/briefs/`)
- `openbot-team/BRAND_BIBLE_CVM.md`
- Feedback semanal de ganchos vencedores do `05-traffic-manager` e dúvidas de leads do `06-social-dm-closer`

## Procedimento Passo a Passo
1. **Definir o Pilar & Objetivo da Peça:**
   - *Reels 08h30:* Autoridade Pré-Pregão (`30s`, gerar salvamentos e hábito diário).
   - *Prova 17h15:* Antes × Depois na Wall (gerar confiança e pedidos de acesso no DM).
   - *Carrossel Ter/Qui:* Educação quantitativa B3 (gerar compartilhamentos e seguidores qualificados).
   - *Stories Diários (4 a 6 frames):* Bastidor + Enquete de Regime + Print da Wall + CTA Direto.
2. **Escrever 3 Opções de Hook (0–3s / Capa):** Máximo 9 palavras, focado em tensão de mercado real (ex.: *"WIN abaixo do Gamma Flip: onde está a aceleração hoje?"*).
3. **Estruturar Corpo & Dados Reais:** Inserir apenas preços, estrelas (`★/★★/★★★`), horários de agenda e regras verificadas no briefing (ex.: filtros `11h WDO` e `12h WIN`).
4. **Fechar com CTA de Palavra-Chave + Disclaimer:** Escolher palavra-chave única do post (`"MAPA"`, `"WALL"`, `"PASS"`, `"PRO"`) para acionar o `06-social-dm-closer`, seguida do disclaimer completo.
5. **Salvar para Revisão:** Gravar em `Shared/magicwalls/producao/YYYY-MM-DD_<tipo>_03-content.md` e notificar `02-brand-compliance`.

## Guardrails e Restrições
- Este workflow gera apenas roteiros e legendas em rascunho; não publica diretamente no Instagram.
- Proibido usar clickbait financeiro ou ocultar contexto de risco.

## Checklist de Verificação
- [ ] Hook com até 9 palavras e tensão clara para trader de WIN/WDO.
- [ ] Números batem 100% com o briefing factual.
- [ ] CTA com palavra-chave definida e disclaimer completo incluído.
