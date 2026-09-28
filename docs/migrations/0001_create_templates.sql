CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001_create_templates

-- [0001] offline：SQLite 版本断言与回填计数校验在离线模式下跳过，请人工核对
CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL DEFAULT '',
    lineage_id TEXT NOT NULL DEFAULT '',
    teacher_id TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    schema_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    parent_template_id INTEGER,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_templates_scope ON templates (lineage_id, teacher_id, type, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_templates_lineage ON templates (parent_template_id, version DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_templates_active_one ON templates (lineage_id, teacher_id, type) WHERE status = 'active';

INSERT INTO templates
    (type, lineage_id, teacher_id, name, schema_json, version, parent_template_id, status, created_at, updated_at)
SELECT
    'treatment', '', pt.teacher_name, '施治模板（存量迁移）',
    json_object(
        'format', 'text',
        'content', COALESCE(pt.content, ''),
        'placeholders', json_array(),
        'meta', json_object('legacy_source', 'plan_templates')
    ),
    1, NULL, 'active',
    COALESCE(NULLIF(pt.updated_at, ''), '2026-09-28T11:31:00.352950'),
    COALESCE(NULLIF(pt.updated_at, ''), '2026-09-28T11:31:00.352950')
FROM plan_templates AS pt
WHERE TRIM(COALESCE(pt.content, '')) <> ''
  AND NOT EXISTS (
      SELECT 1 FROM templates AS t
      WHERE t.type = 'treatment' AND t.teacher_id = pt.teacher_name
        AND (CASE WHEN json_valid(t.schema_json) THEN json_extract(t.schema_json, '$.meta.legacy_source') END) = 'plan_templates'
  )
  AND NOT EXISTS (
      SELECT 1 FROM templates AS a
      WHERE a.type = 'treatment' AND a.teacher_id = pt.teacher_name AND a.status = 'active'
  );

INSERT INTO alembic_version (version_num) VALUES ('0001_create_templates') RETURNING version_num;

