# Plano de Operações — Magic Walls (`100% Web SaaS`)

*(Operação desenhada para fundador solo, VPS dedicada já contratada por R\$ 1.900/2 anos escalável para 1.000+ usuários, backend 100% invisível ao usuário e conformidade com a legislação brasileira.)*

---

## 1. Ciclo Diário (do pós-pregão B3 até o fechamento do dia seguinte)

| Horário (BRT) | Ação operacional | Visível ao cliente? |
| --- | --- | --- |
| **18h15–19h30** | Coleta automatizada do boletim oficial de Posições em Aberto da B3 + fechamento 17h00 na VPS dedicada; cálculo das Walls WIN/WDO (`GEX_DAILY`). | Não (processamento interno) |
| **08h00–08h25** | Checagem automática de saúde do feed na VPS, rollover de vencimento WIN/WDO e geração do card matinal pré-abertura. | Não |
| **08h30–08h35** | **Publicação oficial das Walls do dia no Terminal Web** + publicação no **Instagram `@magicwallsb3`** (antes da abertura às 09h00, carimbando horário público). | **Sim** |
| **08h55–12h30** | Monitoramento do pregão da manhã (alertas Telegram de heartbeat/stale >15s); gravação de trecho curto de tela real em dias de movimento limpo nas Walls. | **Sim** (tempo real no painel) |
| **12h30–17h00** | Atendimento a dúvidas/suporte e manutenção de produto; monitoramento automatizado da sessão da tarde. | Parcial (suporte) |
| **17h30–18h00** | **Auditoria pós-pregão no `@magicwallsb3`:** publicação do balanço técnico em pontos (deslocamento máximo nas marcações + stops/invalidações) + atualização da Página de Histórico Público. | **Sim** |

---

## 2. Fornecedores e Infraestrutura Real (com preços públicos e links)

*(Todos os valores convertidos a referência estimada `R$ 5,80/USD` em `26/11/2026`. Nenhum valor foi inventado; itens de Roadmap Fase 2 estão marcados para cotação.)*

