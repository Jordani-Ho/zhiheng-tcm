// 由 App.tsx 外移的共享常量 / 类型 / 纯函数（D-058 前端拆分第一步）。
//
// 为什么先拆这一段：`App.tsx` 的 `App()` 组件本身约 4566 行（L191-L4757），
// 一次性拆分风险极高；而本段（原 L9-L189）是**自包含的纯声明**——
// 只含类型、样式常量、与本地存储/格式化相关的纯函数，不依赖任何 React 组件，
// 故可机械化外移并逐字验证（`tsc -b` + 行为不变）。
import type React from "react"

export interface HuangliData { date: string; lunar: string; solar_term: string; solar_term_tip: string; health_trend: string; homework: string; }
export interface RoleData { role_type: string; name: string; task: string; detail: string; }
// 【Epic 1 子任務 3】草案溯源：template_id / template_version（0 或缺失 = 未記錄：本地新建草案 / 無模板生成）
export interface Draft { id: number; transcript_id: number; patient_name: string; content: string; signed: boolean; doctor?: string; template_id?: number; template_version?: number; }
export interface Patient { name: string; teacher_name: string; guardian_name: string; relation: string; }
export interface PatientRecord { id: number; patient_name: string; ai_draft: string; final_plan: string; doctor: string; }
export interface PatientProfile { patient_name: string; gender: string; birth_date: string; birth_time: string; birth_place: string; location: string; bazi?: string; wuxing?: string; }
export interface Teacher { name: string; description: string; }
// 【第62天调整】老师端页签：首页 / 诊室 / 管理（原「学生」+「库存」合并） / 设置
export type TeacherTab = 'home' | 'clinic' | 'manage' | 'settings' | 'seal'

// ============================================================================
// 【D-059】身份判定：与老师**姓名**解耦
// ============================================================================
// 背景：原先全仓 16 处把「是否老师端」写成 `currentRole === '李老师' || currentRole === '李老师智能体'`
// —— **老师姓名硬编码进了角色判定**，导致站点只能给「李老师」一个人用（张三/李四同理）。
//
// 角色字符串的语义分类（UI 的四条固定选项）：
//   · 老师端       ：「<某位老师>」「<某位老师>智能体」   ← 姓名嵌在角色名里
//   · 学生端       ：「学生」「学生智能体」
//
// 判据必须**只依赖角色类型，不依赖姓名**：
//   · 学生端两种角色的字面量是固定的 → 可直接比字面量；
//   · 老师端角色名含任意姓名 → 用「不是学生端」来判定（等价且与姓名无关）。
//
// 用 `function` 声明（会被提升）而非 `const`：App.tsx 的 `lineageIsTeacher`
// （渲染期、`isTeacherRole` 之前）也要用它，const 会触发 TDZ ReferenceError。
export function roleIsStudent(role: string): boolean {
  return role === '学生' || role === '学生智能体'
}

export function roleIsTeacher(role: string): boolean {
  return !roleIsStudent(role)
}

/** UI 的四条角色选项，按「老师 / 学生 × 真人 / 智能体」分组。 */
export const ROLE_OPTIONS = ['李老师', '李老师智能体', '学生', '学生智能体'] as const

