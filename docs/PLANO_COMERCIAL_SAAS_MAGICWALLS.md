# PLANO COMERCIAL E ARQUITETURA SAAS — MAGIC WALLS (`@magicwallsb3`)

**Documento Mestre de Produto, Comercial, Jurídico-Compliance (CVM/LGPD), Marketing & Arquitetura Cloud**  
**Marca Oficial:** MAGIC WALLS | **Instagram Oficial:** `@magicwallsb3` | **Status:** Pronto para Provisionamento Cloud & Go-Live

---

## 1. Diagnóstico Executivo dos Ativos Existentes no Repositório

A infraestrutura da **MAGIC WALLS** já conta com motor proprietário completo rodando localmente e pipeline pronto para publicação em nuvem sem exposição do ambiente de cálculo:

| Camada | Ativos Já Construídos no Repositório | Papel na Operação Comercial |
|---|---|---|
| **Motor Quant & Opções GEX** | `gex/`, `core/`, `server.py` (FastAPI `:8080`), `painel_publico.py` | Cálculo de Gamma Exposure, Call/Put Walls, Zero Gamma Flip, HVL, IV Rank e separação Core vs Pro. |
| **Painéis Analíticos** | `regime-dashboard/` (`:5174` Top 8 EAs, `:5176` Sniper Divergência Smart Money, `:8080` Dashboard Principal + `IntradayCompassPanel.jsx`) | Frontend React/Vite com build duplo: local e SaaS (`build-saas.mjs` -> `dist-saas/`). |
| **Ativos de Conteúdo Diário** | `MorningWallsVideoModal.jsx`, `morningVideoData.js`, `morningVideoRenderer.js`, `InstagramCardModal.jsx`, endpoint `GET /api/morning-brief` | Vídeo Reels/Shorts automático de abertura (`30s` Dual WIN+WDO / `20s` ativo único) e Cards de fechamento para `@magicwallsb3`. |
| **Máquina Editorial & Growth** | `openbot-team/` (29 arquivos: `BRAND_BIBLE_CVM.md`, `TEAM_MANIFEST.json`, `PROVISIONING_PROMPTS.md`, 8 agentes, 12 skills, 5 workflows) | Operação autônoma de conteúdo, marca, tráfego pago, funil Telegram/Instagram, recuperação de carrinho e suporte. |
| **Cloud SaaS & Anti-Rateio** | `cloud_saas/` (`app.py`, `config.py`, `database.py`, `store.py`, `security.py`, `supabase_schema.sql`, `Dockerfile`, `railway.toml`, `fly.toml`), `scripts/cloud_publisher.py`, `scripts/verify_cloud_connections.py` | Push Architecture com Supabase PostgREST + Upstash Redis + 4 camadas anti-rateio + watermark forense (`ForensicWatermark.jsx`). |
| **Licenciamento MT5** | `mt5/Include/Jumba_LicenseGuard.mqh`, `mt5/Include/Jumba_SafetyGuard.mqh` | Validação de `AccountInfoInteger(ACCOUNT_LOGIN)` e expiração via API antes de autorizar ordens no Tier QUANT. |

### Referência Histórica Auditada para Comunicação Responsável (Tier Sniper / Pesquisa)

Conforme documentado em `docs/PAINEL_5176_SNIPER_DIVERGENCIA_SMART_MONEY.md`, o estudo auditado de 2026 (`WIN_DIV_WALL` 2 contratos + `WDO_DIV_WALL` 1 contrato, filtros `no 12h WIN` e `no 11h WDO`, fórmula V5b) registrou:
- Resultado acumulado auditado no recorte: **+R$ 12.827**
- Win Rate (WR): **70,0%** | Profit Factor (PF): **2,49**
- Max Drawdown (MDD): **-R$ 380** | Retorno/DD: **33,76x** | Consistência: **11/11 meses positivos** no recorte analisado

> **Regra de Comunicação:** Toda menção a números históricos deve vir acompanhada de contexto de data, parâmetros utilizados e aviso explícito de que resultados passados não garantem retornos futuros.

---

## 2. Identidade de Marca (`@magicwallsb3`), Posicionamento & Blindagem Jurídica (CVM / LGPD / Clickwrap)

