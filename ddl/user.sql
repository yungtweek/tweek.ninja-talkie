-- Required extensions (uuid generation and case-insensitive text)
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;

-- Create users table
CREATE TABLE users
(
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,

    -- Case-insensitive username (citext) with implicit UNIQUE constraint
    username         citext                                     NOT NULL
        CONSTRAINT users_username_check
            CHECK (
                char_length(username) BETWEEN 3 AND 20
                    AND username ~ '^[a-z0-9][a-z0-9._-]*[a-z0-9]$'
                    AND username !~ '[._-]{2,}'
                ),
    email            citext,
    pwd_shadow       text,

    created_at       timestamptz      DEFAULT now(),
    updated_at       timestamptz      DEFAULT now()             NOT NULL,
    pwd_updated_at   timestamptz,
    last_accessed_at timestamptz,

    -- Public-facing namespace (UUID without hyphens)
    public_ns        text                                       NOT NULL DEFAULT replace(gen_random_uuid()::text, '-', ''),

    -- Constraints
    CONSTRAINT users_public_ns_format_chk CHECK (public_ns ~ '^[0-9a-f]{32}$')
);

ALTER TABLE users
    OWNER TO tweek;

-- Unique constraints for username, email, and public_ns
CREATE UNIQUE INDEX IF NOT EXISTS uniq_users_username_ci ON users (username);
CREATE UNIQUE INDEX IF NOT EXISTS uniq_users_email_ci ON users (email) WHERE email IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS users_public_ns_uniq ON users (public_ns);

-- Automatically update 'updated_at' timestamp on modification
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS
$$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_set_updated_at ON users;
CREATE TRIGGER trg_set_updated_at
    BEFORE UPDATE
    ON users
    FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

-- Enforce immutability of public_ns field
CREATE OR REPLACE FUNCTION forbid_public_ns_update() RETURNS trigger AS
$$
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.public_ns IS DISTINCT FROM OLD.public_ns THEN
        RAISE EXCEPTION 'public_ns is immutable';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_forbid_public_ns_update ON users;
CREATE TRIGGER trg_forbid_public_ns_update
    BEFORE UPDATE
    ON users
    FOR EACH ROW
EXECUTE FUNCTION forbid_public_ns_update();

CREATE TABLE departments
(
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name       TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ      DEFAULT now()
);