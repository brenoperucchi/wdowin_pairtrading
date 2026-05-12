# Migração `bar_history` SQLite → TimescaleDB — Design contract (TASK-14, Slice 0)

> **Status:** draft para revisão.
> Este documento é o entregável do Slice 0. **Nenhum código é alterado neste slice.** Slice 1+ só inicia após aprovação.

---

## 1. Escopo e fora-de-escopo

**Dentro:** mover apenas a tabela `bar_history` (em `trades.db`) para um Postgres com extension TimescaleDB. Tudo o que envolve `bar_history`: schema, UPSERT, leituras de janelas de EG/rho/beta, replay.

**Fora:**

- `matador_ops` (trades fechados) permanece em SQLite.
- `runtime_config`, `replays/`, `audits/`, `reports/`, `beta_ultimo.json` permanecem como estão.
- Backtests em `research/` não tocam `bar_history` (zero referências confirmadas via `grep`). Sem impacto.
- Postgres é **opcional** até cutover. Default `BAR_HISTORY_BACKEND=sqlite` mantém o estado atual.

## 2. Inventário atual (verdade SQLite)

```
$ sqlite3 trades.db ".schema bar_history"
CREATE TABLE bar_history (
    timestamp   INTEGER PRIMARY KEY,   -- epoch seconds (UTC)
    date_str    TEXT NOT NULL,         -- "YYYY-MM-DD" (B3 local date)
    bar_time    TEXT NOT NULL,         -- "HH:MM" (B3 local)
    win_price   REAL,
    wdo_price   REAL,
    di_price    REAL,
    spread_wdo  REAL,
    spread_di   REAL,
    z_wdo       REAL,
    z_di        REAL,
    nwe_center  REAL,
    nwe_upper   REAL,
    nwe_lower   REAL,
    nwe_is_up   INTEGER,
    -- adicionados via ALTER:
    eg_pvalue       REAL,
    rho             REAL,
    rho_level       INTEGER,
    beta_value      REAL,
    beta_delta_pct  REAL
);
```

- **54.293 linhas** (2024-06-05 → 2026-05-11), `timestamp` épocas Unix em segundos (`1717605900` → `1778534400`).
- ~482 dias úteis × ~76 barras M5 ≈ 36k esperado; sobra vem de janelas de pré-abertura/after-market amostradas pelo backfill.

## 3. Schema Postgres (proposta)

```sql
CREATE TABLE IF NOT EXISTS bar_history (
    timestamp       BIGINT      NOT NULL,            -- epoch seconds (UTC), idêntico ao SQLite
    date_str        TEXT        NOT NULL,
    bar_time        TEXT        NOT NULL,
    win_price       DOUBLE PRECISION,
    wdo_price       DOUBLE PRECISION,
    di_price        DOUBLE PRECISION,
    spread_wdo      DOUBLE PRECISION,
    spread_di       DOUBLE PRECISION,
    z_wdo           DOUBLE PRECISION,
    z_di            DOUBLE PRECISION,
    nwe_center      DOUBLE PRECISION,
    nwe_upper       DOUBLE PRECISION,
    nwe_lower       DOUBLE PRECISION,
    nwe_is_up       SMALLINT,                        -- 0/1; SMALLINT em vez de BOOLEAN p/ paridade com SQLite
    eg_pvalue       DOUBLE PRECISION,
    rho             DOUBLE PRECISION,
    rho_level       SMALLINT,
    beta_value      DOUBLE PRECISION,
    beta_delta_pct  DOUBLE PRECISION,
    PRIMARY KEY (timestamp)
);
```

### 3.1 Por que `timestamp BIGINT` (não `TIMESTAMPTZ`)

- Código atual passa epoch int em **toda** a API (`save_bar_history(timestamp, ...)`, `WHERE timestamp >= ?`, `ORDER BY timestamp`, `WHERE timestamp = ?`).
- Trocar para `TIMESTAMPTZ` exigiria conversão `int ↔ datetime` em todos os call sites do wrapper.
- TimescaleDB suporta partição em `BIGINT` desde que `chunk_time_interval` seja dado em **segundos** (mesma unidade do dado).
- **Custo da escolha:** consultas ad-hoc em `psql` precisam `to_timestamp(timestamp) AT TIME ZONE 'America/Sao_Paulo'` para legibilidade. Aceitável.
- **Mitigação opcional (não-bloqueante):** coluna gerada
  ```sql
  ALTER TABLE bar_history
    ADD COLUMN bar_ts TIMESTAMPTZ GENERATED ALWAYS AS (to_timestamp(timestamp)) STORED;
  CREATE INDEX ON bar_history (bar_ts);
  ```
  fica fora do path de escrita do wrapper, só para consultas humanas. Decisão de incluir agora ou depois fica registrada no Slice 0.

### 3.2 Hypertable + chunk

```sql
SELECT create_hypertable(
    'bar_history',
    'timestamp',
    chunk_time_interval => 2592000,   -- 30 dias em segundos
    if_not_exists       => TRUE
);
```

- Chunk de 30 dias → ~76 barras × 21 pregões ≈ **~1.600 linhas por chunk**. Bem dentro do recomendado pela Timescale (centenas a milhares por chunk para workloads desse porte).
- Histórico atual gera ~24 chunks (24 meses). Aceitável.

### 3.3 Índices secundários

```sql
CREATE INDEX IF NOT EXISTS bar_history_date_idx ON bar_history (date_str);
```

`WHERE date_str = ?` é o predicado mais usado (replay por dia, dashboard). Index B-tree simples basta — `date_str` tem ~500 valores distintos.

### 3.4 Compressão

```sql
ALTER TABLE bar_history SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'date_str',
    timescaledb.compress_orderby   = 'timestamp'
);

-- BIGINT time column → compress_after deve ser integer-seconds, não INTERVAL.
-- 7_776_000 = 90 * 86_400. INTERVAL '90 days' falha com
-- `invalid value for parameter compress_after`.
SELECT add_compression_policy('bar_history', BIGINT '7776000', if_not_exists => TRUE);
```

