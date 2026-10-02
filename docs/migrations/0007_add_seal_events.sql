-- 知衡社区 · B 板块「数据主权」离线预审 SQL（产物，勿手改）
-- 生成命令（backend/ 目录下执行；本 revision 离线**不读库**，故目标库与本产物无关）：
--     alembic upgrade   0006_add_agent_learning_events:head --sql                        → 段 1/2
--     alembic downgrade 0007_add_seal_events:0006_add_agent_learning_events --sql        → 段 2/2
-- 范围：仅迁移 0007_add_seal_events 的增量（0006 → head）；0001 / 0003 / 0004 / 0005 / 0006 的 DDL 见各自产物（0002 无产物）。
-- 作用：seal_events 表 + idx_seal_events_subject。**零种子、零回填、零 ALTER**（不碰任何既有表 / 列）。
-- 对齐：docs/phase2-data-sovereignty-design.md §3.5（数据封存）——
--       §3.5.4（DDL 唯一真相源 = 迁移 0007）/ §3.5.5（B 板块不定义除名事件：action 只含 seal / readmit）/
--       §3.5.6（flag SEAL_ENABLED 默认 off、API 契约）/ §3.5.7（chain_ready / chain_hash 属阶段四预留）；
--       TD-003（downgrade 只回收结构、不删业务列）。
-- 逐字一致：以下所有语句都由迁移脚本里的内联常量**逐句导出**（与在线执行的是同一批字符串，未重写、未手改）。
--           与含种子 / 回填的产物不同：本 revision 无种子 / 无回填 / 无需枚举存量数据 → 生成时**不打开任何库文件**
--           （不需要 `mode=ro` 只读探测），因此不产生 journal、不触碰真机库。
-- 幂等说明与离线无法判定的部分：
--   ① 表 / 索引是否已存在：在线执行靠 sqlite_master 探测；离线产物一律输出 `CREATE ... IF NOT EXISTS`
--      → 同一库重复执行不报错、不改行数（**无需**人工跳过语句）；
--   ② 收尾结构校验（表名 + 1 个索引名 + 列集合与设计 §3.5.4 逐字比对）与 downgrade 安全闸只在**在线**执行时
--      判定，离线产物不含（在线不符时抛错：版本号停在 0006、业务数据零变更）；
--   ③ 本产物**无参数、无时间戳、无库相关字面量** → 可逐字节复现。
-- 回放判据：在「已升级到 0006 的库」上执行段 1/2 → seal_events 表 + 1 个索引；
--   全新库 `alembic upgrade head` 同样会走到本 revision（0007 无前置数据依赖）。
-- 回退：alembic downgrade 0006_add_agent_learning_events（只回收结构：drop seal_events 表与 1 个索引；
--       **不删**任何既有列 —— TD-003 口径；表内有封存事件行（不可重建）时安全闸中止并提示先导出）。

-- #### 段 1/2：upgrade（可回放）####

-- Running upgrade 0006_add_agent_learning_events -> 0007_add_seal_events

-- [0007] offline：无法判定表 / 索引是否已存在（在线模式靠 sqlite_master 幂等）；若目标库已有同名对象，请人工跳过对应语句；本 revision 无种子 / 无回填 / 不读库
CREATE TABLE IF NOT EXISTS seal_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_type TEXT NOT NULL,
    subject_name TEXT NOT NULL,
    action       TEXT NOT NULL,
    reason       TEXT,
    operator     TEXT,
    created_at   TEXT NOT NULL,
    chain_ready  BOOLEAN DEFAULT FALSE,
    chain_hash   TEXT
);

-- [0007] 已输出：CREATE TABLE seal_events
CREATE INDEX IF NOT EXISTS idx_seal_events_subject ON seal_events (subject_type, subject_name, id DESC);

-- [0007] 已输出：idx_seal_events_subject
-- [0007] offline：收尾结构校验与 downgrade 安全闸只在在线执行时判定，离线产物不含
UPDATE alembic_version SET version_num='0007_add_seal_events' WHERE alembic_version.version_num = '0006_add_agent_learning_events';


-- #### 段 2/2：downgrade（原样导出、已注释：整文件回放不执行）####

-- -- Running downgrade 0007_add_seal_events -> 0006_add_agent_learning_events

-- -- [0007] offline downgrade：安全闸（表内有封存事件行时中止降级）无法离线判定，请人工确认 seal_events 为空（或已导出留档）后再执行；本 revision 只 drop 新表与新索引，**不改任何既有表 / 列 / 数据**
-- DROP INDEX IF EXISTS idx_seal_events_subject;

-- -- [0007] 已输出：DROP INDEX idx_seal_events_subject
-- DROP TABLE IF EXISTS seal_events;

-- -- [0007] 已输出：DROP TABLE seal_events
-- UPDATE alembic_version SET version_num='0006_add_agent_learning_events' WHERE alembic_version.version_num = '0007_add_seal_events';
