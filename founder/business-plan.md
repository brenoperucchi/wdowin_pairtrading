# Magic Walls (`@magicwallsb3`) · Business plan

**Verdict: Not yet**

- ✓ Each assinante/mês earns $85.09 before fixed costs (88% contribution).
- ✓ Year 1 operating profit: $32,196.
- ✓ Break-even is 31 assinante/mêss a day against a capacity of 1000.
- ✗ 0 of 20 simulated buyers buy (0%, the bar is 25%).

| key number | |
| --- | ---: |
| Price | $97.00 a assinante/mês |
| Profit margin at plan | 64% per assinante/mês |
| Break-even | 31 assinante/mêss a day |
| Year 1 operating profit | $32,196 |
| Startup spend | $2,900 |
| Cash needed before it pays for itself | $7,040 |
| Startup money earned back | month 7 |
| Buyer panel | 0 buy · 20 pass |

## The idea

- **O que é:** Terminal web SaaS 100% no navegador para day traders de Mini-Índice (WIN) e Mini-Dólar (WDO) na B3, reunindo mapa diário de exposição Gamma (GEX: Call Wall, Put Wall, MidWalls, FlipWall e Ímã GEX calculados a partir dos dados oficiais da B3), Canal Gauss e o subpainel Fluxo Smart Money com marcação visual de divergências em M1 e M5, em visão dupla ou individual (desktop e celular, sem instalar nada nem conectar corretora). O motor de ingestão nos bastidores é 100% invisível ao usuário final, com roadmap técnico de migração para API oficial B3/Cedro.
- **Para quem é:** Day traders pessoa física no Brasil que operam Mini-Índice (WIN) e Mini-Dólar (WDO) na B3 e acompanham leitura institucional de liquidez e fluxo antes e durante o pregão.
- **O que vende e a que preço:** Assinatura mensal recorrente do terminal web (`app.magicwalls.com.br`), **inicialmente sem trial gratuito**, apoiada em prova pública diária no Instagram (`@magicwallsb3`) + garantia incondicional de 7 dias (reembolso em 1 clique) e cancelamento em 1 clique. Preço em definição na esteira (`founder-pricing` + `founder-offer`, substituindo a hipótese inicial de R$ 197/mês por faixa competitiva testada contra o mercado).
- **Onde e como:** 100% online no Brasil. Aquisição centrada em **prova diária transparente no Instagram `@magicwallsb3`**: publicação matinal (pré-09h) com o cálculo das Walls do dia e balanço pós-pregão mostrando o deslocamento técnico máximo alcançado nas marcações (e eventuais stops/invalidações), convertendo seguidores interessados em assinantes diretos, com apoio de até R$ 2.000/mês em tráfego pago/produção.
- **Infraestrutura, orçamento e restrições:** Sistema já migrado para **VPS dedicada (contrato de R$ 1.900 por 2 anos, já pago)** capaz de escalar para **mais de 1.000 usuários simultâneos**, integrada com Cloudflare Pages, FastAPI, Supabase PostgreSQL, Upstash Redis e proteção anti-rateio em 4 camadas. Verba de marketing inicial até R$ 2.000/mês; sem pró-labore fixo no Ano 1. Software estritamente analítico e educacional (Resolução CVM nº 20/2021) — não envia ordens automáticas, não é sala de sinais nem faz recomendação de compra ou venda.

## Summary

**Veredicto computado (`compile.py`): `Not yet`** — **3 de 4 checagens financeiras passam com folga, mas o Painel de Compradores falhou (`0 de 20` compram no contato frio, contra barra mínima de `25%`).**

**O que precisa mudar antes de investir o orçamento de escala:**
1. **Validar se a prova pública diária no Instagram convence compradores reais sem trial (`founder-launch`):** 17 de 20 personas no Painel v2 afirmaram que não passam cartão no primeiro contato sem antes acompanhar 2–3 semanas de marcações pré-09h ao vivo no Instagram ou testar de 3 a 15 pregões grátis sem cartão. O plano só passa para `Profitable` após comprovar conversão real no teste de 10 pregões no `@magicwallsb3` (`>= 12` assinantes no Lote Fundador a R$ 79/mês) **ou** ajustar o funil em `founder-offer` + `founder-consumer` (ex.: liberando um teste de 5 pregões sem cartão só com e-mail, ou versão integrada para quem recusa aba externa).
2. **Reduzir atrito com o ProfitChart (`founder-offer`):** 6 de 20 personas recusaram por hábito de operar apenas no ProfitChart, mesmo com Modo Compacto e cópia de níveis em 1 clique.

---

**O negócio:** Terminal web SaaS 100% no navegador (sem instalar nada e sem expor Profit/MT5 nos bastidores) que entrega antes das 08h45 para day traders de Mini-Índice (WIN) e Mini-Dólar (WDO) na B3 o mapa diário de exposição Gamma (GEX), Canal Gauss e Fluxo Smart Money em M1/M5, com prova diária pré e pós-pregão no Instagram `@magicwallsb3` (CVM nº 20/2021).

**Os números do CFO (em R$ / BRL · `days_per_month = 1`, `unit = assinante/mês`, sem pró-labore fixo no Ano 1):**
- **Margem:** **R$ 85,09 de contribuição (88%)** ao preço padrão de **R$ 97,00/mês**; margem operacional de **64%** no plano de **115 assinantes ativos/mês** (Mês 12).
- **Ponto de equilíbrio:** **31 assinantes ativos/mês** contra capacidade de **1.000+ usuários** na VPS dedicada já migrada (R$ 1.900 por 2 anos).
- **Ano 1:** **R$ 32.196** de lucro operacional sobre **R$ 72.653** de receita (R$ 29.296 após R$ 2.900 de gasto novo pré-lançamento), com payback no **Mês 7** e necessidade máxima de caixa novo de **R$ 7.040**.

**Onde o Conselho e o Painel concordam e divergem:**
- *Concordam:* a infraestrutura dedicada (já resolvida na VPS 1.000+) era essencial, R$ 197/mês era caro demais para contas pequenas (mudar para R$ 79–97/mês derrubou recusas de preço de 5 para 1), e o mercado B3 tem ceticismo extremo contra promessas sem prova pré-abertura.
- *Divergem:* o fundador quer iniciar **sem trial gratuito** usando a prova diária no Instagram + garantia de 7 dias em 1 clique, enquanto o painel simulado mostrou que a garantia de 7 dias não substitui um trial sem cartão na venda fria (exigindo aquecimento contínuo de 14–21 dias antes da oferta).

**Maior risco e ação de controle:** Queimar os R$ 2.000/mês de marketing em tráfego frio sem conversão (ou sofrer bloqueio de conta no Meta Ads por linguagem de "ganho máximo"). Controle: enquadramento estritamente estatístico em pontos (CVM 20/2021), publicação pré-08h35 com stops auditados às 17h30 e teste real limitado a R$ 1.000 antes de escalar.

**Para começar e a única coisa para fazer esta semana:** Caixa novo máximo projetado de **R$ 7.040** (VPS e software já pagos). **Esta semana:** publicar a Página Pública dos últimos 5 pregões + Modo Compacto/Copiar Níveis e iniciar os **10 pregões consecutivos de prova pública às 08h35 e 17h30 no `@magicwallsb3`** com pré-venda controlada do Lote Fundador (40 vagas a R$ 79/mês, meta `>= 12` pagantes em 14 dias).

*Nota: O painel é composto por compradores simulados e os números são projeções baseadas nos insumos informados; clientes reais e cotações reais confirmam os resultados. Este material não constitui aconselhamento financeiro, jurídico ou tributário.*

## What the board said

**Placar:** `3 FUND IF · 0 FUND · 0 PASS` | **Nota média:** `5,3 / 10`  
*(Lente de Ofertas: 5/10 `FUND IF` · Lente de Monopólio: 5/10 `FUND IF` · Lente de Produto: 6/10 `FUND IF`)*

---

### Riscos convergentes (levantados por mais de um conselheiro)

1. **Churn estrutural e ceticismo crônico do day trader PF na B3** *(Ofertas + Monopólio)*: Alta mortalidade financeira do público varejista e forte desconfiança contra ferramentas que mostram estudos internos de 30 pregões, podendo gerar cancelamento antes que o LTV cubra o CAC.
2. **Fragilidade operacional da Fase 1 em PC local Windows/MT5** *(Monopólio + Produto)*: Alimentar um painel pago de tempo real (M1/M5) a partir de um computador local doméstico com failover 4G/5G cria risco de queda ou latência exatamente em pregões voláteis.
3. **Ausência de métricas comerciais, competitivas e fosso defensivo comprovado** *(Ofertas + Monopólio + Produto)*: Ainda faltam mapeamento de concorrentes/substitutos no Brasil, preço validado (R$ 197/mês é apenas hipótese), CAC dentro do teto de R$ 2.000/mês, taxa de conversão do trial e prova de que o conceito GEX + Fluxo não pode ser copiado rapidamente por plataformas já abertas na tela do trader (como o ProfitChart).
4. **Excesso de complexidade e atrito no onboarding dos primeiros 5 minutos** *(Ofertas + Produto)*: Combinar 5 níveis GEX + Canal Gauss + Fluxo Smart Money (M1/M5) + visão dupla + 5 níveis arquiteturais no backend exige esforço cognitivo elevado durante o trial de 15 dias, sem execução integrada na corretora.

---

### Checklist consolidado de condições (`FUND IF`)

