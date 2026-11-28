# Deploy do Magic Walls no ks4

Guia para quem vai colocar código em produção (pessoa ou agente de IA), sem conhecer o ambiente.
Atualizado em 28/11/2026.

## Resumo rápido

- Produção é **um servidor só, o ks4** (usuário `app`). A API roda num container podman gerenciado
  pelo systemd do usuário; o front é um conjunto de arquivos estáticos servidos pela nginx.
- O jeito suportado de fazer deploy é **um comando**: `deploy/ks4/deploy.sh`.
- O servidor **não tem git**. O script pega o commit do **seu** checkout local (`git archive HEAD`)
  e envia por SSH. Por isso o que importa é o que está no `HEAD` de quem roda.
- Só vai para produção código que já está em `upstream/main` (o `main` do repositório do
  Miqueias). O script recusa o resto. Exceção explícita: `--force`.
- Para rodar de outra máquina é preciso **acesso SSH ao ks4** (usuário `app`, só por chave). O
  Miqueias não precisa de Tailscale: o SSH do ks4 responde pela internet. Ainda falta ele gerar a
  chave e o Breno autorizá-la; veja "Acesso SSH" abaixo. Sem isso nada daqui funciona.
- Hoje quem faz o deploy é o Breno. Se o Miqueias quiser fazer o dele, siga este guia do começo.

```
deploy/ks4/deploy.sh server|front|all [--dry-run] [--yes] [--force] [--skip-tests]
deploy/ks4/deploy.sh rollback server|front
```

## O que roda onde

| Peça | Onde | Como |
|---|---|---|
| API (`cloud_saas`, FastAPI) | ks4, container `localhost/magicwalls-cloud-saas:latest` | serviço systemd de usuário `magicwalls-cloud`, porta `127.0.0.1:6201` (dentro do container 8090) |
| Front (React, `regime-dashboard`) | ks4, `/var/www/magicwalls-app` | arquivos estáticos; a nginx faz `try_files $uri /index.html` (SPA) |
| nginx | ks4, `/etc/nginx/sites-available/profit` | **só root edita** (vps-12/Breno); roteia `/api/`, `/auth/`, `/api/v1/admin/` (com limite de taxa), `/m/` para a API e o resto para o front |
| Dados da API | `/home/app/magicwalls-cloud/data` (volume `/data` do container) | sqlite; o **store de sessões e dias guardados é em memória** |
| Segredos da API | `/home/app/magicwalls-cloud/.env` | **não está no repositório e nunca deve ser impresso**; é lido pelo serviço (`--env-file`) |
| Coleta de mercado (Profit/MT5 sob Wine) | ks4, units `magicwalls-server`, `-publisher`, `-gex`, `-sync-native`, `-signals-recorder` | **fora do escopo do deploy**; não são tocados pelo script |

Domínios: `www.magicwalls.com.br` (oficial), `app.magicwalls.com.br` (ainda responde, mesmo app),
`api.magicwalls.com.br`, todos pela Cloudflare até o ks4. O build do front usa base `/` (rotas por
caminho: `/`, `/admin`, `/admin/marketing`, `/admin/users`, `/manual`, `/morning-video`).

## Antes de tudo: acesso SSH ao ks4

O ks4 aceita SSH **pela internet**, na porta 22, usuário `app`, **somente com chave**
(`PasswordAuthentication no`). Quem não está na Tailscale do Breno, como o Miqueias, usa esse
caminho. Não use `www.magicwalls.com.br` como destino: esse nome passa pela Cloudflare, que não
repassa SSH. Use o **endereço IP do servidor, que o Breno envia em particular** (ele não fica
neste repositório; é o IP de origem que a Cloudflare esconde).

O que é preciso:

1. **Uma chave SSH** gerada por quem vai fazer o deploy.
2. **O Breno (ou o vps-12) autorizar a chave pública** no usuário `app` do ks4.
3. **O IP do ks4**, passado em particular pelo Breno.

Passo a passo, na máquina de quem vai fazer deploy:

```bash
# 1. gerar uma chave (ed25519, com senha de proteção)
ssh-keygen -t ed25519 -C "miqueias-deploy-ks4" -f ~/.ssh/id_ed25519_ks4

# 2. mandar ao Breno só a chave PÚBLICA (a linha que termina em .pub), nunca a privada:
cat ~/.ssh/id_ed25519_ks4.pub
```

