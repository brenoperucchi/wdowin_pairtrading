---
name: mw-dunning-churn-shield
description: Opera réguas de cobrança de assinaturas falhas (Dunning D-2 a D+4), ativação de novos assinantes (Onboarding D0-D7), resgate de usuários inativos por 5 pregões e fluxo de Save Offer anti-cancelamento. Usar para reduzir o churn mensal da MagicWalls.
example-prompt: Prepare os roteiros da régua de Dunning para 3 cartões vencidos e o plano de ação de resgate para assinantes que não acessaram o painel nos últimos 5 pregões.
---

# Escudo Anti-Churn, Dunning & Onboarding (`mw-dunning-churn-shield`)

## Objetivo
Manter o **churn mensal abaixo de 8%** atacando os dois maiores ralos do SaaS no Brasil: inadimplência involuntária (cartão recusado) e cancelamento silencioso por falta de uso nos primeiros 7 dias.

## Entradas Obrigatórias
- Eventos de renovação/falha de assinatura e logs de inatividade (`>= 5 pregões` sem acesso) informados pelo Fundador
- `openbot-team/BRAND_BIBLE_CVM.md`

## Procedimento Passo a Passo
1. **Onboarding D0–D7 (Ativação Imediata):**
   - `D0 (Imediato)`: Link de acesso + vídeo de 3 min (*"Como ler MagicWalls + Profit/TradingView em 5 min"*).
   - `D+1 (08:20 BRT)`: Lembrete rápido de onde copiar os níveis atualizados do dia no painel.
   - `D+3`: Check-in de uso (identificar se conseguiu configurar `WIN`/`WDO`).
   - `D+7`: Pós-garantia CDC com resumo da rotina diária recomendada e convite para o canal de avisos.
2. **Régua de Dunning (Cartão Falho / Renovação):**
   - `D-2`: Lembrete amigável pré-cobrança.
   - `D+0`: Aviso imediato de falha na operadora com link direto de atualização ou **Pix alternativo** (sem cortar o acesso na hora — 3 dias de carência).
   - `D+2`: Novo link Pix e reforço dos níveis da semana.
   - `D+4`: Aviso cordial de pausa automática de acesso até regularização.
3. **Resgate de Risco Silencioso (`5 pregões` sem login):**
   - Mensagem pessoal: *"Notei que você não abriu o terminal MagicWalls nos últimos pregões — travou em alguma configuração ou prefere ajustar o formato de leitura?"*.
4. **Save Offer Inteligente (Ao pedir cancelamento):**
   - Oferecer **Downgrade PRO → CORE (`R$ 197/m`)** por motivo financeiro, **Pausa de 30 dias** por falta de tempo, ou **Sessão de Setup 15 min** por dificuldade técnica. Se insistir em cancelar dentro dos 7 dias (CDC), reembolsar imediatamente sem atrito.

## Guardrails e Restrições
- Nunca dificultar cancelamento nem cobrar após pedido de reembolso válido dentro de 7 dias.
- Toda mensagem sai como rascunho/fila validada por `02-brand-compliance` antes do envio.

## Checklist de Verificação
- [ ] Carência de 3 dias preservada no Dunning antes de sugerir suspensão.
- [ ] Save Offer mapeada por motivo real do usuário.
- [ ] Métricas de recuperação e churn consolidadas em `Shared/magicwalls/recuperacao/`.
