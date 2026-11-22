---
name: mw-ig-closing-proof-card
description: Gera os cards visuais de fechamento no InstagramCardModal (Stories 9:16, Feed 4:5 ou Carrossel 2 slides) após as 17h para comprovar visualmente a reação do preço nas MagicWalls marcadas de manhã. Usar no pós-pregão.
example-prompt: Gere os cards pós-pregão de hoje para WIN e WDO no formato Carrossel 2 slides e Stories 9:16 destacando as melhores defesas e divergências na Wall para o post das 17h30.
---

# Produção de Cards de Prova Pós-Pregão (`mw-ig-closing-proof-card`)

## Objetivo
Gerar material visual limpo e verificável do fechamento (`17:15 BRT`) conectando os níveis publicados às 08h30 aos movimentos reais ocorridos na sessão.

## Pré-requisitos
- Painel `http://localhost:5176/` ativo com a sessão completa do dia carregada.
- Briefing de auditoria do `08-growth-analytics` (`Shared/magicwalls/briefs/YYYY-MM-DD_closing-audit_08-analytics.md`).

## Procedimento Passo a Passo
1. **Selecionar Destaques Factuais:** Ler a auditoria do `08-growth-analytics` para escolher o ativo mais didático do dia (`WIN`, `WDO` ou ambos) e os horários exatos dos toques/divergências em Wall.
2. **Configurar o `📸 Card IG` em `http://localhost:5176/`:**
   - Abrir o modal `📸 Card IG` no painel correspondente.
   - Definir `Título do Card = MAGIC WALLS` e `@Instagram = @magicwallsb3`.
   - Escolher formato: `STORIES (1080×1920)` para prova rápida nos Stories + `CAROUSEL (1080×1350)` (2 slides) ou `FEED (1080×1350)` para o feed.
   - Ajustar régua (`Melhor ★` ou `Todos`) e filtro de sinais mantendo transparência real da sessão.
3. **Exportar & Montar Pareamento "Antes × Depois":**
   - Baixar os PNGs em `Shared/magicwalls/producao/YYYY-MM-DD_card-17h15_*`.
   - Anexar referência da Capa `08h30` do mesmo dia para formar a narrativa visual *"Publicado às 08h30 → Realizado até às 17h"*.
4. **Encaminhar para Revisão:** Notificar `03-instagram-content-head` (legenda) e `02-brand-compliance`.

## Guardrails e Restrições
- Proibido editar imagens em editor externo para fabricar sinais, apagar candles ou alterar preços.
- Sempre incluir no card ou legenda que desempenho passado não garante resultado futuro.

## Checklist de Verificação
- [ ] PNGs exportados em resolução nativa (`1080×1920` / `1080×1350`).
- [ ] Horários e pontos conferem com a auditoria do `08-growth-analytics`.
- [ ] Pareamento com o mapa de 08h30 incluído no manifesto.
