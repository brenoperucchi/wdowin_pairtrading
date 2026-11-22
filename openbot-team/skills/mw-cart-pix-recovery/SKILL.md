---
name: mw-cart-pix-recovery
description: Prepara e gerencia réguas consultivas de recuperação para abandono de checkout, Pix expirado e leads de Direct que pediram link mas não concluíram o pagamento na MagicWalls. Usar diariamente para recuperar receita perdida no checkout.
example-prompt: Monte a fila e os scripts aprovados de recuperação para os 6 Pix gerados hoje que expiraram e para 4 leads que abriram checkout do plano PRO pelo Direct sem concluir.
---

# Recuperação de Checkout, Pix e Links de Direct (`mw-cart-pix-recovery`)

## Objetivo
Recuperar entre **25% e 35%** das vendas perdidas por atrito técnico, expiração de Pix ou distração pós-Direct, mantendo abordagem consultiva e elegante.

## Entradas Obrigatórias
- Handoffs do Direct (`Shared/magicwalls/recuperacao/*dm-pipeline*`)
- Lista de eventos de abandono/Pix expirado fornecida pelo Fundador/gateway

## Procedimento Passo a Passo
1. **Segmentar por Gatilho & Canal:**
   - **Pix Gerado e Não Pago:**
     - `T+10 min`: *"Notei que seu Pix da MagicWalls expirou/ficou pendente — quer que eu gere um novo código para liberar seu acesso ainda antes do próximo pregão?"*
     - `T+3h`: Mensagem curta com vídeo/print do painel rodando e link direto de pagamento.
     - `T+20h`: Último toque educado antes do encerramento da sessão/condição vigente.
   - **Abandono de Checkout (Cartão / Dados preenchidos):**
     - `T+15 min`: Check-in técnico (*"Deu algum erro no cartão ou ficou alguma dúvida sobre compatibilidade com Profit/TradingView?"*).
     - `T+2h`: Esclarecimento da principal objeção + opção de Passe 7 Dias (`R$ 29,90`) como degrau seguro.
     - `T+24h` e `T+48h`: Prova real de fechamento `17h15` mostrando o que o assinante já teria enxergado naquele pregão.
2. **Validar Compliance & Horário:** Submeter novos templates ao `02-brand-compliance`; respeitar janela `08:30–20:30 BRT`.
3. **Registrar Fila & Conversões:** Gravar fila pronta em `Shared/magicwalls/recuperacao/YYYY-MM-DD_fila-recuperacao_07-recovery.md` aguardando aprovação de disparo.

## Guardrails e Restrições
- Nunca disparar mensagens em massa sem aprovação do Fundador.
- Incluir opção simples de não receber mais lembretes (LGPD) e respeitar estritamente a verdade sobre prazos/vagas.

## Checklist de Verificação
- [ ] Leads segmentados por motivo (`Pix`, `Cartão/Checkout`, `DM Link`).
- [ ] Mensagens dentro da janela de horário e sem promessa CVM proibida.
- [ ] Receita recuperada contabilizada para o relatório semanal.
