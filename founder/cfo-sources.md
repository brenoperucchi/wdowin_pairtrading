# Fontes dos Números Financeiros (`founder/numbers.json`)

**Convenções do modelo (`unit_economics.py`):**
- **Moeda:** Todos os valores em `founder/numbers.json` estão em **Reais brasileiros (R$ / BRL)** (mesmo onde o script oficial imprime o prefixo `$` por padrão).
- **Taxa de câmbio de referência (estimativa):** `R$ 5,80 / US$ 1,00` (em `26/11/2026`) aplicada apenas aos itens de infraestrutura faturados em dólar.
- **Unidade de volume:** `"unit": "assinante/mês"` com `"days_per_month": 1`. Assim, `plan_per_day`, `ramp_per_day`, `capacity_per_day` e `breakeven_per_day` representam exatamente **assinantes pagantes ativos por mês**.
- **Regime de pró-labore (premissa confirmada pelo fundador):** Sem pró-labore fixo no Ano 1 (o resultado operacional remanescente é o caixa/lucro gerado para o fundador antes de impostos).

---

## 1. Custos Variáveis (por assinante pagante/mês · base R$ 97,00)

| Item | Valor (R$) | Fonte / Base |
| --- | ---: | --- |
| **Gateway Asaas (Cartão à vista)** | 3,39 | `2,99% + R$ 0,49` por transação (`https://www.asaas.com`, pior caso vs. Pix a `R$ 1,99`). Para R$ 97,00: `97 * 0,0299 + 0,49 = R$ 3,39`. |
| **Provisão de reembolso / garantia 7 dias CDC** | 5,82 | Estimativa conservadora de **6%** de reembolso inicial sem trial gratuito (`97 * 0,06 = R$ 5,82`). Monitorar no mundo real nas primeiras 4 semanas. |
| **Infra marginal + e-mail transacional por usuário** | 2,70 | Estimativa de uso marginal de tráfego/e-mails/logs por assinante ativo. |
| **Total variável por assinante/mês** | **11,91** | Soma dos itens acima. |

---

## 2. Custos Fixos Mensais

| Item | Valor (R$/mês) | Fonte / Base |
| --- | ---: | --- |
| **Supabase Pro** | 145,00 | Plano Pro público `US$ 25/mês` (`https://supabase.com/pricing`) × `R$ 5,80`. |
| **Cloud API (Railway Pro / Fly.io `gru`)** | 116,00 | Plano Railway Pro `US$ 20/mês` (`https://railway.com/pricing`) × `R$ 5,80` (cobre container FastAPI em produção). |
| **Upstash Redis (Fixed Plan)** | 58,00 | Plano Fixed `US$ 10/mês` (`https://upstash.com/pricing`) × `R$ 5,80`. |
| **VPS Dedicada (amortização econômica 24m)** | 79,00 | Contrato já pago pelo fundador de **R$ 1.900 por 2 anos** (`1.900 / 24 = R$ 79,17/mês`). Não gera desembolso mensal novo nos próximos 24 meses, mas entra como reserva econômica de renovação no DRE. Capacidade: **1.000+ usuários**. |
| **Cloudflare Pages + domínio `.com.br`/DNS/e-mail** | 40,00 | Cloudflare Pages Free (`R$ 0` — `https://pages.cloudflare.com`) + estimativa de rateio mensal de domínio `.com.br` (`Registro.br` ~R$ 40/ano) e e-mail transacional. |
| **Contabilidade online PJ** | 190,00 | Estimativa de mercado para contabilidade digital mensal PJ de software no Simples Nacional *(confirmar com contador real)*. |
| **Marketing (orgânico + tráfego pago Meta/Instagram)** | 2.000,00 | Teto mensal informado pelo fundador (`até R$ 2.000/mês`). |
| **Total fixo mensal** | **2.628,00** | Soma dos itens acima. |

> **Item futuro fora do Mês 1 (Fase 2 — cotação pendente):** Migração do feed de cotações para **API oficial B3 / Cedro Technologies** (roadmap técnico futuro). Como o valor depende de proposta comercial direta com a Cedro/B3 conforme volumetria, não é estimado nem inventado aqui; deve ser cotado antes de escalar além de ~150–250 assinantes pagantes.

---

## 3. Investimento Novo Pré-Lançamento (`startup`)

*(O software web já está construído e a VPS de R$ 1.900 por 2 anos já foi contratada e paga previamente pelo fundador — portanto não entram como caixa novo necessário para lançar.)*

| Item | Valor (R$) | Fonte / Base |
| --- | ---: | --- |
| **Registro de marca INPI (1 classe)** | 400,00 | Estimativa de taxa federal GRU (PF/MEI/ME) + busca prévia (`https://www.gov.br/inpi`). |
| **Templates Instagram + edição vídeos onboarding/playbook** | 300,00 | Estimativa interna de ferramentas/ativos iniciais de produção. |
| **Teste pago de pré-lançamento (14 dias)** | 1.000,00 | Orçamento alocado para validar conversão dos posts diários do `@magicwallsb3` antes de escalar verba mensal cheia. |
| **Revisão jurídica básica (CVM 20/2021, Termos, LGPD)** | 1.200,00 | Estimativa para revisão pontual de Termos de Uso, política de privacidade e copy de prova diária. |
| **Total startup (novo caixa)** | **2.900,00** | Soma dos itens acima. |