export const boxStyle: React.CSSProperties = { background: '#fdfcf0', border: '1px solid #d4c8a8', borderRadius: '12px', padding: '24px', marginBottom: '20px', boxShadow: '0 4px 12px rgba(0,0,0,0.06)' }
export const inputStyle: React.CSSProperties = { width: '100%', padding: '8px', borderRadius: '6px', border: '1px solid #d4c8a8', fontFamily: 'serif', marginBottom: '8px', boxSizing: 'border-box' }
export const dateSelectStyle: React.CSSProperties = { padding: '8px', borderRadius: '6px', border: '1px solid #d4c8a8', fontFamily: 'serif', marginRight: '6px', marginBottom: '8px' }
// 【第67天新增】⚙️ 设置页签：四个分区的「大标题 + 分隔线」样式（纯前端 UI 组织，不涉及任何数据/接口）
export const sectionTitleStyle: React.CSSProperties = { fontSize: '20px', fontWeight: 'bold', color: '#8b4513', borderBottom: '2px solid #d4c8a8', paddingBottom: '6px', marginBottom: '12px', letterSpacing: '1px' }
// 【第67天新增】设置页签内分区小卡片样式（复用 boxStyle，内边距略收窄，视觉上从属于所属分区）
export const sectionCardStyle: React.CSSProperties = { ...boxStyle, padding: '16px 24px' }
// 【Epic 4 §7.2】師門小徽章（诊室 / 管理 / 模板配置 卡片标题旁）：只读展示「本頁限師門：xxx」，
// 与顶部「目前師門」条同源同色（#3a4a7a / 淡蓝底），纯展示、不参与任何请求与判定。
export const lineageChipStyle: React.CSSProperties = {
  display: 'inline-block', fontSize: '12px', color: '#3a4a7a', background: '#f5f7fd',
  border: '1px solid #c9d4ea', borderRadius: '10px', padding: '1px 10px',
  marginLeft: '10px', fontWeight: 'normal', verticalAlign: 'middle'
}
// 【第59天新增】诊室二期：把脉可选的脉象（可多选）
export const PULSE_TYPES = ['浮', '沉', '迟', '数', '虚', '实', '滑', '涩']
// 【第59天重构】拍照清晰度检测阈值：Canvas 取灰度 → 3x3 拉普拉斯卷积 → 求灰度方差，< 100 视为“可能不够清晰”，
// 弹「重拍 / 继续使用」让老师自己决定是否仍要使用
export const IMAGE_SHARPNESS_THRESHOLD = 100
// 【第73天新增 / 改动2 + 改动3】诊室拍照归类：舌苔照 / 患处照 / 其他（默认「患处照」）
// 轻量版智能体判断：当前版本先由老师在下拉里手动确认归类，不做后端识别
export const PHOTO_CATEGORIES = ['舌苔照', '患处照', '其他']
export const DEFAULT_PHOTO_CATEGORY = '患处照'
// 【第73天新增 / 改动1】后端静态资源挂在 8000 端口：/uploads/xxx.jpg 要拼成完整地址才能显示 / 打开原图
export const IMAGE_ORIGIN = 'http://localhost:8000'
// 【第61天新增】首页「今日备忘录」本地存储 key：{ date, keys }，存的数据不是今天就自动清空（前端模拟每日 00:00 重置）
export const MEMO_DONE_STORE_KEY = 'zh_memo_done'
// 【第71天新增 / 面诊队列整合】🩺 诊室队列「💻 远程问诊」列的判定关键词：
// appointments 表没有“远程 / 线上”字段，本次后端零改动，所以由前端按「预约原因 reason」里的关键词把已确认预约分成两列：
// 命中关键词 → 右列「💻 远程问诊」，未命中 → 左列「📅 预约面诊」（老师写原因时带上“远程/线上/视频”等词即可归入远程列）。
export const REMOTE_APPT_KEYWORDS = ['远程', '线上', '网诊', '视频', '电话', '微信']
// 【第80天新增 / 改动3】🩺 面诊前准备：问答记录的固定拼接格式（问：…⏎答：…）——
// 后端 agent.ask_next_question 按「答：」的条数判断学生已经答了几轮（LLM 失败时的兜底也靠它算轮次），
// 所以前端只在这一处拼串，改格式要同步改后端。
export const INTAKE_QA_SEP = '\n'
// 【第80天新增 / 改动3】兜底轮数上限：正常情况下「十问是否问全」以后端 done 为准，
// 这里防的是“后端异常 / LLM 绕圈”导致前端一直问不完（最多 12 轮就收起并进入发送确认）。
export const MAX_INTAKE_ROUNDS = 12
// 【第83天新增 / 十问歌会话持久化】学生端「面诊前准备」进行中会话的状态结构（存 localStorage）：
// { currentQuestion: 当前这一问, answers: 已累积的「问：…⏎答：…」, questionIndex: 已答轮数, updatedAt: ISO 时间串 }
export interface IntakeSession { currentQuestion: string; answers: string; questionIndex: number; updatedAt: string }
// localStorage key：intake_session_{patient_name}_{teacher_name}（一个学生对一个老师只保留一份进行中会话）
export const INTAKE_SESSION_KEY_PREFIX = 'intake_session_'
// 会话有效期：updatedAt 距今超过 24 小时视为过期 → 清空重来
export const INTAKE_SESSION_TTL_MS = 24 * 60 * 60 * 1000
export const intakeSessionKey = (patientName: string, teacherName: string) =>
  `${INTAKE_SESSION_KEY_PREFIX}${patientName || ''}_${teacherName || ''}`
