# Veredicto do Conselho de Administração — Magic Walls (`@magicwallsb3`)

**Placar:** `3 FUND IF · 0 FUND · 0 PASS` | **Nota média:** `5,3 / 10`  
*(Lente de Ofertas: 5/10 `FUND IF` · Lente de Monopólio: 5/10 `FUND IF` · Lente de Produto: 6/10 `FUND IF`)*

---

## Riscos convergentes (levantados por mais de um conselheiro)

1. **Churn estrutural e ceticismo crônico do day trader PF na B3** *(Ofertas + Monopólio)*: Alta mortalidade financeira do público varejista e forte desconfiança contra ferramentas que mostram estudos internos de 30 pregões, podendo gerar cancelamento antes que o LTV cubra o CAC.
2. **Fragilidade operacional da Fase 1 em PC local Windows/MT5** *(Monopólio + Produto)*: Alimentar um painel pago de tempo real (M1/M5) a partir de um computador local doméstico com failover 4G/5G cria risco de queda ou latência exatamente em pregões voláteis.
3. **Ausência de métricas comerciais, competitivas e fosso defensivo comprovado** *(Ofertas + Monopólio + Produto)*: Ainda faltam mapeamento de concorrentes/substitutos no Brasil, preço validado (R$ 197/mês é apenas hipótese), CAC dentro do teto de R$ 2.000/mês, taxa de conversão do trial e prova de que o conceito GEX + Fluxo não pode ser copiado rapidamente por plataformas já abertas na tela do trader (como o ProfitChart).
4. **Excesso de complexidade e atrito no onboarding dos primeiros 5 minutos** *(Ofertas + Produto)*: Combinar 5 níveis GEX + Canal Gauss + Fluxo Smart Money (M1/M5) + visão dupla + 5 níveis arquiteturais no backend exige esforço cognitivo elevado durante o trial de 15 dias, sem execução integrada na corretora.

---

## Checklist consolidado de condições (`FUND IF`)

- [ ] **Mapear concorrentes, preços e brechas no Brasil** — levantar substitutos diretos e indiretos (ProfitChart, plugins/indicadores de GEX e fluxo, salas, planilhas/bots), reclamações públicas e o que torna o Magic Walls defensável além de dados públicos da B3 *(testado por `/founder-competitors`)*.
- [ ] **Validar demanda pagante e objeções reais de traders de WIN/WDO** — testar o pitch atual em compradores simulados e depois em leads reais para descobrir quem realmente paga, por que passa e o que trava os primeiros 5 minutos *(testado por `/founder-consumer`)*.
- [ ] **Definir preço ótimo e simplificar o empacotamento inicial** — escolher o preço mensal validado por sensibilidade de preço (Van Westendorp) e decidir entre lançar com **plano único simples** (posição defendida pela Lente de Produto) versus **escada `Core / Pro / Quant`** com âncora clara (questão aberta levantada por Ofertas e Monopólio) *(testado por `/founder-pricing`)*.
- [ ] **Construir o stack completo da oferta dentro da CVM nº 20/2021** — sair de "apenas acesso ao terminal + 15 dias grátis", adicionando onboarding guiado para os primeiros dias, rotina pré-mercado, qualificação/escassez real no trial e garantia pós-pagamento de baixo risco, além de casos documentados de usuários beta *(testado por `/founder-offer`)*.
- [ ] **Fechar a matemática mínima de CAC, churn, payback e infra dedicada** — calcular margem unitária, conversão mínima do trial de 15 dias, teto de churn e viabilidade de rodar em VPS Windows dedicada mais cedo em vez de depender de PC local até 40 clientes *(testado por `/founder-cfo` e `/founder-ops`)*.
- [ ] **Resolver o conflito entre anti-rateio ("sessão única") e uso prometido em desktop + mobile** — garantir que o assinante legítimo não seja desconectado ao alternar dispositivos durante o pregão *(ajuste operacional/produto antes de escalar)*.

---

## A versão mais forte deste negócio (e onde as lentes divergem)

A versão mais forte que o conselho enxerga para o **Magic Walls** não é vendê-lo como "mais um painel cheio de indicadores para todo day trader", e sim como **a tela auxiliar mais limpa e sem instalação para traders ativos de WIN/WDO (especialmente quem opera a partir de 5 minicontratos)**, ancorada em uma rotina pré-mercado objetiva de níveis GEX da B3 + leitura de absorção no Fluxo Smart Money, entregue em infraestrutura dedicada estável e acompanhada de onboarding prático e garantia clara dentro da Resolução CVM nº 20/2021. **Divergências mantidas entre os conselheiros:** a **Lente de Produto** defende cortar escopo visual e lançar obrigatoriamente com um **plano único simples** (adiando a escada `Core / Pro / Quant` e licença MT5 para reduzir complexidade), enquanto a **Lente de Ofertas** questiona se um preço mais alto ou uma **escada de valor com entregáveis educacionais e automação/MT5** não seria necessário para capturar maior ticket e compensar o churn do varejo; já a **Lente de Monopólio** adverte que, mesmo com ótimo produto e oferta, o negócio continuará vulnerável em 6 meses se não construir algum elemento proprietário ou custo de troca (histórico, diário operacional ou comunidade/fluxo exclusivo) que impeça plataformas incumbentes de copiar a ideia.

---

## Atualização de Infraestrutura e Go-to-Market (pós-reunião com o fundador · 26/11/2026)

- **Condição de infra local resolvida:** O sistema já foi migrado para **VPS dedicada** (contrato de **R$ 1.900 por 2 anos**, escalável para **1.000+ usuários**), eliminando o risco operacional da Fase 1 em PC local.
- **Abstração do backend:** O usuário final não tem contato nem conhecimento de Profit/MT5 nos bastidores, e o roadmap técnico prevê migração da coleta para **API oficial B3 / Cedro**. O produto comercializado é **100% Terminal Web SaaS** (sem distribuição de scripts `.nts`/plugins).
- **Mudança de aquisição:** Em vez de depender de trial gratuito de 15 dias na porta de entrada, a estratégia passa a ser **prova pública diária no Instagram (`@magicwallsb3`)** (Walls calculadas pela manhã + balanço técnico das marcações após o pregão) e **assinatura direta inicialmente sem trial**, usando garantia de 7 dias e preço competitivo como reversão de risco.
