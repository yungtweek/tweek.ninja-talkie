CREATE EXTENSION IF NOT EXISTS "pgcrypto";

DROP TABLE IF EXISTS file_metadata CASCADE ;
CREATE TABLE file_metadata
(
    -- 기본 식별자
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 파일 저장 위치
    bucket          TEXT NOT NULL,
    key             TEXT NOT NULL UNIQUE,
    filename        TEXT NOT NULL,
    content_type    TEXT,
    size            BIGINT,
    etag            TEXT,

    -- 소유 및 접근 제어
    owner_id        UUID NOT NULL,                      -- 업로드한 사용자
    department_id   UUID,                               -- 소속 부서 (optional)
    visibility      TEXT DEFAULT 'private',             -- private | department | public

    -- 상태 및 처리 단계
    status          TEXT NOT NULL DEFAULT 'pending',    -- pending | ready | processing | done | failed | indexed | vectorized
    uploaded_at     TIMESTAMPTZ,
    modified_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    delete_requested_at TIMESTAMPTZ,
    deleted_at      TIMESTAMPTZ,
    vectors_deleted_at TIMESTAMPTZ,

    -- 인덱싱 및 임베딩 관련 메타데이터
    language        TEXT,                               -- 감지된 언어
    chunk_count     INTEGER,                            -- 생성된 청크 수
    embedding_model TEXT,                               -- 사용된 임베딩 모델
    indexed_at      TIMESTAMPTZ,                        -- 인덱싱 완료 시각
    vectorized_at   TIMESTAMPTZ,                        -- 벡터화 완료 시각
    source_url      TEXT,                               -- 원본 URL (optional)
    checksum        TEXT,                               -- 파일 무결성 확인용
    meta            JSONB DEFAULT '{}'::jsonb,          -- 추가 메타데이터 (유연 확장용)

    -- 제약 조건
    CONSTRAINT fk_owner FOREIGN KEY (owner_id)
        REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT fk_department FOREIGN KEY (department_id)
        REFERENCES departments (id) ON DELETE SET NULL,
    CONSTRAINT chk_file_status
        CHECK (status IN ('pending', 'ready', 'processing', 'done', 'failed', 'deleting', 'deleted', 'indexed', 'vectorized')),
    CONSTRAINT chk_file_visibility
        CHECK (visibility IN ('private', 'followers', 'department', 'public'))
);

-- Documentation: file_metadata
COMMENT ON TABLE file_metadata IS 'Metadata table for uploaded files (Ingest pipeline).';
COMMENT ON COLUMN file_metadata.bucket IS 'Object storage bucket name.';
COMMENT ON COLUMN file_metadata.key IS 'Unique object key within the bucket.';
COMMENT ON COLUMN file_metadata.filename IS 'Original filename provided by the uploader.';
COMMENT ON COLUMN file_metadata.owner_id IS 'Uploader user ID (FK → users.id).';
COMMENT ON COLUMN file_metadata.visibility IS 'Access scope: private | department | public.';
COMMENT ON COLUMN file_metadata.status IS 'Lifecycle stage: pending | ready | processing | done | failed | indexed | vectorized | deleting | deleted.';
COMMENT ON COLUMN file_metadata.vectors_deleted_at IS 'Timestamp when vectors were removed from the vector store (RAG cleanup marker).';
COMMENT ON COLUMN file_metadata.chunk_count IS 'Number of generated text chunks during indexing.';
COMMENT ON COLUMN file_metadata.embedding_model IS 'Embedding model name used for vectorization.';
COMMENT ON COLUMN file_metadata.meta IS 'Flexible JSON metadata for additional file attributes.';

-- Common query optimizations
CREATE INDEX IF NOT EXISTS idx_file_metadata_owner_status
    ON file_metadata (owner_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_file_metadata_status_updated
    ON file_metadata (status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_file_metadata_visibility
    ON file_metadata (visibility);

CREATE OR REPLACE FUNCTION update_timestamp()
    RETURNS TRIGGER AS
$$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_update_timestamp
    BEFORE UPDATE
    ON file_metadata
    FOR EACH ROW
EXECUTE FUNCTION update_timestamp();

CREATE OR REPLACE FUNCTION set_uploaded_at_when_ready()
    RETURNS TRIGGER AS
$$
BEGIN
    IF NEW.status = 'ready' AND (NEW.uploaded_at IS NULL) THEN
        NEW.uploaded_at = now();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_set_uploaded_at_when_ready
    BEFORE UPDATE
    ON file_metadata
    FOR EACH ROW
    WHEN (OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION set_uploaded_at_when_ready();


CREATE TABLE file_jobs
(
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id       UUID NOT NULL REFERENCES file_metadata (id) ON DELETE CASCADE,
    job_type      TEXT NOT NULL, -- e.g. "embedding", "thumbnail"
    status        TEXT NOT NULL    DEFAULT 'pending',
    error_message TEXT,
    started_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ
);

-- Documentation: file_jobs
COMMENT ON TABLE file_jobs IS 'Tracks background jobs for each file (embedding, thumbnail, cleanup, etc.).';
COMMENT ON COLUMN file_jobs.job_type IS 'Job type identifier, e.g., embedding or thumbnail.';
COMMENT ON COLUMN file_jobs.status IS 'Job lifecycle: pending | running | done | failed.';
COMMENT ON COLUMN file_jobs.error_message IS 'Optional error details if the job failed.';

CREATE TABLE file_access_log
(
    id          BIGSERIAL PRIMARY KEY,
    file_id     UUID NOT NULL REFERENCES file_metadata (id) ON DELETE CASCADE,
    user_id     UUID,
    accessed_at TIMESTAMPTZ DEFAULT now(),
    ip_address  TEXT,
    action      TEXT, -- e.g. "upload", "download"
    user_agent  TEXT
);

-- Documentation: file_access_log
COMMENT ON TABLE file_access_log IS 'Audit log of file access and actions (upload/download).';
COMMENT ON COLUMN file_access_log.action IS 'Action performed by the user: upload, download, delete, etc.';
COMMENT ON COLUMN file_access_log.user_agent IS 'HTTP user agent string from the request.';

-- Accelerate analytics on access logs
CREATE INDEX IF NOT EXISTS idx_file_access_log_file_action
    ON file_access_log (file_id, action, accessed_at DESC);

CREATE INDEX IF NOT EXISTS idx_file_access_log_user
    ON file_access_log (user_id, accessed_at DESC);