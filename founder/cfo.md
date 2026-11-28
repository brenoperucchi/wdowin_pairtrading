# Nota do CFO — Magic Walls (`@magicwallsb3`)

> **Convenção do relatório abaixo:** Todos os valores monetários estão em **Reais brasileiros (R$ / BRL)** (o script `unit_economics.py` imprime `$` por padrão). Como `"days_per_month": 1` e `"unit": "assinante/mês"`, toda referência a *"a day"* na tabela gerada pelo script significa **assinantes pagantes ativos por mês**. Receita informada **antes de impostos** (Simples Nacional/ISS incidem sobre faturamento bruto; **um contador deve validar CNAE, regime tributário, pró-labore mínimo / Fator R e emissão de NFS-e antes de movimentar dinheiro**).

- **A margem:** Ao preço padrão de **R$ 97,00/mês**, cada assinante deixa **R$ 85,09 de contribuição (88%)** após pagar Asaas cartão (`R$ 3,39`), provisão de garantia de 7 dias (`R$ 5,82`) e infra marginal (`R$ 2,70`). No plano de **115 assinantes ativos/mês** (Mês 12), a margem líquida operacional é de **64%** após **R$ 2.628/mês** de custos fixos (incluindo o teto de **R$ 2.000/mês** de marketing e **R$ 79/mês** de amortização econômica da VPS de R$ 1.900/2 anos já paga). O ponto de equilíbrio é de **31 assinantes/mês**, muito abaixo da capacidade da VPS (**1.000+ usuários**).
- **A linha mais sensível:** **Velocidade da rampa inicial (funil Instagram sem trial)** e **preço médio**. Como o Painel v2 mostrou que seguidores levam 2–3 semanas acompanhando as postagens antes de comprar sem trial, calibramos uma rampa conservadora (`6, 14, 24, 34...` até `115` no Mês 12). Se o volume cair 20% em todos os meses (`--volume 0.8`, fechando o Ano 1 em 92 assinantes), o lucro operacional do Ano 1 cai de **R$ 32.196** para **R$ 19.450** e o caixa necessário sobe de **R$ 7.040** para **R$ 8.102**. Se 100% dos assinantes ficassem travados no Lote Fundador de **R$ 79/mês** (`--price 79`), o break-even subiria para **40 assinantes/mês** e o lucro Ano 1 cairia para **R$ 18.714**.
- **Caixa novo necessário:** **R$ 7.040** de pico de caixa novo até o negócio se pagar (**R$ 2.900** de startup novo + déficit acumulado dos Meses 1 a 3 enquanto a base ainda está abaixo de 31 assinantes). O payback ocorre no **Mês 7** (lembrando que o software e a VPS de R$ 1.900 por 2 anos já foram pagos previamente, então o desembolso de caixa real nos Meses 1–3 é ainda **R$ 79/mês menor** que o DRE econômico).
- **Três alavancas concretas para melhorar margem:**
  1. **Limitar o Lote Fundador (R$ 79) a 40 vagas e migrar novos entrantes para R$ 97 (e depois upsell Pro R$ 129–147):** no cenário `--price 129`, a contribuição sobe para **R$ 117,09 (91%)**, o break-even cai de **31 para 23 assinantes/mês** e o lucro operacional Ano 1 salta para **R$ 56.164** (+R$ 23.968).
  2. **Incentivar Pix recorrente no checkout Asaas em vez de cartão:** o cartão à vista custa `R$ 3,39` (`2,99% + R$ 0,49`) contra `R$ 1,99` no Pix publicado pelo Asaas — economia direta de `R$ 1,40` por assinante/mês (equivalente a +1,4 ponto percentual de contribuição unitária).
  3. **Segurar reembolsos da garantia de 7 dias abaixo de 3% via prova pré-09h transparente:** reduzir a provisão conservadora de 6% (`R$ 5,82`) para 3% (`R$ 2,91`) economiza `R$ 2,91` por assinante/mês, deixando a margem unitária mais próxima do cenário sem reembolso.
- **Condições financeiras do Conselho (`founder/board.md`):** Infra dedicada resolvida antecipadamente (VPS 1.000+ usuários); margem unitária e payback dentro de 12 meses validados no modelo. Ficam pendentes apenas: (1) validação em mundo real da taxa de conversão e reembolso sem trial e (2) cotação futura da **API oficial B3/Cedro** para a Fase 2 (não incluída no fixo do Ano 1 porque ainda não há cotação comercial).

---

# Unit economics: Magic Walls (Terminal Web SaaS GEX + Fluxo Smart Money WIN/WDO)

Every number below comes from the input file. Nothing is looked up or guessed.

## One assinante/mês

| line | per assinante/mês |
| --- | ---: |
| Price | $97.00 |
| Gateway Asaas cartão (2,99% + R$0,49) | -$3.39 |
| Provisão reembolso garantia 7d (6%) | -$5.82 |
| Infra marginal + e-mail por assinante | -$2.70 |
| **Contribution** (what each assinante/mês leaves to pay the fixed costs) | **$85.09** (88%) |

## The margin that matters

Fixed costs: $2,628 a month (Supabase Pro (US$ 25) $145, Cloud API Railway Pro (US$ 20) $116, Upstash Redis Fixed (US$ 10) $58, VPS Dedicada (amortização R$ 1.900 / 24m) $79, Cloudflare Pages Free + domínio/e-mail $40, Contabilidade online PJ (estimativa) $190, Marketing (teto informado pelo fundador) $2,000).

- **Break-even: 31 assinante/mêss a day.** Below that you lose money every month.
- **Profit margin at your plan** (115 a day): **64%** of every sale, after every cost.
- Capacity: 1000 a day.

## Year 1, month by month

| month | assinante/mêss a day | revenue | profit | cumulative (after $2,900 startup) |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 6 | $582 | -$2,117 | -$5,017 |
| 2 | 14 | $1,358 | -$1,437 | -$6,454 |
| 3 | 24 | $2,328 | -$586 | -$7,040 |
| 4 | 34 | $3,298 | $265 | -$6,775 |
| 5 | 46 | $4,462 | $1,286 | -$5,489 |
| 6 | 58 | $5,626 | $2,307 | -$3,182 |
| 7 | 70 | $6,790 | $3,328 | $147 |
| 8 | 82 | $7,954 | $4,349 | $4,496 |
| 9 | 92 | $8,924 | $5,200 | $9,696 |
| 10 | 100 | $9,700 | $5,881 | $15,577 |
| 11 | 108 | $10,476 | $6,562 | $22,139 |
| 12 | 115 | $11,155 | $7,157 | $29,296 |

- **Year 1 operating profit: $32,196** on $72,653 of revenue.
- After the $2,900 startup spend: $29,296.
- Startup money earned back: month 7.
- Cash you need before it pays for itself: **$7,040**.

## What if

| scenario | margin at plan | break-even a day | year 1 profit |
| --- | ---: | ---: | ---: |
| Base plan | 64% | 31 | $32,196 |
| Price -10% | 60% | 35 | $24,931 |
| Volume -20% | 58% | 31 | $19,450 |
| Unit costs +15% | 62% | 32 | $30,858 |

No red flags in these numbers. They are only as good as the inputs: check every cost against a real quote.