O Breno adiciona essa linha no ks4 (como `app`, por exemplo pela Tailscale dele, ou como root):

```bash
echo '<conteúdo do .pub>' >> /home/app/.ssh/authorized_keys
chmod 600 /home/app/.ssh/authorized_keys
```

Configuração local do SSH. O padrão do script é `DEPLOY_HOST=app@ks4`, então o nome `ks4` precisa
existir no seu `~/.ssh/config`:

```
# ~/.ssh/config
Host ks4
    HostName <IP-DO-KS4 que o Breno enviou>
    User app
    IdentityFile ~/.ssh/id_ed25519_ks4
    IdentitiesOnly yes
```

Na **primeira conexão** o SSH mostra a impressão digital do servidor e pergunta se confia. Só
responda `yes` se bater com esta (ED25519):

```
SHA256:kLm08AOeZnB3SufE0dtdx1sltyJD0gQ2ZuCxiQvmlvg
```

Teste: `ssh ks4 'podman --version && systemctl --user is-active magicwalls-cloud'` deve imprimir a
versão do podman e `active`. Se pedir senha, der `Permission denied (publickey)` ou timeout, o
passo 1 ou o 2 não está pronto, ou o IP está errado. Não tente contornar com root nem com outro
usuário.

Por que o IP de origem não fica neste repositório:
- `www`, `app` e `api.magicwalls.com.br` passam pela Cloudflare, que esconde o IP real do ks4.
  Quem souber esse IP consegue falar direto com o servidor, **sem passar pela Cloudflare**.
- A nginx do ks4 limita as rotas de administração por visitante usando o cabeçalho
  `CF-Connecting-IP`. Falando direto com o IP de origem, esse cabeçalho pode ser forjado e o
  limite de taxa deixa de proteger. O limite é um freio contra tentativa casual, não proteção forte.
- Por isso o IP vai por mensagem do Breno para quem precisa dele e não é commitado, nem colado em
  PR, issue ou chat público.

O que foi verificado no ks4 em 28/11/2026 (para quem for diagnosticar acesso):
- O `sshd` escuta em `0.0.0.0:22` e `[::]:22`.
- `PasswordAuthentication no` (só chave) e `PermitRootLogin yes` (login de root segue exclusivo
  de quem administra o servidor; o deploy nunca usa root).
- A porta 22 respondeu pelo IPv4 público a partir de uma rede comum. O IPv6 do servidor não foi
  testado (a rede de teste não tinha rota IPv6); use o IPv4 que o Breno enviar.
- A impressão digital ED25519 acima é a do host nesse dia. Se mudar sem aviso (reinstalação do
  servidor ou ataque), pare e pergunte ao Breno antes de aceitar.

Observações de segurança:
- A chave privada nunca sai da máquina de quem a gerou, e o `.pub` é o único que circula.
- O usuário `app` também administra os serviços de coleta do ks4, então a chave dá acesso a mais
  do que o deploy. Quem autoriza pode restringir por origem, colocando na linha do
  `authorized_keys` o prefixo `from="<IP de quem vai conectar>" ` antes da chave.
- Se o Miqueias entrar um dia na Tailscale do Breno, o `HostName` pode ser trocado pelo IP
  tailnet do ks4 (o Breno informa); o resto do guia não muda.

## O que a máquina precisa ter

- `git`, `ssh`, `curl`, `tar` (e a chave SSH autorizada, veja acima)
- Node.js e npm (para o front; o script roda `npm ci` e `node build-saas.mjs`)
- Python 3.12+ com as dependências do projeto, para os testes do servidor
  (`pip install -r cloud_saas/requirements.txt pytest`). Se o Python certo não for o `python3`
  do PATH: `PYTHON=/caminho/do/python deploy/ks4/deploy.sh ...`
- Checkout do repositório com os remotos configurados. O script espera o remoto `upstream`
  apontando para `miqueiasa1/wdowin_pairtrading`. Se o seu remoto tiver outro nome, use
  `MAIN_REF=<remoto>/main`.

## Fluxo normal de deploy

