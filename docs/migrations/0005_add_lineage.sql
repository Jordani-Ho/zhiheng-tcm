-- 知衡社区 · Epic 4「多师管理（师门归属与隔离）」离线预审 SQL（产物，勿手改）
-- 生成命令（backend/ 目录下执行；ZHIENG_DB 指向「真机库的副本」，不要指向 backend/zhiheng.db）：
--     alembic upgrade  0004_add_patient_record_template_refs:head --sql                 → 段 1/2
--     alembic downgrade 0005_add_lineage:0004_add_patient_record_template_refs --sql     → 段 2/2
-- 范围：仅迁移 0005_add_lineage 的增量（0004 → head）；0001 / 0002 / 0003 / 0004 的 DDL 见各自产物（0002 无产物）。
-- 作用：lineage 表 + idx_lineage_owner + idx_patient_teachers_lineage + 12 张必须表补 lineage_id
--       + 默认师门种子（真机 1 位老师 → 1 行）+ 存量回填（真机基线 patient_teachers 10 / templates 5 /
--       patient_records 4 / drafts 1，见设计 §6.2）。
-- 对齐：docs/epic4-lineage-design-v1.md §2.1（lineage DDL）/ §2.3（必须 12 张 + 明确不加）/
--       §2.4（`''` = 未归属，禁兜底）/ §2.5（索引）/ §6.1（upgrade 七步）/ §6.2（回填基线）/
--       §6.3（downgrade 统一口径）；CTO 2026-09-29「step 4.1 放行」五条约束 —— 第 5 条即
--       「本产物与在线执行语句逐字一致」。
-- 逐字一致：以下所有语句都由迁移脚本里的内联常量**逐句导出**（与在线执行的是同一批字符串，未重写、未手改）。
--           离线模式为导出「种子」需以 `mode=ro` **只读**打开 ZHIENG_DB 指向的库枚举老师；不写库文件、不建 journal
--           （已实测：生成前后真机库与副本库的 sha256 均未变化）。
-- 幂等说明与离线无法判定的部分：
--   ① 表 / 列是否已存在：在线执行靠 sqlite_master + PRAGMA table_info 探测；离线产物**一律**输出 ADD COLUMN，
--      若目标库已有该列会报 `duplicate column name`（同一库第二次执行必然如此）→ 请人工跳过对应语句；
--   ② 种子 / 回填语句本身幂等（`INSERT ... WHERE NOT EXISTS` / `UPDATE ... WHERE lineage_id = ''`）：
--      跳过 ADD COLUMN 段后重复执行不报错、不改行数（已实测）；
--   ③ 回填计数校验（应填==实填、真机基线 1/10/5/4/1、每位老师有师门）与 downgrade 安全闸只在**在线**执行时判定，
--      离线产物不含（在线不符时抛错：版本号停在 0004、业务数据零变更）；
--   ④ 种子里的老师名 / `lin-*` id / `<now>` 时间戳由「生成时刻的库 + 执行时刻」决定。
-- 回放判据（§6.4，已实测）：在「已升级到 0004 的真机副本」上执行段 1/2 → lineage 1 行 + 2 个索引 +
--   12 张表 lineage_id + 已归属行数 10/5/4/1，与 §6.2 基线一致。
-- 注意：真机当前停在 0002（0003 / 0004 尚未落地）→ 真机的实际升级路径是 `alembic upgrade head`
--       （0003 → 0004 → 0005 一趟跑完），而不是单独回放本产物。
-- 回退：alembic downgrade 0004_add_patient_record_template_refs（只回收结构：drop lineage 表与 2 个索引；
--       **不删**任何业务列 —— 裁决 ④；师门数 > 老师数或有已退出师门记录时安全闸中止并提示先导出）。

-- #### 段 1/2：upgrade（可回放）####

-- Running upgrade 0004_add_patient_record_template_refs -> 0005_add_lineage

-- [0005] offline：无法判定表 / 列是否已存在（在线模式靠 sqlite_master + PRAGMA table_info 幂等）、不做回填计数校验与 downgrade 安全闸（二者只在在线执行时判定）；若目标库已有同名列，请人工跳过对应 ADD COLUMN 语句
CREATE TABLE IF NOT EXISTS lineage (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    owner_teacher_name  TEXT NOT NULL,
    description         TEXT DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'active',
    created_at          TEXT NOT NULL DEFAULT '',
    updated_at          TEXT NOT NULL DEFAULT ''
);

-- [0005] 已输出：CREATE TABLE lineage
CREATE INDEX IF NOT EXISTS idx_lineage_owner ON lineage (owner_teacher_name, status);