### 2.1 Posicionamento Oficial
- **Handle único em todos os canais, vídeos e cards:** `@magicwallsb3`
- **Proposta de Valor:** Ferramenta quantitativa de leitura institucional de fluxo de opções (Gamma Exposure / Call & Put Walls / Zonas de Liquidez) e engenharia de regime para **WIN (Mini-Índice)** e **WDO (Mini-Dólar)** na B3.
- **O que a MAGIC WALLS É:** Software de análise quantitativa, visualização de dados estatísticos e apoio à decisão operacional (SaaS de ferramentas analíticas / tecnologia).
- **O que a MAGIC WALLS NÃO É:** Casa de análise com call de compra/venda, carteira recomendada, consultoria individual de valores mobiliários ou gestão de recursos de terceiros.

### 2.2 Escudo Regulatório — Resolução CVM nº 20 e Regras de Linguagem
1. **Separação Estrita Ferramenta x Recomendação:**
   - **Proibido:** "compre WIN agora", "venda no ponto X", "sinal garantido", "lucro certo", "ganhe todo dia".
   - **Permitido:** "zona estatística de Call Wall", "regime Gamma Negativo detectado pelo modelo", "região de resistência implícita por concentração de OI/Gamma", "leitura institucional pré-pregão".
2. **Disclaimer Obrigatório em Toda Peça Pública (`@magicwallsb3`):**
   - Rodapé fixo em Reels, Cards, Landing Page e Checkout: *"Ferramenta educacional e analítica de dados de mercado (GEX/Regime). Não constitui recomendação de investimento (Res. CVM 20). Operações em renda variável e futuros envolvem risco substancial de perda."*
3. **Clickwrap Versionado e Auditável (LGPD + Defesa de Chargeback):**
   - Nenhum usuário acessa o snapshot de mercado (`403 TERMS_NOT_ACCEPTED`) antes de aceitar os Termos de Uso e Ciência de Risco (`MW_TERMS_VERSION`, padrão `2026.11`).
   - Registro imutável nas tabelas `terms_acceptance` e `audit_logs` do Supabase contendo `user_id`, `terms_version`, `accepted_at` (UTC), `ip` e `user_agent`.
   - Minimização de dados LGPD: armazenamento de CPF apenas mascarado (`cpf_masked`) para exibição e nota fiscal junto ao gateway, senhas com hash seguro (`PBKDF2-HMAC-SHA256`), e logs de auditoria para exercício de direitos do titular.

---

## 3. Escada de Ofertas & Precificação (Alinhada à `BRAND_BIBLE_CVM.md`)

Estrutura desenhada para maximizar conversão do tráfego orgânico/pago do `@magicwallsb3`, capturar ticket médio recorrente (MRR) e ancorar o plano topo de funil sem comprometer a capacidade computacional:

| Degrau | Produto / Plano | Preço Oficial (BRL) | Entitlement Server-Side (`plan`) | Entregáveis Principais | Papel no Funil |
|---|---|---|---|---|---|
| **0 (Gratuito)** | **Canal Radar 08h30 (`@magicwallsb3`)** | R$ 0 | Público (sem acesso ao live feed) | Vídeo diário pré-pregão (`30s`, `@magicwallsb3`) + resumo de Regime Gamma e 3 níveis principais antes da abertura + prova de fechamento 17h15. | Aquisição, autoridade institucional e aquecimento de audiência. |
| **1 (Tripwire / Ads)** | **Passe Degustação 7 Dias** | R$ 29,90 (pagamento único) | `trial` (acesso `core` por 7 dias) | Acesso completo ao Terminal Web CORE por 7 dias corridos (abate no anual ou converte com transparência). | Quebra de objeção em tráfego frio e validação prática em pregão real. |
| **2 (Entrada Recorrente)** | **MagicWalls CORE** | R$ 197/mês (Anual R$ 1.497) | `core` (payload sanitizado) | WIN + WDO tempo real com Walls, MidWalls, Canal Gauss e Fluxo Smart Money + Download diário ProfitChart (`jumba_neologica`) e TradingView (`jumba_tradingview.pine`), Watermark Forense e Sessão Única. | Base de MRR previsível para traders discricionários de WIN/WDO. |
| **3 (Carro-Chefe)** | **MagicWalls PRO (Sniper)** | R$ 347–397/mês (Anual R$ 2.697) | `pro` (payload completo + telemetria avançada) | Tudo do CORE + Painel Sniper `5176` (divergências `F1->F2 / T1->T2`, projeções `TP/SL/BE`, placar do dia) + Replay Histórico + GEX Global 14 Ativos + Alertas Telegram. | Principal motor de receita e LTV (alvo de 50%+ dos assinantes pagos). |
| **4 (High-Ticket / Automação)** | **MagicWalls QUANT / DESK** | R$ 797–997/mês (Anual R$ 5.997) | `quant` (`pro` + `mt5_license_token`) | Tudo do PRO + EAs compilados `.ex5` MT5 com proteção `Jumba_LicenseGuard.mqh` vinculada a 1 conta `ACCOUNT_LOGIN` + Painel de Carteiras `5174` + kill-switch de expiração por API. | Maximização de ARPU, menor sensibilidade a preço e barreira técnica contra pirataria. |

