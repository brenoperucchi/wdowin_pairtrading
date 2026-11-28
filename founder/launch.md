# Plano de Lançamento — Magic Walls (`100% Web SaaS`)

*(Ancorado na data atual: **26/11/2026**. Como dezembro tem queda gradual de liquidez na B3 pelo recesso de fim de ano, o plano usa o fim de novembro e dezembro para executar o **teste real pré-orçamento** + ajustes finais do produto, abrindo o **Lote Fundador público em 11/01/2027**, na volta plena dos pregões.)*

---

## 1. Teste Barato no Mundo Real (Antes de Gastar R$ 2.000/mês)

**O teste escolhido (assinatura sem trial + prova pública no Instagram):**
1. Durante **10 pregões úteis seguidos (`30/11/2026` a `11/12/2026`)**, publicar todos os dias no `@magicwallsb3`:
   - Às **08h35**: cálculo das Walls do dia (WIN e WDO) antes da abertura.
   - Às **17h30**: auditoria transparente do pregão mostrando deslocamento técnico máximo em pontos **e** eventuais stops/invalidações.
2. No link da bio e na página pública de histórico dos últimos 5 pregões, abrir uma **pré-venda controlada do Lote Fundador (`R$ 79/mês` travado · máximo 40 vagas · sem trial, com Garantia Incondicional de 7 dias em 1 clique)**.
3. Investir no máximo **R$ 1.000 no total** em impulsionamento de prova pré-abertura/remarketing durante esses 14 dias.

**Linha de sucesso definida ANTES de rodar (Critério Go / Adjust):**
- **Meta Go:** atingir **>= 12 assinantes pagantes no Lote Fundador em 14 dias** (`CAC pago <= R$ 100`) e taxa de pedido de reembolso nos 7 dias **<= 15%**.
- **Se ficar abaixo de 5 assinantes pagantes** (repetindo na vida real a trava de "sem trial" detectada no Painel v2): **NÃO liberar os R$ 2.000/mês em anúncios**. Rodar imediatamente um **teste A/B de 10 dias** comparando *Venda Direta com Garantia 7 dias* vs. *Trial de 5 pregões sem cartão (apenas e-mail)*, voltando para `/founder-offer` antes de escalar.

---

## 2. Contagem Regressiva Datada (`27/11/2026` a `11/01/2027`)

*(Tarefas marcadas com **[CAMINHO CRÍTICO]** atrasam o lançamento se escorregarem.)*

| Bloco / Semana | Prazo | Responsável | Entregável / Ação |
| --- | --- | --- | --- |
| **S1 (`27/11`–`04/12`)** **[CAMINHO CRÍTICO]** | `04/12/2026` | Fundador (Dev) | **Ajustes essenciais no produto web:** (1) criar Página Pública de Histórico (5 pregões) sem login; (2) criar Modo Compacto + Alerta Sonoro + Botão "Copiar Níveis (1 clique)"; (3) ajustar anti-rateio para tolerar 1 desktop + 1 mobile do mesmo titular; (4) ligar webhook Asaas + botões 1-clique de cancelar e reembolso 7 dias. |
| **S1–S2 (`30/11`–`11/12`)** **[CAMINHO CRÍTICO]** | `11/12/2026` | Fundador | **Executar o Teste Real de 10 Pregões** no `@magicwallsb3` (08h35 + 17h30) + pré-venda piloto (orçamento máximo R$ 1.000). |
| **S3 (`14/12`–`18/12`)** **[CAMINHO CRÍTICO]** | `18/12/2026` | Fundador + Jurídico/Contador | **Decisão Go/No-Go pós-piloto** (manter venda sem trial vs. habilitar trial de 5 pregões no funil) + revisão jurídica CVM nº 20/2021 / Termos LGPD + validação tributária com contador + protocolo INPI. |
| **S4 (`21/12`–`28/12`)** | `28/12/2026` | Fundador | Gravar **Playbook "5 Minutos Antes das 9h"** (vídeo de 8 min + PDF 1 página), publicar **Nota Metodológica Aberta** e configurar scripts de SLA automático (+7 dias se atrasar pós-08h45). |
| **S5 (`28/12`–`03/01`)** *(D-14 a D-8)* | `03/01/2027` | Fundador | Aquecimento de pré-lançamento (`founder/marketing.md`): liberar replay gravado ao vivo de M1/M5 com alerta sonoro e subir públicos de remarketing no Meta Ads. |
| **S6 (`04/01`–`10/01`)** *(D-7 a D-1)* **[CAMINHO CRÍTICO]** | `10/01/2027` | Fundador | **Soft-open com lista de interessados / amigos operadores (3–5 usuários)** para testar checkout Asaas real, carga da VPS, horário 08h35 e e-mail de onboarding em pregão normal. |
| **Lançamento (`11/01/2027`)** *(D0)* **[CAMINHO CRÍTICO]** | `11/01/2027` | Fundador | **Abertura pública do Lote Fundador (40 vagas a R$ 79/mês travado · 14 dias até `25/01`, passando a R$ 97/mês em `26/01`).** |