-- [0005] 已输出：idx_lineage_owner
ALTER TABLE drafts ADD COLUMN lineage_id TEXT NOT NULL DEFAULT '';

-- [0005] 已输出：ALTER TABLE drafts ADD COLUMN lineage_id
ALTER TABLE patient_records ADD COLUMN lineage_id TEXT NOT NULL DEFAULT '';

-- [0005] 已输出：ALTER TABLE patient_records ADD COLUMN lineage_id
ALTER TABLE complaints ADD COLUMN lineage_id TEXT NOT NULL DEFAULT '';

-- [0005] 已输出：ALTER TABLE complaints ADD COLUMN lineage_id
ALTER TABLE appointments ADD COLUMN lineage_id TEXT NOT NULL DEFAULT '';

-- [0005] 已输出：ALTER TABLE appointments ADD COLUMN lineage_id
ALTER TABLE prescriptions ADD COLUMN lineage_id TEXT NOT NULL DEFAULT '';

-- [0005] 已输出：ALTER TABLE prescriptions ADD COLUMN lineage_id
ALTER TABLE homework ADD COLUMN lineage_id TEXT NOT NULL DEFAULT '';

-- [0005] 已输出：ALTER TABLE homework ADD COLUMN lineage_id
ALTER TABLE transcriptions ADD COLUMN lineage_id TEXT NOT NULL DEFAULT '';

-- [0005] 已输出：ALTER TABLE transcriptions ADD COLUMN lineage_id
ALTER TABLE record_tags ADD COLUMN lineage_id TEXT NOT NULL DEFAULT '';

-- [0005] 已输出：ALTER TABLE record_tags ADD COLUMN lineage_id
ALTER TABLE agent_tasks ADD COLUMN lineage_id TEXT NOT NULL DEFAULT '';

-- [0005] 已输出：ALTER TABLE agent_tasks ADD COLUMN lineage_id
ALTER TABLE agent_action_log ADD COLUMN lineage_id TEXT NOT NULL DEFAULT '';

-- [0005] 已输出：ALTER TABLE agent_action_log ADD COLUMN lineage_id
ALTER TABLE agent_stage_log ADD COLUMN lineage_id TEXT NOT NULL DEFAULT '';

-- [0005] 已输出：ALTER TABLE agent_stage_log ADD COLUMN lineage_id
ALTER TABLE patient_teachers ADD COLUMN lineage_id TEXT NOT NULL DEFAULT '';

-- [0005] 已输出：ALTER TABLE patient_teachers ADD COLUMN lineage_id
CREATE INDEX IF NOT EXISTS idx_patient_teachers_lineage ON patient_teachers (lineage_id, teacher_name, status);

-- [0005] 已输出：idx_patient_teachers_lineage
INSERT INTO lineage (id, name, owner_teacher_name, description, status, created_at, updated_at)
SELECT 'lin-ua8739bc7', '李老师師門', '李老师', '', 'active', '2026-09-29T15:03:45.155440', '2026-09-29T15:03:45.155440'
WHERE NOT EXISTS (
    SELECT 1 FROM lineage WHERE id = 'lin-ua8739bc7' OR owner_teacher_name = '李老师'
);

-- [0005] 已输出：种子默认师门 lin-ua8739bc7（owner=李老师，name=李老师師門）
UPDATE patient_teachers
   SET lineage_id = (SELECT id FROM lineage WHERE owner_teacher_name = patient_teachers.teacher_name)
 WHERE lineage_id = ''
   AND EXISTS (SELECT 1 FROM lineage WHERE owner_teacher_name = patient_teachers.teacher_name);

-- [0005] 已输出：回填 patient_teachers（按 teacher_name）
UPDATE templates
   SET lineage_id = (SELECT id FROM lineage WHERE owner_teacher_name = templates.teacher_id)
 WHERE lineage_id = ''
   AND EXISTS (SELECT 1 FROM lineage WHERE owner_teacher_name = templates.teacher_id);

-- [0005] 已输出：回填 templates（按 teacher_id）
UPDATE patient_records
   SET lineage_id = (SELECT id FROM lineage WHERE owner_teacher_name = patient_records.teacher_name)
 WHERE lineage_id = ''
   AND EXISTS (SELECT 1 FROM lineage WHERE owner_teacher_name = patient_records.teacher_name);

-- [0005] 已输出：回填 patient_records（按 teacher_name）
UPDATE drafts
   SET lineage_id = (SELECT id FROM lineage WHERE owner_teacher_name = drafts.teacher_name)
 WHERE lineage_id = ''
   AND EXISTS (SELECT 1 FROM lineage WHERE owner_teacher_name = drafts.teacher_name);