1. **Integre no `main`.** Abra PR para `main`, revise, faça o merge. Depois:
   ```bash
   git checkout main && git pull upstream main
   ```
2. **Veja o plano sem executar nada:**
   ```bash
   deploy/ks4/deploy.sh all --dry-run
   ```
   Confere o repositório, o acesso SSH, o horário e mostra o que seria feito.
3. **Execute.** O script pede confirmação (`--yes` pula a pergunta):
   ```bash
   deploy/ks4/deploy.sh all          # API + front
   deploy/ks4/deploy.sh server       # só a API
   deploy/ks4/deploy.sh front        # só o front
   ```
4. **Confira no navegador** (veja "Verificação depois do deploy").

Escolha do alvo: mudou `cloud_saas/` ou os dois arquivos do motor
(`core/div_engines_view.py`, `research/div_master/especialistas/modulo.py`) → `server`.
Mudou `regime-dashboard/` → `front`. Na dúvida, `all`.

## Regras que o script impõe (e por quê)

| Regra | Por quê |
|---|---|
| Árvore limpa nos caminhos de produção | o build vem do `HEAD`; alteração solta não iria para o ar e confundiria quem lê |
| `HEAD` já enviado a um remoto | outra pessoa precisa conseguir reproduzir o que está no ar |
| `HEAD` dentro de `upstream/main` (`MAIN_REF`) | evita deploy de checkout antigo que desfaz o que está em produção. `--force` só para hotfix de branch, e avise o outro |
| Testes passam (pytest do servidor, `node --test` do front) | `--skip-tests` existe, mas só use com motivo |
| **Servidor não reinicia em dia útil das 09:00 às 18:40 (BRT)** | o store é em memória: reiniciar apaga os dias guardados e deixa o painel vazio até o produtor reenviar. `--force` só em emergência. O front não reinicia a API e pode ser enviado a qualquer hora |
| Trava no ks4 (`~/.mw-deploy.lock`) | impede dois deploys ao mesmo tempo |
| Registro em `~/deploy.log` no ks4 | quem, qual commit e quando |

## O que o script faz

**Servidor**
1. `git archive HEAD` de `cloud_saas`, `core/div_engines_view.py` e
   `research/div_master/especialistas/modulo.py` enviado por pipe a um diretório temporário no ks4.
2. `podman build -f cloud_saas/Dockerfile` gera `localhost/magicwalls-cloud-saas:<AAAAMMDD-HHMM>-<sha>`.
3. Teste de fumaça: sobe o container em `127.0.0.1:18090` (o app escuta na **8090** dentro do
   container) e exige `/health` = 200 e `POST /auth/login` com corpo vazio = 422.
4. Troca: a tag `latest` atual vira `previous`, a nova vira `latest`, `systemctl --user restart
   magicwalls-cloud`. Espera até 30 s por `/health` = 200; se não vier, **volta sozinho** para
   `previous`.
5. Confere `https://www.magicwalls.com.br/api/health`.

**Front**
1. `git archive HEAD regime-dashboard` em diretório temporário local, `npm ci`, `node build-saas.mjs`
   (gera `dist-saas/`; o `index.html` precisa referenciar `/assets/...`).
2. Backup `cp -a /var/www/magicwalls-app ~/web-backup-<AAAAMMDD-HHMM>` no ks4.
3. Envia por `tar` primeiro tudo menos `index.html`, depois o `index.html` (quem estiver carregando
   a página não recebe um index que aponta para arquivos que ainda não chegaram).
4. Confere `/`, `/admin`, `/admin/marketing`, `/manual`, `/morning-video` = 200 e que o bundle
   novo é servido.

O script **não apaga** backups antigos do front; avisa quando passam de oito. Apague à mão os
mais velhos (`~/web-backup-*` no ks4) quando quiser.

## Rollback

```bash
deploy/ks4/deploy.sh rollback server   # troca latest <-> previous e reinicia (mesmas regras de horário)
deploy/ks4/deploy.sh rollback front    # restaura o backup mais recente de ~/web-backup-*
```

O rollback do servidor só existe depois de pelo menos um deploy feito pelo script (cria a tag
`previous`). Rodar de novo volta para a versão de antes do rollback (é uma troca).

## Verificação depois do deploy