---

## 3. Run Sheet do Dia do Lançamento (`11/01/2027` — Segunda-feira)

- **07h30:** Checar VPS dedicada, logs de processamento do boletim B3, Asaas em modo produção e disponibilidade do site em modo anônimo.
- **08h15:** Validar os níveis do dia no painel e o funcionamento do botão "Copiar Níveis (1 clique)" + Modo Compacto.
- **08h35:** Publicar o card oficial pré-abertura no Instagram `@magicwallsb3` + Stories com contagem real de vagas do Lote Fundador (40 vagas).
- **08h55:** Ativar campanha de Remarketing no Meta Ads (`R$ 50/dia` inicial) direcionando para a Página de Histórico Público + Checkout Lote Fundador (R$ 79/mês).
- **09h00–12h30:** Monitorar pregão da manhã ao vivo (heartbeat VPS + fila de suporte). Responder todas as dúvidas de novos assinantes em <30 min (sempre sob CVM 20/2021).
- **12h30–14h00:** Verificar primeiros pagamentos confirmados no Asaas, entrega automática de e-mail e eventuais falhas de login desktop+mobile.
- **17h30:** Publicar card de auditoria pós-pregão no `@magicwallsb3` (deslocamento técnico em pontos + stops/invalidações) + link para quem acompanhou o dia entrar no Lote Fundador.
- **18h30:** Consolidar placar do Dia 1 (visitas, checkouts iniciados, assinantes pagos, vagas restantes) e conferir se algum cliente precisou do suporte/reembolso.

---

## 4. Primeiros 30 Dias: Métricas Semanais e Revisões

**Números semanais acompanhados:**
- Assinantes pagantes ativos vs. meta da rampa do CFO (**Mês 1 = 6 assinantes líquidos**, caminhando para break-even de **31 assinantes** no Mês 4);
- Custo por Assinante Pago (CAC <= R\$ 85 ideal / teto alerta R\$ 120);
- Taxa de reembolso em 7 dias (<= 8% meta / >15% gatilho de alerta);
- Pontualidade pré-08h45 (100% dos pregões com dados B3 publicados no prazo).

**Agenda de revisões obrigatórias:**
- **Dia 7 (`18/01/2027`):** *Quantas pessoas compraram no Lote Fundador sem trial? Quantas pediram reembolso nos 7 dias e qual o motivo exato?* -> Se vendas < 6 ou reembolso > 15%, ligar teste de trial 5 dias sem cartão imediatamente.
- **Dia 14 (`25/01/2027`):** *Encerramento do Lote Fundador (40 vagas ou prazo de 14 dias) e virada para R$ 97/mês.* Avaliar se o preço de R$ 97/mês mantém ritmo de entrada.
- **Dia 30 (`10/02/2027`):** *Retenção do primeiro ciclo mensal (quantos renovaram para o Mês 2?)* Calcular LTV real vs. CAC antes de manter ou ajustar a verba de R$ 2.000/mês.