### Campanha de Lançamento — Turma Fundadores (50 Vagas Limitadas)
- **Objetivo:** Validar fluxo de cobrança, telemetria e feedback com os primeiros 50 assinantes antes de escalar tráfego pago pesado.
- **Condição Especial Fundadores:** Desconto vitalício enquanto a assinatura permanecer ativa (ex.: **PRO Fundadores com até 40% OFF**, cerca de R$ 237/mês sobre tabela PRO de R$ 397/mês; **CORE Fundadores** R$ 147/mês; até 10 vagas **QUANT Fundadores** com homologação acompanhada da conta MT5).
- **Mecanismo de Escassez Real:** Contador vinculado à tabela `subscriptions` no Supabase; encerradas as 50 vagas fundadoras, o checkout assume automaticamente a tabela cheia.

---

## 4. Arquitetura Técnica de Produção (Push, Escala & Anti-Rateio em 4 Camadas)

### 4.1 Decisão #1 de Engenharia: Push Architecture (Zero Exposição do Windows Local)
Em vez de expor o `server.py` (`:8080`) diretamente via túnel para centenas de navegadores (o que derrubaria o MT5/Profit e o servidor local às 10h00), a máquina produtora **empurra** os snapshots sanitizados para a nuvem a cada `2-3s`:

1. **Produtor Local (`scripts/cloud_publisher.py`):**
   - Faz **apenas 1 leitura local** no `http://127.0.0.1:8080` por ciclo (2-3 segundos).
   - Aplica sanitização diferenciada antes mesmo do envio: gera `snapshot core` e `snapshot pro` separados.
   - Assina o pacote com **HMAC-SHA256** (`X-Producer-Signature`) + `X-Producer-Id` + `X-Producer-Role` (`primary` ou `standby`).
2. **Camada de Estado Ultra-Rápida (Upstash Redis REST):**
   - Armazena o último snapshot `core` e `pro` em memória com TTL configurável (`MW_SNAPSHOT_TTL_SEC=300`).
   - Armazena a sessão ativa única do usuário (`sess:{user_id}`) e os metadados de saúde do feed (`snap:meta`) para resposta sub-10ms para milhares de clientes simultâneos.
3. **Persistência & Auditoria (Supabase PostgreSQL / PostgREST — 5+1 Tabelas):**
   - `profiles`: dados cadastrais mínimos, `cpf_masked`, flag `is_blocked`, `blocked_reason` e senha hashed.
   - `subscriptions`: plano contratado (`trial`, `core`, `pro`, `quant`, `admin`), status (`active`, `past_due`, `suspended`, `blocked`, `canceled`), `expires_at`, `gateway`, `external_sub_id`, vínculo `mt5_account_login` e `mt5_license_token`.
   - `active_sessions`: espelho persistente e histórico por pregão da sessão (`user_id`, `session_id`, `ip`, `device_fp`, `user_agent`, `trading_day`, `is_active`, `revoked_reason`) + base do contador diário de trocas por pregão.
   - `terms_acceptance`: histórico imutável de aceites clickwrap com `terms_version`, `accepted_at`, `ip` e `user_agent`.
   - `audit_logs`: trilha forense de segurança (`LOGIN_OK`, `SESSION_REPLACED`, `ABUSE_BLOCKED`, `TERMS_ACCEPTED`, `BILLING_EVENT`, `ADMIN_KICK`, `ADMIN_UNBLOCK`).
   - `producer_heartbeats`: telemetria de saúde dos produtores `primary` e `standby` para SLA e failover.
