-- Phase 00.04 storage bootstrap. Idempotent -- safe to re-run.
-- Password placeholder (__APP_READONLY_PASSWORD__) is substituted by
-- scripts/apply_schema.py via psycopg2.sql.Literal before this runs; do not
-- run this file directly with a raw SQL client without substituting it first.

-- Read-only role for the Aggregator (Phase 3) and CLAUDE.md §4 rule 4's
-- DB-level enforcement layer (defense in depth alongside sql_guard.validate_sql()).
-- CREATE ROLE has no native IF NOT EXISTS form, hence the DO block.
DO $$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'app_readonly') THEN
      CREATE ROLE app_readonly WITH LOGIN PASSWORD __APP_READONLY_PASSWORD__;
   END IF;
END
$$;

GRANT CONNECT ON DATABASE audience_match TO app_readonly;
GRANT USAGE ON SCHEMA public TO app_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO app_readonly;

-- Segmenter output (Phase 1) -- Audience Match's own data, real DDL
CREATE TABLE IF NOT EXISTS cluster_profiles (
    cluster_id SERIAL PRIMARY KEY,
    client_id VARCHAR(255) NOT NULL,
    cluster_name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    summary_points JSONB NOT NULL,
    member_count INT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cluster_profiles_client_id ON cluster_profiles(client_id);

-- Folded in from DynamoDB (see blueprint's "Storage follow-up" amendment)
CREATE TABLE IF NOT EXISTS chat_history (
    id BIGSERIAL PRIMARY KEY,
    session_key VARCHAR(255) NOT NULL,  -- {user_id}_{module}_{session_id}, CLAUDE.md §4 rule 7
    turn_index INT NOT NULL,
    role VARCHAR(20) NOT NULL,          -- 'human' | 'ai' | 'system'
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chat_history_session_key ON chat_history(session_key);

CREATE TABLE IF NOT EXISTS schema_metadata (
    table_name VARCHAR(255) PRIMARY KEY,
    enriched_description TEXT NOT NULL,
    sample_rows JSONB,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS prompt_registry (
    id BIGSERIAL PRIMARY KEY,
    agent VARCHAR(100) NOT NULL,
    prompt_version VARCHAR(50) NOT NULL,
    prompt_text TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(agent, prompt_version)
);

-- campaigns / channel_performance / customer_transactions: NOT created here --
-- pre-existing client data, schema unknown to this feature. app_readonly's
-- broad SELECT grants above cover them once they exist.