- **`segmentby = date_str`** agrupa linhas do mesmo dia → leituras `WHERE date_str = ?` pulam descompressão de outros dias.
- **`orderby = timestamp`** preserva a ordem natural dentro do segmento → melhora compressão (delta encoding).
- Política automática só comprime chunks com >= 90 dias de idade — preserva a janela quente (EG=2240 barras ≈ 30 dias) sempre descomprimida.
- **Exige edition Community (TSL)** — a Debian Apache strip (`+dfsg`) não inclui o engine de compressão. Ver §13.

### 3.5 Nullability

- Todas as colunas analíticas (`eg_pvalue`, `rho`, …) permanecem `NULL`-able. O wrapper precisa preservar a semântica `COALESCE` do SQLite (ver §4).
- `timestamp`, `date_str`, `bar_time` são `NOT NULL` (já são na prática no SQLite, formalizado aqui).

## 4. Contrato de UPSERT

### 4.1 SQLite atual (`server.py:save_bar_history`)

```sql
INSERT INTO bar_history (...) VALUES (...)
ON CONFLICT(timestamp) DO UPDATE SET
    wdo_price       = COALESCE(bar_history.wdo_price,  excluded.wdo_price),    -- preserva
    di_price        = COALESCE(bar_history.di_price,   excluded.di_price),     -- preserva
    z_di            = COALESCE(excluded.z_di,          bar_history.z_di),      -- SOBRESCREVE
    eg_pvalue       = COALESCE(bar_history.eg_pvalue,  excluded.eg_pvalue),    -- preserva
    rho             = COALESCE(bar_history.rho,        excluded.rho),          -- preserva
    rho_level       = COALESCE(bar_history.rho_level,  excluded.rho_level),    -- preserva
    beta_value      = COALESCE(bar_history.beta_value, excluded.beta_value),   -- preserva
    beta_delta_pct  = COALESCE(bar_history.beta_delta_pct, excluded.beta_delta_pct);
```

> **Asymmetria importante:** `z_di` é o único campo que **sobrescreve** quando o INSERT traz valor não-nulo. Demais campos **preservam** o valor existente. O wrapper Postgres tem que reproduzir essa assimetria exatamente.

### 4.2 Postgres equivalente

```sql
INSERT INTO bar_history (...) VALUES (...)
ON CONFLICT (timestamp) DO UPDATE SET
    wdo_price       = COALESCE(bar_history.wdo_price,  EXCLUDED.wdo_price),
    di_price        = COALESCE(bar_history.di_price,   EXCLUDED.di_price),
    z_di            = COALESCE(EXCLUDED.z_di,          bar_history.z_di),
    eg_pvalue       = COALESCE(bar_history.eg_pvalue,  EXCLUDED.eg_pvalue),
    rho             = COALESCE(bar_history.rho,        EXCLUDED.rho),
    rho_level       = COALESCE(bar_history.rho_level,  EXCLUDED.rho_level),
    beta_value      = COALESCE(bar_history.beta_value, EXCLUDED.beta_value),
    beta_delta_pct  = COALESCE(bar_history.beta_delta_pct, EXCLUDED.beta_delta_pct);
```

Só muda `excluded` (lowercase SQLite) → `EXCLUDED` (uppercase Postgres). PK em `timestamp` = coluna de partição, então a constraint é compatível com hypertable.

### 4.3 UPDATE pontual de colunas (idempotent backfills)

Padrões existentes em scripts:

- `UPDATE bar_history SET z_di = ? WHERE timestamp = ?` (backfill_z_di.py)
- `UPDATE bar_history SET eg_pvalue = ?, rho = ?, ... WHERE timestamp = ?` (backfill_bar_history_indicators.py)

Ambos funcionam idênticos no Postgres — sem mudança sintática.

## 5. Driver / dependências

- **Driver:** `psycopg[binary]==3.x` (psycopg3 sync). Justificativa: server.py e scripts são síncronos; asyncpg adicionaria event-loop sem benefício no path quente atual.
- Adicionado ao `requirements.txt` **apenas após Slice 2** (wrapper depende). Slice 0 só documenta.

## 6. Variáveis de ambiente

| Var | Default | Onde lida | Função |
| --- | --- | --- | --- |
| `BAR_HISTORY_BACKEND` | `sqlite` | wrapper (`core/bar_history_db.py`) | `sqlite` (atual), `dual` (write em ambos, read SQLite), `postgres` (cutover total) |
| `PG_URI` | unset | wrapper | conexão Postgres prod/dev — só usada se backend ≠ `sqlite` |
| `PG_TEST_URI` | unset | testes | conexão para suite de integração; ausente → `pytest.skip()` |
| `BAR_HISTORY_SQLITE_PATH` | `trades.db` | wrapper | mantém o SQLite path configurável (já existe implícito) |

### 6.1 `.env.example`

Entregue no Slice 8 — `/.env.example` no root do repo, versionado (a regra `!.env.example` no `.gitignore` libera o template apesar do bloqueio `.env.*` genérico).

```bash
# Backend de bar_history: sqlite (default) | dual | postgres
BAR_HISTORY_BACKEND=sqlite

# Optional: override the SQLite path (defaults to trades.db).
# BAR_HISTORY_SQLITE_PATH=trades.db

# Postgres + TimescaleDB (necessário se BAR_HISTORY_BACKEND != sqlite)
# PG_URI=postgresql://pairtrading@localhost:5432/pairtrading

# Postgres para testes de integração opt-in
# PG_TEST_URI=postgresql://pairtrading@localhost:5432/pairtrading_test
```

> Segredos reais ficam em `~/.pgpass` ou `.env.local` (já no `.gitignore`). `.env.example` só documenta a chave.

## 7. Rollback

Hard rollback sem deploy:

```bash
export BAR_HISTORY_BACKEND=sqlite
systemctl --user restart pairtrading-server
```

- SQLite mantido vivo (sem `DROP`) até no mínimo 30 dias após cutover bem-sucedido.
- Em modo `postgres`, SQLite fica somente-leitura (escritas vão para PG). Para voltar, env switch restaura o estado anterior — eventuais barras gravadas só no PG durante o intervalo voltam via re-export pelo script do Slice 3.