4. **Backend SaaS Leve (`cloud_saas/app.py` — FastAPI na Railway ou Fly.io `gru`):**
   - Região recomendada: **São Paulo (`gru` no Fly.io ou deploy próximo na Railway)** para latência mínima em pregão B3.
   - Checa plano no JWT + banco no servidor (**Server-Side Entitlements**) antes de entregar qualquer dado — impossível escalar privilégio via DevTools.
5. **Frontend Edge (Cloudflare Pages):**
   - Build dedicado gerado por `cd regime-dashboard && node build-saas.mjs` (`dist-saas/`), apontando exclusivamente para a URL do Cloud SaaS (`VITE_API_BASE` + `VITE_SAAS_AUTH=1`), sem expor caminhos locais.

### 4.2 Blindagem Anti-Rateio em 4 Camadas
1. **Camada 1 — Sessão Única Rigorosa (`single_session`):** Novo login gera novo `session_id` gravado no Upstash Redis e `active_sessions`. Em até 3 segundos de polling, a sessão antiga recebe HTTP `401 SESSION_REPLACED` com mensagem *"Acesso iniciado em outro dispositivo"* e é deslogada automaticamente.
2. **Camada 2 — Fingerprint & Limite Diário por Pregão:** O cliente envia `device_fp` + IP. Mais de **4 trocas** no mesmo pregão (`MW_MAX_DEVICE_SWITCHES_PER_DAY=4`) aciona flag automática `ABUSE_BLOCKED`, registra evento em `audit_logs` e bloqueia preventivamente até revisão administrativa.
3. **Camada 3 — Watermark Forense Dinâmica (`ForensicWatermark.jsx`):** Sobreposição diagonal de baixa opacidade (`opacity: 0.04`, `pointer-events: none`) exibindo `e-mail + ID do cliente` diretamente sobre o `IntradayCompassPanel.jsx`, identificando instantaneamente retransmissões piratas ou gravações em Discord/Telegram.
4. **Camada 4 — Licenciamento MT5 On-Chain Local (`Jumba_LicenseGuard.mqh` + `Jumba_SafetyGuard.mqh`):** Os EAs do Tier QUANT validam `AccountInfoInteger(ACCOUNT_LOGIN)` + token contra `/api/v1/mt5/verify` com janela de expiração — inadimplência suspende novas entradas no pregão seguinte.

### 4.3 Resiliência de Pregão (SLA 99,9%) & Plano de Continuidade
- **Monitor de Heartbeat (`08:55–17:30 BRT`):** Se o produtor ativo ficar **> 15s** sem publicar pacote durante o horário de pregão (`MW_HEARTBEAT_STALE_SEC=15`), a API/monitor dispara alerta crítico instantâneo no Telegram pessoal do operador (`TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`).
- **Fase 1 (0–40 clientes pagos):** PC local atual como `primary` + Nobreak + link celular 4G/5G de contingência.
- **Fase 2 (40+ clientes — financiado pelo próprio MRR):** VPS Windows dedicada (~R$ 400/mês) operando como produtor `primary` 24/7 e o PC local rebaixado para `standby` (Hot Standby assume o push automaticamente se o primary cair por >= `MW_PRIMARY_FAILOVER_SEC=12` segundos).
- **Segurança Estrita de Segredos:** Nenhuma referência a `serviceAccountKey.json` no pipeline SaaS; 100% das chaves (`MW_JWT_SECRET`, `MW_PUSH_HMAC_SECRET`, `SUPABASE_SERVICE_ROLE_KEY`, `UPSTASH_REDIS_REST_TOKEN`, `MW_BILLING_WEBHOOK_SECRET`, `MW_ADMIN_API_KEY`, `MW_MT5_LICENSE_SECRET`) residem exclusivamente em variáveis de ambiente na nuvem.

---

## 5. Pagamentos Brasil, Webhooks & Régua de Cobrança / Dunning

