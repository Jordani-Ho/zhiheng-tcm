﻿-- 知衡社区 · Epic 2「老師智能體五階段」离线预审 SQL（产物，勿手改）
-- 生成命令（backend/ 目录下执行）：alembic upgrade 0002_add_draft_template_refs:head --sql
-- 范围：仅迁移 0003_add_agent_stage 的增量（0002 → head）；0001 / 0002 的 DDL 见各自产物。
-- 作用：3 张新表 + 2 个索引 + 2 个快照列 + 种子（存量老师 → learning、全局配置行）。
-- 对齐：docs/epic2-agent-stage-design-v1.md §1.4（DDL 唯一真相源）/ §3.5 / §7.1-①⑪。
-- 注意：离线模式无法探测表 / 列是否已存在（在线执行靠 sqlite_master + PRAGMA table_info 幂等），
--       若目标库已有这些对象，请人工跳过对应语句；种子语句的 <now> 由执行时刻生成。
-- 回退：alembic downgrade 0002_add_draft_template_refs（agent_stage_log 有审计事件时会中止并提示先导出）。

-- Running upgrade 0002_add_draft_template_refs -> 0003_add_agent_stage

-- [0003] offline：无法探测表 / 索引 / 列是否已存在（在线模式靠 sqlite_master + PRAGMA table_info 幂等）；若目标库已有这些对象，请人工跳过对应语句
CREATE TABLE IF NOT EXISTS agent_stage_state (
    teacher_name TEXT PRIMARY KEY,
    lineage_id TEXT NOT NULL DEFAULT '',
    stage TEXT NOT NULL DEFAULT 'observation',
    stage_since TEXT NOT NULL DEFAULT '',
    stage_source TEXT NOT NULL DEFAULT 'default',
    pending_stage TEXT NOT NULL DEFAULT '',
    pending_task_id INTEGER DEFAULT 0,
    last_evaluated_at TEXT NOT NULL DEFAULT '',
    last_metrics_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS agent_stage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_name TEXT,
    event_type TEXT,
    from_stage TEXT,
    to_stage TEXT,
    capability TEXT,
    task_id INTEGER,
    metrics_json TEXT,
    detail TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS agent_stage_config (
    teacher_name TEXT PRIMARY KEY,
    config_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_agent_stage_state_scope ON agent_stage_state (lineage_id, stage);

CREATE INDEX IF NOT EXISTS idx_agent_stage_log_teacher_time ON agent_stage_log (teacher_name, created_at DESC);

-- [0003] offline：下面两条 ADD COLUMN 依赖目标库已有 drafts / patient_records 表（由 init_db() 创建）；表不存在时请人工跳过
ALTER TABLE drafts ADD COLUMN ai_original_content TEXT DEFAULT '';

ALTER TABLE patient_records ADD COLUMN ai_original_text TEXT DEFAULT '';

-- [0003] offline：下面两条种子依赖目标库已有 teachers 表；agent_stage_config 的全局行（teacher_name=''）必须存在
INSERT INTO agent_stage_state
    (teacher_name, stage, stage_since, stage_source, updated_at)
SELECT t.name, 'learning', '2026-09-28T16:17:46.213699', 'default', '2026-09-28T16:17:46.213699'
FROM teachers AS t
WHERE NOT EXISTS (
    SELECT 1 FROM agent_stage_state AS s WHERE s.teacher_name = t.name
);

INSERT OR IGNORE INTO agent_stage_config (teacher_name, config_json, updated_at)
VALUES ('', '{}', '2026-09-28T16:17:46.213699');

UPDATE alembic_version SET version_num='0003_add_agent_stage' WHERE alembic_version.version_num = '0002_add_draft_template_refs';