## 8. Mapeamento de call sites

| Arquivo | Operação | SQL portável? | Notas |
| --- | --- | --- | --- |
| `server.py:init_bar_history` | DDL `CREATE TABLE IF NOT EXISTS` + `ALTER ADD COLUMN` | ⚠️ Postgres não tolera `ALTER ADD COLUMN` em coluna já existente sem `IF NOT EXISTS` | Wrapper aplica DDL via script de bootstrap (Slice 3), não em runtime |
| `server.py:save_bar_history` | UPSERT (§4.1) | ✅ | Único `excluded`/`EXCLUDED` |
| `server.py:load_bar_history` | `SELECT * FROM bar_history WHERE timestamp >= ? ORDER BY timestamp ASC` | ✅ | `SELECT *` exige paridade de colunas (garantida pelo bootstrap) |
| `server.py:_persist_history_payload` | chama `save_bar_history` | ✅ (via wrapper) | |
| `server.py` linha 734 | `SELECT COUNT(*) FROM bar_history` | ✅ | |
| `server.py` linha 1259 | `load_bar_history(days=2)` | ✅ (via wrapper) | |
| `scripts/backfill_bar_history.py` | UPSERT espelhando `save_bar_history` | ✅ | Após Slice 6 chama o wrapper |
| `scripts/backfill_bar_history_indicators.py` | `ALTER`, `SELECT *`, `UPDATE ... WHERE timestamp = ?` | ⚠️ `ALTER` precisa ir para bootstrap | DDL movido p/ Slice 3 |
| `scripts/backfill_z_di.py` | `SELECT timestamp FROM bar_history ... ORDER BY timestamp`, `UPDATE bar_history SET z_di = ? WHERE timestamp = ?` | ✅ | |
| `scripts/replay_execution_timeline.py` | `SELECT * FROM bar_history WHERE date_str = ? ORDER BY timestamp ASC`, `SELECT ... FROM bar_history WHERE date_str <= ? ...` | ✅ | Predicados em `date_str` se beneficiam do index B-tree do §3.3 |
| `scripts/replay_bar_history_to_matador_ops.py` | `SELECT * FROM bar_history WHERE date_str = ?` | ✅ | |
| `scripts/seed_dashboard_demo_trades.py` | `SELECT COUNT(*) FROM bar_history WHERE date_str = ?`, `SELECT MIN/MAX(bar_time) ...` | ✅ | |
| `tests/test_bar_history.py` | DDL + inserts em SQLite in-memory | ✅ continua só SQLite | Unit suite |
| `tests/test_backfill_bar_history_indicators.py` | SQLite | ✅ continua só SQLite | Unit suite |
| `tests/test_replay_execution_timeline.py` | SQLite | ✅ continua só SQLite | Unit suite |

**Veredito:** quase 100% das queries são portáveis sem mudança sintática. Os dois pontos de atrito são DDL (`ALTER ADD COLUMN`) e `SELECT *` (resolvido pelo schema do §3 ser idêntico em ordem de coluna).

`scratch/` e `research/` confirmados sem referências a `bar_history` — fora de escopo.

## 9. Migração / bootstrap (implementação em Slice 3)

Fluxo do `scripts/migrate_bar_history_to_pg.py`:

```
1. Conecta em PG, garante: extension timescaledb, schema, hypertable, índices, política de compressão.
2. Conecta em SQLite (trades.db) read-only.
3. Em transação única no PG, insere em batches de 5k linhas:
   - Default: ON CONFLICT(timestamp) DO NOTHING (idempotente).
   - --force-refresh: ON CONFLICT(timestamp) DO UPDATE SET col = EXCLUDED.col, ... (repara drift).
4. Verifica linha-por-linha via SHA-256 sobre todas as colunas, agrupado por date_str.
5. Imprime relatório: total, dias, primeiro/último ts, tempo. Sai com código 1 se houver drift.
```

### 9.1 Por que content-hash, não apenas COUNT + SUM(timestamp)

A primeira versão do verify usava `COUNT(*) + SUM(timestamp)` por dia. Esse checksum **não detecta drift por célula**: se uma linha já está no Postgres com `z_di`, `rho`, `beta_value` ou preços divergentes do SQLite, `ON CONFLICT DO NOTHING` mantém o valor stale e o checksum continua batendo (timestamps e contagem são idênticos).

Cenário concreto: corrompemos `z_di` de um timestamp no `pairtrading_test`, rodamos a migração — verify imprimiu "OK" e o valor stale ficou no PG. Para cutover de cutover esse silêncio é o pior dos mundos: a migração "passa" enquanto esconde exatamente o tipo de drift que estamos tentando eliminar.

Solução implementada: o verify computa um SHA-256 que **incorpora todas as colunas de todas as linhas**, agrupado por `date_str`. `repr()` em Python serializa floats com round-trip lossless, então SQLite e Postgres produzem bytes idênticos para o mesmo valor. Drift por célula em qualquer coluna muda o hash do dia.

### 9.2 Quando usar `--force-refresh`

- Default permanece `DO NOTHING` para preservar a idempotência (re-rodar a migração não bate Postgres à toa).
- Use `--force-refresh` quando o verify reportar `content hash differs`. Faz `INSERT ... ON CONFLICT DO UPDATE` reescrevendo cada coluna não-PK com o snapshot SQLite.
- Em produção / cutover real, considerar rodar o `--force-refresh` na janela imediatamente anterior ao flip do `BAR_HISTORY_BACKEND` para garantir paridade exata.

## 10. Aceitação do Slice 0

- [ ] Schema do §3 revisado e aprovado.
- [ ] Decisão tomada sobre `bar_ts TIMESTAMPTZ` gerado (incluir agora vs depois).
- [ ] Driver (psycopg3) aprovado.
- [ ] Nomes de env vars do §6 aprovados.
- [ ] Mapeamento do §8 confere com o entendimento do usuário (sem call site faltando).
- [ ] Nenhuma linha de código foi alterada.

