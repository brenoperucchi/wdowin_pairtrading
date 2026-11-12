# NWE30 × NWE100 (12/11/2026)

Script: `teste_nwe.py`. Saídas: `results/nwe.csv` e `results/trades.json`.

O motor de divergência é o v2.2 (`V22_ABERTURA`) nas duas estratégias. Período: 02/01 a 06/11/2026.

## Onde cada NWE é usada

| NWE | Parâmetros | Uso |
| :-- | :-- | :-- |
| NWE30 | L 30 · bw 3 · mult 1,6 | alvo do lote 1 do Sniper WIN (banda oposta, limitado a 260–750 pts); era a linha do painel 5176, só no WIN |
| NWE50 | L 50 · bw 8 · mult 3 | filtros de contexto do especialista (`ext50 > −0,5`, `slope50 > −0,5`) |
| NWE "principal" | L 40 · bw 8 · mult 1,8 (MAE 200) | campo `nwe_line` do payload; usado no 5174 |
| NWE100 | L 100 · bw 8 · mult 3 | igual ao `UpdateNWE` do MT5; não era usada em M5 |

## Resultado

| Onde troca | Atual | NWE100 (8 · 3) | NWE100 (8 · 1,8) |
| :-- | :-- | :-- | :-- |
| Alvo do Sniper (v2.2), Ret/DD (jan–jul) · DD | 23,5 (17,4) · R$ 553 | 13,4 (18,5) · R$ 983 | 14,0 (17,6) · R$ 894 |
| Alvo do Sniper atual (B), Ret/DD | 14,2 | 15,0 | 14,3 |
| Filtros do especialista, Ret/DD (jan–jul) | 9,9 (5,5) | 8,0 (4,5) | 4,9 (1,5) |
| **Carteira**, Ret/DD (jan–jul) | **23,9 (15,9)** | 22,0 (16,5) | 23,4 (16,0) |

**Leitura:**
- **Alvo do Sniper:** com a NWE100, o lucro fica praticamente igual (R$ 13,1 mil contra R$ 13,0 mil) e jan–jul sai um pouco melhor, mas o DD quase dobra.
- **Filtros do especialista:** pioram com a NWE100.
- **Carteira:** a diferença em jan–jul fica abaixo de 10% (empate pelo critério), e no período completo a NWE atual é melhor.

**Decisão:** manter a NWE30 no alvo e a NWE50 nos filtros.

## NWE50 e NWE100 com bw 8 têm o mesmo centro

Com bw = 8, o peso gaussiano da barra 32 para trás é 0,03%, e o da barra 50 é praticamente zero. Por isso a linha central da NWE50 e a da NWE100 são **idênticas** (diferença máxima de 0,00 em 11/11, nos dois ativos).

A diferença está só nas bandas: o erro médio (MAE) é calculado em 50 ou em 100 barras. Em 11/11 a NWE100 ficou mais larga, com envelope médio de 973 pts no WIN e 21,8 no WDO, contra 830 e 17,8 da NWE50. Para mudar o centro de verdade, o parâmetro que importa é o bw, não o período.

## Painel 5176
- O motor ao vivo (`core/gex_live_dealer_engine.py`) passa a mandar, em cada barra M5:
  - `nwe50_*` (50 · 8 · 3);
  - `nwe100_*` (100 · 8 · 3).

  É só para exibição e usa o mesmo aquecimento da NWE30.
- O botão da NWE virou um seletor `NWE30 | NWE50 | NWE100 | Off`:
  - fica ligado nos dois ativos;
  - o padrão é a NWE100;
  - a escolha fica lembrada no navegador.
- A linha de alvo TP1 das caixas de trade continua vindo da NWE30, que é a que o Sniper usa.
