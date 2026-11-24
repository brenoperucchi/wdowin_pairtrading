-- Migração Incremental 002 — Ambiente de Ativação de Trials (15 Dias) MagicWalls
-- 100% idempotente: execute no SQL Editor do projeto Supabase antes ou durante o deploy.

-- 1. Estende profiles com telefone, e-mail canônico, carimbo de trial e origem de aquisição
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS phone TEXT NOT NULL DEFAULT '';
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS email_canonical TEXT NOT NULL DEFAULT '';
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS trial_started_at TIMESTAMPTZ;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS acquisition_source TEXT NOT NULL DEFAULT '';
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS acquisition_meta JSONB NOT NULL DEFAULT '{}'::jsonb;

-- Backfill seguro para contas existentes
UPDATE profiles
SET email_canonical = lower(trim(email))
WHERE email_canonical = '';

CREATE INDEX IF NOT EXISTS idx_profiles_email_canonical
    ON profiles (email_canonical)
    WHERE email_canonical <> '';

CREATE INDEX IF NOT EXISTS idx_profiles_phone
    ON profiles (phone)
    WHERE phone <> '';

-- 2. Códigos / links de convite de trial rastreados por campanha
CREATE TABLE IF NOT EXISTS trial_invites (
    code        TEXT PRIMARY KEY,
    label       TEXT NOT NULL DEFAULT '',
    trial_days  INTEGER NOT NULL DEFAULT 15,
    max_uses    INTEGER,
    used_count  INTEGER NOT NULL DEFAULT 0,
    expires_at  TIMESTAMPTZ,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Lista de espera (quando lote estiver cheio ou modo paused) e intenções de conversão
CREATE TABLE IF NOT EXISTS waitlist_leads (
    id          BIGSERIAL PRIMARY KEY,
    email       TEXT NOT NULL UNIQUE,
    full_name   TEXT NOT NULL DEFAULT '',
    phone       TEXT NOT NULL DEFAULT '',
    source      TEXT NOT NULL DEFAULT '',
    meta        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Segurança Supabase: Row Level Security habilitado (acesso exclusivo via SUPABASE_SERVICE_ROLE_KEY no servidor)
ALTER TABLE trial_invites ENABLE ROW LEVEL SECURITY;
ALTER TABLE waitlist_leads ENABLE ROW LEVEL SECURITY;
