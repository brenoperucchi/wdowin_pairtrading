# Brief para o Conselho de Administração — Magic Walls (`@magicwallsb3`)

## Resumo da Ideia (`founder/idea.md`)
- **Negócio:** Magic Walls (`@magicwallsb3` · `app.magicwalls.com.br`)
- **O que é:** Terminal web SaaS em tempo real para day traders de Mini-Índice (WIN) e Mini-Dólar (WDO) na B3, combinando mapa diário de exposição Gamma (GEX: Call Wall, Put Wall, MidWalls, FlipWall e Ímã GEX calculados a partir dos dados oficiais da B3), Canal Gauss e o subpainel Fluxo Smart Money com marcação visual de divergências em M1 e M5, em visualização dupla ou individual direto no navegador (desktop e mobile, sem instalar programas nem conectar corretora).
- **Público-alvo:** Day traders pessoa física no Brasil que operam Mini-Índice (WIN) e Mini-Dólar (WDO) na B3.
- **Oferta e preço:** Assinatura mensal recorrente de acesso ao terminal web, começando por um teste gratuito de 15 dias (cadastro de nome, e-mail e WhatsApp com acesso imediato; opcionalmente controle de convite/lista de espera e Cloudflare Turnstile). O backend já suporta níveis `trial`, `core`, `pro`, `quant` (licença MT5) e `admin`, mas **o preço comercial e o formato de planos ainda estão em aberto** (hipótese inicial em teste: **R$ 197/mês** após o trial de 15 dias).
- **Canais e operação:** 100% online no Brasil. Aquisição inicial orgânica (`@magicwallsb3`, Reels, YouTube, WhatsApp e landing page com trial de 15 dias) + verba inicial baixa de marketing (até **R$ 2.000/mês**).
- **Infraestrutura e restrições:** O software já está desenvolvido (stack: Cloudflare Pages + FastAPI no Railway/Fly.io + Supabase PostgreSQL + Upstash Redis + produtor push em Windows/MT5). Fase 1 (0–40 clientes) roda em PC local com nobreak + 4G/5G failover; Fase 2 (40+ clientes) migra o produtor primário para VPS Windows dedicada com o PC local em hot standby. Possui sistema anti-rateio em 4 camadas (sessão única, detector de abuso, watermark forense e licença MT5).

## Fatos Adicionais do Produto e Estado Atual
1. **O que o visitante vê na página de entrada (`SaasWelcomePortal`):**
   - Demonstração interativa dos regimes de Gamma positivo (acima da FlipWall, defesa nas extremidades) e Gamma negativo (abaixo da FlipWall, expansão direcional).
   - 3 prints reais de pregões recentes (novembro de 2026) mostrando WIN, WDO e visão dupla com marcações de divergência.
   - Bloco de estudo histórico interno de 30 pregões (`07/10 a 19/11/2026`, 122 sinais em WIN e 122 em WDO, exibidos como estatística educacional de comportamento das marcações).
   - FAQ explicando que os níveis do dia são liberados conforme a B3 publica os dados oficiais do pregão anterior, que não exige ProfitChart nem integração com corretora, e que está enquadrado na Resolução CVM nº 20/2021 (software analítico/educacional, sem recomendação de compra/venda e sem execução automática no terminal web).
2. **O que ainda NÃO foi validado ou decidido:**
   - Preço ótimo mensal e se vale mais lançar com plano único simples ou escada `Core / Pro / Quant (MT5)`.
   - Mapeamento formal de concorrentes e substitutos no Brasil (ex.: plataformas como ProfitChart, indicadores de fluxo/GEX locais, salas e planilhas/bots).
   - Custo real de aquisição de clientes (CAC), taxa de conversão de trial de 15 dias para pagante, retenção/churn mensal e unidade econômica completa (`unit_economics`).
   - Tamanho endereçável real do nicho disposto a pagar assinatura recorrente mensal por GEX + Fluxo para WIN/WDO.