| Serviço | Fornecedor | Preço publicado / contrato | Papel na operação | Link |
| --- | --- | --- | --- | --- |
| **VPS Dedicada Windows** | Provedor já contratado pelo fundador | **R\$ 1.900 / 2 anos** *(já pago; R\$ 79/mês amortizado)* | Motor de cálculo GEX/fluxo + produtor push escalável para **1.000+ usuários** | Contrato ativo |
| **Banco PostgreSQL / Auth** | **Supabase Pro** | **US\$ 25/mês** (~R\$ 145/mês) | Perfis, assinaturas, termos, audit logs e RLS | [supabase.com/pricing](https://supabase.com/pricing) |
| **Cloud API (FastAPI)** | **Railway Pro** *(ou Fly.io `gru`)* | **US\$ 20/mês** (~R\$ 116/mês) | API REST, JWT, anti-rateio 4 camadas e entrega de snapshots | [railway.com/pricing](https://railway.com/pricing) |
| **Cache Edge / Sessão** | **Upstash Redis (Fixed)** | **US\$ 10/mês** (~R\$ 58/mês) | Controle de sessão e cache de snapshots em baixa latência | [upstash.com/pricing](https://upstash.com/pricing) |
| **Frontend Web** | **Cloudflare Pages** | **US\$ 0** *(Free; Workers Paid US\$ 5 se precisar)* | Hospedagem global estática da interface React | [pages.cloudflare.com](https://pages.cloudflare.com) |
| **Gateway & Recorrência** | **Asaas** | Cartão **2,99% + R\$ 0,49** / Pix **R\$ 1,99** *(mensalidade R\$ 0)* | Checkout cartão/Pix recorrente, webhooks automáticos e estorno | [asaas.com](https://www.asaas.com) |
| **Domínio & DNS** | **Registro.br** (`magicwalls.com.br`) | ~R\$ 40/ano | Domínio ativo (`HAS_NS` verificado em 26/11/2026) | [registro.br](https://registro.br) |
| **Feed Oficial (Fase 2)** | **Cedro Technologies / B3 Market Data** | **A cotar diretamente** *(não estimado no Ano 1)* | Substituir ponte de coleta atual por API oficial B3/Cedro quando a base escalar | [cedrotech.com](https://www.cedrotech.com) |

*(Nenhum custo real encontrado aqui diverge de `founder/numbers.json`.)*

---

## 3. Rotina Semanal (Fundador Solo)

- **Mês 1 (6 a 15 assinantes):** ~22h/semana dedicadas ao negócio — `08h00–09h30` rotina pré-abertura + post Instagram (7,5h/sem); `17h30–18h30` coleta B3 + post de fechamento (5h/sem); `ter/qui tarde` produção de conteúdo/anúncios + ajustes de UX (6h/sem); `sexta 18h` revisão de métricas e reembolsos (3,5h/sem).
- **Ritmo de 115 assinantes (Mês 12):** ~28h/semana — automatizar a geração do card 08h35 e 17h30 (já há utilitários base no repositório), mantendo apenas supervisão humana de 20 min pré-abertura, suporte assíncrono via e-mail/ticket (janela fixa 12h30–14h00 e 17h30–18h30) e 1 análise semanal de churn/anúncios.

---

## 4. Procedimentos Operacionais Padrão (SOPs de 1 Página)

### SOP 1 — Publicação Pré-Abertura até 08h35
1. Às `08h05`, conferir alerta do Telegram confirmando que o boletim da B3 da noite anterior foi processado sem erro na VPS.
2. Às `08h15`, validar no painel admin se Call Wall, Put Wall, FlipWall e MidWalls conferem com o vencimento vigente de WIN e WDO (checar datas de rollover na quarta-feira de vencimento).
3. Às `08h25`, confirmar o carregamento no navegador em modo anônimo (`app.magicwalls.com.br`).
4. Até `08h35`, publicar o card padrão no Instagram `@magicwallsb3` com horário visível antes da abertura.

### SOP 2 — Incidente ou Queda Durante o Pregão (09h–17h)
1. Ao receber alerta de `HEARTBEAT_STALE` no Telegram (>15s sem push), checar serviço da VPS imediatamente via RDP/SSH.
2. Se a indisponibilidade ultrapassar **5 minutos**, postar aviso nos Stories / banner no painel informando instabilidade em verificação.
3. Se ultrapassar **15 minutos** na sessão da manhã (`09h–12h`) ou atrasar publicação regular além de **08h45**, acionar o script administrativo para creditar **+7 dias automáticos** na assinatura de todos os usuários ativos (cumprindo o SLA prometido sem o cliente precisar pedir).

### SOP 3 — Onboarding e Suporte (Zero Atrito)
1. Após confirmação do webhook Asaas, enviar e-mail imediato (sem pedir WhatsApp) com link de acesso, botão para o Playbook de 8 minutos e resumo visual da **Visão Limpa**.
2. Dúvidas técnicas respondidas em até 4h úteis por e-mail/central de ajuda; nunca responder dando recomendação de compra/venda ou call de preço (sempre responder em termos de leitura educacional de níveis e metodologia CVM nº 20/2021).

### SOP 4 — Cancelamento e Reembolso em 1 Clique (Garantia 7 Dias)
1. Dentro de "Minha Conta", manter botão explícito **"Cancelar assinatura"** (sem retenção abusiva) e, nos primeiros 7 dias corridos após a primeira compra, **"Solicitar reembolso integral (Garantia 7 dias)"**.
2. Ao clicar em reembolso nos primeiros 7 dias, disparar estorno automático via API do Asaas, encerrar sessão ativa e enviar e-mail de confirmação com pesquisa opcional de 1 pergunta (*"O que faltou para encaixar no seu operacional?"*).

### SOP 5 — Fechamento Semanal & Auditoria Anti-Rateio (Sexta 18h)
1. Revisar logs de abuso do `cloud_saas` (excesso de troca de dispositivos/IPs distintos).
2. Ajustar a política de sessão única para **tolerar 1 navegador desktop + 1 dispositivo mobile do mesmo titular** (sem derrubar por uso legítimo), bloqueando apenas uso simultâneo em múltiplos IPs/cidades diferentes.
3. Conferir métricas semanais (seguidores -> visitas histórico -> assinantes -> reembolsos 7d -> churn).

---

## 5. Stack Mínimo de Ferramentas

- **Backend / API / DB / Cache:** Python FastAPI (`Railway Pro` US\$ 20/mês) + `Supabase Pro` (US\$ 25/mês) + `Upstash Redis` (US\$ 10/mês) + `Cloudflare Pages` (US\$ 0).
- **Produtor de Mercado:** `VPS Windows Dedicada` (R\$ 1.900/2 anos já paga, 1.000+ usuários).
- **Pagamentos & Recorrência:** `Asaas` (mensalidade R\$ 0; taxas por transação).
- **E-mail transacional:** `Resend` ou `Brevo` (faixa gratuita inicial para até 3.000 e-mails/mês; confirmar volume conforme base crescer).

---

## 6. Checklist Legal, Fiscal e Regulatório (Brasil)

*Aviso: regras fiscais e regulatórias mudam e dependem do enquadramento exato da empresa; um contador e um advogado devem confirmar cada item antes de escalar vendas.*

1. **CNPJ e Regime Tributário (SaaS / Software):** Software analítico/licenciamento não se enquadra no MEI; estruturar ME no Simples Nacional (ex.: CNAE de desenvolvimento/licenciamento de software, avaliando Fator R entre Anexos III e V com contador) e emissão de NFS-e automática — conferir em [gov.br/empresas-e-negocios](https://www.gov.br/empresas-e-negocios/pt-br/empreendedor).
2. **Resolução CVM nº 20/2021 (Valores Mobiliários):** Manter linguagem estritamente analítica/educacional em todo o terminal, no Playbook e especialmente nos posts diários do Instagram (evitar recomendações personalizadas de compra/venda ou promessas de retorno financeiro) — consultar [conteudo.cvm.gov.br](https://conteudo.cvm.gov.br).
3. **Código de Defesa do Consumidor (Art. 49):** Direito de arrependimento de 7 dias em compras online — transformado em vantagem comercial com reembolso em 1 clique — consultar [planalto.gov.br (CDC)](https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm).
4. **LGPD (Lei 13.709/2018):** Coleta mínima (apenas e-mail/nome para acesso + dados fiscais no Asaas), termos de uso e política de privacidade explícitos para watermark forense e registro de IP anti-rateio — consultar [gov.br/anpd](https://www.gov.br/anpd/pt-br).
5. **Registro de Marca:** Busca prévia e depósito no **INPI** nas classes **9** (software), **36** (ferramentas de informação financeira) e **41** (conteúdo educacional) — consultar [gov.br/inpi](https://www.gov.br/inpi/pt-br).

---

## 7. Registro de Riscos Operacionais (Top 10)

| # | Risco | Probabilidade | Impacto | Plano de ação / contingência |
| --- | --- | --- | --- | --- |
| 1 | **Atraso na publicação do boletim oficial pela B3** | Média | Alto | Comunicar nos Stories até 08h30 se a B3 atrasar arquivo; usar modo de fallback com observação visível no painel e isentar penalidade de SLA quando a fonte oficial B3 não estiver disponível. |
| 2 | **Bloqueio de conta Meta Ads ou restrição no Instagram por copy de "ganho máximo"** | Média-Alta | Alto | Nunca prometer retorno financeiro em R\$. Enquadrar sempre como *"deslocamento técnico estatístico em pontos nas regiões de liquidez"* + mostrar dias de stop + evitar jargões de enriquecimento rápido nos anúncios. |
| 3 | **Queda da coleta/VPS às 09h05 em pregão volátil** | Baixa-Média | Alto | Watchdog automático na VPS + alerta Telegram em 15s + hot standby pronto + crédito automático de +7 dias se passar de 15 min fora. |
| 4 | **Taxa de reembolso acima de 12% na garantia de 7 dias (por falta de trial)** | Média | Médio-Alto | Auditar motivo na saída; se >15%, ativar teste A/B com trial de 5 pregões sem cartão (só e-mail). |
| 5 | **Conflito da trava anti-rateio entre desktop e mobile** | Alta (se não ajustar) | Médio | Liberar 1 sessão desktop + 1 mobile no mesmo IP/titular e aplicar bloqueio apenas para compartilhamento multi-IP simultâneo. |
| 6 | **Erro no rollover de vencimento WIN / WDO** | Baixa | Alto | Checklist fixo de calendário B3 nas quartas-feiras de vencimento + validação visual antes das 08h20. |
| 7 | **Pirataria / rateio de conta em grupos de Telegram** | Média | Médio | Manter watermark forense com e-mail/timestamp do usuário + detector de abuso de IPs distintos. |
| 8 | **Chargeback por esquecimento de renovação mensal** | Baixa-Média | Baixo-Médio | Enviar lembrete por e-mail 3 dias antes da renovação + botão de cancelamento em 1 clique no painel. |
| 9 | **Dependência de ponte local antes da API oficial B3/Cedro** | Média | Médio-Alto | Iniciar cotação comercial com a Cedro/B3 assim que atingir 100–150 assinantes pagantes para planejar migração limpa na Fase 2. |
| 10 | **Doença ou indisponibilidade do fundador solo às 08h00** | Baixa | Alto | Pipeline `GEX_DAILY` 100% agendado e autônomo na VPS, com verificação rápida pelo celular em 2 minutos. |