- `curl -s https://www.magicwalls.com.br/api/health` → `{"ok":true,...}`
- Abrir `https://www.magicwalls.com.br/`, dar `Ctrl+Shift+R` (abas abertas antes do deploy seguem
  com o JS antigo; o `index.html` não manda `Cache-Control`).
- Logado como admin: `/admin/users` e `/admin/marketing` carregam sem "HTTP 403".
- No ks4: `ssh ks4 'tail -5 ~/deploy.log'` mostra o deploy registrado.
- Admin pode ter até 10 sessões simultâneas; usuário comum tem 1 (o segundo login derruba o primeiro).

## Passo a passo manual (só se o script não puder ser usado)

Equivale ao que o script faz; use quando precisar entender ou consertar algo. Rode a partir da raiz
do repositório, com o `HEAD` que quer publicar.

```bash
TAG=$(date +%Y%m%d-%H%M)-$(git rev-parse --short HEAD)

# servidor
D=$(ssh app@ks4 'mktemp -d -p /home/app mw-deploy.XXXXXXXX')
git archive HEAD cloud_saas core/div_engines_view.py research/div_master/especialistas/modulo.py \
  | ssh app@ks4 "tar -x -C $D"
ssh app@ks4 "cd $D && podman build -q -t localhost/magicwalls-cloud-saas:$TAG -f cloud_saas/Dockerfile ."
# fumaça: -p 127.0.0.1:18090:8090 (porta do container é 8090) e conferir /health
ssh app@ks4 "podman tag localhost/magicwalls-cloud-saas:latest localhost/magicwalls-cloud-saas:previous &&
             podman tag localhost/magicwalls-cloud-saas:$TAG localhost/magicwalls-cloud-saas:latest &&
             systemctl --user restart magicwalls-cloud"
ssh app@ks4 'curl -s http://127.0.0.1:6201/health'
# se falhar: tag previous -> latest e restart

# front
cd regime-dashboard && npm ci && node build-saas.mjs
ssh app@ks4 'cp -a /var/www/magicwalls-app ~/web-backup-$(date +%Y%m%d-%H%M)'
tar -C dist-saas --exclude=index.html -cf - . | ssh app@ks4 'tar -C /var/www/magicwalls-app -xf -'
tar -C dist-saas -cf - index.html | ssh app@ks4 'tar -C /var/www/magicwalls-app -xf -'
```

Apague o diretório temporário do ks4 (`$D`, caminho literal impresso pelo `mktemp`) quando terminar.

## O que NÃO é do deploy (peça a quem administra o servidor)

- **nginx**: `/etc/nginx/sites-available/profit` e `/etc/nginx/conf.d/magicwalls-ratelimit.conf`
  são do root. Já estão liberados `/api/v1/admin/` (com limite de 10 req/s por visitante) e
  `/m/` (mídia que a Meta busca). `/internal/` segue restrito a loopback e Tailscale. O limite do
  corpo de requisição é 10 MB (`snippets/magicwalls-api.conf`) e precisa subir para vídeo.
  Backup da config anterior: `/root/profit.nginx.bak-20261128`.
- **Containers de coleta e o terminal `mt5-a`**: reiniciar é combinado com o Breno (é o terminal
  que o Miqueias usa).
- **Segredos**: `~/magicwalls-cloud/.env` (chave de admin, token do Instagram etc.). Nunca copie
  valores para o repositório, para o chat nem para a saída do terminal.
- **DNS e Cloudflare**.

## Problemas comuns

| Sintoma | Causa e saída |
|---|---|
| `ERRO: já existe um deploy em andamento` | trava ativa ou órfã. Veja quem: `ssh ks4 'cat ~/.mw-deploy.lock/info'`. Se ninguém está rodando: `ssh ks4 'rm -f ~/.mw-deploy.lock/info && rmdir ~/.mw-deploy.lock'` |
| `o commit ... não está em upstream/main` | faça o merge no `main`, ou `--force` para hotfix (e avise o outro) |
| `sem acesso SSH a app@ks4` | falta chave autorizada, IP errado no bloco `Host ks4` ou o bloco não existe. Veja "Acesso SSH" |
| `pregão aberto ... reiniciar a API apaga os dias guardados` | espere depois das 18:40 BRT ou, em emergência, `--force` |
| Teste de fumaça falhou | nada foi trocado; veja `podman logs mw-smoke` no ks4 e corrija o código |
| `a API não ficou saudável; voltou para a imagem anterior` | a imagem nova subiu mas `/health` não respondeu em 30 s; o serviço já voltou. Veja `journalctl --user -u magicwalls-cloud -n 80` |
| Painel vazio ou gráfico sem dia depois de reiniciar a API | store em memória: os dias voltam quando o produtor reenviar |
| Tela de Logins/Marketing com `HTTP 403` | regra da nginx; conferir `location /api/v1/admin/` com quem administra o servidor |
| Aba antiga mostra tela velha | `Ctrl+Shift+R` |