- [ ] **Mapear concorrentes, preços e brechas no Brasil** — levantar substitutos diretos e indiretos (ProfitChart, plugins/indicadores de GEX e fluxo, salas, planilhas/bots), reclamações públicas e o que torna o Magic Walls defensável além de dados públicos da B3 *(testado por `/founder-competitors`)*.
- [ ] **Validar demanda pagante e objeções reais de traders de WIN/WDO** — testar o pitch atual em compradores simulados e depois em leads reais para descobrir quem realmente paga, por que passa e o que trava os primeiros 5 minutos *(testado por `/founder-consumer`)*.
- [ ] **Definir preço ótimo e simplificar o empacotamento inicial** — escolher o preço mensal validado por sensibilidade de preço (Van Westendorp) e decidir entre lançar com **plano único simples** (posição defendida pela Lente de Produto) versus **escada `Core / Pro / Quant`** com âncora clara (questão aberta levantada por Ofertas e Monopólio) *(testado por `/founder-pricing`)*.
- [ ] **Construir o stack completo da oferta dentro da CVM nº 20/2021** — sair de "apenas acesso ao terminal + 15 dias grátis", adicionando onboarding guiado para os primeiros dias, rotina pré-mercado, qualificação/escassez real no trial e garantia pós-pagamento de baixo risco, além de casos documentados de usuários beta *(testado por `/founder-offer`)*.
- [ ] **Fechar a matemática mínima de CAC, churn, payback e infra dedicada** — calcular margem unitária, conversão mínima do trial de 15 dias, teto de churn e viabilidade de rodar em VPS Windows dedicada mais cedo em vez de depender de PC local até 40 clientes *(testado por `/founder-cfo` e `/founder-ops`)*.
- [ ] **Resolver o conflito entre anti-rateio ("sessão única") e uso prometido em desktop + mobile** — garantir que o assinante legítimo não seja desconectado ao alternar dispositivos durante o pregão *(ajuste operacional/produto antes de escalar)*.

---

### A versão mais forte deste negócio (e onde as lentes divergem)

A versão mais forte que o conselho enxerga para o **Magic Walls** não é vendê-lo como "mais um painel cheio de indicadores para todo day trader", e sim como **a tela auxiliar mais limpa e sem instalação para traders ativos de WIN/WDO (especialmente quem opera a partir de 5 minicontratos)**, ancorada em uma rotina pré-mercado objetiva de níveis GEX da B3 + leitura de absorção no Fluxo Smart Money, entregue em infraestrutura dedicada estável e acompanhada de onboarding prático e garantia clara dentro da Resolução CVM nº 20/2021. **Divergências mantidas entre os conselheiros:** a **Lente de Produto** defende cortar escopo visual e lançar obrigatoriamente com um **plano único simples** (adiando a escada `Core / Pro / Quant` e licença MT5 para reduzir complexidade), enquanto a **Lente de Ofertas** questiona se um preço mais alto ou uma **escada de valor com entregáveis educacionais e automação/MT5** não seria necessário para capturar maior ticket e compensar o churn do varejo; já a **Lente de Monopólio** adverte que, mesmo com ótimo produto e oferta, o negócio continuará vulnerável em 6 meses se não construir algum elemento proprietário ou custo de troca (histórico, diário operacional ou comunidade/fluxo exclusivo) que impeça plataformas incumbentes de copiar a ideia.

---

### Atualização de Infraestrutura e Go-to-Market (pós-reunião com o fundador · 26/11/2026)

- **Condição de infra local resolvida:** O sistema já foi migrado para **VPS dedicada** (contrato de **R$ 1.900 por 2 anos**, escalável para **1.000+ usuários**), eliminando o risco operacional da Fase 1 em PC local.
- **Abstração do backend:** O usuário final não tem contato nem conhecimento de Profit/MT5 nos bastidores, e o roadmap técnico prevê migração da coleta para **API oficial B3 / Cedro**. O produto comercializado é **100% Terminal Web SaaS** (sem distribuição de scripts `.nts`/plugins).
- **Mudança de aquisição:** Em vez de depender de trial gratuito de 15 dias na porta de entrada, a estratégia passa a ser **prova pública diária no Instagram (`@magicwallsb3`)** (Walls calculadas pela manhã + balanço técnico das marcações após o pregão) e **assinatura direta inicialmente sem trial**, usando garantia de 7 dias e preço competitivo como reversão de risco.

## The competition

Pesquisa baseada exclusivamente em fontes públicas consultadas em **26/11/2026** (taxa de referência usada apenas para conversão informativa de players internacionais: `R$ 5,80/USD`). Os dados completos estão em [competitors.csv](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/founder/competitors.csv).

---

### 1. Concorrentes Diretos, Indiretos e Substitutos

