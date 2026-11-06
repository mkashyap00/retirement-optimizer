-- Retirement Optimizer — trimmed 5-table schema
-- Tax rules live in code; this DB stores only user data + run results.

DROP TABLE IF EXISTS profile_portfolios;
DROP TABLE IF EXISTS profiles;
DROP TABLE IF EXISTS portfolios;
DROP TABLE IF EXISTS runs;
DROP TABLE IF EXISTS settings;
DROP TABLE IF EXISTS income_sources;
DROP TABLE IF EXISTS accounts;
DROP TABLE IF EXISTS households;

CREATE TABLE households (
    id                UUID         PRIMARY KEY,
    filing_status     TEXT         NOT NULL,
    self_birth_date   DATE         NOT NULL,
    spouse_birth_date DATE,
    state             TEXT         NOT NULL,
    nickname          TEXT,
    created_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE accounts (
    id              UUID          PRIMARY KEY,
    household_id    UUID          NOT NULL REFERENCES households(id),
    account_type    TEXT          NOT NULL,
    owner           TEXT          NOT NULL,
    balance         DECIMAL(15,2) NOT NULL,
    basis           DECIMAL(15,2),
    created_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE income_sources (
    id              UUID          PRIMARY KEY,
    household_id    UUID          NOT NULL REFERENCES households(id),
    category        TEXT          NOT NULL,
    owner           TEXT,
    amount          DECIMAL(15,2) NOT NULL,
    start_year      INT,
    end_year        INT
);

CREATE TABLE settings (
    household_id        UUID          PRIMARY KEY REFERENCES households(id),
    required_spending   DECIMAL(15,2),
    inflation           DECIMAL(6,4),
    nominal_return      DECIMAL(6,4),
    ss_pia_self         DECIMAL(10,2),
    ss_claim_age_self   INT,
    ss_pia_spouse       DECIMAL(10,2),
    ss_claim_age_spouse INT,
    heir_tax_rate       DECIMAL(6,4),  -- heirs' rate on inherited trad IRA (default 0.25)
    estate_weight       DECIMAL(6,4),  -- deprecated, ignored (old objective priority); kept for old plans
    spending_rule       TEXT,          -- 'fixed' (default) | 'guardrails'
    spending_floor      DECIMAL(15,2), -- essential spending; NULL = no discretionary band
    constraints_json    TEXT,
    ss_cola             DECIMAL(6,4)   -- projected SS COLA; NULL = follow inflation (floored at 0)
);

CREATE TABLE runs (
    id              UUID          PRIMARY KEY,
    household_id    UUID          NOT NULL REFERENCES households(id),
    created_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    duration_ms     INT,
    request_json    TEXT,
    result_json     TEXT
);

-- portfolios: legacy per-household store, retained for one-time migration
-- into profile_portfolios (see database.py v4 migration). No longer written.
CREATE TABLE portfolios (
    household_id    UUID          PRIMARY KEY REFERENCES households(id),
    uploaded_at     TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    lots_json       TEXT          NOT NULL,
    warnings_json   TEXT          NOT NULL
);

-- profiles: a person/household-of-record that owns a portfolio. Minimal build
-- seeds exactly one "Default" profile; the CFP/multi-client future adds more.
CREATE TABLE profiles (
    id          UUID       PRIMARY KEY,
    name        TEXT       NOT NULL DEFAULT 'Default',
    created_at  TIMESTAMP  NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- profile_portfolios: one uploaded portfolio per profile (upserted on upload),
-- reused across every plan and run.
CREATE TABLE profile_portfolios (
    profile_id     UUID       PRIMARY KEY REFERENCES profiles(id),
    uploaded_at    TIMESTAMP  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    lots_json      TEXT       NOT NULL,
    warnings_json  TEXT       NOT NULL
);