// 读会话：没有 / JSON 坏了 / 已过期（> 24 小时）/ 一条答案都没有 → 一律返回 null，并顺手删掉脏数据（下次从第一问开始）
export const loadIntakeSession = (patientName: string, teacherName: string): IntakeSession | null => {
  const key = intakeSessionKey(patientName, teacherName)
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    const answers = parsed && typeof parsed.answers === 'string' ? parsed.answers : ''
    const updatedMs = Date.parse(String((parsed && parsed.updatedAt) || ''))
    if (!answers.trim() || !updatedMs || Date.now() - updatedMs > INTAKE_SESSION_TTL_MS) {
      localStorage.removeItem(key)
      return null
    }
    return {
      currentQuestion: String(parsed.currentQuestion || ''),
      answers,
      questionIndex: Number(parsed.questionIndex) || 0,
      updatedAt: String(parsed.updatedAt || '')
    }
  } catch {
    return null   // 解析失败不抛错，按“没有进行中会话”处理
  }
}
// 写会话：每答完一题、拿到下一问后调用一次（updatedAt 每次都刷新，用于 24 小时过期判定）
export const saveIntakeSession = (patientName: string, teacherName: string, session: IntakeSession) => {
  try {
    localStorage.setItem(intakeSessionKey(patientName, teacherName), JSON.stringify(session))
  } catch { /* 忽略写入失败（隐私模式 / 空间不足），不影响问答流程 */ }
}
// 清会话：发送成功后 / 学生点「放弃本次」时调用
export const clearIntakeSession = (patientName: string, teacherName: string) => {
  try {
    localStorage.removeItem(intakeSessionKey(patientName, teacherName))
  } catch { /* 忽略删除失败 */ }
}
// 【第56天重构 / 智能体工作台】时间显示：后端返回 ISO 串（如 2026-09-24T10:30:00.123456）→ 显示成 "09-24 10:30"；
// 空值显示 "—"，格式异常（长度不足）则原样返回，绝不抛错影响卡片渲染。
export const formatAgentTime = (value?: string | null) => {
  if (!value) return '—'
  const s = String(value)
  if (s.length < 16) return s
  return `${s.slice(5, 10)} ${s.slice(11, 16)}`
}
// 【第82天新增 / 老师端待处理陈述】📝 待处理陈述的「内容摘要」：把换行 / 连续空白折叠成一个空格后，
// 超过 80 字截断并加 "..."（只影响摘要展示，展开后的完整内容仍是原文，不做任何改写）；
// 空内容给一个中性占位，避免卡片出现空白块。
export const COMPLAINT_SUMMARY_LIMIT = 80
export const summarizeComplaint = (content?: string | null) => {
  const text = String(content || '').replace(/\s+/g, ' ').trim()
  if (!text) return '（无内容）'
  return text.length > COMPLAINT_SUMMARY_LIMIT ? text.slice(0, COMPLAINT_SUMMARY_LIMIT) + '...' : text
}

