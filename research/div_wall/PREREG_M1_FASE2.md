# Pré-registro — M1 Fase 2: divergência forte (10/11/2026, antes de rodar)

**Motivação:** na Fase 1 (IS jan–jul) o PF mediano subiu de forma monotônica com `wave_k`
(WIN 0,84 → 0,98 → 1,21 em k = 0,5 / 1,0 / 1,5). A Fase 2 testa se a melhora continua com k maior.

**Mudança de critério (aprovada pelo usuário):** o mínimo de trades no IS cai de 120 para **50**
(~0,35 trade/dia por ativo), porque divergência forte é, por definição, rara. PF >= 1,30 e MDD > 0 seguem.

**Grade (só IS, jan–jul):**
- `wave_k` ∈ {1,5; 2,0; 2,5; 3,0; 4,0}
- `pivot_right` ∈ {1, 2}; `wall_radius` WIN {25, 40, 60} / WDO {1,0; 1,5; 2,5}; `wall_types` ∈ {Wall+MidWall, Wall}
- `nwe_filter` ∈ {none, slope_against, extreme} (`slope_with` saiu: quase não gerava trades na Fase 1)
- Saídas: as mesmas 48 da Fase 1 (sl pivot/wall × 6 alvos × BE on/off × max_bars 30/60), mesmos custos.

**Regra de escolha para o OOS (fixada agora):**
1. Ranking por platô (mediana do Ret/DD da config e dos vizinhos de 1 parâmetro; inelegível = 0).
2. Só vai para o OOS a config nº 1 de cada ativo, e só se o platô dela for > 1,0.
3. O OOS (ago–nov) roda **uma vez**. Aprovação no OOS: PF >= 1,20, resultado líquido > 0 e
   pelo menos metade dos meses positivos. Se reprovar, a config morre (não se re-otimiza olhando o OOS).
4. Se nenhum ativo tiver platô > 1,0 no IS, a conclusão é que a divergência forte não tem vantagem e o OOS fica fechado.