## 11. Próximo passo após aprovação

Slice 1 — `docs/migration_bar_history_timescale.md#install` + `scripts/setup_timescale_wsl.sh` idempotente para subir Postgres + TimescaleDB no WSL. **Não toca a app.**

## 12. Install (Slice 1)

> **Atualização sobre o §3:** o WSL deste projeto já tem **PostgreSQL 17.5** instalado (cluster `17/main`, parado). Debian trixie distribui `postgresql-17-timescaledb 2.19.3+dfsg-1+deb13u1` no repo `main` — **sem necessidade de adicionar o apt repo do Timescale**.
>
> Trocamos a meta de "PG 16" do plano original para **PG 17** para evitar instalar uma segunda versão. Schema e contratos da §3–§4 permanecem idênticos (BIGINT + hypertable + COALESCE).

### 12.1 Pré-requisitos

- Debian/Ubuntu WSL com `postgresql-17` instalado (`dpkg -s postgresql-17`).
- `sudo` disponível.
- Porta `5432` livre.

### 12.2 Provisionamento idempotente

```bash
sudo bash scripts/setup_timescale_wsl.sh
```

O script faz, em sequência (e cada passo checa estado primeiro — pode rodar de novo sem efeito):

1. `apt-get install postgresql-17-timescaledb` se ausente.
2. Edita `/etc/postgresql/17/main/postgresql.conf` adicionando `shared_preload_libraries = 'timescaledb'` (backup `.bak-<epoch>` automático).
3. `pg_ctlcluster 17 main start` (ou `restart` se o passo 2 mudou config).
4. `CREATE ROLE pairtrading LOGIN PASSWORD 'pairtrading_dev'` se não existir.
5. `CREATE DATABASE pairtrading OWNER pairtrading` e `pairtrading_test` se não existem.
6. `CREATE EXTENSION IF NOT EXISTS timescaledb` nos dois DBs.
7. Imprime o resumo com os `PG_URI` / `PG_TEST_URI` sugeridos.

Overrides via env: `DB_USER`, `DB_PASSWORD`, `DB_MAIN`, `DB_TEST`, `PG_VER`, `PG_CLUSTER`.

### 12.3 Validação manual

```bash
sudo -u postgres psql -d pairtrading -c "SELECT extname, extversion FROM pg_extension;"
# deve listar:  timescaledb | 2.19.3

sudo -u postgres psql -d pairtrading -c \
  "SELECT current_database(), current_user, version();"
```

### 12.4 Segurança / credenciais

- A senha default `pairtrading_dev` é dev-only. Em qualquer ambiente onde haja acesso de rede, exportar `DB_PASSWORD=<senha forte>` antes de rodar o script e registrar em `~/.pgpass`.
- `.env.example` (Slice 8) lista apenas o **nome** das variáveis (`PG_URI`, `PG_TEST_URI`); senhas reais ficam em `.env.local` (já ignorado).
- `pg_hba.conf` padrão do Debian usa `peer` no socket Unix e `scram-sha-256` no TCP local — suficiente para dev local.

### 12.5 Rollback

`BAR_HISTORY_BACKEND=sqlite` (default) mantém a app totalmente desacoplada do Postgres. Os DBs criados ficam ociosos até o Slice 2 entregar o wrapper. Para remover:

```bash
sudo -u postgres dropdb pairtrading_test
sudo -u postgres dropdb pairtrading
sudo -u postgres dropuser pairtrading
sudo apt-get remove postgresql-17-timescaledb
```

(O script de install não chama nenhum dos comandos acima — destruição é sempre manual.)

---

### Pontos abertos para confirmação do usuário

1. **`bar_ts` gerado:** incluir já no schema inicial ou adicionar só se virar necessário em consulta ad-hoc?
2. **`psycopg3` vs `asyncpg`:** confirmar sync (psycopg3). asyncpg só faz sentido se o server.py migrar para async em outra trilha.
3. **`compress_segmentby`:** `date_str` é a escolha óbvia para o predicado mais comum; alguma janela de leitura adicional que devêssemos otimizar (ex.: por mês)?
4. **Bootstrap em DDL:** preferência de gerenciar schema via `scripts/migrate_bar_history_to_pg.py` apenas, ou também via Alembic/Flyway? (Recomendação: script simples; volume de DDL é mínimo.)

---

## 13. TSL (Community) edition — pré-requisito de compressão (Slice 3)

**O que descobrimos durante o Slice 3:** a Debian trixie distribui o pacote `postgresql-17-timescaledb 2.19.3+dfsg-1+deb13u1`, que é a **Apache 2.0 edition**. Ela retira o engine TSL: `ALTER TABLE ... SET (timescaledb.compress, ...)` e `add_compression_policy(...)` retornam:

```
FeatureNotSupported: functionality not supported under the current "apache" license
```

Sem compressão, perdemos o benefício prático mais visível (linhas mais antigas que 90 dias ficam 5–10× maiores em disco) e o agendador interno. A política de compressão é parte do contrato do §3.4 e do critério de aceitação.

**Decisão (2026-05-12):** instalar a **Community/TSL edition** do repo `packagecloud.io/timescale/timescaledb`. Script: `scripts/setup_timescale_tsl.sh`.

### 13.1 Diferença entre edições

| Feature | Debian `+dfsg` (Apache) | Timescale TSL (Community) |
| --- | --- | --- |
| Hypertables / chunks | ✅ | ✅ |
| Continuous aggregates | parcial | ✅ |
| **Compressão colunar** | ❌ | ✅ |
| **Job scheduler (policies)** | ❌ | ✅ |
| Retention policy | ❌ | ✅ |
| Licença | Apache 2.0 | Timescale License (source available, gratuita para uso interno) |

### 13.2 Procedimento (one-shot)

```bash
sudo bash scripts/setup_timescale_tsl.sh
```

O script:

