-- Schema oficial Supabase (PostgreSQL) — MagicWalls Cloud SaaS (5+1 Tabelas)
-- Execute no SQL Editor do projeto Supabase.
-- O backend FastAPI (cloud_saas) conecta exclusivamente via PostgREST usando SUPABASE_SERVICE_ROLE_KEY.

CREATE TABLE IF NOT EXISTS profiles (
    id              BIGSERIAL PRIMARY KEY,
    email           TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    full_name       TEXT NOT NULL DEFAULT '',
    cpf_masked      TEXT NOT NULL DEFAULT '',
    role            TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('member', 'admin')),
    is_blocked      BOOLEAN NOT NULL DEFAULT FALSE,
    blocked_reason  TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at   TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id                BIGSERIAL PRIMARY KEY,
    user_id           BIGINT NOT NULL UNIQUE REFERENCES profiles(id) ON DELETE CASCADE,
    plan              TEXT NOT NULL DEFAULT 'none' CHECK (plan IN ('none', 'trial', 'core', 'pro', 'quant', 'admin')),
    status            TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'past_due', 'suspended', 'blocked', 'canceled')),
    expires_at        TIMESTAMPTZ,
    gateway           TEXT NOT NULL DEFAULT '',
    external_sub_id   TEXT NOT NULL DEFAULT '',
    mt5_account_login BIGINT,
    mt5_license_token TEXT NOT NULL DEFAULT '',
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_mt5_token
    ON subscriptions (mt5_license_token)
    WHERE mt5_license_token <> '';

CREATE TABLE IF NOT EXISTS active_sessions (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    session_id      TEXT NOT NULL,
    ip              TEXT NOT NULL,
    device_fp       TEXT NOT NULL,
    user_agent      TEXT NOT NULL DEFAULT '',
    trading_day     DATE NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    revoked_reason  TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_active_sessions_user_day
    ON active_sessions (user_id, trading_day, id);

CREATE INDEX IF NOT EXISTS idx_active_sessions_user_active
    ON active_sessions (user_id, is_active);

CREATE TABLE IF NOT EXISTS terms_acceptance (
    id            BIGSERIAL PRIMARY KEY,
    user_id       BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    terms_version TEXT NOT NULL,
    ip            TEXT NOT NULL DEFAULT '',
    user_agent    TEXT NOT NULL DEFAULT '',
    accepted_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, terms_version)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT REFERENCES profiles(id) ON DELETE SET NULL,
    event_type  TEXT NOT NULL,
    ip          TEXT NOT NULL DEFAULT '',
    device_fp   TEXT NOT NULL DEFAULT '',
    user_agent  TEXT NOT NULL DEFAULT '',
    trading_day DATE,
    details     JSONB NOT NULL DEFAULT '{}'::jsonb,
    resolved    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_type_resolved
    ON audit_logs (event_type, resolved, id DESC);

CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id
    ON audit_logs (user_id, id DESC);

CREATE TABLE IF NOT EXISTS producer_heartbeats (
    producer_id   TEXT PRIMARY KEY,
    role          TEXT NOT NULL CHECK (role IN ('primary', 'standby')),
    last_seen_ts  DOUBLE PRECISION NOT NULL,
    payload_bytes INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'online'
);

-- Segurança Supabase: habilita Row Level Security em todas as tabelas.
-- Acessos públicos via anon key ficam bloqueados; a Cloud API usa SUPABASE_SERVICE_ROLE_KEY no servidor.
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE active_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE terms_acceptance ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE producer_heartbeats ENABLE ROW LEVEL SECURITY;
