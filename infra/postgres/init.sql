-- Initial schema setup. Runs once on first container start.

-- pgvector for embeddings (KG node embeddings, semantic search)
CREATE EXTENSION IF NOT EXISTS vector;

-- pgcrypto for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Apache AGE will be enabled here once block B introduces it.
-- The current pgvector/pgvector:pg16 image does not bundle AGE; switching to a custom
-- image (infra/postgres/Dockerfile) is a Phase 0 task per BUILD-PLAN-v2 risks table.
-- CREATE EXTENSION IF NOT EXISTS age;
-- LOAD 'age';
-- SET search_path = ag_catalog, "$user", public;