| Fluxo | Especificação Técnica e Comercial |
|---|---|
| **Meios de Pagamento** | Cartão de Crédito recorrente (aprovação imediata), Pix Recorrente/Mensal (baixa fricção no público trader BR) e Boleto apenas para plano anual. |
| **Gateways Suportados** | Kiwify, Hotmart, Asaas, Pagar.me ou Stripe integrados via `POST /webhooks/billing` protegido por assinatura HMAC-SHA256 (`X-MW-Webhook-Signature` / `MW_BILLING_WEBHOOK_SECRET`). |
| **Provisionamento Instantâneo** | Evento `paid` / `renewed` / `subscription.active` -> cria/atualiza `profiles` e `subscriptions` com `status=active`, envia credenciais/link de acesso e libera login com clickwrap em segundos. |
| **Dunning Automático (Recuperação)** | Evento `past_due` / `payment_failed`: concede carência controlada (`grace_3d`) + disparo automático do agente `07-recovery-retention` no WhatsApp/E-mail com link Pix de quitação. Evento `canceled` / `refunded` / `chargeback`: suspende `subscriptions`, revoga imediatamente a sessão no Redis e revoga acesso ao `mt5_license_token`. |
| **Antecipação de Chargeback** | Logs de `terms_acceptance` + `active_sessions` + `audit_logs` (IP, timestamp, dispositivo e uso efetivo do dashboard) fornecem dossiê completo para contestação em caso de má-fé. |

---

## 6. Funil de Aquisição no Instagram (`@magicwallsb3`) & Operação `openbot-team/`

### 6.1 Máquina Editorial Semanal (100% Integrada ao Dashboard)
O perfil `@magicwallsb3` opera como vitrine viva do motor, alimentado diariamente pelos exportadores nativos do sistema:
1. **08:15–08:30 BRT (Pré-Pregão):** Exportação do vídeo animado de 30 segundos (`MorningWallsVideoModal.jsx`, trilha limpa, Call Wall, Put Wall, Flip e zonas WIN/WDO) -> Reels + Stories no `@magicwallsb3` + Canal Telegram.
2. **12:30 BRT (Meio de Pregão — Stories):** Bastidor de comportamento de fluxo na zona calculada (sem dar call operacional).
3. **17:15–17:45 BRT (Pós-Pregão):** Exportação do card de fechamento (`InstagramCardModal.jsx`, handle `@magicwallsb3`) mostrando como o preço respeitou ou rompeu as walls publicadas às 08h30 — prova visual auditável ("mapeado antes da abertura").
4. **DM & Stories Funnel:** Palavra-chave nos comentários/DM (ex: `MAPA`, `GEX`, `PASS`, `FUNDADORES`) -> direciona para o Passe Degustação 7 Dias (R$ 29,90) ou Checkout Fundadores com sequência automática de qualificação.

### 6.2 Equipe Autônoma (`openbot-team/`)
A equipe documentada em `openbot-team/` orquestra 8 agentes especializados e 5 workflows:
- `01-ceo-magicwalls`: coordenação de metas de MRR, priorização diária e revisão executiva.
- `02-brand-compliance`: guardião da Bíblia de Marca (`BRAND_BIBLE_CVM.md`) e veto absoluto contra promessas ilegais (Res. CVM 20).
- `03-instagram-content-head`: roteiros curtos (Reels, Carrosséis educativos de GEX, Stories de bastidor) para `@magicwallsb3`.
- `04-editor-motion`: produção operacional com `MorningWallsVideoModal` (`30s`) e `InstagramCardModal` (`@magicwallsb3`).
- `05-traffic-manager`: gestão de criativos Meta Ads / Google Ads focados em CAC sustentável sobre Passe 7 Dias e CORE/PRO.
- `06-social-dm-closer`: atendimento consultivo via DM no Instagram `@magicwallsb3` e fechamento para planos pagos.
- `07-recovery-retention`: régua de carrinhos abandonados, Pix pendente, dunning `D+0..D+3` e reativação de cancelados.
- `08-growth-analytics`: acompanhamento diário/semanal de CPL, CAC, auditoria de fechamento 17h15, ativação e churn.

---

## 7. Onboarding, Retenção & Combate ao Churn