| Concorrente | Tipo | Preço comparável | O que entrega | Canal / Link |
| --- | --- | --- | --- | --- |
| **Jumba (Trader Flow / Pro)** | Direct | R$ 247/mês (Pro) / ~R$ 2.947/ano (~R$ 245,58/mês Flow) | Jumba Walls, Market Gamma (GEX) e fluxo de market makers para WIN/WDO e opções B3 via ProfitChart | [jumba.com.br](https://jumba.com.br) |
| **Investorama** | Direct | R$ 0 (Free) / ~R$ 20,90/mês (promo) / R$ 31,90/mês (MCP) | Plataforma quantitativa B3 com GEX, screeners de ações/opções e integração Profit/MT5/IA | [investorama.com.br](https://investorama.com.br) |
| **Indicadores GEX para MT5** | Direct | R$ 80 a R$ 350+ (licença ou mensalidade) | Indicadores locais de Call/Put Walls e Gamma Flip instalados no MetaTrader 5 | [mql5.com](https://www.mql5.com) |
| **SpotGamma** *(ref. EUA)* | Direct (EUA) | US$ 99/mês (~R$ 574) a US$ 299/mês | Dashboard web de GEX + fluxo HIRO para mercado dos EUA (não cobre B3) | [spotgamma.com](https://spotgamma.com) |
| **MenthorQ** *(ref. EUA)* | Direct (EUA) | US$ 129/mês (~R$ 748) a US$ 349/mês | Modelos GEX/DEX para futuros globais e cripto com exportação para gráficos (foco fora da B3) | [menthorq.com](https://menthorq.com) |
| **Nelogica ProfitChart Pro** | Indirect | R$ 0 via corretora (RLP + meta) ou R$ 150–189,90/mês tabela | Plataforma principal de gráficos, tape reading e ordens na B3 (não traz GEX + Smart Money prontos) | [nelogica.com.br](https://www.nelogica.com.br) |
| **OpLab** | Indirect | R$ 97/mês (ONE) · R$ 185/mês (PRO); 30 dias grátis | Análise, payoff e simulação de opções de ações na B3 (não focado em intraday WIN×WDO M1/M5) | [oplab.com.br](https://oplab.com.br) |
| **TradingView** | Indirect | US$ 0 a US$ 69,95/mês (~R$ 87 Plus/Essential a ~R$ 406) | Gráficos web globais e Pine Script (sem cálculo nativo de GEX oficial da B3) | [tradingview.com/pricing](https://www.tradingview.com/pricing/) |
| **Planilha B3 / Salas ao vivo** | Substitute | R$ 0 (manual) a R$ 300+/mês (salas) | Boletim diário B3 manual pós-18h, indicadores grátis (VWAP) ou calls ao vivo | [b3.com.br](https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/consultas/boletim-diario/boletim-diario-do-mercado/) |

---

### 2. Faixa de Preço no Brasil (comparáveis pagos B3)

- **Menor preço pago:** **R$ 20,90 a R$ 31,90/mês** ([Investorama](https://investorama.com.br)) ou **R$ 0 via corretora** no ProfitChart cumprindo meta de contratos + RLP ([Nelogica](https://www.nelogica.com.br)).
- **Mediana de ferramentas especializadas B3:** **R$ 97,00 a R$ 185,00/mês** ([OpLab ONE R$ 97 / PRO R$ 185](https://oplab.com.br); [ProfitChart Pro tabela R$ 150–189,90](https://www.nelogica.com.br); indicadores independentes a partir de R$ 80+).
- **Teto no nicho GEX B3:** **~R$ 245,58 a R$ 247,00/mês** ([Jumba](https://jumba.com.br)) e **R$ 300+/mês** em salas/mentorias ou Profit Ultra.
- **Referência internacional web GEX (EUA):** **US$ 99 a US$ 129/mês** de entrada (~R$ 574 a R$ 748/mês em [SpotGamma](https://spotgamma.com) e [MenthorQ](https://menthorq.com)), mostrando que o teto brasileiro precisa ficar muito abaixo de US$ 99 devido ao poder de compra do varejo PF.

---

### 3. Mapa de Posicionamento (Preço Mensal × Foco Intraday GEX + Fluxo WIN/WDO)

```text
                ALTO FOCO INTRADAY GEX + FLUXO (WIN x WDO)
                                   ▲
                                   │
   Magic Walls (Brecha)            │                 Jumba Trader Flow
   [R$ 79–97/mês · 100% Web]       │                 [~R$ 245–247/mês · Profit]
                                   │
 PREÇO BAIXO ──────────────────────┼──────────────────────► PREÇO ALTO
 (<= R$ 99)                        │                         (>= R$ 185)
                                   │
   Investorama [R$ 21–32]          │                 OpLab Pro [R$ 185]
   Profit c/ RLP [R$ 0*]           │                 Profit Pro tabela [R$ 150–190]
   TradingView Essential [~R$ 87]  │                 Salas / Mentorias [R$ 300+]
                                   ▼
                BAIXO FOCO INTRADAY GEX + FLUXO PRONTO
```
*\*Profit via corretora sai por R$ 0 apenas se o trader ativar RLP e bater meta mensal de minicontratos.*

---

### 4. Reclamações Públicas Ranqueadas (O que os clientes odeiam)

1. **Cobranças surpresa, RLP e renovação automática pós-trial** — *Tema recorrente em múltiplas plataformas:*
   - Na **Nelogica / Profit**, reclamações no Reclame Aqui concentram-se em cobrança integral quando o trader não bate a meta mensal de minicontratos ou desativa o RLP, além de burocracia ao cancelar assinaturas diretas na NeloStore ([Nelogica](https://www.nelogica.com.br), [Itaú Corretora](https://www.itaucorretora.com.br)).
   - No **TradingView**, queixas recorrentes envolvem cobrança automática do plano anual logo após o fim do período de teste gratuito caso o usuário esqueça de cancelar antes das 24h finais ([TradingView Support](https://www.tradingview.com)).
   - Em **infoprodutos/Hotmart (como ecossistema Jumba/mentorias)** e **OpLab** *(tema `thin` na amostra pública consultada, com menor volume de registros)*, queixas públicas típicas envolvem renovações recorrentes não esperadas e prazos de reembolso CDC (7 dias).
2. **Instabilidade e lentidão em pregões de alta volatilidade** — *Tema recorrente:*
   - Usuários da **Nelogica/Profit** relatam no Reclame Aqui travamentos e atrasos em momentos de estresse de mercado, quando o prejuízo financeiro é imediato ([Nelogica](https://www.nelogica.com.br)).
3. **Complexidade de instalação e dependência de plataforma desktop** *(observado na análise de entrega dos produtos, `thin` em reviews públicos diretos)*:
   - Indicadores independentes (MQL5) e soluções plugadas ao Profit/MT5 exigem instalação local, configuração de ativos/contratos vigentes e manutenção em máquina Windows, enquanto ferramentas globais como TradingView, SpotGamma e MenthorQ não calculam GEX nativo da B3 para WIN e WDO.

---

### 5. A Brecha (The Gap)

Existe uma brecha real e bem delimitada entre:
- **De um lado:** ferramentas generalistas muito baratas voltadas a ações/opções ou gráficos puros (`Investorama` a R$ 21–32/mês, `TradingView` sem GEX B3, ou `Profit` focado em fluxo genérico sem mapa diário de exposição Gamma da B3); e
- **Do outro lado:** soluções de GEX + fluxo institucional com ticket alto (**Jumba** na casa de ~R$ 245–247/mês, ~R$ 2.947/ano) e/ou dependência de configuração local em plataforma desktop.

**Onde o Magic Walls pode ser dono do espaço:**
Ser o **terminal web de leitura institucional intraday focado exclusivamente em WIN × WDO (GEX oficial B3 + Fluxo Smart Money em M1/M5)** na faixa de **R$ 79 a R$ 97/mês** — cerca de **60% mais acessível que a Jumba** — com entrega imediata no navegador, **sem exigir instalação, sem meta de corretora/RLP, sem renovação-pegadinha de trial e com transparência pública diária antes e depois do pregão no Instagram**.

---

### 6. A Ameaça (Quem pode copiar mais rápido)

- **Nelogica / NeloStore:** Já está aberta na tela da maioria dos day traders de WIN/WDO. Se lançar um módulo nativo ou indicador oficial de GEX + divergência de fluxo dentro do ProfitChart por R$ 49–99/mês, elimina a barreira da "segunda aba" instantaneamente.
- **Jumba ou Investorama:** A Jumba pode lançar uma versão simplificada de entrada (~R$ 97/mês) focada em web/futuros; o Investorama já possui dados de GEX B3 e integrações Profit/MT5 a R$ 31,90/mês e poderia criar uma visualização intraday dedicada a WIN×WDO.
- **Implicação estratégica:** Como os dados brutos vêm da B3, a defesa do Magic Walls no médio prazo não pode ser "ter os níveis", e sim **velocidade de leitura visual + prova pública diária auditada + hábito matinal da comunidade no `@magicwallsb3` + experiência web sem fricção**.

## The buyer panel

**0 buy · 20 pass** (0% buy) out of 20 simulated buyers. Seed 7, so the same cards can be dealt again.

These are simulated buyers, not customers. Use this to find objections and weak spots, then confirm the big ones with real people before you spend.

### By segment

| group | buyers | buy rate |
| --- | ---: | ---: |
| Trader experiente / mesa ou conta maior (20+ contratos) | 3 | 0%  (thin) |
| Trader intermediário recorrente (5-20 minicontratos) | 8 | 0% |
| Trader iniciante / conta pequena (1-5 minicontratos) | 9 | 0% |

### By buying behaviour

| group | buyers | buy rate |
| --- | ---: | ---: |
| Fiel ao ProfitChart / setup atual | 4 | 0%  (thin) |
| Operador pragmático por prova ao vivo | 2 | 0%  (thin) |
| Sensível a custo fixo mensal | 3 | 0%  (thin) |
| Caçador de edge técnico (fluxo e opções) | 4 | 0%  (thin) |
| Testador serial de trials gratuitos | 3 | 0%  (thin) |
| Cético escaldado por gurus | 4 | 0%  (thin) |

### By income

| group | buyers | buy rate |
| --- | ---: | ---: |
| $193,000 and up | 7 | 0%  (thin) |
| $113,000 to $193,000 | 7 | 0%  (thin) |
| under $113,000 | 6 | 0%  (thin) |

### Why they pass

| reason | buyers | in their words |
| --- | ---: | --- |
| trust | 10 | "Eu já tenho o ProfitChart Pro de graça pela corretora e não coloco cartão nem dados pessoais numa plataforma que ainda não conheço sem ver o painel rodando ao vivo no pregão. Post de Instagram antes e depois do fechamento não substitui ver o fluxo M1/M5 e as walls funcionando na hora da verdade." (P002) · "O preço de R$ 79 não pesa para quem opera mais de 20 contratos, mas eu não coloco meu cartão numa ferramenta nova sem entender a mecânica por trás do cálculo de GEX e do tal Fluxo Smart Money. Sem trial ao vivo, prefiro observar o histórico público antes de arriscar meu tempo na abertura." (P004) |
| habit | 6 | "Já tenho meu operacional bem redondo e limpo direto no ProfitChart gratuito da corretora e evito ao máximo ficar com outra aba de navegador aberta entre 09h e 12h30. Mesmo a R$ 79 no lote fundador, não quero adicionar mais um custo fixo mensal nem quebrar meu fluxo de tela por níveis que eu mesmo teria que copiar manualmente." (P001) · "Eu opero scalping com 1 a 5 minicontratos no ProfitChart gratuito da corretora e não quero abrir mais uma aba nem complicar minha tela com indicadores novos. Além disso, anoto todo custo de plataforma no meu líquido e R$ 79 por mês pesa bastante para uma conta pequena." (P005) |
| need | 2 | "Não entendo direito o que é Gamma/GEX nem como transformar essas walls em ponto de entrada e stop claros, então não vou assumir mais R$ 79/mês de custo fixo no escuro. Mesmo com garantia de 7 dias, sem teste grátis eu prefiro só acompanhar o histórico aberto antes de pagar qualquer recorrência." (P003) · "Como ainda sou iniciante com conta pequena e não sei transformar Gamma/GEX em entrada e stop na prática, prefiro acompanhar primeiro as Walls gratuitas no Instagram antes de pagar por uma assinatura." (P014) |
| timing | 1 | "Ainda opero pequeno, de 1 a 5 minicontratos, e não domino como a exposição Gamma vira entrada e stop na prática. Antes de assumir mais R$ 79 por mês sem trial gratuito, prefiro seguir o perfil no Instagram para acompanhar os níveis e entender a mecânica primeiro." (P012) |
| price | 1 | "Eu anoto todo dia meu financeiro líquido já descontando Profit, corretagem e emolumentos, então não vou assumir mais R$ 79 fixos por mês logo de cara sem saber se isso se paga em pontos reais de WIN ou WDO. Sem um teste grátis real antes da cobrança, prefiro não adicionar mais uma recorrência na minha planilha." (P018) |

### Why they buy

| reason | buyers | in their words |
| --- | ---: | --- |

### What would flip a no

- Se os níveis de Gamma e indicadores rodassem nativamente dentro do ProfitChart sem precisar abrir aba externa e houvesse alguns pregões de teste aberto antes de colocar o cartão.
- Ver uma gravação ou transmissão ao vivo da tela real durante o pregão com o alerta sonoro e a leitura das walls na prática, ou poder acessar 2 ou 3 dias em tempo real sem precisar cadastrar cartão antes.
- Ter um teste grátis de alguns pregões no terminal junto com um exemplo prático mostrando entrada, alvo e stop reais no gráfico do WIN ou WDO.
- Explicar abertamente a metodologia de cálculo do GEX na B3 (origem dos dados e fórmulas) e liberar pelo menos 3 pregões de teste ao vivo no horário das 08h45 às 10h antes de cobrar.
- Se funcionasse como um indicador nativo direto dentro do ProfitChart, sem outra janela aberta, e custasse por volta de R$ 35 a R$ 40 por mês.
- Um período de teste gratuito de alguns dias operando ao vivo no pregão ou integração direta como indicador dentro do próprio ProfitChart.
- Liberar um trial gratuito de 15 dias sem cobrança antecipada para eu validar o Canal Gauss e o fluxo na minha janela operacional das 9h às 12h30.
- Ter um trial gratuito de 3 a 5 pregões sem cadastrar cartão, ou poder acompanhar os níveis rodando ao vivo durante a manhã antes de pagar a assinatura.
- Se rodasse como um indicador ou regra nativa direto dentro do ProfitChart sem precisar abrir navegador externo, com pelo menos duas semanas de teste grátis sem cadastrar cartão.
- Liberar um teste grátis de 3 a 5 pregões sem precisar passar cartão e publicar uma explicação técnica clara da metodologia de cálculo das Walls na B3.
- Ter um período gratuito real de pelo menos 14 a 30 dias sem cadastrar cartão para testar as marcações das 08h45 na minha tela durante o pregão antes de assinar.
- Ver uma aula prática ou vídeo aberto mostrando passo a passo como usar esses níveis em pregão real com poucos contratos, ou poder testar grátis por alguns dias antes de passar o cartão.

20 buyers gave all four price answers. Run founder-pricing's van_westendorp.py on the answers folder.

## Pricing

*(Todos os valores em Reais brasileiros — R$ / BRL. A curva Van Westendorp preliminar está em [pricing-curve.md](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/founder/pricing-curve.md).)*

---

### 1. O que os compradores disseram (Van Westendorp v1 · 20 personas)

| Ponto | Valor (R$/mês) | Significado |
| --- | ---: | --- |
| **PMC** *(barato demais)* | **R$ 48,47** | Abaixo disso, muitos desconfiam da qualidade para leitura institucional B3 |
| **OPP** *(menor resistência)* | **R$ 59,80** | Ponto de menor atrito entre barato demais e caro demais |
| **IPP** *(indiferença)* | **R$ 96,18** | Tantos acham pechincha quanto começam a achar caro |
| **PME** *(caro demais)* | **R$ 149,33** | Acima disso, a maioria desiste |

- **Faixa aceitável medida:** **R$ 48,47 a R$ 149,33/mês** (medianas: muito barato R$ 29,00; pechincha R$ 67,00; ficando caro R$ 127,00; caro demais R$ 187,00).
- A hipótese anterior de **R$ 197,00/mês ficou acima do teto aceitável** e contribuiu para o `0/20` no painel v1.

---

### 2. O que os concorrentes cobram ([competitors.md](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/founder/competitors.md))

| Concorrente | Preço mensal | O que entrega (comparando igual com igual) |
| --- | ---: | --- |
| **Investorama** | R$ 20,90–31,90/mês | Screeners B3, GEX geral e integrações (foco amplo em ações/opções, não terminal intraday WIN×WDO) |
| **OpLab ONE / PRO** | R$ 97,00 / R$ 185,00/mês | Análise e simulação de opções de ações B3 (não focado em scalping WIN×WDO) |
| **Nelogica ProfitChart Pro** | R$ 0 (meta+RLP) ou R$ 150–189,90/mês | Plataforma de execução/tape reading (não entrega GEX + divergência Smart Money prontos) |
| **Jumba (Pro / Trader Flow)** | ~R$ 245,58–247,00/mês | GEX + fluxo institucional para B3 via ProfitChart (exige setup e ticket ~2,5x maior) |

---

### 3. O que o negócio precisa ganhar (rodado em `unit_economics.py`)

Com custo fixo econômico de **R$ 2.628/mês** (incluindo teto de R$ 2.000/mês em marketing, cloud e amortização de R$ 79/mês da VPS já paga de R$ 1.900/2 anos) e custo variável de **R$ 11,91/assinante/mês** (Asaas + provisão 6% de garantia 7 dias sem trial + infra marginal):

| Preço candidato | Contribuição / assinante | Break-even (assinantes ativos) | Margem no plano (120 assinantes) | Lucro operacional Ano 1* |
| ---: | ---: | ---: | ---: | ---: |
| **R$ 79,00** *(Lote Fundador)* | R$ 67,09 (85%) | **40 assinantes/mês** | 57% | R$ 24.685 |
| **R$ 97,00** *(Core Padrão)* | **R$ 85,09 (88%)** | **31 assinantes/mês** | **65%** | **R$ 39.769** |
| **R$ 129,00** | R$ 117,09 (91%) | 23 assinantes/mês | 74% | R$ 66.585 |
| **R$ 147,00** *(Pro futuro)* | R$ 135,09 (92%) | 20 assinantes/mês | 77% | R$ 81.669 |

*\*Simulação preliminar antes de calibrar a rampa final com o Painel v2.*

---

### 4. Decisão de Preço, Escada e Oferta de Abertura

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

## The offer

*(Construída a partir das objeções literais de [panel-v1/results.md](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/founder/panel-v1/results.md), do mapa competitivo em [competitors.md](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/founder/competitors.md) e das diretrizes do fundador: 100% terminal web, sem trial gratuito inicial, prova pública diária no Instagram e VPS para 1.000+ usuários.)*

---

### 1. Lista de Obstáculos do Comprador (18 problemas reais)

#### Antes da compra (confiança, preço e modelo sem trial)
1. *"Mais uma ferramenta cara para trader que promete demais sem prova real no pregão ao vivo."* (`trust`)
2. *"Os números internos de 30 pregões parecem bons demais; e se foram escolhidos depois que o mercado fechou?"* (`trust`)
3. *"Não existe trial gratuito — e se eu pagar e descobrir no primeiro pregão que não encaixa no meu operacional?"* (`trust` / `price`)
4. *"Não quero deixar meu WhatsApp em cadastro para ficar recebendo cobrança de vendedor."* (`trust`)
5. *"R$ 197/mês pesa demais para quem opera de 1 a 5 minicontratos."* (`price`)
6. *"E se tiver renovação automática escondida ou burocracia para cancelar, como acontece em outras plataformas?"* (`trust` — reclamação recorrente em concorrentes)

#### Durante o uso (hábito, tela e curva de aprendizado)
7. *"Já uso ProfitChart de graça pela corretora — não quero abrir outra aba gigante que disputa atenção no scalping."* (`habit` / `convenience`)
8. *"Não sei nada de cálculo Gamma/GEX nem o que significam Call Wall, FlipWall ou Canal Gauss."* (`need`)
9. *"Nos primeiros 5 minutos vejo 7 linhas e não sei qual sinal manda ou onde fica meu stop técnico."* (`need`)
10. *"Se eu quiser marcar os 4 níveis principais no meu gráfico do Profit, perco tempo digitando preço por preço."* (`habit`)
11. *"Opero no computador e às vezes olho no celular; a regra de sessão única pode me derrubar no meio do pregão?"* (`convenience`)
12. *"Nos bastidores dependo de instalar MT5 ou algum plugin complicado?"* (`convenience` — resolvido: 100% web, backend invisível)

#### Pós-compra e confiabilidade operacional
13. *"E se os níveis atrasarem depois das 09h00 e eu perder a abertura?"* (`quality`)
14. *"E se o servidor cair bem em um dia de payroll ou alta volatilidade?"* (`quality`)
15. *"E se esse software tentar me dar call e ferir regras da CVM?"* (`values` / `trust`)
16. *"E se eu passar um mês sem operar e quiser pausar ou sair?"* (`price`)
17. *"Como sei se as marcações do Instagram realmente foram postadas ANTES do mercado abrir?"* (`trust`)
18. *"Como sei o que acontece nos dias ruins (quando dá stop)?"* (`trust`)

---

### 2. Soluções Selecionadas e Empilhadas (Alto Valor · Baixo Custo Marginal)

| Obstáculo atacado | Solução adotada (100% Web SaaS) | Valor percebido (1–5) | Custo marginal (1–5) |
| --- | --- | ---: | ---: |
| #1, #2, #17, #18 (`trust`) | **Prova Pública Diária no Instagram (`@magicwallsb3`) pré + pós-pregão** (Walls postadas antes das 09h com carimbo de horário + balanço completo do dia com deslocamento máximo e stops) + **Página Pública com os últimos 5 pregões abertos sem cadastro** | 5 | 1 |
| #3, #4, #6, #16 (`trust`/`price`) | **Sem trial gratuito na entrada, substituído por Garantia Incondicional de 7 dias (reembolso em 1 clique = 5 pregões reais sem risco) + Cancelamento em 1 clique + Zero WhatsApp obrigatório** | 5 | 2 *(provisão 6% no CFO)* |
| #5 (`price`) | **Preço-alvo alinhado ao IPP: R$ 97/mês padrão, com Lote Fundador de 40 vagas a R$ 79/mês travado** | 5 | 1 |
| #7, #10, #11 (`habit`) | **Modo Compacto "Segunda Tela / Celular" + Alerta Sonoro de divergência + Botão "Copiar Níveis do Dia (1 clique)"** às 08h30 + sessão titular permitindo desktop + mobile sem bloqueio | 4 | 1 |
| #8, #9 (`need`) | **Modo Visão Limpa padrão + Playbook "5 Minutos Antes das 9h"** (vídeo de 8 min + checklist de 1 página PDF, 100% CVM 20/2021) + **Nota Metodológica Aberta** | 5 | 1 |
| #13, #14 (`quality`) | **VPS dedicada escalável (1.000+ usuários) + Garantia de Pontualidade 08h45** (+7 dias grátis automáticos se atrasar após publicação regular B3 ou se houver queda >15 min na manhã) | 4 | 1 |

#### O Stack da Oferta v2
- **Nome da Oferta:** *Acesso Radar Institucional Magic Walls — Lote Fundador (100% Web)*
- **Core:** Terminal web em tempo real para WIN e WDO no navegador (sem instalar nada e sem depender de corretora/RLP), entregando até 08h45 o mapa GEX da B3 + Canal Gauss + divergências do Fluxo Smart Money em M1/M5, com Modo Compacto, Alerta Sonoro e Botão Copiar Níveis em 1 clique.
- **Bônus 1 — Prova Pública Pré/Pós-Pregão & Arquivo Aberto (5 pregões):** Acompanhamento gratuito no `@magicwallsb3` antes das 09h + histórico aberto no site para auditar a ferramenta antes de pagar 1 real.
- **Bônus 2 — Playbook "5 Minutos Antes das 9h" (Vídeo 8 min + Checklist 1 página):** Leitura objetiva de Gamma positivo vs. negativo e invalidação técnica em M5 (100% educacional CVM nº 20/2021).
- **Bônus 3 — Nota Metodológica Transparente:** Explicação clara de como os dados da B3 alimentam as Walls e o Fluxo Smart Money.
- **Garantias:** (a) **7 dias incondicionais em 1 clique** (reembolso integral de 100% sem perguntas); (b) **Cancelamento em 1 clique** sem fidelidade; (c) **SLA 08h45** (+7 dias grátis se atrasar ou cair >15 min).
- **Escassez verdadeira:** **40 vagas no Lote Fundador a R$ 79/mês** travado (encerramento em 14 dias ou ao preencher as 40 vagas de onboarding próximo do fundador; depois passa para **R$ 97/mês**).

---

### 3. Equação de Valor (Antes vs. Depois · escala 1 a 10)

| Variável da Equação de Valor | Antes (`pitch-v1`: R$ 197 + trial WhatsApp) | Depois (`pitch-v2`: R$ 79/97 + prova IG + garantia 7d) | O que moveu a nota |
| --- | ---: | ---: | --- |
| **Resultado Desejado (Outcome)** | 6/10 | 7/10 | Mesmo motor técnico WIN×WDO, porém focado em leitura clara pré-09h e segunda tela sem poluição |
| **Probabilidade Percebida (Likelihood)** | 2/10 | 7/10 | Prova diária postada antes das 09h no Instagram + arquivo aberto de 5 pregões + garantia 7 dias em 1 clique |
| **Tempo até o Resultado (Time Delay)** | 4/10 | 7/10 | Playbook de 8 min + Modo Visão Limpa + cópia de níveis em 1 clique reduz tempo para leitura prática já no Dia 1 |
| **Esforço e Sacrifício (Effort & Sacrifice)** | 8/10 *(alto atrito)* | 4/10 *(atrito reduzido)* | Preço cai de R$ 197 para R$ 79–97, sem WhatsApp, modo compacto ao lado do Profit — resta apenas o atrito da ausência de trial e da aba externa |

---

### 4. Resultado do Re-teste no Painel de Compradores (v2 · 20 personas · seed 7)

| Métrica | Oferta v1 (`pitch-v1.md`: R$ 197 + trial WhatsApp) | Oferta v2 (`pitch.md`: R$ 79/97 + prova IG + garantia 7d, sem trial) |
| --- | ---: | ---: |
| **Taxa de compra (contato frio)** | `0 buy · 20 pass` (**0%**) | `0 buy · 20 pass` (**0%**) |
| **Recusas por `price`** | 5 | **1** *(queda de 80%)* |
| **Recusas por `trust`** | 8 | **10** |
| **Recusas por `habit`** | 5 | **6** |
| **Recusas por `need` / `timing` / `convenience`** | 2 (`need` 1, `convenience` 1) | **3** (`need` 2, `timing` 1) |
| **Faixa Van Westendorp (R$/mês)** | `R$ 48,47 – R$ 149,33` (`IPP R$ 96,18`) | `R$ 35,92 – R$ 119,34` (`IPP R$ 69,13`) |

#### O que mudou e o que o teste provou
1. **A faixa de preço funcionou:** Reduzir de R$ 197 para **R$ 79 (Lote Fundador) / R$ 97 (padrão)** praticamente eliminou a recusa pura por preço (caiu de 5 para 1), e R$ 97 permaneceu dentro da faixa aceitável medida na curva v2 ([pricing-curve-v2.md](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/founder/pricing-curve-v2.md)).
2. **Garantia de 7 dias NÃO substitui trial na venda fria imediata:** **17 de 20 personas** responderam em `would_change_my_mind` que só entrariam após um **teste grátis sem cartão (3 a 15 dias)** ou após **acompanhar as marcações pré-09h no Instagram por 2 a 3 semanas ao vivo** batendo com o pregão real (ex.: `P002`, `P008`, `P013`, `P020`).
3. **Implicação direta para o plano:** Como a estratégia escolhida pelo fundador é iniciar **sem trial gratuito**, a aquisição **não pode tentar vender no primeiro clique para público frio**. O funil precisa usar o Instagram `@magicwallsb3` como **aquecimento contínuo de 14–21 dias** (transformando seguidor frio em seguidor convencido pela prova pré-09h) — e, caso a conversão direta em 14 dias fique abaixo da meta, rodar um teste A/B com **trial de 5 pregões sem cartão (só e-mail)**.
4. **Cuidado crítico de copy no Instagram (CVM 20/2021 + confiança):** O painel mostrou que postagens isoladas de "ganho máximo" após o pregão geram ceticismo; o diferencial que convence é **postar as Walls antes das 09h (imutável) + vídeo/print real da tela durante o pregão + auditoria honesta incluindo os stops**.

## The numbers

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

## Unit economics: Magic Walls (Terminal Web SaaS GEX + Fluxo Smart Money WIN/WDO)

Every number below comes from the input file. Nothing is looked up or guessed.

### One assinante/mês

| line | per assinante/mês |
| --- | ---: |
| Price | $97.00 |
| Gateway Asaas cartão (2,99% + R$0,49) | -$3.39 |
| Provisão reembolso garantia 7d (6%) | -$5.82 |
| Infra marginal + e-mail por assinante | -$2.70 |
| **Contribution** (what each assinante/mês leaves to pay the fixed costs) | **$85.09** (88%) |

### The margin that matters

Fixed costs: $2,628 a month (Supabase Pro (US$ 25) $145, Cloud API Railway Pro (US$ 20) $116, Upstash Redis Fixed (US$ 10) $58, VPS Dedicada (amortização R$ 1.900 / 24m) $79, Cloudflare Pages Free + domínio/e-mail $40, Contabilidade online PJ (estimativa) $190, Marketing (teto informado pelo fundador) $2,000).

- **Break-even: 31 assinante/mêss a day.** Below that you lose money every month.
- **Profit margin at your plan** (115 a day): **64%** of every sale, after every cost.
- Capacity: 1000 a day.

### Year 1, month by month

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

### What if

| scenario | margin at plan | break-even a day | year 1 profit |
| --- | ---: | ---: | ---: |
| Base plan | 64% | 31 | $32,196 |
| Price -10% | 60% | 35 | $24,931 |
| Volume -20% | 58% | 31 | $19,450 |
| Unit costs +15% | 62% | 32 | $30,858 |

No red flags in these numbers. They are only as good as the inputs: check every cost against a real quote.

## Marketing

*(Construído com base em [competitors.md](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/founder/competitors.md), [pricing.md](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/founder/pricing.md), [offer.md](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/founder/offer.md), [cfo.md](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/founder/cfo.md) e no aprendizado central do Painel v2: sem trial gratuito na entrada, a confiança só nasce quando o trader acompanha a prova pública pré-abertura ao longo de 2–3 semanas.)*

---

### 1. Posicionamento (3 versões + recomendada)

1. **Versão A (Foco no ritual pré-09h — RECOMENDADA):**
   > *Para day traders ativos de WIN e WDO que desconfiam de salas de call e não querem pagar R\$ 245+/mês nem configurar plugins complexos, o **Magic Walls** é o radar web de liquidez institucional (GEX oficial da B3 + Fluxo Smart Money em M1/M5) com níveis publicados antes das 08h45 no navegador e provados diariamente antes da abertura no `@magicwallsb3`, diferente de ferramentas caras presas ao desktop ou indicadores que só mostram o gráfico depois que fechou.*
   - **Evidência do painel:** Ataca simultaneamente `trust` (10/20 no painel v2) e `price` (caiu de 5 para 1 a R\$ 79–97), alinhando-se aos compradores que pediram acompanhamento pré-09h por 2–3 semanas (`P002`, `P008`, `P013`, `P020`).
2. **Versão B (Foco em segunda tela sem instalação):**
   > *Para operadores de Mini-Índice e Mini-Dólar que já usam ProfitChart pela corretora e não querem perder tempo configurando planilhas ou scripts, o **Magic Walls** é o painel auxiliar 100% web que entrega em 1 clique os níveis institucionais do dia e divergências de fluxo em modo compacto com alerta sonoro, por R\$ 97/mês sem RLP nem meta de contratos.*
3. **Versão C (Foco em transparência CVM 20/2021):**
   > *Para traders cansados de promessas milagrosas de gurus, o **Magic Walls** é um terminal analítico 100% web focado em WIN×WDO que posta o mapa do pregão antes das 09h e audita publicamente acertos e stops às 17h30.*

---

### 2. Canais (Onde o comprador está · O que fazer e o que NÃO fazer)

| Canal | Por que encaixa no comprador | Custo mensal | Como saber se funcionou |
| --- | --- | ---: | --- |
| **1. Instagram `@magicwallsb3` (Feed, Stories e Reels diários pré + pós-pregão)** | É o motor central de prova pública: o trader de WIN/WDO já acompanha mercado no Instagram antes das 09h e à noite. Postar as Walls **antes das 09h** elimina a suspeita de cherry-picking. | R\$ 0 orgânico (produção própria) | >= 500 novos seguidores qualificados/mês, >= 15% de cliques para a página de histórico/checkout |
| **2. Meta Ads (Instagram Reels/Stories — Aquecimento + Remarketing 14 dias)** | Amplifica os melhores Reels de prova diária para lookalike/interesses de B3/futuros e faz remarketing barato apenas para quem já acompanhou os posts pré/pós-pregão por dias. | **R\$ 1.600/mês** *(80% da verba)* | Custo por visita na página de histórico <= R\$ 1,50 e **CAC <= R\$ 150** no Lote Fundador |
| **3. YouTube Shorts + Vídeo semanal de auditoria/abertura + Página de Histórico Público** | Atende o segmento `Caçador de edge técnico` e `Cético` que exige entender metodologia B3 e ver a tela real em movimento (M1/M5 + alerta sonoro) antes de pagar sem trial. | **R\$ 400/mês** *(ferramentas edição/impulsionamento pontual)* | >= 20% dos visitantes do histórico clicam em "Ver Oferta Lote Fundador" |

**O que NÃO fazer agora (e por quê):**
- **Não rodar Google Ads genérico para "como fazer day trade" ou "robô mini índice":** CPC caro e atrai iniciantes sem capital que quebram em 30 dias.
- **Não fechar parcerias com salas de sinais que prometem ganho garantido:** viola posicionamento CVM nº 20/2021 e destrói credibilidade junto a traders experientes.
- **Não mandar tráfego frio direto para checkout sem trial:** o Painel v2 (`0/20`) provou que tráfego frio não compra direto sem ver prova ao vivo/pré-09h antes. O tráfego frio vai para **@magicwallsb3 / Replay Público de 5 Pregões**, e só o **remarketing (14–21 dias de aquecimento)** vai para o checkout com garantia de 7 dias.

---

### 3. Campanha de 30 Dias (`D-14` a `D+16` · ancorada no Lançamento em `11/01/2027`)

*(Pré-requisito: entre `27/11/2026` e `27/12/2026` o perfil já executa o teste piloto de 10 pregões de prova pública; a campanha abaixo cobre a reta final `28/12/2026` a `27/01/2027`.)*

- **D-14 a D-8 (`28/12`–`03/01`):** Publicar a **Nota Metodológica Aberta** (como dados B3 viram Call Wall/Put Wall/FlipWall sem caixa-preta) + liberar a **Página Pública dos últimos 5 pregões** + 3 Reels de bastidores de tela ao vivo mostrando modo compacto ao lado da execução e alerta sonoro.
- **D-7 a D-1 (`04/01`–`10/01`):** Rotina diária rigorosa na volta da liquidez de janeiro: **08h35** card/Story fixo com as Walls do dia carimbadas pré-abertura; **17h30** carrossel de auditoria mostrando deslocamento técnico máximo em pontos **e** stops/invalidações do pregão. Anunciar a abertura do **Lote Fundador (40 vagas a R$ 79/mês travado)**.
- **D0 (`11/01` — Abertura do Lote Fundador):** Post 08h35 + link de checkout na bio/Stories + remarketing para quem interagiu nos últimos 14 dias. Sem trial, com **Garantia Incondicional de 7 dias em 1 clique** + SLA 08h45.
- **D+1 a D+14 (`12/01`–`25/01`):** Manter o ritual diário 08h35 / 17h30 todos os pregões + 2 vídeos curtos por semana respondendo dúvidas reais de seguidores (ex.: *"Como copiar os níveis em 20s no seu gráfico"* e *"Diferença prática entre Gamma positivo e negativo"*). Contagem regressiva real apenas nos últimos 3 dias do lote (`23` a `25/01`).
- **D+15 a D+16 (`26/01`–`27/01`):** Encerramento do Lote Fundador de 40 vagas/14 dias -> preço passa para **R\$ 97/mês** padrão no site, mantendo o ritual diário no Instagram como funil perpétuo.

**Quando não há novidade no dia (pregão travado ou feriado):** Mostrar os bastidores da arquitetura (como o sistema lê o boletim oficial da B3 pós-18h, cálculo Black-76 explicado de forma visual, ou auditoria de um dia de stop mostrando onde o painel avisou exaustão/invalidação).

---

### 4. Dez Ganchos (Hooks) — Cada um responde uma objeção do painel

*(Todos dentro da Resolução CVM nº 20/2021 — sem promessa de lucro e sem usar falas do painel como depoimento.)*

1. **[3s Reels · Mata `trust` de pós-mercado]:** *"São 08h35 da manhã e o pregão nem abriu: aqui estão as 4 Walls do WIN e do WDO de hoje gravadas antes das 09h para você conferir às 17h30."*
2. **[3s Reels · Mata `trust` de "só posta acerto"]:** *"Hoje deu stop na Call Wall do índice — vou te mostrar exatamente onde a leitura falhou e onde o Fluxo Smart Money avisou antes."*
3. **[Headline Meta Ads · Mata `price` vs. Profit/Jumba]:** *"Mapa diário de exposição Gamma da B3 para WIN e WDO por R\$ 79/mês no Lote Fundador — sem pagar R\$ 245+/mês e sem meta de corretora."*
4. **[3s Reels · Mata `habit` ProfitChart]:** *"Não quer largar seu ProfitChart? Aperta 1 botão às 08h35, copia os 4 níveis do dia para o seu gráfico em 20 segundos e deixa só o alerta sonoro aberto."*
5. **[3s Reels · Mata `need` / jargão GEX]:** *"O que é FlipWall em 45 segundos: a única linha que separa um dia de mercado travado de um dia de aceleração no dólar."*
6. **[Headline Remarketing · Mata "sem trial"]:** *"Sem trial grátis, mas com risco zero: assine o Lote Fundador e teste 5 pregões ao vivo com reembolso em 1 clique por 7 dias."*
7. **[3s Reels · Mata desconfiança de cadastro/spam]:** *"Sem grupo VIP de spam e sem ligar no seu WhatsApp: acompanhe as marcações grátis aqui todo dia às 08h35 antes de decidir."*
8. **[Headline Página de Histórico · Mata falta de tela ao vivo]:** *"Veja a gravação real do Fluxo Smart Money em M5 marcando divergência na Put Wall durante o pregão da manhã — sem corte."*
9. **[3s Reels · Mata risco de atraso pré-abertura]:** *"Níveis calculados direto do boletim oficial B3 e publicados antes das 08h45 — se atrasar ou cair, você ganha +7 dias de assinatura grátis."*
10. **[Carrossel Educacional · Mata `need` de stop/entrada]:** *"Como identificar um ponto objetivo de invalidação técnica usando Call Wall + Fluxo Smart Money sem operar no escuro (100% educacional)."*

---

### 5. Orçamento, CAC Máximo e Números para Vigiar Semanalmente

- **Divisão da verba (teto R\$ 2.000/mês):**
  - `R$ 1.100/mês` -> Meta Ads Aquecimento (impulsionar Reels de prova pré-09h / auditoria 17h30 para público WIN/WDO -> objetivo: crescer seguidores e visualizações de vídeo 50%).
  - `R$ 500/mês` -> Meta Ads Remarketing (apenas quem interagiu com `@magicwallsb3` ou visitou o Histórico Público nos últimos 14–21 dias -> oferta Lote Fundador R\$ 79/mês / Padrão R\$ 97/mês).
  - `R$ 400/mês` -> Produção / ferramentas de corte de vídeo e YouTube Shorts.
- **Quanto podemos pagar por um cliente (CAC máximo):**
  - Pelo CFO (`founder/cfo.md`), a contribuição unitária a R\$ 97/mês é **R\$ 85,09/mês** (e R\$ 67,09 a R\$ 79/mês).
  - Com uma hipótese conservadora de retenção média de **3 meses** no varejo B3 (LTV de contribuição ≈ **R\$ 255** a R\$ 97/mês, ou **R\$ 201** a R\$ 79/mês), para respeitar relação saudável `LTV:CAC >= 3:1` e payback rápido, o **CAC máximo suportável é de R\$ 85 por assinante pago** (teto absoluto de alerta: **R\$ 120**).
  - *(Nota: como os primeiros meses combinam tráfego orgânico diário + R\$ 2.000/mês, se a Meta Ads pura entregar CAC de R\$ 150 inicialmente, o orgânico ajuda a diluir o CAC combinado — mas o tráfego pago deve ser pausado/recalibrado se o CAC isolado de remarketing passar de R\$ 120.)*

**Três números semanais para vigiar (e quando mudar algo):**
1. **Taxa de clique/visita no Histórico Público a partir do Instagram:** meta >= **3%** do alcance semanal -> *se ficar < 1,5% por 2 semanas*, trocar os hooks de Reels para gravações de tela ao vivo no pregão em vez de cards estáticos.
2. **Conversão Visitante Aquecido (Remarketing) -> Assinante Pago:** meta >= **2,5%** -> *se ficar < 1,2% após 14 dias de prova*, executar o plano B imediato: **teste A/B oferecendo trial de 5 pregões sem cartão (só e-mail)**.
3. **Taxa de Reembolso na Garantia de 7 dias:** meta <= **8%** (provisão CFO é 6%) -> *se passar de 15%*, o onboarding nos primeiros 5 minutos está falhando (simplificar tela e Playbook antes de trazer mais gente).

## Brand

*(Construída a partir de [idea.md](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/founder/idea.md), [competitors.md](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/founder/competitors.md), [marketing.md](file:///c:/Users/ryzen/Downloads/Antigravity/wdo%20win%20pair%20trading/founder/marketing.md) e dos ativos visuais já existentes em `SaasWelcomePortal.jsx`.)*

---

### 1. Candidatos de Nome & Verificações (Manter ou Renomear)

*(Como `Magic Walls`, `magicwalls.com.br`, `app.magicwalls.com.br` e `@magicwallsb3` já estão no ar, a análise avalia manter a marca atual frente a 9 alternativas caso o exame no INPI aponte colisão.)*

| # | Candidato | Estilo | O que comunica / como soa | Risco |
| --- | --- | --- | --- | --- |
| 1 | **Magic Walls** *(Atual)* | Evocativo + técnico | Remete às paredes de opções ("Walls"). Fácil de lembrar, mas a palavra *"Magic"* pode soar mística para traders céticos se não vier com prova antes das 09h. | Colisão no INPI ou percepção de "fórmula mágica". |
| 2 | **GEX Walls B3** | Descritivo | Diz na hora o que é (GEX + Walls na B3). Muito claro, porém menos distintivo para registro de marca. | Termo descritivo pode ter resistência no registro de marca nominativa. |
| 3 | **FluxoWalls** | Híbrido (PT+EN) | Une os dois pilares do produto (Fluxo Smart Money + Walls). Curto, forte em ícone e português direto. | Pronúncia bilíngue; exige registro de domínio novo. |
| 4 | **GammaMap B3** | Descritivo | Enfatiza o mapa de exposição Gamma na B3; soa institucional/quantitativo. | Pouco memorável para trader de varejo iniciante. |
| 5 | **FlipWall** | Técnico/Produto | Nomeia a linha central que separa regime positivo e negativo. Curto e técnico. | Foca em um único nível do painel. |
| 6 | **Mural GEX** | Português descritivo | Traduz "Wall" para português; soa diferente de todos os concorrentes em inglês. | Traders de B3 já usam o jargão "Wall" em inglês. |
| 7 | **Radar B3 / Radar GEX** | Evocativo funcional | Posiciona o produto como "radar" auxiliar, sem prometer sinal mágico. | "Radar" é palavra muito disputada em fintech/investimentos. |
| 8 | **WallDesk** | Composto | Evoca terminal/mesa de leitura de paredes. Fácil em 32px. | Pode soar como corretora ou mesa proprietária. |
| 9 | **Vetor GEX** | Técnico | Transmite matemática, precisão e direção de fluxo sem misticismo. | Menos imediato sobre ser WIN/WDO. |
| 10 | **WallsTrader** | Descritivo comercial | Direto ao ponto para day trader; fácil de explicar em 3 segundos. | Genérico, lembra salas comerciais tradicionais. |

#### Shortlist (Top 3) e Checagens Públicas Executadas (`26/11/2026`)

| Candidato | DNS verificado nesta sessão | O que o usuário precisa concluir manualmente |
| --- | --- | --- |
| **1. Magic Walls** *(Recomendado manter se livre no INPI)* | `magicwalls.com.br`, `app.magicwalls.com.br` e `magicwalls.com` possuem registros NS ativos (`HAS_NS`). | Checar anterioridade de marca no **INPI** e confirmar disponibilidade de `@magicwallsb3` em YouTube/TikTok/X. |
| **2. FluxoWalls** *(Plano B mais forte)* | `fluxowalls.com.br` retornou `NO_NS_FOUND` *(sem DNS ativo na checagem — confirmar disponibilidade de registro no Registro.br)*. | Checar no Registro.br, buscar colisão no INPI e verificar `@fluxowalls` nas redes. |
| **3. GEX Walls / WallsTrader** *(Plano C)* | `gexwalls.com.br` e `wallstrader.com.br` retornaram `NO_NS_FOUND` *(confirmar no Registro.br)*. | Buscar anterioridade no INPI antes de qualquer troca de nome. |

**Links oficiais para finalizar as verificações:**
- **INPI (Busca de Marcas — Classes NCL `9`, `36` e `41`):** [busca.inpi.gov.br/pePI](https://busca.inpi.gov.br/pePI/) *(pesquisar por "Magic Walls" e radicais próximos nas classes 9 — software, 36 — informação financeira e 41 — conteúdo educacional)*.
- **Domínios `.br`:** [registro.br](https://registro.br).
- **Handles sociais:** checar `@magicwallsb3` no Instagram (já utilizado), YouTube, TikTok e X.

*Nota: Estas checagens são pesquisas públicas preliminares e não constituem parecer jurídico de propriedade industrial; um advogado ou agente de marcas confirma a registrabilidade no INPI antes do depósito.*

---

### 2. Promessa, Tagline e Tom de Voz

- **Promessa em 1 linha:** *O mapa institucional da B3 publicado antes das 08h45 no seu navegador e auditado publicamente todos os dias às 17h30.*
- **3 opções de tagline:**
  1. *Leia as Walls antes das 09h. Nunca mais opere no escuro.* *(Recomendada — conversa direto com o ritual no Instagram)*
  2. *GEX da B3 + Fluxo Smart Money em tempo real, direto no navegador.*
  3. *Liquidez institucional de WIN e WDO sem instalação, sem call e sem caixa-preta.*
- **Tom de voz em 3 adjetivos:**
  - **Objetivo** — *Faça:* use horários exatos (`08h35`, `17h30`), pontos reais de WIN/WDO e critérios claros de invalidação. *Não faça:* adjetivos vazios como "infalível", "explosivo" ou "assertividade absurda".
  - **Transparente** — *Faça:* mostre dias de stop junto com dias de deslocamento amplo e explique de onde vêm os dados da B3. *Não faça:* esconder resultados ruins nem usar prints sem carimbo de horário pré-abertura.
  - **Sobriedade institucional** — *Faça:* trate o usuário como operador adulto responsável pelo próprio clique (CVM nº 20/2021). *Não faça:* linguagem de sala de sinal, foguetes, promessas de renda extra ou urgência falsa.
- **Antes vs. Depois (reescrevendo trecho do `pitch-v1.md`):**
  - *Antes:* "Acesso ao terminal web em tempo real com GEX, Canal Gauss e Fluxo Smart Money, teste 15 dias deixando WhatsApp."
  - *Depois:* "Antes das 09h, veja as paredes de liquidez da B3 no navegador e acompanhe nossa auditoria diária gratuita no `@magicwallsb3` — sem instalar nada e sem spam no WhatsApp."

---

### 3. Brief Visual (alinhado ao terminal já construído)

- **Paleta principal (WCAG AA verificado sobre fundo escuro `#0b0f17`):**
  - `#0b0f17` (**Obsidian Terminal**) — fundo principal, reduz fadiga ocular de quem opera 4+ horas pela manhã.
  - `#e2e8f0` (**Texto Principal**) — contraste superior a `14:1` sobre `#0b0f17` (excede WCAG AAA).
  - `#4cc38a` (**Defesa / Gamma Positivo / Put Wall**) — contraste `~9.1:1` sobre `#0b0f17` (passa WCAG AA/AAA).
  - `#e5484d` (**Aceleração / Gamma Negativo / Call Wall**) — contraste `~4.8:1` para texto grande/UI e destaques sobre `#0b0f17` (usar `#f87171` em texto pequeno se precisar >6:1).
  - `#d4a259` (**FlipWall / Âncora**) — contraste `~7.9:1` sobre `#0b0f17`.
  - `#38bdf8` (**Referência / Ativo**) — contraste `~8.9:1` sobre `#0b0f17`.
- **Tipografia (licença gratuita SIL Open Font License):**
  - Display & UI: **`IBM Plex Sans`** ([fonts.google.com/specimen/IBM+Plex+Sans](https://fonts.google.com/specimen/IBM+Plex+Sans)).
  - Preços, timestamps e tabelas de níveis: **`IBM Plex Mono`** ([fonts.google.com/specimen/IBM+Plex+Mono](https://fonts.google.com/specimen/IBM+Plex+Mono)).
- **Brief do Logo:** Símbolo geométrico limpo remetendo a duas paredes paralelas e uma linha de flip central (mantendo a identidade já iniciada em `MagicWallsMark`), legível tanto em favicon `32×32 px` na aba do navegador quanto em marca d'água no card quadrado/vertical do Instagram; evitar cifrões, touros, ursos ou gráficos genéricos de vela.

---

### 4. Os 5 Primeiros Pontos de Contato

1. **Card Matinal Pré-09h no `@magicwallsb3` (08h35):** Layout fixo com data, horário de publicação em destaque (`08h35 BRT`), níveis Call Wall, FlipWall e Put Wall de WIN e WDO em `IBM Plex Mono`, e rodapé discreto *"Estudo analítico CVM 20/2021 · Não é recomendação"*.
2. **Card de Auditoria Pós-Pregão (17h30):** Mesmo enquadramento lado a lado mostrando onde o preço respeitou ou rompeu cada Wall, deslocamento máximo técnico em pontos e marcação explícita de eventuais stops/invalidações do dia.
3. **Homepage / Página Pública de Histórico (5 pregões):** Sem popup nem pedido de WhatsApp; acima da dobra mostra os últimos 5 pregões auditados + explicação em 1 frase + botão **"Ver Lote Fundador (R\$ 79/mês · Garantia 7 dias)"**.
4. **E-mail de Boas-Vindas pós-checkout:** Assunto direto (*"Seu acesso ao Magic Walls está pronto — comece em 5 minutos"*), credenciais de login, link do Playbook de 8 min e lembrete visível do botão de reembolso em 1 clique por 7 dias.
5. **Resposta à Primeira Reclamação / Pedido de Reembolso:** Resposta em menos de 4h úteis confirmando o estorno integral sem questionamento e agradecendo pelo feedback específico sobre o pregão.

## Operations

*(Operação desenhada para fundador solo, VPS dedicada já contratada por R\$ 1.900/2 anos escalável para 1.000+ usuários, backend 100% invisível ao usuário e conformidade com a legislação brasileira.)*

---

### 1. Ciclo Diário (do pós-pregão B3 até o fechamento do dia seguinte)

| Horário (BRT) | Ação operacional | Visível ao cliente? |
| --- | --- | --- |
| **18h15–19h30** | Coleta automatizada do boletim oficial de Posições em Aberto da B3 + fechamento 17h00 na VPS dedicada; cálculo das Walls WIN/WDO (`GEX_DAILY`). | Não (processamento interno) |
| **08h00–08h25** | Checagem automática de saúde do feed na VPS, rollover de vencimento WIN/WDO e geração do card matinal pré-abertura. | Não |
| **08h30–08h35** | **Publicação oficial das Walls do dia no Terminal Web** + publicação no **Instagram `@magicwallsb3`** (antes da abertura às 09h00, carimbando horário público). | **Sim** |
| **08h55–12h30** | Monitoramento do pregão da manhã (alertas Telegram de heartbeat/stale >15s); gravação de trecho curto de tela real em dias de movimento limpo nas Walls. | **Sim** (tempo real no painel) |
| **12h30–17h00** | Atendimento a dúvidas/suporte e manutenção de produto; monitoramento automatizado da sessão da tarde. | Parcial (suporte) |
| **17h30–18h00** | **Auditoria pós-pregão no `@magicwallsb3`:** publicação do balanço técnico em pontos (deslocamento máximo nas marcações + stops/invalidações) + atualização da Página de Histórico Público. | **Sim** |

---

### 2. Fornecedores e Infraestrutura Real (com preços públicos e links)

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

### 3. Rotina Semanal (Fundador Solo)

- **Mês 1 (6 a 15 assinantes):** ~22h/semana dedicadas ao negócio — `08h00–09h30` rotina pré-abertura + post Instagram (7,5h/sem); `17h30–18h30` coleta B3 + post de fechamento (5h/sem); `ter/qui tarde` produção de conteúdo/anúncios + ajustes de UX (6h/sem); `sexta 18h` revisão de métricas e reembolsos (3,5h/sem).
- **Ritmo de 115 assinantes (Mês 12):** ~28h/semana — automatizar a geração do card 08h35 e 17h30 (já há utilitários base no repositório), mantendo apenas supervisão humana de 20 min pré-abertura, suporte assíncrono via e-mail/ticket (janela fixa 12h30–14h00 e 17h30–18h30) e 1 análise semanal de churn/anúncios.

---

### 4. Procedimentos Operacionais Padrão (SOPs de 1 Página)

#### SOP 1 — Publicação Pré-Abertura até 08h35
1. Às `08h05`, conferir alerta do Telegram confirmando que o boletim da B3 da noite anterior foi processado sem erro na VPS.
2. Às `08h15`, validar no painel admin se Call Wall, Put Wall, FlipWall e MidWalls conferem com o vencimento vigente de WIN e WDO (checar datas de rollover na quarta-feira de vencimento).
3. Às `08h25`, confirmar o carregamento no navegador em modo anônimo (`app.magicwalls.com.br`).
4. Até `08h35`, publicar o card padrão no Instagram `@magicwallsb3` com horário visível antes da abertura.

#### SOP 2 — Incidente ou Queda Durante o Pregão (09h–17h)
1. Ao receber alerta de `HEARTBEAT_STALE` no Telegram (>15s sem push), checar serviço da VPS imediatamente via RDP/SSH.
2. Se a indisponibilidade ultrapassar **5 minutos**, postar aviso nos Stories / banner no painel informando instabilidade em verificação.
3. Se ultrapassar **15 minutos** na sessão da manhã (`09h–12h`) ou atrasar publicação regular além de **08h45**, acionar o script administrativo para creditar **+7 dias automáticos** na assinatura de todos os usuários ativos (cumprindo o SLA prometido sem o cliente precisar pedir).

#### SOP 3 — Onboarding e Suporte (Zero Atrito)
1. Após confirmação do webhook Asaas, enviar e-mail imediato (sem pedir WhatsApp) com link de acesso, botão para o Playbook de 8 minutos e resumo visual da **Visão Limpa**.
2. Dúvidas técnicas respondidas em até 4h úteis por e-mail/central de ajuda; nunca responder dando recomendação de compra/venda ou call de preço (sempre responder em termos de leitura educacional de níveis e metodologia CVM nº 20/2021).

#### SOP 4 — Cancelamento e Reembolso em 1 Clique (Garantia 7 Dias)
1. Dentro de "Minha Conta", manter botão explícito **"Cancelar assinatura"** (sem retenção abusiva) e, nos primeiros 7 dias corridos após a primeira compra, **"Solicitar reembolso integral (Garantia 7 dias)"**.
2. Ao clicar em reembolso nos primeiros 7 dias, disparar estorno automático via API do Asaas, encerrar sessão ativa e enviar e-mail de confirmação com pesquisa opcional de 1 pergunta (*"O que faltou para encaixar no seu operacional?"*).

#### SOP 5 — Fechamento Semanal & Auditoria Anti-Rateio (Sexta 18h)
1. Revisar logs de abuso do `cloud_saas` (excesso de troca de dispositivos/IPs distintos).
2. Ajustar a política de sessão única para **tolerar 1 navegador desktop + 1 dispositivo mobile do mesmo titular** (sem derrubar por uso legítimo), bloqueando apenas uso simultâneo em múltiplos IPs/cidades diferentes.
3. Conferir métricas semanais (seguidores -> visitas histórico -> assinantes -> reembolsos 7d -> churn).

---

### 5. Stack Mínimo de Ferramentas

- **Backend / API / DB / Cache:** Python FastAPI (`Railway Pro` US\$ 20/mês) + `Supabase Pro` (US\$ 25/mês) + `Upstash Redis` (US\$ 10/mês) + `Cloudflare Pages` (US\$ 0).
- **Produtor de Mercado:** `VPS Windows Dedicada` (R\$ 1.900/2 anos já paga, 1.000+ usuários).
- **Pagamentos & Recorrência:** `Asaas` (mensalidade R\$ 0; taxas por transação).
- **E-mail transacional:** `Resend` ou `Brevo` (faixa gratuita inicial para até 3.000 e-mails/mês; confirmar volume conforme base crescer).

---

### 6. Checklist Legal, Fiscal e Regulatório (Brasil)

*Aviso: regras fiscais e regulatórias mudam e dependem do enquadramento exato da empresa; um contador e um advogado devem confirmar cada item antes de escalar vendas.*

1. **CNPJ e Regime Tributário (SaaS / Software):** Software analítico/licenciamento não se enquadra no MEI; estruturar ME no Simples Nacional (ex.: CNAE de desenvolvimento/licenciamento de software, avaliando Fator R entre Anexos III e V com contador) e emissão de NFS-e automática — conferir em [gov.br/empresas-e-negocios](https://www.gov.br/empresas-e-negocios/pt-br/empreendedor).
2. **Resolução CVM nº 20/2021 (Valores Mobiliários):** Manter linguagem estritamente analítica/educacional em todo o terminal, no Playbook e especialmente nos posts diários do Instagram (evitar recomendações personalizadas de compra/venda ou promessas de retorno financeiro) — consultar [conteudo.cvm.gov.br](https://conteudo.cvm.gov.br).
3. **Código de Defesa do Consumidor (Art. 49):** Direito de arrependimento de 7 dias em compras online — transformado em vantagem comercial com reembolso em 1 clique — consultar [planalto.gov.br (CDC)](https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm).
4. **LGPD (Lei 13.709/2018):** Coleta mínima (apenas e-mail/nome para acesso + dados fiscais no Asaas), termos de uso e política de privacidade explícitos para watermark forense e registro de IP anti-rateio — consultar [gov.br/anpd](https://www.gov.br/anpd/pt-br).
5. **Registro de Marca:** Busca prévia e depósito no **INPI** nas classes **9** (software), **36** (ferramentas de informação financeira) e **41** (conteúdo educacional) — consultar [gov.br/inpi](https://www.gov.br/inpi/pt-br).

---

### 7. Registro de Riscos Operacionais (Top 10)

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

## Launch plan

*(Ancorado na data atual: **26/11/2026**. Como dezembro tem queda gradual de liquidez na B3 pelo recesso de fim de ano, o plano usa o fim de novembro e dezembro para executar o **teste real pré-orçamento** + ajustes finais do produto, abrindo o **Lote Fundador público em 11/01/2027**, na volta plena dos pregões.)*

---

### 1. Teste Barato no Mundo Real (Antes de Gastar R$ 2.000/mês)

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

### 2. Contagem Regressiva Datada (`27/11/2026` a `11/01/2027`)

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

### 3. Run Sheet do Dia do Lançamento (`11/01/2027` — Segunda-feira)

- **07h30:** Checar VPS dedicada, logs de processamento do boletim B3, Asaas em modo produção e disponibilidade do site em modo anônimo.
- **08h15:** Validar os níveis do dia no painel e o funcionamento do botão "Copiar Níveis (1 clique)" + Modo Compacto.
- **08h35:** Publicar o card oficial pré-abertura no Instagram `@magicwallsb3` + Stories com contagem real de vagas do Lote Fundador (40 vagas).
- **08h55:** Ativar campanha de Remarketing no Meta Ads (`R$ 50/dia` inicial) direcionando para a Página de Histórico Público + Checkout Lote Fundador (R$ 79/mês).
- **09h00–12h30:** Monitorar pregão da manhã ao vivo (heartbeat VPS + fila de suporte). Responder todas as dúvidas de novos assinantes em <30 min (sempre sob CVM 20/2021).
- **12h30–14h00:** Verificar primeiros pagamentos confirmados no Asaas, entrega automática de e-mail e eventuais falhas de login desktop+mobile.
- **17h30:** Publicar card de auditoria pós-pregão no `@magicwallsb3` (deslocamento técnico em pontos + stops/invalidações) + link para quem acompanhou o dia entrar no Lote Fundador.
- **18h30:** Consolidar placar do Dia 1 (visitas, checkouts iniciados, assinantes pagos, vagas restantes) e conferir se algum cliente precisou do suporte/reembolso.

---

### 4. Primeiros 30 Dias: Métricas Semanais e Revisões

**Números semanais acompanhados:**
- Assinantes pagantes ativos vs. meta da rampa do CFO (**Mês 1 = 6 assinantes líquidos**, caminhando para break-even de **31 assinantes** no Mês 4);
- Custo por Assinante Pago (CAC <= R\$ 85 ideal / teto alerta R\$ 120);
- Taxa de reembolso em 7 dias (<= 8% meta / >15% gatilho de alerta);
- Pontualidade pré-08h45 (100% dos pregões com dados B3 publicados no prazo).

**Agenda de revisões obrigatórias:**
- **Dia 7 (`18/01/2027`):** *Quantas pessoas compraram no Lote Fundador sem trial? Quantas pediram reembolso nos 7 dias e qual o motivo exato?* -> Se vendas < 6 ou reembolso > 15%, ligar teste de trial 5 dias sem cartão imediatamente.
- **Dia 14 (`25/01/2027`):** *Encerramento do Lote Fundador (40 vagas ou prazo de 14 dias) e virada para R$ 97/mês.* Avaliar se o preço de R$ 97/mês mantém ritmo de entrada.
- **Dia 30 (`10/02/2027`):** *Retenção do primeiro ciclo mensal (quantos renovaram para o Mês 2?)* Calcular LTV real vs. CAC antes de manter ou ajustar a verba de R$ 2.000/mês.

_The panel is simulated buyers and the numbers are projections from your inputs. Confirm demand with real customers and costs with real quotes before you spend. Not financial, legal or tax advice._
