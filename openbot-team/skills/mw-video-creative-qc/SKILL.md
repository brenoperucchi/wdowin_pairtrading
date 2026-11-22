---
name: mw-video-creative-qc
description: Executa controle de qualidade técnico e visual em vídeos e PNGs gerados para Instagram Reels, Stories e Meta Ads (safe zones, legibilidade, sincronia, resolução, áudio e fidelidade numérica). Usar antes de liberar mídia para Compliance.
example-prompt: Faça o controle de qualidade técnico nos arquivos de vídeo 30s e capa PNG de hoje em Shared/magicwalls/producao/ antes de enviar ao Compliance.
---

# Controle de Qualidade Audiovisual (`mw-video-creative-qc`)

## Objetivo
Eliminar falhas técnicas de exportação antes que qualquer vídeo ou card chegue ao Compliance ou ao Fundador.

## Entradas Obrigatórias
- Arquivos de mídia em `Shared/magicwalls/producao/`
- Briefing de dados do dia (`Shared/magicwalls/briefs/`)

## Procedimento Passo a Passo
1. **Checagem de Arquivo & Resolução:**
   - Vídeo Reels/Stories: `1080×1920`, tamanho > `500 KB`, duração correta (`30.0s` ou `20.0s`), formato `.mp4` ou `.webm`.
   - Vídeo Landscape: `1920×1080`.
   - Capa / Cards: PNG `1080×1920` ou `1080×1350`, nitidez sem artefatos de compressão.
2. **Checagem de Safe Zones (Mobile IG):**
   - Nenhum texto crítico ou número de Wall nos `96px` superiores, `170px` inferiores ou `56px` laterais.
   - Capa PNG com título e níveis principais centralizados dentro do quadrado `1080×1080` (recorte de grid do perfil IG!).
3. **Checagem de Legibilidade & Paleta:**
   - Sem sobreposição de linhas laser sobre texto, sem frases cortadas nas caixas, sem caracteres corrompidos/mojibake.
4. **Checagem Sonora & Factual:**
   - Confirmar que faixa de áudio não está muda nem saturada/clipando e que os preços exibidos batem com o `morning-brief` do dia.
5. **Emitir Status:** Registrar `[QC_OK]` ou `[QC_REFAZER]` com o ajuste exato dentro do manifesto do dia.

## Guardrails e Restrições
- Não corrigir texto alterando dados reais; se houver erro numérico na tela, re-exportar da fonte atualizada.

## Checklist de Verificação
- [ ] Resolução nativa e duração exata confirmadas.
- [ ] Safe zones 9:16 e recorte 1:1 da capa de perfil verificados.
- [ ] Zero truncamento de texto e zero divergência numérica.
