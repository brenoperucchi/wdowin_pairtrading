---
name: mw-ig-morning-video-prod
description: Opera o Estúdio Vídeo 08h30 da MagicWalls (30s em 9:16 e 16:9) para exportar o vídeo animado pré-pregão, Capa PNG e legenda oficial com dados reais do dia. Usar toda manhã entre 07:55 e 08:20 BRT antes da abertura da B3.
example-prompt: Gere o pacote visual de pré-pregão 08h30 de hoje usando o Estúdio http://localhost:5176/morning-video no formato Reels 9:16 (30s) com capa PNG e legenda pronta.
---

# Produção do Vídeo Matinal 08h30 (`mw-ig-morning-video-prod`)

## Objetivo
Produzir com pontualidade (até `08:15 BRT`) o vídeo animado de **30 segundos** com as MagicWalls calculadas antes da abertura do pregão, acompanhado de Capa PNG e legenda pronta.

## Pré-requisitos
- Backend `http://127.0.0.1:8080/api/morning-brief` ativo e com a data do pregão vigente.
- Frontend acessível em `http://localhost:5176/morning-video`.

## Procedimento Passo a Passo
1. **Validar Fonte de Dados:** Abrir `http://localhost:5176/morning-video` e verificar no topo o badge verde **`DADOS REAIS · DD/MM/AAAA`**. Se aparecer `SNAPSHOT LOCAL` ou data vencida, **parar e escalar ao `01-ceo-magicwalls`**.
2. **Configurar Estúdio:**
   - Formato: `9:16 Reels/Stories (1080×1920)` (e opcionalmente `16:9 YouTube/Live` se pedido na ordem do dia).
   - Roteiro e Ativos: `WIN + WDO (30s)`.
   - Marca: `MAGIC WALLS`, `@magicwallsb3`, URL `magicwalls.com.br`, Carimbo `PRÉ-PREGÃO · 08:30 BRT`.
   - Confirmar `🔊 SFX & Trilha Institucional (Web Audio)` em `ATIVO`.
3. **Exportar Entregáveis:**
   - Clicar em `🎬 Exportar Vídeo (60fps + Áudio)` e aguardar conclusão (100%).
   - Posicionar a timeline em `t = 8.5s` (WIN completo na tela) e clicar em `🖼️ Baixar Capa PNG`.
   - Clicar em `📋 Copiar Legenda 08h30` como base para o ajuste editorial do `03-instagram-content-head`.
4. **Empacotar na Pasta de Produção:** Salvar arquivos em `Shared/magicwalls/producao/` seguindo o padrão `YYYY-MM-DD_video-08h30_9x16.*` e registrar manifesto `YYYY-MM-DD_morning-pack_04-editor.md`.

## Guardrails e Restrições
- Nunca exportar vídeo se o badge não mostrar a data do pregão de hoje.
- Nunca postar diretamente; enviar para QC (`mw-video-creative-qc`) e Compliance (`02-brand-compliance`).

## Checklist de Verificação
- [ ] Badge `DADOS REAIS` com a data de hoje confirmado.
- [ ] Vídeo 30s (`1080×1920`), Capa PNG e Legenda salvos em `Shared/magicwalls/producao/`.
- [ ] Áudio e duração `30.0s` conferidos antes do handoff.
