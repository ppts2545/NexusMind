-- Run by the postgres container on first boot
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- fast full-text LIKE queries

-- Alembic will create the actual tables via migrations.
-- This file just ensures the extensions are present.