1. Adiciona o repo `packagecloud.io/timescale/timescaledb` para o codename do Debian detectado, com fallback para `bookworm`.
2. Remove `postgresql-17-timescaledb` (Apache) se presente.
3. Instala `timescaledb-2-postgresql-17` (TSL, atualmente 2.26.4).
4. Reinicia o cluster.
5. Tenta `ALTER EXTENSION timescaledb UPDATE` em cada DB. **Se o loader não conseguir abrir o `.so` da versão antiga** (cenário típico quando se pula da `2.19.3` para `2.26.x` sem versão intermediária instalada), o script aborta com instruções para `ALLOW_DESTRUCTIVE_UPGRADE=1`.
6. Com a flag: `DROP DATABASE ... WITH (FORCE)` + `CREATE DATABASE` + `CREATE EXTENSION timescaledb` em cada DB.

### 13.3 Caveats

- **Recovery destrutivo:** se a extensão estiver presa em uma versão cujo `.so` foi removido, **o único caminho é dropar o database**. Isso vale porque o TimescaleDB faz dlopen na conexão, antes do primeiro `SELECT`. Para essa instalação dev (DBs ainda vazios fora de `bar_history`), aceitável. **Em produção** o caminho seria instalar uma versão intermediária via apt pin antes de rodar `ALTER EXTENSION UPDATE`.
- **`shared_preload_libraries`:** ambos os pacotes usam `'timescaledb'` — não precisa re-patchar `postgresql.conf` na troca.
- **`compress_after` em integer-seconds:** ver §3.4. INTERVAL falha para hypertables com coluna de tempo BIGINT.

### 13.4 Verificação

```bash
sudo -u postgres psql -d pairtrading_test -c "SHOW timescaledb.license;"
# esperado:  timescale   (não  apache)

PG_URI="postgresql://pairtrading:pairtrading_dev@localhost:5432/pairtrading_test" \
python3 scripts/migrate_bar_history_to_pg.py --source-db trades.db
# esperado:  "OK — totals + per-date checksums match"
```

## 14. Slice 4 — dual-write live (`BAR_HISTORY_BACKEND=dual`)

Após o Slice 3 (snapshot one-shot), o `server.py` agora espelha cada bar para Postgres em tempo real **quando** `BAR_HISTORY_BACKEND=dual`. SQLite continua **autoritativo** — reads (`load_bar_history`, `/api/history`) ainda vêm dele. O switch para Postgres como source-of-truth é o Slice 5.

### 14.1 O que mudou

- `server.py:init_bar_history` → após criar a tabela em SQLite, chama `bhdb.init_schema(backend="postgres")` quando o backend ativo é `dual` ou `postgres`. Falha (e.g. `PG_URI` ausente) só loga `[ERRO PG]`, não levanta.
- `server.py:save_bar_history` → após o `INSERT ... ON CONFLICT` em SQLite, chama `bhdb.upsert_bar(row, backend="postgres")` quando backend == `dual` **e somente se o commit SQLite teve sucesso** (`sqlite_ok` guard). Isso evita inserir em PG uma barra que SQLite (source-of-truth) rejeitou. Exceções no path PG são engolidas com log `[ERRO PG] dual-write bar_history ts=...`.
- O wrapper (`core/bar_history_db.py`) aplica em PG **exatamente** o mesmo contrato de UPSERT do §4 — `z_di` overwrite, demais COALESCE (preserva first non-NULL).
- Default (`BAR_HISTORY_BACKEND` unset) é byte-equivalente ao baseline pré-TASK-14.

### 14.2 Modo de falha tolerado

A poll loop **não pode** parar se o Postgres cair. Por design o dual-write captura toda exceção do wrapper e segue adiante mantendo SQLite como verdade. Isso significa que durante uma janela de PG-down, o Postgres acumula gap — o Slice 8 (cron/manual de paridade) precisa lidar com isso via `migrate_bar_history_to_pg.py --force-refresh` agendado.

### 14.3 Como ativar / desativar em dev

```bash
# Ativa espelho live:
export BAR_HISTORY_BACKEND=dual
export PG_URI="postgresql://pairtrading:pairtrading_dev@localhost:5432/pairtrading"
systemctl --user restart pairtrading-server.service

# Reverte (volta a baseline):
unset BAR_HISTORY_BACKEND
systemctl --user restart pairtrading-server.service
```

### 14.4 Smoke test manual

Com PG levantado e o servidor em modo `dual`, depois de pelo menos uma barra M5 fechada:

```bash
sqlite3 trades.db "SELECT COUNT(*), MAX(timestamp) FROM bar_history;"
PGPASSWORD=pairtrading_dev psql -h localhost -U pairtrading -d pairtrading \
    -c "SELECT COUNT(*), MAX(timestamp) FROM bar_history;"
# esperado: ambos retornam o mesmo COUNT e o mesmo MAX(timestamp).
```

### 14.5 Cobertura de teste

`tests/test_bar_history.py` (novos casos):

- `test_save_bar_history_default_backend_skips_pg` — sem env, `bhdb.upsert_bar`/`init_schema` nunca são chamados.
- `test_save_bar_history_dual_backend_mirrors_to_pg` — com `dual`, recebe a row com **todas as 19 colunas** preenchidas via `kwargs={"backend": "postgres"}`.
- `test_save_bar_history_dual_pg_failure_does_not_break_sqlite` — exceção em `bhdb.upsert_bar` apenas loga `[ERRO PG]`; SQLite é gravado normalmente.

## 15. Slice 5 — read cutover (`BAR_HISTORY_BACKEND=postgres`)

Slice 5 troca o **read path** em `server.py` para o hypertable. Daqui em diante, `BAR_HISTORY_BACKEND=postgres` faz a app inteira ler de Postgres; `dual` e `sqlite` continuam lendo de SQLite (o wrapper já cuidava disso em `_read_backend`).

**Importante:** writes continuam indo para **ambos** backends em modo `postgres` — não só para PG. A diferença entre `dual` e `postgres` é só o read path. Isso preserva rollback por env var (basta voltar para `dual` ou `sqlite` que SQLite ainda tem as barras mais recentes) e evita a janela de cutover quebrada onde reads vão para PG enquanto writes ficam só em SQLite.

