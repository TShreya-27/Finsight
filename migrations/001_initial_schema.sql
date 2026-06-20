CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS companies (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    erp_code    TEXT UNIQUE NOT NULL,
    industry    TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY,
    email           VARCHAR(255) UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    last_sign_in_at TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS financial_documents (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id    UUID REFERENCES companies(id),
    document_type TEXT,
    period_start  DATE,
    period_end    DATE,
    raw_text      TEXT,
    file_hash     TEXT UNIQUE,
    ingested_at   TIMESTAMPTZ DEFAULT NOW(),
    status        TEXT DEFAULT 'PENDING'
);

CREATE TABLE IF NOT EXISTS document_meta (
    document_id             UUID PRIMARY KEY,
    user_id                 TEXT,
    workflow_id             TEXT,
    filename                TEXT,
    status                  TEXT NOT NULL,
    source_pdf_path         TEXT,
    highlighted_pdf_path    TEXT,
    source_storage_path     TEXT,
    highlighted_storage_path TEXT,
    anomalies               JSONB DEFAULT '[]'::jsonb,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document_files (
    document_id  UUID NOT NULL,
    file_kind    TEXT NOT NULL,
    filename     TEXT NOT NULL,
    content_type TEXT NOT NULL,
    file_data    BYTEA NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (document_id, file_kind)
);

CREATE TABLE IF NOT EXISTS agent_sessions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_run_id  TEXT NOT NULL,
    agent_name       TEXT NOT NULL,
    session_data     JSONB,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_contexts (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id       UUID REFERENCES agent_sessions(id),
    step_name        TEXT NOT NULL,
    input_snapshot   JSONB,
    output_snapshot  JSONB,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS workflow_states (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    temporal_workflow_id  TEXT UNIQUE NOT NULL,
    agno_workflow_name    TEXT NOT NULL,
    status                TEXT NOT NULL,
    state_data            JSONB,
    started_at            TIMESTAMPTZ DEFAULT NOW(),
    completed_at          TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS anomalies (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID REFERENCES financial_documents(id),
    metric_name     TEXT NOT NULL,
    expected_range  JSONB,
    actual_value    NUMERIC,
    deviation_pct   NUMERIC,
    severity        TEXT NOT NULL,
    description     TEXT,
    status          TEXT DEFAULT 'PENDING',
    resolution_note TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hitl_approvals (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    anomaly_id            UUID REFERENCES anomalies(id),
    temporal_workflow_id  TEXT NOT NULL,
    slack_message_ts      TEXT,
    decision              TEXT,
    reviewer_slack_id     TEXT,
    reviewed_at           TIMESTAMPTZ,
    notes                 TEXT
);

CREATE TABLE IF NOT EXISTS financial_reports (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id       UUID REFERENCES financial_documents(id) UNIQUE,
    report_data       JSONB NOT NULL,
    executive_summary TEXT,
    generated_at      TIMESTAMPTZ DEFAULT NOW(),
    delivered_at      TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_run_id  TEXT,
    agent_name       TEXT NOT NULL,
    action           TEXT NOT NULL,
    input_hash       TEXT,
    output_hash      TEXT,
    eval_score       NUMERIC,
    duration_ms      INTEGER,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pl_statements (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id         UUID REFERENCES financial_documents(id),
    revenue             NUMERIC,
    cogs                NUMERIC,
    gross_profit        NUMERIC,
    operating_expenses  NUMERIC,
    ebitda              NUMERIC,
    net_income          NUMERIC,
    period_start        DATE,
    period_end          DATE,
    currency            TEXT DEFAULT 'INR'
);

CREATE TABLE IF NOT EXISTS balance_sheets (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id             UUID REFERENCES financial_documents(id),
    total_assets            NUMERIC,
    current_assets          NUMERIC,
    non_current_assets      NUMERIC,
    total_liabilities       NUMERIC,
    current_liabilities     NUMERIC,
    non_current_liabilities NUMERIC,
    equity                  NUMERIC,
    period_date             DATE,
    currency                TEXT DEFAULT 'INR'
);
