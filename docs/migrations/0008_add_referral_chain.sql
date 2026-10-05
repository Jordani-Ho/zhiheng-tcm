-- 知衡社区 · C 板块「社区规则」离线预留 SQL（产物，勿手改）
-- 生成命令（backend/ 目录下执行；本 revision 离线**不读库**，故目标库与本产物无关）：
--     alembic upgrade   0007_add_seal_events:0008_add_referral_chain --sql        → 段 1/2
--     alembic downgrade 0008_add_referral_chain:0007_add_seal_events --sql        → 段 2/2
-- 范围：仅迁移 0008_add_referral_chain 的增量（0007 → head）；0001 / 0003 / 0004 / 0005 / 0006 / 0007 的 DDL 见各自产物（0002 无产物）。
-- 作用：referral_chain 表 + 3 个索引。**零种子、零回填、零 ALTER**（不碰任何既有表 / 列）。
-- 对齐：docs/phase3-governance-design-v1.md §2（M1 引荐链）—— 迁移 0008 是引荐链表结构的唯一真相源；
--       §2.5 数据模型 / §2.6 接口（5 端点）；docs/phase3-governance-design.md v0.5 §3.1（已冻结，仅历史）。
-- 逐字一致：以下所有语句都由迁移脚本里的内联常量**逐句导出**（与在线执行的是同一批字符串，未重写、未手改）。
--           与含种子 / 回填的产物不同：本 revision 无种子 / 无回填 / 无需枚举存量数据 → 生成时**不打开任何库文件**
--           （不需要 `mode=ro` 只读探测），因此不产生 journal、不触碰真机库。
-- 幂等说明与离线无法判定的部分：
--   ① 表 / 索引是否已存在：在线执行靠 sqlite_master 探测；离线产物一律输出 `CREATE ... IF NOT EXISTS`
--      → 同一库重复执行不报错、不改行数（**无需**人工跳过语句）；
--   ② 收尾结构校验（表名 + 3 个索引名 + 列集合与设计逐字比对）与 downgrade 安全闸只在**在线**执行时
--      判定，离线产物不含（在线不符时抛错：版本号停在 0007、业务数据零变更）；
--   ③ 本产物**无参数、无时间戳、无库相关字面量** → 可逐字节复现。
-- 回放判据：在「已升级到 0007 的库」上执行段 1/2 → referral_chain 表 + 3 个索引；
--   全新库 `alembic upgrade head` 同样会走到本 revision（0008 无前置数据依赖）。
-- 回退：alembic downgrade 0007_add_seal_events（只回收结构：drop referral_chain 表与 3 个索引；
--       **不删**任何既有列 —— TD-003 口径；表内有引荐行（不可重建）时安全闸中止并提示先导出）。

-- #### 段 1/2：upgrade（可回放）####

-- Running upgrade 0007_add_seal_events -> 0008_add_referral_chain

-- [0008] offline：无法判定表 / 索引是否已存在（在线模式靠 sqlite_master 幂等）；若目标库已有同名对象，请人工跳过对应语句；本 revision 无种子 / 无回填 / 不读库
CREATE TABLE IF NOT EXISTS referral_chain (
    referral_id        TEXT PRIMARY KEY,
    referrer_id        TEXT NOT NULL,
    referrer_type      TEXT NOT NULL,
    referee_id         TEXT NOT NULL,
    referee_type       TEXT NOT NULL,
    lineage_id         TEXT,
    referral_reason    TEXT,
    created_at         TIMESTAMP NOT NULL,
    revoked_at         TIMESTAMP,
    revoke_reason      TEXT,
    chain_ready        BOOLEAN DEFAULT FALSE,
    chain_hash         TEXT
);

-- [0008] 已输出：CREATE TABLE referral_chain
CREATE INDEX IF NOT EXISTS idx_referral_chain_referrer ON referral_chain (referrer_id);

-- [0008] 已输出：idx_referral_chain_referrer
CREATE INDEX IF NOT EXISTS idx_referral_chain_referee ON referral_chain (referee_id);

-- [0008] 已输出：idx_referral_chain_referee
CREATE INDEX IF NOT EXISTS idx_referral_chain_lineage ON referral_chain (lineage_id);

-- [0008] 已输出：idx_referral_chain_lineage
-- [0008] offline：收尾结构校验与 downgrade 安全闸只在在线执行时判定，离线产物不含
UPDATE alembic_version SET version_num='0008_add_referral_chain' WHERE alembic_version.version_num = '0007_add_seal_events';


-- #### 段 2/2：downgrade（原样导出、已注释：整文件回放不执行）####

-- -- Running downgrade 0008_add_referral_chain -> 0007_add_seal_events

-- -- [0008] offline downgrade：安全闸（表内有引荐行时中止降级）无法离线判定，请人工确认 referral_chain 为空（或已导出留档）后再执行；本 revision 只 drop 新表与新索引，**不改任何既有表 / 列 / 数据**
-- DROP INDEX IF EXISTS idx_referral_chain_referrer;

-- -- [0008] 已输出：DROP INDEX idx_referral_chain_referrer
-- DROP INDEX IF EXISTS idx_referral_chain_referee;

-- -- [0008] 已输出：DROP INDEX idx_referral_chain_referee
-- DROP INDEX IF EXISTS idx_referral_chain_lineage;

-- -- [0008] 已输出：DROP INDEX idx_referral_chain_lineage
-- DROP TABLE IF EXISTS referral_chain;

-- -- [0008] 已输出：DROP TABLE referral_chain
-- UPDATE alembic_version SET version_num='0007_add_seal_events' WHERE alembic_version.version_num = '0008_add_referral_chain';