| backend  | write SQLite | write PG | read     |
|----------|--------------|----------|----------|
| `sqlite` | ✅           | —        | SQLite   |
| `dual`   | ✅           | ✅       | SQLite   |
| `postgres` | ✅         | ✅       | Postgres |

### 15.1 O que mudou

- `server.py:save_bar_history` → o guard de dual-write agora é `bhdb.get_backend() in ("dual", "postgres")`. Sem isso, depois do cutover read PG ficaria stale (reads no PG, writes só em SQLite).
- `server.py:load_bar_history` → quando `bhdb.get_backend() == "postgres"`, busca rows via `bhdb.select_window(days=days, backend="postgres")` em vez de abrir SQLite. O loop subsequente é backend-agnostic (rows tanto de SQLite quanto de PG são `dict` com as mesmas chaves).
- `server.py:do_backfill_if_empty` → em modo `postgres`, o `COUNT(*)` passa por `bhdb.count_rows(backend="postgres")` em vez de `sqlite3.connect("trades.db")`.
- `db_path` continua sendo aceito como parâmetro (tests usam `tmp_path`), mas é **ignorado** pelas leituras em modo `postgres`. Writes ainda gravam na SQLite indicada por `db_path`.

### 15.2 Como ativar o cutover read

```bash
# Pré-requisito: ter rodado dual-write (Slice 4) por uma janela suficiente
#   para PG estar com paridade contra SQLite, idealmente confirmada por
#   `scripts/migrate_bar_history_to_pg.py --no-verify-headers-only` (ou
#   re-rodar a migração com --force-refresh).

export BAR_HISTORY_BACKEND=postgres
export PG_URI="postgresql://pairtrading:pairtrading_dev@localhost:5432/pairtrading"
systemctl --user restart pairtrading-server.service

# Rollback imediato em caso de divergência:
export BAR_HISTORY_BACKEND=dual   # ou sqlite
systemctl --user restart pairtrading-server.service
```

### 15.3 Cobertura de teste

Sem PG (sempre roda):
- `test_load_bar_history_default_unaffected_by_wrapper` — sem env, `bhdb.select_window` não é chamado.
- `test_do_backfill_if_empty_uses_postgres_count` — modo `postgres` roteia `COUNT(*)` para `bhdb.count_rows(backend="postgres")`.
- `test_save_bar_history_mirrors_to_pg_when_backend_dual_or_postgres` (parametrizado `dual`/`postgres`) — **regression do cutover**: em ambos modos, `bhdb.upsert_bar(backend="postgres")` é invocado E o SQLite também é gravado. Garante que postgres mode não vira write-only-to-SQLite.
- `test_save_bar_history_pg_failure_does_not_break_sqlite` (parametrizado) — em ambos modos, PG falha → SQLite continua coerente.
- `test_save_bar_history_skips_pg_when_sqlite_fails` (parametrizado) — em ambos modos, SQLite falha → PG não é tocado (preserva parity).

Gated em `PG_TEST_URI` (skip clean quando ausente):
- `test_load_bar_history_reads_from_postgres_when_backend_postgres` — seed via wrapper, lê via `load_bar_history(db_path="/ghost.db")`; rows vêm do PG, db_path é ignorado.
- `test_load_bar_history_dual_still_reads_from_sqlite` — em modo `dual`, leitura continua na SQLite (preserva a baseline durante o período dual).

### 15.4 Não escopo (próximas slices)

- Scripts secundários (`scripts/backfill_bar_history_indicators.py`, `scripts/replay_bar_history_to_matador_ops.py`, `scripts/seed_dashboard_demo_trades.py`) ainda leem SQLite direto. Slice 7 troca o restante.
- `DROP TABLE bar_history` em `trades.db` (cutover final) é Slice 9.

## 16. Slice 6 — scripts replay + backfill via wrapper

Os três scripts mais usados em desenvolvimento agora rodam contra qualquer backend (`BAR_HISTORY_BACKEND=sqlite|dual|postgres`):

- `scripts/backfill_z_di.py` — usa `bhdb.select_di_warmup`, `bhdb.select_timestamps_by_date`, `bhdb.update_columns_batch("z_di", ...)`. Flag `--db` removida (a SQLite path vem de `BAR_HISTORY_SQLITE_PATH`).
- `scripts/backfill_bar_history.py` — colocta os bars em memória e chama `bhdb.upsert_bars_batch(rows, mode="replace" if force else "merge")`. Flag `--db-path` removida.
- `scripts/replay_execution_timeline.py` — `load_bars_for_date` e `load_eg_source_rows` agora delegam para `bhdb.select_by_date` / `bhdb.select_eg_warmup`. Flag `--source` mantida: quando o backend efetivo lê SQLite (`sqlite`/`dual`), o CLI valida `os.path.exists(--source)` e exporta `BAR_HISTORY_SQLITE_PATH`. Em modo `postgres` a flag é ignorada (sem guard, sem forward) — permite rodar o replay de fora da raiz do repo / em ambientes PG-only sem `trades.db`.

### 16.1 Adições no wrapper

- `select_di_warmup(date_str)` — retorna `(timestamp, win_price, di_price)` com `date_str <= cutoff` e ambos preços NOT NULL.
- `select_timestamps_by_date(date_str)` — apenas a lista de PKs daquela sessão (usado para limitar o UPDATE aos bars do dia).
- `upsert_bar(row, mode="merge"|"replace")` — modo `replace` espelha `force=True` do backfill: sobrescreve toda coluna não-PK. `merge` segue a semântica produção do `save_bar_history`.
- `upsert_bars_batch(rows, mode=...)` — versão `executemany` (1 conexão por chamada) para backfills com milhares de bars.
- `update_columns_batch(column, [(value, ts), ...])` — UPDATE em massa de uma coluna por PK (usado por `backfill_z_di`).

### 16.2 Validação A/B (data 2026-05-08)

Replay completo em modos `sqlite` e `postgres` da mesma data (após dados migrados via Slice 3):

