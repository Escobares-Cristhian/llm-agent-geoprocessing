# Migration Guide

## 1. Copy overlay

```bash
cp -R llm-geoprocessing-production-ready/* /path/to/repo/
```

## 2. Preserve legacy modules temporarily

Do not delete existing `src/llm_geoprocessing/app` modules immediately. Run the new API in parallel first.

## 3. Migrate GEE execution

Move the existing Earth Engine export logic into:

```python
llm_geoprocessing.plugins.gee.api._execute_real_gee
```

Return only `GeeToolResponse` objects. Keep the existing low-level export helpers private to the plugin package.

## 4. Replace CLI orchestration

Convert the current CLI/GUI app into clients that call:

- `POST /runs`
- `POST /runs/{run_id}/resume`
- `GET /runs/{run_id}`

## 5. Move persistence behind interfaces

The current ChatDB/PostGIS logs can be migrated into `persistence/postgres.py`. Keep graph state and artifact metadata separate from raster/vector payload storage.

## 6. Promote tests

Keep existing JSON fixture tests as integration/e2e tests and add them under `tests/e2e` with a `real_gee` marker.
