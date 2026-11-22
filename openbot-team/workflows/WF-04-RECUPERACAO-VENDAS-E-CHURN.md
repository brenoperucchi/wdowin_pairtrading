# WF-04 — Recuperação de Vendas, Cobrança (Dunning) & Retenção (Anti-Churn)

## 1. Objetivo
Estancar vazamentos de receita em todo o ciclo de vida do cliente MagicWalls: recuperar Pix/checkouts abandonados (`>= 25%`), recuperar falhas de cartão (`>= 50%`), ativar novos pagantes em `< 5 minutos` (`D0–D7`) e reter cancelamentos evitáveis.

## 2. Gatilho & Agenda
- **Pipeline Diário de Carrinho / Pix / Links DM:** Checagens às `11:30`, `16:30` e `19:00 BRT`.
- **Onboarding & Resgate de Inativos (`5 pregões`):** Verificação diária às `08:40 BRT` e `18:00 BRT`.

## 3. Agentes Envolvidos
`07-recovery-retention` (Líder) · `06-social-dm-closer` · `02-brand-compliance` · `01-ceo-magicwalls`

## 4. As 5 Réguas Oficiais

### Régua 1 — Pix Gerado & Não Pago
| Tempo | Canal | Mensagem / Objetivo |
| :--- | :--- | :--- |
| **T + 10 min** | WhatsApp / DM | *"Seu código Pix da MagicWalls foi gerado, mas ainda não constou compensação — quer o link atualizado para liberar antes da próxima abertura?"* |
| **T + 3 horas** | WhatsApp | Print/vídeo rápido da tela ao vivo + novo código Pix com 1 clique. |
| **T + 20 horas** | WhatsApp / E-mail | Último lembrete educado antes da expiração do pedido + opção de descadastro. |

### Régua 2 — Abandono de Checkout / Link Enviado no Direct
- **`T + 15 min`:** Check-in consultivo (*"Aconteceu algum erro no cartão ou ficou alguma dúvida sobre Profit/TradingView?"*).
- **`T + 2 horas`:** Envio do comparativo enxuto `CORE vs PRO` ou convite para iniciar pelo **Passe 7 Dias (`R$ 29,90`)**.
- **`T + 24 horas`:** Prova real do fechamento `17h15` do pregão mais recente.

### Régua 3 — Dunning (Falha de Renovação / Cartão Vencido)
- **`D - 2`:** Lembrete cordial antes da cobrança recorrente.
- **`D + 0`:** Aviso amigável de recusa pela operadora + link rápido de troca de cartão ou **Pix de renovação** (acesso **mantido por 3 dias de carência**).
- **`D + 2`:** Segundo lembrete com link direto de regularização sem perda da condição atual (ex.: Turma Fundadores).
- **`D + 4`:** Aviso transparente de pausa automática temporária até regularização.

### Régua 4 — Onboarding D0–D7 (Garantia de Uso Real)
- **`D0 (Imediato)`:** Boas-vindas + link do painel + vídeo de 3 min + passo a passo para copiar o código do Profit/TradingView.
- **`D+1 (08:20 BRT)`:** Lembrete pré-pregão indicando onde ver o Regime Gamma e as Walls do dia.
- **`D+3`:** Pergunta rápida de acompanhamento (*"Conseguiu rodar liso no seu gráfico?"*).
- **`D+7`:** Resumo de boas práticas + canal oficial de novidades.

### Régua 5 — Resgate de Inativos (`5 pregões`) & Save Offer
- **5 pregões sem login:** Mensagem pessoal oferecendo ajuda técnica de 5 minutos para destravar uso.
- **Pedido de cancelamento:**
  - Motivo Preço → **Downgrade PRO → CORE (`R$ 197/m`)**.
  - Motivo Tempo/Viagem → **Pausa de 30 dias** mantendo histórico.
  - Motivo Dúvida → **Call rápida 15 min de setup**.
  - Pedido dentro de `<= 7 dias` (CDC Art. 49) → **Reembolso imediato e cordial sem atrito**.

## 5. Gate & Plano B
- **Gate:** Todos os templates ficam pré-aprovados em `Shared/magicwalls/aprovacao/` pelo `02-brand-compliance`. A fila diária é gravada em `Shared/magicwalls/recuperacao/YYYY-MM-DD_fila-recuperacao_07-recovery.md` para disparo autorizado pelo Fundador ou ferramenta homologada.
- **Plano B:** Se um lead responder com irritação ou pedir remoção, marcar `[OPT_OUT]` imediatamente em todos os canais.
