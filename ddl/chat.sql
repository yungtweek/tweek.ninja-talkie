-- UUID 생성 함수용 (gen_random_uuid)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 공용: updated_at 자동 갱신 트리거
CREATE OR REPLACE FUNCTION set_updated_at()
    RETURNS trigger AS
$$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- --------------------------------------------
-- 채팅 세션
-- --------------------------------------------
DROP TABLE IF EXISTS chat_sessions CASCADE;
CREATE TABLE IF NOT EXISTS chat_sessions
(
    id         uuid PRIMARY KEY     DEFAULT gen_random_uuid(),
    user_id    uuid        NOT NULL,
    title      text,
    status     text        NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'deleting', 'deleted')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    delete_requested_at timestamptz
--     FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE -- (있다면 활성화)
);

-- Documentation: chat_sessions
COMMENT ON TABLE chat_sessions IS 'Chat session header per user (soft-deletable).';
COMMENT ON COLUMN chat_sessions.id IS 'Session UUID (primary key).';
COMMENT ON COLUMN chat_sessions.user_id IS 'Owner user UUID (FK → users.id).';
COMMENT ON COLUMN chat_sessions.title IS 'Optional session title (may be generated asynchronously).';
COMMENT ON COLUMN chat_sessions.status IS 'Lifecycle: active | deleting | deleted (soft delete states).';
COMMENT ON COLUMN chat_sessions.delete_requested_at IS 'Timestamp when deletion was requested (soft delete marker).';

ALTER TABLE chat_sessions
    ADD CONSTRAINT fk_chat_sessions_user
        FOREIGN KEY (user_id)
            REFERENCES users (id)
            ON DELETE CASCADE;

-- NOTE: ON DELETE CASCADE is enforced by fk_chat_sessions_user below.

CREATE INDEX IF NOT EXISTS idx_chat_sessions_user
    ON chat_sessions (user_id, created_at DESC);

-- Speed up reads for active sessions only
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_active
    ON chat_sessions (user_id, created_at DESC)
    WHERE status = 'active';

-- Filter by status and recency
CREATE INDEX IF NOT EXISTS idx_chat_sessions_status_created
    ON chat_sessions (status, created_at DESC);

DROP TRIGGER IF EXISTS trg_chat_sessions_updated_at ON chat_sessions;
CREATE TRIGGER trg_chat_sessions_updated_at
    BEFORE UPDATE
    ON chat_sessions
    FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- --------------------------------------------
-- 메시지 (조회 원천)  ※ 채팅 순서 보장: message_index
-- --------------------------------------------
DROP TABLE IF EXISTS chat_messages CASCADE;
CREATE TABLE IF NOT EXISTS chat_messages
(
    id               uuid PRIMARY KEY     DEFAULT gen_random_uuid(),
    session_id       uuid        NOT NULL REFERENCES chat_sessions (id) ON DELETE CASCADE,
    turn             INT         NOT NULL DEFAULT 0,
    role             text        NOT NULL CHECK (role IN ('user', 'assistant', 'system')),

    -- 메시지 생성 모드: 'gen' | 'rag'
    mode            text        NOT NULL DEFAULT 'gen' CHECK (mode IN ('gen', 'rag')),

    -- ⭐ 세션 내 메시지 순서 (1,2,3...) — 정확한 정렬/페이지네이션을 위해 필수
    message_index    int         NOT NULL,

    content          text        NOT NULL DEFAULT '',
    content_raw      text,  -- (옵션) 포맷 전 원문
    sources_json     jsonb, -- RAG 근거 [{id,title,uri,page,score,snippet}]
    usage_prompt     int,
    usage_completion int,

    job_id           uuid,  -- assistant 최종 메시지에 연결 (NULL 허용)
    status           text        NOT NULL DEFAULT 'done' CHECK (status IN ('done', 'error')),
    error_code       text,
    error_message    text,
    trace_id         text,

    created_at       timestamptz NOT NULL DEFAULT now()
);

