-- Runs ONCE, the first time the Postgres container starts with an empty data volume
-- (the official image runs every file in /docker-entrypoint-initdb.d/).
-- It is NOT re-run on later starts, so changing this file later needs a fresh volume.
--
-- The main app database (POSTGRES_DB, "atlas") is created by the image itself.
-- Here we add the extra databases that share this one Postgres instance:

-- Langfuse's own tables (users, projects, prompts). Kept separate from app data.
CREATE DATABASE langfuse;

-- Throwaway database for pytest, so tests never touch your real chat history.
CREATE DATABASE atlas_test;

-- Note: the pgvector extension is enabled by an Alembic migration (step 3), not here,
-- because migrations also run on cloud databases where this init script never runs.
