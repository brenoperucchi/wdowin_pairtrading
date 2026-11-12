# Sniper 5176 + versões do runner — resultados (11/11/2026)

Protocolo: `PLANO.md`. Tabela IS de cada candidata: `results/candidatas_is.csv`. OOS: `results/oos_log.json`.

## Resultado
- Base (Sniper 5176 corrigido): 287 trades, PF 1,95, R$ 7.436, Ret/DD 14,2 · IS Ret/DD 9,0 · OOS Ret/DD 6,3.
- Das 48 candidatas, **nenhuma entrou**. Passando pelo mesmo caminho (3 motores, divergência, saída, horário, meta), cada uma
  acrescenta só 0–36 trades no IS. A única elegível (WDO_09 sem fluxo, 15 trades, PF 1,90) baixa o Ret/DD do IS
  (9,04 → 8,24). O OOS foi rodado com a carteira igual à base.
- As que mais subiram o Ret/DD do IS (WDO_05 sem fluxo 11,2 · WDO_01/07 sem fluxo 10,5 · WDO_02 sem fluxo 10,5)
  acrescentam 5–14 trades cada (abaixo do mínimo de 15).

## Por quê: o gargalo é a entrada, não a divergência
| | Divergências no ano | Por dia | Com entrada da base logo depois | Com entrada de qualquer versão |
| :-- | --: | --: | --: | --: |
| WIN | 1.229 | 5,8 | 262 (21%) | 385 (31%) |
| WDO | 1.818 | 8,6 | 246 (14%) | 450 (25%) |

Cerca de 70–75% das divergências do detector nunca têm uma entrada de setup nas 3 barras seguintes. Somar setups
quase não muda isso. Para operar mais, o caminho é testar a **entrada na própria divergência** (3 motores + saída 2 lotes).