```bash
BAR_HISTORY_BACKEND=sqlite \
  python3 scripts/replay_execution_timeline.py --date 2026-05-08 --out /tmp/replay-sqlite

BAR_HISTORY_BACKEND=postgres PG_URI=... \
  python3 scripts/replay_execution_timeline.py --date 2026-05-08 --out /tmp/replay-pg
```

Resultado: ambos sumários idênticos (bars_total=115, bars_processed=108, mesmos blockers EG/RHO). Diff cell-level entre os dois `execution_timeline_*.db` (ignorando `id` PK + wall-clock `timestamp`): **0 linhas divergentes em 704 eventos**.

`backfill_z_di --dates 2026-05-11` em ambos backends gerou os mesmos 112 z-scores (mesmo `beta_di=-26099.5354`, 0 diffs cell-level em 113 rows).

### 16.3 Cobertura de teste

Sem PG (rodam sempre):
- `test_select_di_warmup_filters_null_prices` — exclui bars sem win_price/di_price.
- `test_select_timestamps_by_date_returns_only_that_session` — só PKs do dia.
- `test_upsert_bar_replace_overwrites_all_columns` — modo `replace` sobrescreve mesmo onde `merge` faria COALESCE.
- `test_upsert_bar_replace_rejects_bad_mode` — `mode='bogus'` levanta `ValueError`.
- `test_upsert_bars_batch_inserts_all_rows` / `test_upsert_bars_batch_replace_overwrites` / `test_upsert_bars_batch_empty_is_noop`.
- `test_update_columns_batch_writes_one_column` / `test_update_columns_batch_rejects_unknown_column`.

Gated em `PG_TEST_URI`:
- `test_slice6_new_helpers_against_postgres` — smoke E2E: batch upsert + `select_di_warmup` + `select_timestamps_by_date` + `update_columns_batch` em uma conexão PG real.

Os 18 testes existentes de `tests/test_replay_execution_timeline.py` continuam passando inalterados (rodam via wrapper + `BAR_HISTORY_SQLITE_PATH`). Acrescentados dois testes de regressão para o guard `--source`:
- `test_main_skips_source_db_existence_check_under_postgres_backend` — `BAR_HISTORY_BACKEND=postgres` com `--source` inexistente roda normalmente; `source_db` não é repassado para `run_replay`.
- `test_main_validates_source_db_under_sqlite_backend` — em modo `sqlite`, `--source` inexistente continua abortando com exit 2.

### 16.4 Não escopo (próximas slices)

- Slice 7: `backfill_bar_history_indicators.py`, `replay_bar_history_to_matador_ops.py`, `seed_dashboard_demo_trades.py`.
- Slice 8: docs (`.env.example`, README, CLAUDE.md) + gate `PG_TEST_URI` em CI.
- Slice 9: stop-write SQLite quando `BAR_HISTORY_BACKEND=postgres` + `DROP TABLE bar_history` em `trades.db`.

## 17. Slice 7 — scripts secundários via wrapper

Migra os três scripts restantes para enxergar `bar_history` apenas via `core.bar_history_db`. A meta de Slice 7 é fechar o front: nenhum caller produtivo abre mais `sqlite3.connect("trades.db")` para ler/escrever `bar_history`.

### 17.1 Mudanças

| Script | Antes | Depois |
| --- | --- | --- |
| `scripts/seed_dashboard_demo_trades.py` | `sqlite3` direto para checar bars + escrever DEMO trades | `bhdb.count_rows(date_str=...)` e `bhdb.bar_time_range(...)` para a leitura; `matador_ops` continua em SQLite (TASK-15) |
| `scripts/replay_bar_history_to_matador_ops.py` | `load_rows(conn)` em SQLite + abertura imediata do `--db` | `bhdb.select_by_date(date)` para reads; a conexão SQLite só abre no caminho `--commit` (matador_ops segue SQLite por enquanto) |
| `scripts/backfill_bar_history_indicators.py` | `ensure_indicator_columns(conn)`, `apply_price_rows(conn, ...)`, `apply_updates(conn, ...)` | `apply_price_rows(rows, price_rows, backend=...)` e `apply_updates(rows, updates, backend=...)` usando `bhdb.upsert_bars_batch(mode="merge")` + `bhdb.update_columns(...)`; `ensure_indicator_columns` é no-op em postgres; `create_backup` retorna `None` em postgres |

A semântica "preserve non-NULL" continua igual: `apply_price_rows`/`apply_updates` filtram em memória (`overwrite or row[col] is None`) antes de chamar o wrapper. Isso evita depender da cláusula `ON CONFLICT DO UPDATE` do backend e mantém parity exata entre SQLite/PG.

### 17.2 Source-DB e backup

`run_backfill(source_db=...)` continua aceitando o caminho legacy, mas:
- Sob `BAR_HISTORY_BACKEND` em `sqlite`/`dual` → exige que o arquivo exista, mantém o backup `.bak`, exporta `BAR_HISTORY_SQLITE_PATH=source_db` enquanto a função roda (context manager, restaurado no `finally`).
- Sob `postgres` → ignora o caminho, pula o backup (use `pg_dump`/Timescale base backup externamente), e o resumo registra `source_db="<postgres:postgres>"` para auditoria.

Idem para `replay_bar_history_to_matador_ops.py`: o `--db` agora só é validado/aberto quando `--commit` é passado, então `--dry-run` em ambiente PG-only não falha mais.

### 17.3 Validação A/B (data 2026-05-08)

Smoke test back-to-back nos dois backends mostrou paridade:

```
$ BAR_HISTORY_BACKEND=sqlite   ./replay_bar_history_to_matador_ops.py --date 2026-05-08 --mode ops
$ BAR_HISTORY_BACKEND=postgres ./replay_bar_history_to_matador_ops.py --date 2026-05-08 --mode ops
# diff -q saídas (ignorando o label "backend=..."): byte-equivalent

$ BAR_HISTORY_BACKEND=sqlite   ./backfill_bar_history_indicators.py --date 2026-05-08 --dry-run --no-backup
$ BAR_HISTORY_BACKEND=postgres ./backfill_bar_history_indicators.py --date 2026-05-08 --dry-run --no-backup
# rows_total=54293, rows_in_scope=115, rows_with_pair_prices=113, rows_computed=113 nos dois.
```

