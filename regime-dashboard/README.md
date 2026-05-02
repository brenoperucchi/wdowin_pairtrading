# WIN×WDO Regime Dashboard

Interface frontend em React (Vite) para monitoramento do sistema de Pair Trading WIN×WDO.

## Arquitetura e Portas

Este sistema é composto por duas partes que devem rodar simultaneamente:
- **Backend (FastAPI)**: Roda na porta **8080** (`wdo win pair trading/server.py`)
- **Frontend (Vite/React)**: Roda na porta **5174** (este diretório)

*(Nota: Estas portas são exclusivas do Pair Trading. Não confundir com as portas do sistema IRAI, que utiliza 8888 e 5175).*

## Como Iniciar o Sistema

Para iniciar o sistema completo de forma automática, basta executar o script:

**`start.bat`** (localizado nesta pasta)

O script irá:
1. Limpar quaisquer processos "fantasmas" travados nas portas 8080 e 5174.
2. Iniciar o servidor Backend (FastAPI).
3. Iniciar o servidor Frontend (Vite).
4. Abrir o navegador automaticamente em `http://localhost:5174/`.

> [!IMPORTANT]  
> O **MetaTrader 5 Terminal** já deve estar aberto e logado na sua conta **antes** de rodar o `start.bat`. Caso contrário, o Backend não conseguirá buscar os dados do mercado.

## Troubleshooting (Solução de Problemas)

### O Backend trava/congela na inicialização sem gerar erros
Se a janela do Backend abrir mas não exibir nada e o dashboard mostrar que está "offline", isso geralmente é causado por um conflito de IPC com instâncias em background do MetaTrader 5 (ex: rodando como Serviço do Windows).

**Solução:**
Verifique o arquivo `core/config.py` (na raiz do projeto backend) e certifique-se de que a variável `MT5_PATH` está configurada como `None`:
```python
MT5_PATH = None
```
Isso força o Python a se conectar à instância do MT5 que já está aberta na sua tela (na sua sessão de usuário atual), resolvendo o deadlock.

### As janelas fecham sozinhas ao clicar em start.bat
O `start.bat` agora utiliza `cmd /k`, o que significa que se houver algum erro fatal no código (ex: erro de sintaxe no Python ou pacote do Node não encontrado), a janela permanecerá aberta para que você possa ler a mensagem de erro. Verifique o output na janela preta correspondente.