-- [0005] 已输出：回填 drafts（按 teacher_name）
UPDATE complaints
   SET lineage_id = (SELECT id FROM lineage WHERE owner_teacher_name = complaints.teacher_name)
 WHERE lineage_id = ''
   AND EXISTS (SELECT 1 FROM lineage WHERE owner_teacher_name = complaints.teacher_name);

-- [0005] 已输出：回填 complaints（按 teacher_name）
UPDATE appointments
   SET lineage_id = (SELECT id FROM lineage WHERE owner_teacher_name = appointments.teacher_name)
 WHERE lineage_id = ''
   AND EXISTS (SELECT 1 FROM lineage WHERE owner_teacher_name = appointments.teacher_name);

-- [0005] 已输出：回填 appointments（按 teacher_name）
UPDATE prescriptions
   SET lineage_id = (SELECT id FROM lineage WHERE owner_teacher_name = prescriptions.teacher_name)
 WHERE lineage_id = ''
   AND EXISTS (SELECT 1 FROM lineage WHERE owner_teacher_name = prescriptions.teacher_name);

-- [0005] 已输出：回填 prescriptions（按 teacher_name）
UPDATE homework
   SET lineage_id = (SELECT id FROM lineage WHERE owner_teacher_name = homework.teacher_name)
 WHERE lineage_id = ''
   AND EXISTS (SELECT 1 FROM lineage WHERE owner_teacher_name = homework.teacher_name);

-- [0005] 已输出：回填 homework（按 teacher_name）
UPDATE transcriptions
   SET lineage_id = (SELECT id FROM lineage WHERE owner_teacher_name = transcriptions.teacher_name)
 WHERE lineage_id = ''
   AND EXISTS (SELECT 1 FROM lineage WHERE owner_teacher_name = transcriptions.teacher_name);

-- [0005] 已输出：回填 transcriptions（按 teacher_name）
UPDATE record_tags
   SET lineage_id = (SELECT id FROM lineage WHERE owner_teacher_name = record_tags.teacher_name)
 WHERE lineage_id = ''
   AND EXISTS (SELECT 1 FROM lineage WHERE owner_teacher_name = record_tags.teacher_name);

-- [0005] 已输出：回填 record_tags（按 teacher_name）
UPDATE agent_tasks
   SET lineage_id = (SELECT id FROM lineage WHERE owner_teacher_name = agent_tasks.teacher_name)
 WHERE lineage_id = ''
   AND EXISTS (SELECT 1 FROM lineage WHERE owner_teacher_name = agent_tasks.teacher_name);

-- [0005] 已输出：回填 agent_tasks（按 teacher_name）
UPDATE agent_action_log
   SET lineage_id = (SELECT id FROM lineage WHERE owner_teacher_name = agent_action_log.teacher_name)
 WHERE lineage_id = ''
   AND EXISTS (SELECT 1 FROM lineage WHERE owner_teacher_name = agent_action_log.teacher_name);

-- [0005] 已输出：回填 agent_action_log（按 teacher_name）
UPDATE agent_stage_log
   SET lineage_id = (SELECT id FROM lineage WHERE owner_teacher_name = agent_stage_log.teacher_name)
 WHERE lineage_id = ''
   AND EXISTS (SELECT 1 FROM lineage WHERE owner_teacher_name = agent_stage_log.teacher_name);

-- [0005] 已输出：回填 agent_stage_log（按 teacher_name）
-- [0005] offline：收尾计数校验（应填==实填、真机基线 1/10/5/4/1、每位老师有师门）与 downgrade 安全闸只在在线执行时判定，离线产物不含
UPDATE alembic_version SET version_num='0005_add_lineage' WHERE alembic_version.version_num = '0004_add_patient_record_template_refs';


-- #### 段 2/2：downgrade（原样导出、已注释：整文件回放不执行）####

-- -- Running downgrade 0005_add_lineage -> 0004_add_patient_record_template_refs

-- -- [0005] offline downgrade：安全闸（lineage 行数 > 老师数 / 有已退出师门记录）无法离线判定，请人工确认后再执行；12 张表的 lineage_id 列与其值**一律不删**（裁决 ④：只回收结构）
-- DROP INDEX IF EXISTS idx_patient_teachers_lineage;

-- -- [0005] 已输出：DROP INDEX idx_patient_teachers_lineage
-- DROP INDEX IF EXISTS idx_lineage_owner;

-- -- [0005] 已输出：DROP INDEX idx_lineage_owner
-- DROP TABLE IF EXISTS lineage;

-- -- [0005] 已输出：DROP TABLE lineage
-- UPDATE alembic_version SET version_num='0004_add_patient_record_template_refs' WHERE alembic_version.version_num = '0005_add_lineage';