`seed_dashboard_demo_trades.py --date 2026-05-08` lê `bar_history` via PG (a partir de `/tmp/`, fora do repo) sem precisar de `trades.db` local; a inserção em `matador_ops` falha como esperado quando o `--db` SQLite não existe.

### 17.4 Cobertura de teste

`tests/test_backfill_bar_history_indicators.py`:
- 11 testes SQLite originais continuam passando inalterados.
- +4 testes novos:
  - `test_run_backfill_skips_source_existence_check_under_postgres` — postgres-only não checa nem repassa `source_db`.
  - `test_run_backfill_still_requires_source_db_under_sqlite` — sqlite mantém `FileNotFoundError`.
  - `test_create_backup_skips_under_postgres` — retorna `None` em vez de tentar copiar arquivo.
  - `test_ensure_indicator_columns_is_noop_under_postgres` — não tenta abrir SQLite quando backend é PG.
- +2 testes PG-gated (gated em `PG_TEST_URI`):
  - `test_backfill_updates_missing_indicators_postgres` — full pipeline contra Timescale.
  - `test_backfill_preserves_existing_values_postgres` — verifica que `eg_pvalue` previamente populado sobrevive a um run sem `--overwrite`.

### 17.5 Não escopo (próximas slices)

- Slice 8: docs operacionais (`.env.example`, README/CLAUDE.md), gate `PG_TEST_URI` em CI, atualização do runbook de migration.
- Slice 9: cutover final — desliga o write SQLite de `bar_history` quando `BAR_HISTORY_BACKEND=postgres`, então `DROP TABLE bar_history` em `trades.db`. Apenas Postgres permanece para dados temporais.

## 18. Slice 8 — docs operacionais + gate `PG_TEST_URI`

Cierre da fase de documentação antes do cutover. Sem mudanças de código: o objetivo é deixar o setup do Postgres / Timescale auto-explicativo para quem vier amanhã (incluindo a próxima sessão do agente).

### 18.1 Entregáveis

| Artefato | Status | Conteúdo |
| --- | --- | --- |
| `.env.example` | novo | Documenta `BAR_HISTORY_BACKEND`, `BAR_HISTORY_SQLITE_PATH`, `PG_URI`, `PG_TEST_URI`. Sem segredos. Copiado para `.env.local` (gitignored) na máquina. |
| `.gitignore` | edit | Adiciona `!.env.example` após `.env.*` para permitir checkin do template. |
| `README.md` | edit | Nova seção "🗄 Backend de `bar_history`" com tabela dos três modos, comando de ativação, rollback e instruções de teste opt-in. Link para o plano completo. |
| `docs/migration_bar_history_timescale.md` | edit | Esta §18 + ajustes pontuais no §6 / §16.4 / §17.5 marcando Slice 8 como entregue. |

Nota: o block "bar_history backend (TASK-14)" originalmente planejado em `CLAUDE.md` foi descartado por decisão de escopo — CLAUDE.md cobre invariantes estáveis, não estado transitório de migração. Os invariantes (`core.bar_history_db`, env-driven dispatch) vivem no README e na memória do agente.

### 18.2 Gate `PG_TEST_URI`

Padrão consolidado e verificado nos três arquivos de teste relevantes:

| Arquivo | Padrão | Ação sem `PG_TEST_URI` |
| --- | --- | --- |
| `tests/test_bar_history_db.py` (fixture na L37) | `if not uri: pytest.skip(...)` | skipa os testes PG, mantém os SQLite |
| `tests/test_bar_history.py` (fixture na L536) | idem | idem |
| `tests/test_backfill_bar_history_indicators.py` (fixture na L392, adicionada no Slice 7) | idem | idem |

Resultado verificado (2026-05-12) na suíte completa `pytest tests/`:

```
$ PG_TEST_URI=postgresql://… pytest tests/
... 381 passed in 9.11s

$ unset PG_TEST_URI; pytest tests/
... 367 passed, 14 skipped in 7.44s
```

Os 14 skipped são exatamente os testes que tocam Postgres (fixtures `pg_clean_table` em `test_bar_history.py` / `test_backfill_bar_history_indicators.py` e `pg_test_uri` em `test_bar_history_db.py`).

Não há workflow de CI no repo (`.github/workflows/` ausente). O "gate" entregue é a documentação operacional: o README mostra exatamente o que exportar para rodar a suite de integração localmente, e o `.env.example` documenta a chave.

### 18.3 Rollback documentado

Resumido em README, detalhado no §7 deste doc. Comando único:

```bash
unset BAR_HISTORY_BACKEND   # ou export BAR_HISTORY_BACKEND=sqlite
systemctl --user restart pairtrading-server
```

Pós-Slice 9 (commit a8e9833), o write-through SQLite no live path foi removido — `save_bar_history` sob `BAR_HISTORY_BACKEND=postgres` escreve apenas em PG. O comando acima volta o **read path** para SQLite, mas bars gravadas durante a janela `postgres` ficam invisíveis até um backfill explícito PG→SQLite. Wrapper-driven I/O (`bhdb.upsert_*`, `select_*`) já respeitava o backend selecionado de forma estrita desde Slice 2. A assimetria pré-Slice 9 está refletida no README §"Backend de `bar_history`".

### 18.4 Pendências pós-Slice 9

- ~~Stop-write SQLite no live path~~ — entregue no commit a8e9833 (Slice 9). `save_bar_history` sob `BAR_HISTORY_BACKEND=postgres` agora chama `bhdb.upsert_bar(..., mode="merge")` e retorna; o bloco SQLite só roda em `sqlite` ou `dual`.
- Remover branch SQLite legada de `server.py:save_bar_history` quando o `DROP TABLE` for confirmado.
- `DROP TABLE bar_history` em `trades.db` após janela de paridade verificada (operacionalmente decisão do usuário).
- Atualização da memória do agente registrando que `bar_history` agora vive em Postgres como source-of-truth.
