---
name: mw-meta-ads-manager
description: Planeja, estrutura e otimiza campanhas de Meta Ads (Instagram Reels, Stories e Feed) com funil TOF/MOF/BOF, seleção de vencedores orgânicos, matriz de testes de ganchos, regras de corte/escala e proteção contra bloqueios. Usar para tráfego pago.
example-prompt: Analise os Reels do Instagram com mais salvamentos desta semana e monte o plano de campanha Meta Ads (TOF + MOF Click-to-DM + BOF Passe 7 Dias) com budget sugerido e criativos para aprovação.
---

# Gestão de Tráfego Meta Ads MagicWalls (`mw-meta-ads-manager`)

## Objetivo
Escalar alcance qualificado de traders B3 no Instagram e gerar fluxo previsível para Directs, Passe 7 Dias (`R$ 29,90`) e assinaturas `CORE`/`PRO` com payback inferior a 30 dias.

## Entradas Obrigatórias
- Métricas orgânicas do IG e histórico de anúncios (`Shared/magicwalls/analytics/` e `publicados/`)
- `openbot-team/BRAND_BIBLE_CVM.md`

## Procedimento Passo a Passo
1. **Seleção de Criativos Vencedores:** Eleger Reels orgânicos com taxa de salvamento `>= 2,5%` ou compartilhamento `>= 2×` média do perfil para subir como Dark Post / Ads.
2. **Estruturar os 3 Conjuntos do Funil:**
   - **TOF (Topo):** Visita ao Perfil IG / Engajamento com Reels `Antes 08h30 × Depois 17h15` e Carrosséis GEX.
   - **MOF (Meio):** Click-to-DM (`"MAPA"` / `"WALL"`) ou tráfego para Passe 7 Dias (`R$ 29,90`).
   - **BOF (Fundo):** Remarketing 7d/30d (Engajou IG + Visitou LP + Checkout Iniciado) com demonstração ao vivo do Cockpit `5176` e condição Fundadores.
3. **Aplicar Regras de Corte e Escala:**
   - *Cortar:* Hook Rate 3s `< 22%` após 1.000 impressões ou gasto `>= 1,5× CPA alvo` sem evento de checkout/DM.
   - *Escalar:* Conjuntos lucrativos há 48–72h com subida gradual máxima de `+20%` por ciclo.
4. **Padronizar UTMs e Solicitar Novos Hooks:** Gerar briefing de 3 variações de gancho (primeiros 3s) ao `04-editor-motion` para criativos com fadiga de frequência (`> 2,8`).
5. **Enviar ao Compliance:** Toda copy/criativo passa pelo `02-brand-compliance` antes do envio ao Fundador.

## Guardrails e Restrições
- Gera apenas planos e rascunhos em `Shared/magicwalls/ads/`; nunca altera orçamento ou publica anúncio sem `[APROVADO_FUNDADOR]`.
- Proibido prometer retorno financeiro ou usar termos da lista proibida da `BRAND_BIBLE_CVM.md`.

## Checklist de Verificação
- [ ] Funil TOF/MOF/BOF separado com UTMs padronizadas.
- [ ] Regras objetivas de corte e escala aplicadas.
- [ ] Parecer `[APROVADO_BRAND]` obtido antes de apresentar ao Fundador.
