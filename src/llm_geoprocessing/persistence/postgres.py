from __future__ import annotations

from llm_geoprocessing.domain.config import Settings


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS geollm_runs (
  run_id TEXT PRIMARY KEY,
  thread_id TEXT NOT NULL,
  status TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS geollm_artifacts (
  artifact_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES geollm_runs(run_id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  uri TEXT NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT now()
);
"""


def checkpoint_dsn(settings: Settings) -> str:
    return settings.postgres_dsn
