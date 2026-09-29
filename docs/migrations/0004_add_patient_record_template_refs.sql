-- 知衡社区 · Epic 2「老師智能體五階段」离线预审 SQL（产物，勿手改）
-- 生成命令（backend/ 目录下执行）：alembic upgrade 0003_add_agent_stage:head --sql
-- 范围：仅迁移 0004_add_patient_record_template_refs 的增量（0003 → head）；0001 / 0002 / 0003 的 DDL 见各自产物。
-- 作用：patient_records 补 template_id / template_version（① 一致率指标的「已签字样本按模板归因」，CTO 批复 A1）。
-- 对齐：docs/epic2-agent-stage-design-v1.md §3.2 + CTO 2026-09-28 批复 A1（新建 0004 补列，不做 updated_at 近似归因）。
-- 注意：离线模式无法探测列是否已存在（在线执行靠 sqlite_master + PRAGMA table_info 幂等），
--       若目标库已有这两列，请人工跳过对应语句；老行由 DEFAULT 0 兜底 = 未记录。
-- 回退：alembic downgrade 0003_add_agent_stage（本 revision 的回退会 DROP 这两列 —— A1 批复「可删列」；
--       回退即放弃「已签字样本按模板归因」能力，存量病历内容不受影响）。

-- Running upgrade 0003_add_agent_stage -> 0004_add_patient_record_template_refs

-- [0004] offline：無法探測列是否已存在（在線模式靠 PRAGMA table_info 冪等）——若 patient_records 已有這兩列，請人工跳過對應語句
ALTER TABLE patient_records ADD COLUMN template_id INTEGER DEFAULT 0;

-- [0004] 已輸出：patient_records.template_id
ALTER TABLE patient_records ADD COLUMN template_version INTEGER DEFAULT 0;

-- [0004] 已輸出：patient_records.template_version
UPDATE alembic_version SET version_num='0004_add_patient_record_template_refs' WHERE alembic_version.version_num = '0003_add_agent_stage';

