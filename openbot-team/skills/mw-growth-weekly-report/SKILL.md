---
name: mw-growth-weekly-report
description: Consolida semanalmente os KPIs de Instagram (alcance, salvamentos, directs), Tráfego Pago (CPM, Hook Rate, CPA, ROAS), Recuperação (Pix/Dunning/Churn) e SaaS (MRR, LTV/CAC) para a reunião executiva de sexta-feira com o CEO e Fundador.
example-prompt: Consolide o relatório semanal de crescimento da MagicWalls cruzando os posts publicados no Instagram, campanhas Meta Ads, directs convertidos e receita recuperada para a reunião de sexta-feira.
---

# Relatório Executivo Semanal de Growth (`mw-growth-weekly-report`)

## Objetivo
Entregar ao CEO e ao Fundador, toda sexta-feira (`17:45 BRT`), uma visão objetiva do negócio em 1 página, apontando gargalos e decisões práticas para a semana seguinte.

## Entradas Obrigatórias
- Histórico de posts em `Shared/magicwalls/publicados/`
- Dados de campanhas em `Shared/magicwalls/ads/`
- Dados de DMs e recuperação em `Shared/magicwalls/recuperacao/`
- Métricas de assinaturas/faturamento informadas pelo Fundador

## Procedimento Passo a Passo
1. **Consolidar Bloco 1 — Motor Orgânico (Instagram):** Nº de Reels 08h30 publicados, taxa média de salvamento, top 2 posts da semana (por salvamentos e por DMs geradas) e post de menor retenção.
2. **Consolidar Bloco 2 — Aquisição Paga (Meta Ads):** Investimento, Hook Rate 3s, CTR, Custo por DM / Passe 7d, CPA e ROAS por funil (`TOF`, `MOF`, `BOF`).
3. **Consolidar Bloco 3 — Conversão DM & Recuperação:** Directs recebidos, taxa `DM → Checkout`, receita recuperada de Pix/Carrinho/Dunning, assinantes em risco (5d inativos) e Churn do período.
4. **Consolidar Bloco 4 — Unit Economics SaaS:** MRR ativo, Net New MRR, distribuição de clientes (`Passe 7d` / `CORE` / `PRO` / `QUANT`) e `LTV / CAC`.
5. **Diagnosticar Top 3 Gargalos & 3 Ações da Próxima Semana:** Ex.: *"Reels de WDO tiveram 1,8× mais salvamentos que WIN → testar 2 variações no MOF"*.
6. **Gravar em `Shared/magicwalls/analytics/YYYY-Www_growth-kpi_08-analytics.md`.**

## Guardrails e Restrições
- Nunca estimar números ausentes como reais; marcar qualquer campo não fornecido como `[PENDENTE_DADO_FUNDADOR]`.
- Manter relatório conciso e acionável (leitura em menos de 3 minutos).

## Checklist de Verificação
- [ ] Todos os 4 blocos preenchidos com separação clara entre dado verificado e dado pendente.
- [ ] Top 2 criativos candidatos a Dark Post identificados.
- [ ] Arquivo salvo no padrão semanal em `Shared/magicwalls/analytics/`.
