# Estratégia de Preço — Magic Walls (`100% Web SaaS`)

*(Todos os valores em Reais brasileiros — R$ / BRL. A curva Van Westendorp preliminar está em [pricing-curve.md](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/founder/pricing-curve.md).)*

---

## 1. O que os compradores disseram (Van Westendorp v1 · 20 personas)

| Ponto | Valor (R$/mês) | Significado |
| --- | ---: | --- |
| **PMC** *(barato demais)* | **R$ 48,47** | Abaixo disso, muitos desconfiam da qualidade para leitura institucional B3 |
| **OPP** *(menor resistência)* | **R$ 59,80** | Ponto de menor atrito entre barato demais e caro demais |
| **IPP** *(indiferença)* | **R$ 96,18** | Tantos acham pechincha quanto começam a achar caro |
| **PME** *(caro demais)* | **R$ 149,33** | Acima disso, a maioria desiste |

- **Faixa aceitável medida:** **R$ 48,47 a R$ 149,33/mês** (medianas: muito barato R$ 29,00; pechincha R$ 67,00; ficando caro R$ 127,00; caro demais R$ 187,00).
- A hipótese anterior de **R$ 197,00/mês ficou acima do teto aceitável** e contribuiu para o `0/20` no painel v1.

---

## 2. O que os concorrentes cobram ([competitors.md](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/founder/competitors.md))

| Concorrente | Preço mensal | O que entrega (comparando igual com igual) |
| --- | ---: | --- |
| **Investorama** | R$ 20,90–31,90/mês | Screeners B3, GEX geral e integrações (foco amplo em ações/opções, não terminal intraday WIN×WDO) |
| **OpLab ONE / PRO** | R$ 97,00 / R$ 185,00/mês | Análise e simulação de opções de ações B3 (não focado em scalping WIN×WDO) |
| **Nelogica ProfitChart Pro** | R$ 0 (meta+RLP) ou R$ 150–189,90/mês | Plataforma de execução/tape reading (não entrega GEX + divergência Smart Money prontos) |
| **Jumba (Pro / Trader Flow)** | ~R$ 245,58–247,00/mês | GEX + fluxo institucional para B3 via ProfitChart (exige setup e ticket ~2,5x maior) |

---

## 3. O que o negócio precisa ganhar (rodado em `unit_economics.py`)

Com custo fixo econômico de **R$ 2.628/mês** (incluindo teto de R$ 2.000/mês em marketing, cloud e amortização de R$ 79/mês da VPS já paga de R$ 1.900/2 anos) e custo variável de **R$ 11,91/assinante/mês** (Asaas + provisão 6% de garantia 7 dias sem trial + infra marginal):

| Preço candidato | Contribuição / assinante | Break-even (assinantes ativos) | Margem no plano (120 assinantes) | Lucro operacional Ano 1* |
| ---: | ---: | ---: | ---: | ---: |
| **R$ 79,00** *(Lote Fundador)* | R$ 67,09 (85%) | **40 assinantes/mês** | 57% | R$ 24.685 |
| **R$ 97,00** *(Core Padrão)* | **R$ 85,09 (88%)** | **31 assinantes/mês** | **65%** | **R$ 39.769** |
| **R$ 129,00** | R$ 117,09 (91%) | 23 assinantes/mês | 74% | R$ 66.585 |
| **R$ 147,00** *(Pro futuro)* | R$ 135,09 (92%) | 20 assinantes/mês | 77% | R$ 81.669 |

*\*Simulação preliminar antes de calibrar a rampa final com o Painel v2.*

---

## 4. Decisão de Preço, Escada e Oferta de Abertura

1. **Preço padrão escolhido: `R$ 97,00/mês` (Plano Único de Lançamento — Magic Walls Core Web)**
   - Senta exatamente em cima do **IPP (`R$ 96,18`)** da curva Van Westendorp e empatado com o **OpLab ONE (R$ 97/mês)**, ficando **~60% abaixo da Jumba (~R$ 247/mês)** e confortavelmente dentro da faixa aceitável (`R$ 48,47`–`R$ 149,33`).
   - Dá **88% de margem de contribuição (R$ 85,09)** e exige apenas **31 assinantes ativos** para pagar 100% da operação + R$ 2.000/mês em marketing.
   - Mantém foco de produto (um único plano web simples no lançamento, evitando confundir o comprador com `Core / Pro / Quant`).

2. **Escada de Preço planejada para a Fase 2 (após validar retenção no Core):**
   - **Degrau 1 — Core Web (Lançamento):** **R$ 97/mês** (ou **R$ 79/mês** no plano trimestral pago adiantado R$ 237). Acesso completo ao terminal web WIN×WDO + modo compacto + cópia de níveis em 1 clique + Playbook de 8 min.
   - **Degrau 2 — Pro Web (Fase 2, pós-40 clientes):** **R$ 147/mês**. Adiciona replay histórico navegável de 90 pregões, alertas automáticos de aproximação de Wall/divergência e resumo matinal gravado às 08h35.
   - **Degrau 3 — Pro Anual (Fase 2):** **R$ 1.188/ano** (equivale a R$ 99/mês, priorizando caixa e retenção).

3. **Oferta de Abertura (real e com prazo definido, sem âncora falsa):**
   - **Lote Fundador — 40 vagas a `R$ 79,00/mês`** (valor travado enquanto a assinatura permanecer ativa; encerra ao completar 40 assinantes ou em **14 dias corridos após a abertura das vendas**, passando para o preço padrão de **R$ 97/mês**).
   - *Por que a escassez é real:* a VPS já suporta 1.000+ usuários, portanto o limite de 40 vagas refere-se exclusivamente à capacidade de acompanhamento próximo e onboarding direto do fundador nas primeiras duas semanas, **nunca** a limite de servidor.

4. **O que testar com compradores reais:**
   - Após 10 pregões consecutivos de prova diária pública no Instagram `@magicwallsb3`, testar dois links reais de checkout direto na bio/Stories: **Oferta A (`R$ 79/mês` Lote Fundador)** vs. **Oferta B (`R$ 97/mês` padrão)**, ambos sem trial gratuito e com **Garantia Incondicional de 7 dias em 1 clique**.

5. **Top 3 objeções literais de preço do painel v1 (para o marketing atacar de frente):**
   - *"Operando de 1 a 5 minicontratos, R$ 197 por mês pesa muito em pontos de WIN ou WDO só para empatar o custo fixo antes mesmo de eu saber se a ferramenta se paga no dia a dia."* (`P008`)
   - *"R$ 197 por mês pesa no meu custo fixo operacional para uma ferramenta cujo conceito de Gamma/GEX eu nem domino direito."* (`P003`)
   - *"Ter um plano de entrada na faixa de R$ 79 a R$ 99/mês para quem opera poucos contratos e transparência sobre como o GEX e o fluxo são calculados."* (`P017` em *What would flip a no*)
