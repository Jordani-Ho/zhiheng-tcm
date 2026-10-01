-- 知衡社区 · Epic 3「学习闭环」离线预审 SQL（产物，勿手改）
-- 生成命令（backend/ 目录下执行；本 revision 离线**不读库**，故 ZHIENG_DB 与本产物无关）：
--     alembic upgrade   0005_add_lineage:head --sql                            → 段 1/2
--     alembic downgrade 0006_add_agent_learning_events:0005_add_lineage --sql  → 段 2/2
-- 范围：仅迁移 0006_add_agent_learning_events 的增量（0005 → head）；0001 / 0003 / 0004 / 0005 的 DDL 见各自产物（0002 无产物）。
-- 作用：agent_learning_events 表 + uq_agent_learning_events_teacher_seq（A2：UNIQUE(teacher_name, seq)）
--       + idx_agent_learning_events_teacher_time。**零种子、零回填、零 ALTER**（不碰任何既有表 / 列）。
-- 对齐：docs/epic3-learning-design-v1.md §2.1（DDL 唯一真相源 = 迁移 0006）/ §2.2（列全集 +
--       「投影列 / 链元列」两分法）/ §2.5（A2 按老师单链）/ §7（回退方案）；
--       CTO 2026-09-30「Epic 3 调研验收 + A1–A8 裁决」；TD-003（downgrade 只回收结构）。
-- 逐字一致：以下所有语句都由迁移脚本里的内联常量**逐句导出**（与在线执行的是同一批字符串，未重写、未手改）。
--           与 0005 产物不同：本 revision 无种子 / 无回填 / 无需枚举存量数据 → 生成时**不打开任何库文件**
--           （不需要 0005 那种 `mode=ro` 只读探测），因此不产生 journal、不触碰真机库。
-- 幂等说明与离线无法判定的部分：
--   ① 表 / 索引是否已存在：在线执行靠 sqlite_master 探测；离线产物一律输出 `CREATE ... IF NOT EXISTS`
--      → 同一库重复执行不报错、不改行数（**无需**像 0005 那样人工跳过补列语句）；
--   ② 收尾结构校验（表名 + 2 个索引名 + 列集合与设计 §2.2 逐字比对）与 downgrade 安全闸只在**在线**执行时
--      判定，离线产物不含（在线不符时抛错：版本号停在 0005、业务数据零变更）；
--   ③ 本产物**无参数、无时间戳、无库相关字面量** → 可逐字节复现（0005 的种子 / 回填产物做不到这点）。
-- 回放判据：在「已升级到 0005 的库」上执行段 1/2 → agent_learning_events 表 + 2 个索引；
--   全新库 `alembic upgrade head` 同样会走到本 revision（0006 无前置数据依赖）。
-- 回退：alembic downgrade 0005_add_lineage（只回收结构：drop agent_learning_events 表与 2 个索引；
--       **不删**任何既有列 —— TD-003 新口径；表内有学习事件行（哈希链节，不可重建）时安全闸中止并提示先导出）。

-- #### 段 1/2：upgrade（可回放）####

-- Running upgrade 0005_add_lineage -> 0006_add_agent_learning_events

-- [0006] offline：无法判定表 / 索引是否已存在（在线模式靠 sqlite_master 幂等）；若目标库已有同名对象，请人工跳过对应语句；本 revision 无种子 / 无回填 / 不读库
CREATE TABLE IF NOT EXISTS agent_learning_events (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_name      TEXT NOT NULL,
    seq               INTEGER NOT NULL,
    event_type        TEXT NOT NULL,
    lineage_id        TEXT NOT NULL DEFAULT '',
    patient_name_hash TEXT NOT NULL DEFAULT '',
    draft_id          INTEGER DEFAULT 0,
    template_id       INTEGER DEFAULT 0,
    payload_json      TEXT NOT NULL DEFAULT '{}',
    payload_hash      TEXT NOT NULL DEFAULT '',
    prev_hash         TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL DEFAULT ''
);

-- [0006] 已输出：CREATE TABLE agent_learning_events
CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_learning_events_teacher_seq ON agent_learning_events (teacher_name, seq);

CREATE INDEX IF NOT EXISTS idx_agent_learning_events_teacher_time ON agent_learning_events (teacher_name, created_at DESC);

-- [0006] 已输出：uq_agent_learning_events_teacher_seq / idx_agent_learning_events_teacher_time
-- [0006] offline：收尾结构校验与 downgrade 安全闸只在在线执行时判定，离线产物不含
UPDATE alembic_version SET version_num='0006_add_agent_learning_events' WHERE alembic_version.version_num = '0005_add_lineage';


-- #### 段 2/2：downgrade（原样导出、已注释：整文件回放不执行）####

-- -- Running downgrade 0006_add_agent_learning_events -> 0005_add_lineage

-- -- [0006] offline downgrade：安全闸（表内有学习事件行时中止降级）无法离线判定，请人工确认 agent_learning_events 为空（或已导出留档）后再执行；本 revision 只 drop 新表与新索引，**不改任何既有表 / 列 / 数据**
-- DROP INDEX IF EXISTS idx_agent_learning_events_teacher_time;

-- DROP INDEX IF EXISTS uq_agent_learning_events_teacher_seq;

-- -- [0006] 已输出：DROP INDEX uq_agent_learning_events_teacher_seq / idx_agent_learning_events_teacher_time
-- DROP TABLE IF EXISTS agent_learning_events;

-- -- [0006] 已输出：DROP TABLE agent_learning_events
-- UPDATE alembic_version SET version_num='0005_add_lineage' WHERE alembic_version.version_num = '0006_add_agent_learning_events';
