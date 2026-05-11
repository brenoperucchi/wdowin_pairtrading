---
name: gsd-gex-daily
description: Automação diária do pipeline GEX. Busca preços M5 sincronizados às 17h, processa as walls e faz commit do resultado.
---

<objective>
Executar o workflow diário de atualização do Jumba Walls (GEX), garantindo que os dados de Open Interest e preços de fechamento (17h) do pregão anterior sejam integrados e publicados.
</objective>

<execution_context>
- gex/data/
- gex/docs/jumba_neologica
- gex/engine/main.py
</execution_context>

<process>

## Passo 1: Executar o Motor GEX
O arquivo CSV mais recente (`Posições em aberto-*.csv`) já deve ter sido colocado manualmente na pasta `gex/data/` pelo usuário.

Execute o motor python para puxar os preços M5 do fechamento do IBOV no MT5 e processar o arquivo CSV:
```bash
python -m gex.engine.main
```
Isso vai atualizar o `gex/docs/jumba_neologica` e publicar no Firebase automaticamente.

## Passo 2: Verificação do Resultado
Verifique se a saída do comando acima indicou sucesso (código de saída 0).
Se falhar, reporte o erro ao usuário. Não prossiga para o commit se falhar.

## Passo 3: Commit no Git
Execute o commit dos arquivos alterados:
```bash
git add gex/data/Posi* gex/docs/jumba_neologica
git commit -m "chore(gex): atualizacao diaria do jumba walls via gsd-gex-daily"
```

## Passo 4: Feedback
Informe o usuário que o processo foi concluído com sucesso, listando:
- Os valores do `F_WIN` e `S_IBOV` capturados.
- O fator gerado.
- Que os dados foram publicados no Firebase.
- E que o commit foi realizado no git.
</process>
