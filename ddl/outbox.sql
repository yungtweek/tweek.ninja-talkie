-- --------------------------------------------
-- Transactional Outbox (one-shot create)
-- --------------------------------------------
DROP TABLE IF EXISTS outbox;

CREATE TABLE IF NOT EXISTS outbox
(
    id               bigserial PRIMARY KEY,
    topic            text        NOT NULL,
    key              text,
    payload_json     jsonb       NOT NULL,

    -- idempotency / state
    idempotency_key  text,
    status           text        NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','publishing','published','failed','dead_lettered','canceled')),

    -- retry / scheduling
    retry_count      int         NOT NULL DEFAULT 0
        CHECK (retry_count BETWEEN 0 AND 100),
    next_attempt_at  timestamptz,
    last_attempt_at  timestamptz,

    -- timestamps / diagnostics
    created_at       timestamptz NOT NULL DEFAULT now(),
    published_at     timestamptz,
    last_error       text
);

-- Partial unique index so multiple NULLs are allowed
CREATE UNIQUE INDEX IF NOT EXISTS ux_outbox_idempotency
    ON outbox (idempotency_key)
    WHERE idempotency_key IS NOT NULL;

-- Scheduler-friendly scan (pending & due)
CREATE INDEX IF NOT EXISTS idx_outbox_sched
    ON outbox (status, next_attempt_at, created_at)
    WHERE status = 'pending';

-- Failed / DLQ monitoring
CREATE INDEX IF NOT EXISTS idx_outbox_failed
    ON outbox (status, retry_count)
    WHERE status IN ('failed','dead_lettered');

-- Operational lookup by topic
CREATE INDEX IF NOT EXISTS idx_outbox_topic_created
    ON outbox (topic, created_at DESC);

-- --------------------------------------------
-- Recommended: Transaction Example (for reference)
-- BEGIN;
--   1) Insert user message (message_index calculated as MAX+1 within the same transaction)
--   2) Insert job entry (queued)
--   3) Insert outbox record (broker publish request)
-- COMMIT;
-- --------------------------------------------