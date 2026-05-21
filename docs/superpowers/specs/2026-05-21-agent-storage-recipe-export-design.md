# Agent Data Storage & Recipe Import/Export — Design Specification

**Date**: 2026-05-21
**Branch**: feat/react-agent-framework
**Status**: approved

## Overview

Two additions to the agent framework branch before cloud deployment:

1. **Generic JSONB-backed agent collection result storage** — persist arbitrary agent outputs (tables, lists, text) without coupling to business schema, supporting CSV download
2. **Recipe import/export** — allow recipes discovered in development to be transferred to the cloud server

## 1. Agent Collection Results — JSONB Storage

### 1.1 Database Table

New table `agent_collection_results` — fully generic, zero business coupling:

```sql
CREATE TABLE agent_collection_results (
    id              SERIAL PRIMARY KEY,
    namespace       VARCHAR(100) NOT NULL,
    resource_key    VARCHAR(200) NOT NULL,
    resource_date   DATE NOT NULL,
    recipe_id       INT NOT NULL REFERENCES agent_recipes(id),
    output          JSONB NOT NULL,
    status          VARCHAR(20) DEFAULT 'success',
    error_message   TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX ux_agent_collection_result
    ON agent_collection_results(namespace, resource_key, resource_date);
```

- `namespace` — business domain, e.g. `"shop_dashboard"`, reuses the agent recipe namespace convention
- `resource_key` — resource identifier within the namespace, e.g. `shop_id`
- `resource_date` — data date for the collected record
- `recipe_id` — FK to `agent_recipes`, traces which recipe version produced each row
- `output` — complete `RunResult.output` snapshot, recipe-defines-what-gets-stored
- `status` / `error_message` — collection outcome tracking

`shop_dashboard_scores` is **not modified** — it retains the 5 score columns for SQL querying, aggregation, and sorting. The two tables join naturally on `(shop_id ≈ resource_key, metric_date ≈ resource_date)`.

### 1.2 Persistence Flow

```
AgentCrawler.run() → RunResult.output (dict)
    → BrowserAgentAdapter collects and returns payload
    → CollectionResultPersister:
        1. UPSERT shop_dashboard_scores (5 scores + metadata)
        2. INSERT agent_collection_results (output JSONB + metadata)
```

### 1.3 CSV Download API

Single endpoint, CSV only:

```
GET /api/v1/agent-results/download
    ?namespace=shop_dashboard
    &resource_key=shop_123456
    &date_from=2026-05-01
    &date_to=2026-05-21
```

Behavior:
- Queries `agent_collection_results` within the date range
- Finds the first `kind=table` observation in each record's `output`
- Merges all rows into a single CSV with `date` as the first column
- Skips dates with no data (no blank rows)
- Returns `Content-Disposition: attachment; filename="{namespace}_{resource_key}_{date_from}_{date_to}.csv"`

No multi-format support, no ZIP packaging, no observation selection parameter — YAGNI.

### 1.4 Query API

```
GET /api/v1/agent-results
    ?namespace=shop_dashboard
    &resource_key=shop_123456
    &date_from=2026-05-01
    &date_to=2026-05-21

GET /api/v1/agent-results/{id}
```

### 1.5 Cleanup

Remove residual data structures from the old HTTP scraper era:
- `reviews` / `violations` / `cold_metrics` defaults in `BrowserAgentAdapter._map_output()`
- `reviews` / `violations` / `cold_metrics` from `presentation_mapper.py`
- Empty `reviews` / `violations` / `cold_metrics` from `ExperienceQueryService.list_display_materials()`
- `experience/models.py` empty `__all__`

## 2. Recipe Import/Export

### 2.1 Export

```
GET /api/v1/agent-recipes/{recipe_id}/export
```

Returns a JSON file download. Content is the full `Recipe` Pydantic model serialized (namespace, key, version, entrypoint, steps, observations, assertions, recovery_policy, security_policy), excluding DB-internal fields (id, status, stability, timestamps).

Filename: `{namespace}_{key}_v{version}.agent-recipe.json`

### 2.2 Import

```
POST /api/v1/agent-recipes/import
Content-Type: multipart/form-data
Body: file (application/json)
```

Logic:
- Parse file, validate format
- If `(namespace, key, version)` exists → 409 Conflict
- Otherwise → create with `status=active`, `stability=candidate`
- Return created recipe id and version

### 2.3 File Format

```json
{
  "format_version": 1,
  "recipe": {
    "namespace": "shop_dashboard",
    "key": "overview",
    "version": 3,
    "entrypoint": {"url": "https://..."},
    "steps": [],
    "observations": {},
    "assertions": [],
    "recovery_policy": {},
    "security_policy": {}
  }
}
```

`format_version` provides forward compatibility as the recipe schema evolves.

## 3. New Domain Module

```
src/domains/agent_result/
    __init__.py
    models.py       # AgentCollectionResult SQLModel
    repository.py   # AgentResultRepository
    schemas.py      # Pydantic request/response schemas
    services.py     # AgentResultService (query, download)
```

## 4. API Routes

All routes registered under `/api/v1`:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/agent-results` | List agent collection results |
| GET | `/agent-results/{id}` | Get single result detail |
| GET | `/agent-results/download` | CSV download (date range) |
| GET | `/agent-recipes/{recipe_id}/export` | Export recipe as .agent-recipe.json |
| POST | `/agent-recipes/import` | Import recipe from file |

## 5. Migration

Single new migration:
- Create `agent_collection_results` table with indexes and FK constraint

No changes to existing tables.