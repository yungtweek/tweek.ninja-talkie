DROP TABLE IF EXISTS llm_metrics CASCADE;

-- 1) Table Definition
CREATE TABLE llm_metrics
(
    id                bigserial PRIMARY KEY,
    schema_version    smallint    NOT NULL DEFAULT 1,

    request_id        uuid        NOT NULL,
    trace_id          uuid        NOT NULL,
    span_id           uuid        NOT NULL,
    parent_span_id    uuid,
    user_id           uuid,

    request_tag       text,
    model_name        text        NOT NULL,
    model_path        text        NOT NULL DEFAULT 'unknown',

    use_rag           boolean     NOT NULL DEFAULT FALSE,
    rag_hits          integer     NOT NULL DEFAULT 0,
    count_eot         boolean     NOT NULL DEFAULT TRUE,

    prompt_chars      integer     NOT NULL DEFAULT 0,
    prompt_tokens     integer     NOT NULL DEFAULT 0,
    output_chars      integer     NOT NULL DEFAULT 0,
    completion_tokens integer     NOT NULL DEFAULT 0,
    total_tokens      integer GENERATED ALWAYS AS (prompt_tokens + completion_tokens) STORED,

    ttft_ms           double precision,
    gen_time_ms       double precision,
    total_ms          double precision,
    tok_per_sec       double precision,

    response_status   smallint             DEFAULT 0,
    error_message     text,

    created_at        timestamptz NOT NULL DEFAULT NOW()
)
;

-- Documentation: llm_metrics
COMMENT ON TABLE llm_metrics IS 'Token- and latency-level metrics for LLM runs (both chat and ingest workers).';
COMMENT ON COLUMN llm_metrics.request_id IS 'External request UUID, used for cross-system correlation.';
COMMENT ON COLUMN llm_metrics.trace_id IS 'Root trace ID for distributed tracing (OpenTelemetry style).';
COMMENT ON COLUMN llm_metrics.span_id IS 'Child span ID (unique per LLM invocation).';
COMMENT ON COLUMN llm_metrics.parent_span_id IS 'Parent span for hierarchical trace linking.';
COMMENT ON COLUMN llm_metrics.user_id IS 'User owning this request (optional for system jobs).';
COMMENT ON COLUMN llm_metrics.request_tag IS 'Semantic tag for job type (e.g., llm:chat, llm:ingest).';
COMMENT ON COLUMN llm_metrics.model_name IS 'Model display name (e.g., gpt-4o-mini, llama3-8b).';
COMMENT ON COLUMN llm_metrics.model_path IS 'Physical or relative model path (e.g., gguf filename).';
COMMENT ON COLUMN llm_metrics.use_rag IS 'Indicates if the request used retrieval-augmented generation.';
COMMENT ON COLUMN llm_metrics.rag_hits IS 'Number of retrieved documents used in RAG context.';
COMMENT ON COLUMN llm_metrics.prompt_chars IS 'Character count of prompt (input text).';
COMMENT ON COLUMN llm_metrics.prompt_tokens IS 'Token count of prompt (input tokens).';
COMMENT ON COLUMN llm_metrics.output_chars IS 'Character count of generated output.';
COMMENT ON COLUMN llm_metrics.completion_tokens IS 'Token count of generated completion.';
COMMENT ON COLUMN llm_metrics.total_tokens IS 'Computed total = prompt_tokens + completion_tokens.';
COMMENT ON COLUMN llm_metrics.ttft_ms IS 'Time-to-first-token in milliseconds.';
COMMENT ON COLUMN llm_metrics.gen_time_ms IS 'Generation duration (first to last token).';
COMMENT ON COLUMN llm_metrics.total_ms IS 'End-to-end total latency (request to done).';
COMMENT ON COLUMN llm_metrics.tok_per_sec IS 'Throughput: total_tokens / total_ms * 1000.';
COMMENT ON COLUMN llm_metrics.response_status IS 'Response code (0=OK, 1=TIMEOUT, 2=ERROR, etc.).';
COMMENT ON COLUMN llm_metrics.error_message IS 'Error text for failed requests (truncated if too long).';
COMMENT ON COLUMN llm_metrics.created_at IS 'Insertion timestamp.';

-- 2) Integrity & Consistency
ALTER TABLE llm_metrics
    ADD CONSTRAINT ck_llm_metrics_nonneg
        CHECK (
            prompt_chars >= 0 AND
            prompt_tokens >= 0 AND
            completion_tokens >= 0 AND
            total_tokens >= 0 AND
            rag_hits >= 0 AND
            output_chars >= 0
            )
;

-- Common query optimizations
CREATE INDEX IF NOT EXISTS idx_llm_metrics_user_time
    ON llm_metrics (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_llm_metrics_model_status
    ON llm_metrics (model_name, response_status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_llm_metrics_latency
    ON llm_metrics (gen_time_ms DESC, total_ms DESC);

CREATE INDEX IF NOT EXISTS idx_llm_metrics_tokens
    ON llm_metrics (total_tokens DESC);

-- 3) Ownership
ALTER TABLE llm_metrics
    OWNER TO tweek
;

-- 4) Indexes
CREATE INDEX idx_llm_metrics_request_id ON llm_metrics (request_id)
;

CREATE INDEX idx_llm_metrics_trace_span ON llm_metrics (trace_id, span_id)
;

CREATE INDEX idx_llm_metrics_trace_id ON llm_metrics (trace_id)
;

CREATE INDEX idx_llm_metrics_span_id ON llm_metrics (span_id)
;

CREATE INDEX idx_llm_metrics_created_at_brin ON llm_metrics USING brin (created_at)
;

CREATE INDEX idx_llm_metrics_created_at ON llm_metrics (created_at DESC)
;

CREATE INDEX idx_llm_metrics_model_created_at ON llm_metrics (model_name ASC, created_at DESC)
;

CREATE INDEX idx_llm_metrics_use_rag ON llm_metrics (use_rag)
;

CREATE INDEX idx_llm_metrics_rag_true_created ON llm_metrics (created_at DESC) WHERE (use_rag = TRUE)
;

-- Common filter combination optimization (model + tag + time range)
CREATE INDEX idx_llm_metrics_tag_model_time ON llm_metrics (request_tag, model_name, created_at DESC)
;

-- 5) Optional Unique Constraint: prevent duplicate events
-- Useful if Kafka retries or worker idempotency require event deduplication
-- ALTER TABLE llm_metrics ADD CONSTRAINT uq_llm_metrics_event UNIQUE (trace_id, span_id);

-- 6) Optional View: aggregated latency and token summaries (planned feature)
CREATE OR REPLACE VIEW llm_metrics_compact AS
SELECT id,
       created_at,
       schema_version,
       request_id,
       trace_id,
       span_id,
       parent_span_id,
       user_id,
       request_tag,
       model_name,
       model_path,
       use_rag,
       rag_hits,
       prompt_chars,
       prompt_tokens,
       completion_tokens,
       (prompt_tokens + completion_tokens) AS v_total_tokens,
       count_eot,
       ttft_ms,
       gen_time_ms,
       total_ms,
       tok_per_sec,
       output_chars
FROM llm_metrics
;

-- Documentation: llm_metrics_compact
COMMENT ON VIEW llm_metrics_compact IS 'Lightweight view for aggregated latency and token stats per request.';