// ============== 【Epic 4 / step 4.3】師門（lineage）前端上下文 ==============
// 對齊：docs/epic4-lineage-design-v1.md §7（7.1 两个维度并存 / 7.2 老师端 / 7.3 学生端 / 7.4 手动清单）。
// 四条纪律（本段 + 全部调用点共同遵守，改一处要一起看）：
//   ① flag off（探测接口非 2xx）→ **不渲染任何师门 UI**，且所有请求 URL **不带** lineage_id
//      （§4.4 零行为变化：既有 URL 逐字面不变，后端 lineage_read_scope() 直接返回 (False, "")）；
//   ② lineage_id 只在**一处**拼进 URL（组件里的 `withLineage`）= §7.2「集中在一处拼参」，避免散落漏传；
//   ③ 切换师门 = 换上下文 → **先清场再重拉**（切 selectedTeacher 触发既有 effect 全量重拉，同时同步清空旧列表，防串门）；
//   ④ UI 文案一律繁体古字（Epic 1 §13.4 / 决策 11），与 TemplateStudio 的繁體口径一致。
/** `GET /api/lineages?teacher_name=` 的一行（老师端视角；含 `archived`，§7.2 要显示封存提示条）。 */
export interface LineageRow {
  id: string
  name: string
  owner_teacher_name: string
  description: string
  status: string
  created_at: string
  updated_at: string
}
/** `GET /api/student-lineages?student_name=` 的一行（学生端**唯一**真相源：人 / 组织两个维度同源，§7.1）。 */
export interface StudentLineageRow {
  student_name: string
  teacher_name: string
  lineage_id: string
  name: string
  status: string          // 归属行状态：active = 在門內 / inactive = 已退出
  lineage_status: string  // 師門自身状态：active / archived（与上一行语义不同，勿混用）
  owner_teacher_name: string
  joined_at: string
  unassigned: boolean     // true = `lineage_id` 为空（未歸屬，§2.4）：只提示，不兜底成任何师门
}
/** `GET /api/lineages/summary?student_name=` 的一项（跨师门**只读**汇总，不做单一级别，§7.3）。 */
export interface LineageSummaryRow {
  lineage_id: string
  name: string
  teacher_name: string
  status: string
  visits: number
  unsigned_drafts: number
  last_visit_at: string
}
/** 学生端视图哨兵：`本門` = 具体 lineage_id；「全部師門（彙總）」= 本值。 */
export const LINEAGE_ALL_VIEW = '__all__'
/** localStorage key 前缀（附录 A3：记住学生上次选的师门视图；flag off 时**不写**任何 key）。 */
export const LINEAGE_VIEW_STORE_PREFIX = 'zh.lineage.'
export const lineageViewStoreKey = (studentName: string) => `${LINEAGE_VIEW_STORE_PREFIX}${studentName || ''}`
export const loadLineageView = (studentName: string): string => {
  try { return window.localStorage.getItem(lineageViewStoreKey(studentName)) || '' } catch { return '' }
}
export const saveLineageView = (studentName: string, view: string) => {
  // 隐私模式 / 配额满 → 静默忽略：记住选择是加分项，不是功能前置条件
  try { window.localStorage.setItem(lineageViewStoreKey(studentName), view) } catch { /* noop */ }
}
/** 师门切换按钮样式（全站 serif 宋体 + 棕金主色，与 teacherBtnStyle / teacherTabBtnStyle 同风格）。 */
export const lineageTabStyle = (active: boolean): React.CSSProperties => ({
  padding: '4px 12px', margin: '3px', borderRadius: '15px', cursor: 'pointer', fontFamily: 'serif', fontSize: '12px',
  border: `1px solid ${active ? '#8b4513' : '#d4c8a8'}`,
  background: active ? '#8b4513' : 'transparent',
  color: active ? '#fdfcf0' : '#8b4513'
})
// 【第74天新增 / 开方九宫格改造】开方「君臣佐使」与「煎法」选项（与后端 database.py 的
// PRESCRIPTION_ROLES / PRESCRIPTION_COOKING_METHODS 白名单一一对应，改一处要同步另一处）
export const HERB_ROLES = ['君', '臣', '佐', '使']
export const ROLE_UNMARKED_LABEL = '未标注'          // role 为空串时下拉里显示的文字
export const COOKING_METHODS = ['常规', '先煎', '后下', '包煎', '烊化', '另煎', '冲服']
export const DEFAULT_COOKING_METHOD = '常规'          // 新选入的药材默认煎法
// 【第74天新增】九宫格主色（与全站主色 #8b4513 一致）：未选中灰白底 / 已选中棕底白字
export const HERB_GRID_CELL_BASE: React.CSSProperties = {
  padding: '8px 4px', borderRadius: '6px', cursor: 'pointer', fontFamily: 'serif',
  fontSize: '13px', lineHeight: 1.4, boxSizing: 'border-box', textAlign: 'center'
}
