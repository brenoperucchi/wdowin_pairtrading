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

SELECT add_compression_policy('bar_history', INTERVAL '90 days');
```

- **`segmentby = date_str`** agrupa linhas do mesmo dia → leituras `WHERE date_str = ?` pulam descompressão de outros dias.
- **`orderby = timestamp`** preserva a ordem natural dentro do segmento → melhora compressão (delta encoding).
- Política automática só comprime chunks com >= 90 dias de idade — preserva a janela quente (EG=2240 barras ≈ 30 dias) sempre descomprimida.

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

### 6.1 `.env.example` proposto (Slice 8 entrega o arquivo)

```bash
# Backend de bar_history: sqlite (default) | dual | postgres
BAR_HISTORY_BACKEND=sqlite

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

## 9. Migração / bootstrap (preview — implementação em Slice 3)

Pseudo-fluxo do `scripts/migrate_bar_history_to_pg.py`:

```
1. Conecta em PG, garante: extension timescaledb, schema, hypertable, índices, política de compressão.
2. Conecta em SQLite (trades.db) read-only.
3. Em transação única no PG:
   - COPY bar_history FROM stdin com binário, ou
   - INSERT ... ON CONFLICT DO NOTHING em batches de 5k linhas.
4. Conta linhas (PG vs SQLite). Falha se divergir.
5. Para cada date_str distinto: checksum (SUM(timestamp) FILTER...) compara.
6. Imprime relatório: primeiro/último ts, total, dias cobertos, tempo decorrido.
```

Idempotência: `INSERT ... ON CONFLICT (timestamp) DO NOTHING` torna a re-execução um no-op.

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