-- Documentation: chat_messages
COMMENT ON TABLE chat_messages IS 'Append-only message log per session with stable in-session ordering.';
COMMENT ON COLUMN chat_messages.message_index IS 'Strictly increasing per session (1..n) to guarantee order & keyset pagination.';
COMMENT ON COLUMN chat_messages.turn IS 'Conversation turn counter (optional auxiliary index).';
COMMENT ON COLUMN chat_messages.mode IS 'Message generation mode: gen | rag.';
COMMENT ON COLUMN chat_messages.sources_json IS 'RAG citations array: [{id,title,uri,page,score,snippet}]';
COMMENT ON COLUMN chat_messages.job_id IS 'Kafka job id that produced the assistant final message (nullable).';
COMMENT ON COLUMN chat_messages.status IS 'Message terminal state: done | error.';

-- 세션 내 인덱스 고유 (중복/경쟁 방지)
CREATE UNIQUE INDEX IF NOT EXISTS ux_chat_messages_session_idx
    ON chat_messages (session_id, message_index);

-- assistant 최종 메시지는 job 당 1개 (NULL 중복 허용됨)
CREATE UNIQUE INDEX IF NOT EXISTS ux_chat_messages_job
    ON chat_messages (job_id);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session_order
    ON chat_messages (session_id, message_index);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session_turn
    ON chat_messages (session_id, turn);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session_mode
    ON chat_messages (session_id, mode, message_index);

-- Query assistant-only previews efficiently
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_role
    ON chat_messages (session_id, role, message_index);

-- Filter by status (e.g., hide errored when needed)
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_status
    ON chat_messages (session_id, status, message_index);

-- --------------------------------------------
-- 스트리밍 이벤트 (append-only)
-- --------------------------------------------
CREATE TABLE IF NOT EXISTS chat_events
(
    id           bigserial PRIMARY KEY,
    job_id       uuid        NOT NULL,
    session_id   uuid        NOT NULL,
    event_type   text        NOT NULL, -- 'token' | 'sources' | 'usage' | 'done' | 'error' | 'heartbeat'
    seq          int         NOT NULL, -- 게이트웨이가 증가시키는 순번
    payload_json jsonb       NOT NULL,
    received_at  timestamptz NOT NULL DEFAULT now()
);

-- Documentation: chat_events
COMMENT ON TABLE chat_events IS 'Append-only stream of per-job events mirrored from Redis (optional persistence).';
COMMENT ON COLUMN chat_events.seq IS 'Monotonic sequence per job (enforced unique).';
COMMENT ON COLUMN chat_events.payload_json IS 'Event payload as JSON (token/sources/usage/done/error/heartbeat).';

-- 동일 job 내 이벤트 순서/중복 방지
CREATE UNIQUE INDEX IF NOT EXISTS ux_chat_events_job_seq
    ON chat_events (job_id, seq);

CREATE INDEX IF NOT EXISTS idx_chat_events_job
    ON chat_events (job_id, seq);

-- --------------------------------------------
-- 잡 상태 (옵션: 상태 추적/복원)
-- --------------------------------------------
CREATE TABLE IF NOT EXISTS jobs
(
    id         uuid PRIMARY KEY     DEFAULT gen_random_uuid(),
    session_id uuid        NOT NULL REFERENCES chat_sessions (id) ON DELETE CASCADE,
    type       text        NOT NULL CHECK (type IN ('CHAT', 'INGEST')),
    status     text        NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'processing', 'done', 'error')),
    error      text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Documentation: jobs
COMMENT ON TABLE jobs IS 'Background jobs tied to sessions (CHAT/INGEST).';
COMMENT ON COLUMN jobs.type IS 'Job type: CHAT | INGEST';
COMMENT ON COLUMN jobs.status IS 'Job status lifecycle: queued | processing | done | error';

CREATE INDEX IF NOT EXISTS idx_jobs_session_status
    ON jobs (session_id, status, created_at);

-- Dashboard-friendly index: recent jobs by type/status
CREATE INDEX IF NOT EXISTS idx_jobs_type_status_created
    ON jobs (type, status, created_at DESC);

DROP TRIGGER IF EXISTS trg_jobs_updated_at ON jobs;
CREATE TRIGGER trg_jobs_updated_at
    BEFORE UPDATE
    ON jobs
    FOR EACH ROW
EXECUTE FUNCTION set_updated_at();