## Testar localmente antes do deploy

- API: `uvicorn --factory cloud_saas.app:create_app --host 127.0.0.1 --port 8100`, com banco e
  mídia em diretório próprio (variáveis `MW_DB_PATH`, `MW_MARKETING_DIR`). Por padrão o marketing
  fica em simulação; `MW_MARKETING_LIVE=1` liga a publicação real no Instagram (não ligue sem
  combinar com o Breno).
- Front: build com `base: "/"` e um servidor estático com fallback para `index.html`
  (as rotas são por caminho). Porta usada em desenvolvimento: 8101.
- Use uma conta de teste própria para logar; o login de outra pessoa pode derrubar a sessão dela
  (usuário comum tem sessão única).
- Testes: `python -m pytest tests/test_cloud_saas.py tests/test_admin_multi_session.py tests/test_admin_session.py tests/test_marketing.py tests/test_marketing_drafts.py` e, em `regime-dashboard/`, `npm test`.

## Estado atual de produção e pendências (28/11/2026)

**O que está no ar.** O commit `efa38d4` da branch `feature/marketing-admin` (API e front, deploy
de 28/11 por volta de 00:25 BRT). O `main` do repositório do Miqueias ainda **não tem** esse
código: o PR #2 (`miqueiasa1/wdowin_pairtrading`, branch `feature/marketing-admin` para `main`)
espera revisão. Foi enviado por `origin` e `upstream`. No ks4 as imagens são `latest` (a de agora)
e `previous` (a de antes da sessão múltipla do admin).

**Risco enquanto o PR #2 não for integrado.** Quem rodar o deploy a partir do `main` antigo
colocaria em produção o código **sem** as rotas por caminho (`/admin/marketing`...), sem a sessão
múltipla do admin e sem o Marketing novo. A trava do `deploy.sh` (`MAIN_REF`) existe para isso e,
até o merge, **bloqueia qualquer deploy a partir da branch**; só passa com `--force`. Depois do
merge, o fluxo normal (acima) volta a valer sem `--force`.

**Pendências de quem faz o quê**

| Quem | O que falta |
|---|---|
| Miqueias | revisar e fazer o merge do PR #2 no `main`; gerar a chave SSH e mandar o `.pub` ao Breno |
| Breno | enviar ao Miqueias o IP do ks4 em particular; adicionar a chave dele em `/home/app/.ssh/authorized_keys` (opcionalmente com `from="..."`) |
| vps-12 / quem tem root | subir o `client_max_body_size` (hoje 10 MB) quando entrar vídeo; decidir se `app.magicwalls.com.br` redireciona para `www`; considerar fechar a origem do ks4 só aos IPs da Cloudflare (resolve o limite de taxa forjável) |
| Ainda sem dono definido | persistência do store no ks4 (hoje é memória: cada restart apaga os dias guardados); limpeza dos `~/web-backup-*` antigos (o script só avisa) |

**Quem faz o deploy hoje.** O Breno. O Miqueias pode passar a fazer o dele seguindo este guia
depois de ter a chave autorizada. Se os dois fizerem deploy, avisem um ao outro antes (a trava do
ks4 só evita deploys simultâneos, não conflito de versão), e use sempre o `main`.

## Regras de desenvolvimento que valem também no deploy

- Nomes de código, rotas e ids em inglês; texto em português só na interface.
- A URL é sempre o estado da página (caminho = recurso, query = filtro/aba/data).
- Mensagens de commit e descrições de PR que vão para remoto público não mencionam ferramentas
  de IA e passam por revisão de texto antes de publicar.