Um trader que não entende o indicador nos primeiros **3 dias** cancela no primeiro mês. Protocolo obrigatório de ativação:
1. **Primeiros 15 Minutos (Aha! Moment):** Ao aceitar os termos no dashboard SaaS, o usuário recebe guia visual curto explicando 3 leituras essenciais: *Call Wall*, *Put Wall* e *Zero Gamma Flip*.
2. **Checklist de 7 Dias (E-mail + Telegram):**
   - Dia 1: Boas-vindas + mini-aula de 4 minutos *"Como ler as Walls às 08h30 antes da abertura B3"*.
   - Dia 3: *"Diferença entre Gamma Positivo (mercado travado) e Gamma Negativo (aceleração)"*.
   - Dia 5: Check-in proativo de uso + convite para tirar dúvidas sobre leitura de regime.
   - Dia 6 (para Passe 7 Dias): Oferta de upgrade com bônus de desconto para CORE ou PRO antes da expiração.
3. **Alerta Silencioso de Risco de Churn:** Assinante ativo que passar **5 pregões seguidos** sem login dispara mensagem automática de reengajamento personalizada.

---

## 8. Unit Economics, Metas de Receita (0 -> 100 Clientes) & Checklist Go-Live

### 8.1 Custo Fixo Cloud Enxuto vs Escala de MRR

| Marco | Composição Estimada (Exemplo Mix 45% CORE / 45% PRO / 10% QUANT) | MRR Bruto Estimado | Infra Cloud Estimada (Supabase + Upstash + Railway/Fly) | Resultado Operacional da Infra |
|---|---|---|---|---|
| **Validação (10 clientes)** | 4 CORE + 5 PRO + 1 QUANT (tabela cheia) | ~R$ 3.570/mês | Free / Starter (~R$ 0 a R$ 150/mês) | Margem de software > 95% |
| **Turma Fundadores (50 clientes)** | 22 CORE (R$ 147) + 23 PRO (R$ 237) + 5 QUANT (R$ 597) | ~R$ 11.670/mês | Pro starters + VPS Windows Fase 2 (~R$ 650/mês total) | VPS dedicada paga por ~5,6% do MRR |
| **Escala Inicial (100 clientes)** | 40 CORE (R$ 197) + 48 PRO (R$ 397) + 12 QUANT (R$ 797) | ~R$ 36.500/mês | Infra escalada + VPS + monitoria (~R$ 950/mês) | Base sólida para escala em tráfego pago |

*Meta de Eficiência SaaS:* CAC alvo <= 1,0x ticket mensal no tráfego direto (recuperado no 1º mês ou no Passe Degustação 7 Dias de R$ 29,90) e Churn mensal alvo < 6% via onboarding estruturado + utilidade diária obrigatória pré-pregão.

### 8.2 Checklist Final de Go-Live (Execução Técnica em 5 Passos)
1. **Supabase:** Criar projeto -> abrir SQL Editor -> executar `cloud_saas/supabase_schema.sql` (cria as 6 tabelas: `profiles`, `subscriptions`, `active_sessions`, `terms_acceptance`, `audit_logs`, `producer_heartbeats` com RLS habilitado) -> copiar `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY`.
2. **Upstash Redis:** Criar banco Redis em região próxima (preferencialmente `sa-east-1` ou menor ping disponível) -> copiar `UPSTASH_REDIS_REST_URL` e `UPSTASH_REDIS_REST_TOKEN`.
3. **Backend SaaS (`cloud_saas/`):** Fazer deploy na **Railway** (`cloud_saas/railway.toml`) ou **Fly.io** (`cloud_saas/fly.toml`, região `gru`) com todas as variáveis de `cloud_saas/.env.example` configuradas.
4. **Frontend SaaS:** Na pasta `regime-dashboard/`, configurar `VITE_API_BASE` apontando para o domínio HTTPS da Cloud API + `VITE_SAAS_AUTH=1`, rodar `node build-saas.mjs` e publicar `regime-dashboard/dist-saas/` no Cloudflare Pages.
5. **Validação & Virada de Chave:**
   - Rodar `python scripts/verify_cloud_connections.py` e confirmar `OK` em Supabase (6 tabelas), Upstash (`SET/GET/DEL`) e Cloud API (`/health` + `/api/v1/feed/status`).
   - Iniciar `python scripts/cloud_publisher.py` apontando para a URL cloud em modo loop contínuo durante o pregão e validar o primeiro ciclo no dashboard publicado.
