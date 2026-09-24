import { useEffect, useState, useRef } from 'react'

interface HuangliData { date: string; lunar: string; solar_term: string; solar_term_tip: string; health_trend: string; homework: string; }
interface RoleData { role_type: string; name: string; task: string; detail: string; }
interface Draft { id: number; transcript_id: number; patient_name: string; content: string; signed: boolean; doctor?: string; }
interface Patient { name: string; teacher_name: string; guardian_name: string; relation: string; }
interface PatientRecord { id: number; patient_name: string; ai_draft: string; final_plan: string; doctor: string; }
interface PatientProfile { patient_name: string; gender: string; birth_date: string; birth_time: string; birth_place: string; location: string; bazi?: string; wuxing?: string; }
interface Teacher { name: string; description: string; }
// 【第62天调整】老师端页签：首页 / 诊室 / 管理（原「学生」+「库存」合并） / 设置
type TeacherTab = 'home' | 'clinic' | 'manage' | 'settings'

const boxStyle: React.CSSProperties = { background: '#fdfcf0', border: '1px solid #d4c8a8', borderRadius: '12px', padding: '24px', marginBottom: '20px', boxShadow: '0 4px 12px rgba(0,0,0,0.06)' }
const inputStyle: React.CSSProperties = { width: '100%', padding: '8px', borderRadius: '6px', border: '1px solid #d4c8a8', fontFamily: 'serif', marginBottom: '8px', boxSizing: 'border-box' }
const dateSelectStyle: React.CSSProperties = { padding: '8px', borderRadius: '6px', border: '1px solid #d4c8a8', fontFamily: 'serif', marginRight: '6px', marginBottom: '8px' }
// 【第67天新增】⚙️ 设置页签：四个分区的「大标题 + 分隔线」样式（纯前端 UI 组织，不涉及任何数据/接口）
const sectionTitleStyle: React.CSSProperties = { fontSize: '20px', fontWeight: 'bold', color: '#8b4513', borderBottom: '2px solid #d4c8a8', paddingBottom: '6px', marginBottom: '12px', letterSpacing: '1px' }
// 【第67天新增】设置页签内分区小卡片样式（复用 boxStyle，内边距略收窄，视觉上从属于所属分区）
const sectionCardStyle: React.CSSProperties = { ...boxStyle, padding: '16px 24px' }
// 【第59天新增】诊室二期：把脉可选的脉象（可多选）
const PULSE_TYPES = ['浮', '沉', '迟', '数', '虚', '实', '滑', '涩']
// 【第59天重构】拍照清晰度检测阈值：Canvas 取灰度 → 3x3 拉普拉斯卷积 → 求灰度方差，< 100 视为“可能不够清晰”，
// 弹「重拍 / 继续使用」让老师自己决定是否仍要使用
const IMAGE_SHARPNESS_THRESHOLD = 100
// 【第73天新增 / 改动2 + 改动3】诊室拍照归类：舌苔照 / 患处照 / 其他（默认「患处照」）
// 轻量版智能体判断：当前版本先由老师在下拉里手动确认归类，不做后端识别
const PHOTO_CATEGORIES = ['舌苔照', '患处照', '其他']
const DEFAULT_PHOTO_CATEGORY = '患处照'
// 【第73天新增 / 改动1】后端静态资源挂在 8000 端口：/uploads/xxx.jpg 要拼成完整地址才能显示 / 打开原图
const IMAGE_ORIGIN = 'http://localhost:8000'
// 【第61天新增】首页「今日备忘录」本地存储 key：{ date, keys }，存的数据不是今天就自动清空（前端模拟每日 00:00 重置）
const MEMO_DONE_STORE_KEY = 'zh_memo_done'
// 【第71天新增 / 面诊队列整合】🩺 诊室队列「💻 远程问诊」列的判定关键词：
// appointments 表没有“远程 / 线上”字段，本次后端零改动，所以由前端按「预约原因 reason」里的关键词把已确认预约分成两列：
// 命中关键词 → 右列「💻 远程问诊」，未命中 → 左列「📅 预约面诊」（老师写原因时带上“远程/线上/视频”等词即可归入远程列）。
const REMOTE_APPT_KEYWORDS = ['远程', '线上', '网诊', '视频', '电话', '微信']
// 【第80天新增 / 改动3】🩺 面诊前准备：问答记录的固定拼接格式（问：…⏎答：…）——
// 后端 agent.ask_next_question 按「答：」的条数判断学生已经答了几轮（LLM 失败时的兜底也靠它算轮次），
// 所以前端只在这一处拼串，改格式要同步改后端。
const INTAKE_QA_SEP = '\n'
// 【第80天新增 / 改动3】兜底轮数上限：正常情况下「十问是否问全」以后端 done 为准，
// 这里防的是“后端异常 / LLM 绕圈”导致前端一直问不完（最多 12 轮就收起并进入发送确认）。
const MAX_INTAKE_ROUNDS = 12
// 【第56天重构 / 智能体工作台】时间显示：后端返回 ISO 串（如 2026-09-24T10:30:00.123456）→ 显示成 "09-24 10:30"；
// 空值显示 "—"，格式异常（长度不足）则原样返回，绝不抛错影响卡片渲染。
const formatAgentTime = (value?: string | null) => {
  if (!value) return '—'
  const s = String(value)
  if (s.length < 16) return s
  return `${s.slice(5, 10)} ${s.slice(11, 16)}`
}
// 【第82天新增 / 老师端待处理陈述】📝 待处理陈述的「内容摘要」：把换行 / 连续空白折叠成一个空格后，
// 超过 80 字截断并加 "..."（只影响摘要展示，展开后的完整内容仍是原文，不做任何改写）；
// 空内容给一个中性占位，避免卡片出现空白块。
const COMPLAINT_SUMMARY_LIMIT = 80
const summarizeComplaint = (content?: string | null) => {
  const text = String(content || '').replace(/\s+/g, ' ').trim()
  if (!text) return '（无内容）'
  return text.length > COMPLAINT_SUMMARY_LIMIT ? text.slice(0, COMPLAINT_SUMMARY_LIMIT) + '...' : text
}
// 【第74天新增 / 开方九宫格改造】开方「君臣佐使」与「煎法」选项（与后端 database.py 的
// PRESCRIPTION_ROLES / PRESCRIPTION_COOKING_METHODS 白名单一一对应，改一处要同步另一处）
const HERB_ROLES = ['君', '臣', '佐', '使']
const ROLE_UNMARKED_LABEL = '未标注'          // role 为空串时下拉里显示的文字
const COOKING_METHODS = ['常规', '先煎', '后下', '包煎', '烊化', '另煎', '冲服']
const DEFAULT_COOKING_METHOD = '常规'          // 新选入的药材默认煎法
// 【第74天新增】九宫格主色（与全站主色 #8b4513 一致）：未选中灰白底 / 已选中棕底白字
const HERB_GRID_CELL_BASE: React.CSSProperties = {
  padding: '8px 4px', borderRadius: '6px', cursor: 'pointer', fontFamily: 'serif',
  fontSize: '13px', lineHeight: 1.4, boxSizing: 'border-box', textAlign: 'center'
}

export default function App() {
  const now = new Date()
  const currentYear = now.getFullYear()
  const currentMonth = now.getMonth() + 1
  const currentDay = now.getDate()

  const [huangli, setHuangli] = useState<HuangliData | null>(null)
  const [currentRole, setCurrentRole] = useState('学生')
  const [roleData, setRoleData] = useState<RoleData | null>(null)
  const [inputText, setInputText] = useState('')
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [patientRecords, setPatientRecords] = useState<PatientRecord[]>([])
  const [finalPlans, setFinalPlans] = useState<{ [key: number]: string }>({})
  const [points, setPoints] = useState<{ patient_points: number; teacher_points: number } | null>(null)
  const [patients, setPatients] = useState<Patient[]>([])
  const [selectedPatient, setSelectedPatient] = useState('张三')
  const [showHistory, setShowHistory] = useState(false)
  const [profile, setProfile] = useState<PatientProfile | null>(null)
  const [editingProfile, setEditingProfile] = useState(false)
  const [draftProfile, setDraftProfile] = useState<PatientProfile | null>(null)

  const [teachers, setTeachers] = useState<Teacher[]>([])
  const [patientTeachers, setPatientTeachers] = useState<string[]>([])
  const [selectedTeacher, setSelectedTeacher] = useState('李老师')
  const [showTeacherPicker, setShowTeacherPicker] = useState(false)
  const [teacherPatients, setTeacherPatients] = useState<any[]>([])

  const [showAddFamily, setShowAddFamily] = useState(false)
  const [newFamilyName, setNewFamilyName] = useState('')
  const [newRelation, setNewRelation] = useState('')
  const [newGender, setNewGender] = useState('')
  const [newBirthYear, setNewBirthYear] = useState('')
  const [newBirthMonth, setNewBirthMonth] = useState('')
  const [newBirthDay, setNewBirthDay] = useState('')
  const [newBirthTime, setNewBirthTime] = useState('')
  const [newBirthPlace, setNewBirthPlace] = useState('')
  const [newLocation, setNewLocation] = useState('')
  const [guardianLocation, setGuardianLocation] = useState('')
  const [guardianGender, setGuardianGender] = useState('')
  const [guardianBirthDate, setGuardianBirthDate] = useState('')

  const [healthTrend, setHealthTrend] = useState<any>(null)
  const [dailyAdvice, setDailyAdvice] = useState<any>(null)

  const [invites, setInvites] = useState<any[]>([])
  const [pendingInviteCode, setPendingInviteCode] = useState<string>('')
  const [newStudentNameFromInvite, setNewStudentNameFromInvite] = useState<string>('')

  const [structuredPreview, setStructuredPreview] = useState<string | null>(null)
  const [pendingImages, setPendingImages] = useState<string[]>([])
  const [pendingAudios, setPendingAudios] = useState<string[]>([])
  const [isRecordingStudent, setIsRecordingStudent] = useState(false)
  const [recognitionStudent, setRecognitionStudent] = useState<any>(null)
  const [mediaRecorder, setMediaRecorder] = useState<any>(null)
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [teacherLiveText, setTeacherLiveText] = useState<{ [draftId: number]: string }>({})
  const [teacherLiveRecording, setTeacherLiveRecording] = useState<number | null>(null)
  const [teacherLiveRecognition, setTeacherLiveRecognition] = useState<any>(null)
  const [teacherLiveStructurizing, setTeacherLiveStructurizing] = useState<{ [draftId: number]: boolean }>({})
  const [liveUploading, setLiveUploading] = useState<{ [draftId: number]: boolean }>({})
  // 【第68天新增】智能体清洗状态：录音停止后调 POST /api/agent/clean_transcript 期间置 true（按钮显示“🔄 智能体处理中...”）
  const [teacherLiveCleaning, setTeacherLiveCleaning] = useState<{ [draftId: number]: boolean }>({})
  // 【第68天新增】录音原始转写缓冲区：录音过程中只往这里攒，停止后才交给智能体清洗，再把清洗结果写进文本框
  const teacherLiveRawRef = useRef<{ [draftId: number]: string }>({})

  // 【第75天新增 / 改动1】「辨证施治方案」语音输入：与“现场辅助记录”的录音完全同套路
  // （Web Speech API zh-CN 录音 → 停止 → POST /api/agent/clean_transcript 清洗 → 追加到施治方案文本框末尾）。
  // 全部按 draftId 分开存（第五部分一次只渲染当前学生的草案，但仍按 id 隔离，避免切换学生时串台）。
  const [planRecording, setPlanRecording] = useState<number | null>(null)                     // 正在录音的草案 id（null = 没在录音）
  const [planRecognition, setPlanRecognition] = useState<any>(null)                          // 语音识别实例（再次点击按钮时 stop）
  const [planCleaning, setPlanCleaning] = useState<{ [draftId: number]: boolean }>({})       // 清洗中 → 按钮显示“🔄 智能体处理中...”
  const planRawRef = useRef<{ [draftId: number]: string }>({})                               // 录音原始转写缓冲（停止后才送清洗）
  // 【第75天新增 / 改动2】施治方案模板：老师维度的常用写法记忆（后端 plan_templates 表，teacher_name 唯一）
  const [planTemplate, setPlanTemplate] = useState('')                                       // GET /api/plan_template 拉回来的模板（空串 = 没模板）
  const [planTemplateApplied, setPlanTemplateApplied] = useState<{ [draftId: number]: boolean }>({})  // 哪些草案的方案是自动套用来的（显示小灰字）
  // 已经自动套用过模板的草案 id：同一位学生只自动套用一次，老师手动清空后不会被立刻填回（随“切学生清场”一起重置）
  const planTemplateFilledRef = useRef<{ [draftId: number]: boolean }>({})
  // 【第81天修复 / 录音时间太短】Web Speech API 在检测到几秒静音后会自行触发 onend（不是用户点的“停止录音”），
  // 旧代码在 onend 里直接切回“未录音”，于是停顿一下录音就被中断。isUserStoppedRef 专门区分这两种“结束”：
  //   false = 用户还在录 → onend 里自动 rec.start() 续上（静音打断不影响继续录）；
  //   true  = 用户主动点停 → onend 里才走原有的收尾逻辑（清洗 / 追加 / 切回未录音状态）。
  // 放在顶层用 useRef 而不是 state：不触发重渲染；学生端（🗣️ 学生智能体 / 🩺 面诊前准备）与老师端
  // （📸 现场辅助记录 / 辨证施治方案）这四处独立写的录音逻辑共用同一个标记（同一时刻只会有一个在录）。
  const isUserStoppedRef = useRef(true)

  const [previewDraft, setPreviewDraft] = useState<{ id: number; content: string } | null>(null)
  const [draftTags, setDraftTags] = useState<{ [draftId: number]: { area: string; symptom: string } }>({})

  // 【第80天新增 / 改动3】🩺 面诊前准备（学生端首页 · 黄历卡片下方）：十问歌主动追问的问答状态
  const [showIntake, setShowIntake] = useState(false)             // 是否展开问答界面（点「开始面诊前准备」后展开）
  const [intakeQuestion, setIntakeQuestion] = useState('')         // 当前这一问（POST /api/agent/ask_next_question 返回）
  const [intakeAnswer, setIntakeAnswer] = useState('')             // 当前这一问的输入框内容（🎙️ 语音输入也写这里）
  const [intakeAnswers, setIntakeAnswers] = useState('')           // 累积的问答记录，格式：问：…⏎答：…（首次为空串）
  const [intakeRounds, setIntakeRounds] = useState(0)              // 本地已答轮数（仅用于进度显示与上限兜底）
  const [intakeDone, setIntakeDone] = useState(false)              // 十问是否已问全（后端 done=true）
  const [intakeLoading, setIntakeLoading] = useState(false)        // 正在拉下一问
  const [intakeSending, setIntakeSending] = useState(false)        // 正在发送给老师
  const [intakeSent, setIntakeSent] = useState(false)              // 已发送成功
  const [intakeRecording, setIntakeRecording] = useState(false)    // 🎙️ 语音输入是否在录音
  const [intakeRecognition, setIntakeRecognition] = useState<any>(null)

  // 【第57天新增 / 第62天调整】老师端页签（首页/诊室/管理/设置），切换时不清空 selectedPatient
  const [teacherTab, setTeacherTab] = useState<TeacherTab>('home')
  // 【第57天新增】诊室：老师搜索学生（前端过滤 teacherPatients）
  const [studentSearch, setStudentSearch] = useState('')
  // 【第71天新增 / 面诊队列整合】🩺 诊室队列：临时加插名单（仅本次会话有效，刷新页面自动清空；不落库、不调后端）
  const [tempQueue, setTempQueue] = useState<{ name: string; time: string }[]>([])
  // 临时加插：是否展开「从当前学生列表里选一位没预约的学生」的选择面板
  const [showTempInsertPicker, setShowTempInsertPicker] = useState(false)
  // 【第82天新增 / 老师端待处理陈述】📝 待处理陈述（位置：「🩺 诊室队列」下方、「🩺 诊室工作台」上方）：
  // 学生完成「十问歌」面诊前准备后走 POST /api/agent/save_intake 落库到 complaints 表（status='pending'），
  // 老师在诊室页这里看到这些陈述，看完点「已处理」把它们移出待办列表。
  // 数据源：GET /api/complaints?teacher_name=…&status=pending；全部复用现有 fetch 写法，不新增依赖。
  const [pendingComplaints, setPendingComplaints] = useState<any[]>([])                // 待处理陈述列表
  const [complaintsLoading, setComplaintsLoading] = useState(false)                    // 正在拉取 / 刷新
  const [complaintsMissing, setComplaintsMissing] = useState(false)                    // 后端接口缺失（404 / 非 2xx）→ 只给灰字提示，不弹窗
  const [expandedComplaintIds, setExpandedComplaintIds] = useState<string[]>([])       // 「查看详情」的展开状态（按行 key 记录，可多条同时展开）
  const [processingComplaintIds, setProcessingComplaintIds] = useState<string[]>([])   // 正在「已处理」的行 key（按钮置灰，防重复点击）

  // 【第59天重构】诊室二期：把脉记录（录音 / 拍照 / AI整理 已合并进“现场辅助记录”卡片，复用该卡片自己的 state）
  const [pulseTypes, setPulseTypes] = useState<string[]>([])
  const [pulseRate, setPulseRate] = useState('')
  const [pulseNote, setPulseNote] = useState('')

  // 【第69天新增】诊室拍照缩略图列表：每上传成功一张图片就记一条（仅当前会话有效，刷新页面即清空）
  // 点缩略图 → window.open(url, '_blank') 看原图；点右上角 × → 只从本列表移除，不影响已追加到文本框的 URL
  // 【第73天改动3】结构由 string[] 改成对象数组 { url, category }：
  //   · url      → 图片地址（/uploads/xxx.jpg，与追加进文本框的 URL 完全一致）
  //   · category → 归类的智能体标签（轻量版：默认「患处照」，老师在缩略图下方下拉里手动确认 / 切换）
  const [uploadedImages, setUploadedImages] = useState<{ url: string; category: string }[]>([])

  // 【第59天重构】拍照清晰度不通过时，弹「重拍 / 继续使用」两个选项（老师自己决定是否仍要使用）
  const [blurryPhoto, setBlurryPhoto] = useState<{ draftId: number; file: File } | null>(null)
  // 诊室拍照 input 引用：选“重拍”时直接再次唤起相机（同一个 input，选完即清空，可重复选同一张图片）
  const clinicPhotoInputRef = useRef<HTMLInputElement>(null)
  // 【第70天修复 / 数据串台】当前就诊学生 ref：拍照上传属于异步回调，返回时用它判断“学生是否已经被切换过”，
  // 避免上一个学生的上传结果（缩略图 / 图片 URL）落到下一位学生身上（ref 不受闭包快照影响）
  const clinicPatientRef = useRef(selectedPatient)

  // 【第59天修复】本地占位草案：诊室里选中学生、但该学生还没有“正在编辑的草案”时，
  // 前端本地先生成一条空草案（id 为负数），让录音 / 拍照 / 把脉立刻可用；老师点“保存病历修改”时再落库。
  const [localDrafts, setLocalDrafts] = useState<Draft[]>([])
  // 【第71天修复 / 签字死锁】本地占位草案落库中：用于置灰“保存病历修改”按钮，避免重复点击造出重复草案
  const [localDraftSaving, setLocalDraftSaving] = useState(false)
  // 诊室可编辑草案 = 后端草案 + 本地占位草案（同一学生以后端草案为准，避免重复显示）
  const clinicDrafts: Draft[] = [...drafts, ...localDrafts.filter(ld => !drafts.some(d => d.patient_name === ld.patient_name))]
  // 【第70天修复 / 数据串台】【第72天改名】🩺 诊室工作台第二～第五部分（病历草案 / 病历标签 / 开方 / 辨证施治方案）只取“当前就诊学生”的草案：
  // 后端 GET /api/drafts 是“按老师”返回全部学生的草案，若直接渲染 clinicDrafts，一屏上就会同时出现多位学生的内容
  const clinicPatientDrafts: Draft[] = clinicDrafts.filter(d => d.patient_name === selectedPatient)

  // 本地占位草案一旦被后端草案取代（落库成功 / 学生提交陈述），就清理掉，避免签字后又“复活”
  useEffect(() => {
    setLocalDrafts(prev => {
      if (!prev.some(ld => drafts.some(d => d.patient_name === ld.patient_name))) return prev
      return prev.filter(ld => !drafts.some(d => d.patient_name === ld.patient_name))
    })
  }, [drafts])

  // 【第58天新增】学生智能体一期：照镜子 + 习惯追踪 + 周报（纯前端 localStorage）
  // 照镜子：记录今日早/晚是否已完成，key 形如 { patientName: { 'YYYY-MM-DD': { morning: true, evening: false } } }
  const [mirrorLog, setMirrorLog] = useState<{ [patient: string]: { [date: string]: { morning: boolean; evening: boolean } } }>({})
  // 习惯打卡：key 形如 { patientName: { 'YYYY-MM-DD': { '早睡': true, ... } } }
  const [habitLog, setHabitLog] = useState<{ [patient: string]: { [date: string]: { [habit: string]: boolean } } }>({})
  // 习惯列表（学生可增删，默认三条）
  const [habitList, setHabitList] = useState<string[]>(['早睡', '揉太渊', '喝温水'])
  const [newHabitName, setNewHabitName] = useState('')
  // 提醒频率：A 每天 / B 隔天 / C 每周（老师端可设置，学生端只读展示）
  const [reminderFrequency, setReminderFrequency] = useState<'A' | 'B' | 'C'>('A')

  // 预约相关
  const [appointments, setAppointments] = useState<any[]>([])
  const [showApptForm, setShowApptForm] = useState(false)
  const [apptDate, setApptDate] = useState('')
  const [apptTime, setApptTime] = useState('')
  const [apptReason, setApptReason] = useState('')

  // 老师工作时间（新）
  const [schedule, setSchedule] = useState<{ [day: string]: string[] } | null>(null)
  const [scheduleEditDay, setScheduleEditDay] = useState('1') // 当前编辑的星期，默认周一
  const [editingSchedule, setEditingSchedule] = useState(false)
  const [tempSchedule, setTempSchedule] = useState<{ [day: string]: string[] }>({})
  // 【第49天新增】节假日管理
  const [holidays, setHolidays] = useState<string[]>([])
  const [newHolidayDate, setNewHolidayDate] = useState('')
    // 【第51天新增】中药材库存
  const [herbs, setHerbs] = useState<any[]>([])
  const [showHerbForm, setShowHerbForm] = useState(false)
  // 【第55天新增】库存量/预警阈值改为默认留空（保存时留空分别按 0 / 50 处理），用户不必先删 0
  const [herbForm, setHerbForm] = useState({ herb_name: '', stock_amount: '', unit: '克', warn_threshold: '' })
  const [showLowOnly, setShowLowOnly] = useState(false)
  const [adjustingHerb, setAdjustingHerb] = useState<any>(null)
  const [adjustDelta, setAdjustDelta] = useState(0)
  // 【第66天新增】💰 财务管理接真实接口：账户数据（GET /api/finance/accounts）+ 三个按钮的内联小表单状态
  const [financeAccounts, setFinanceAccounts] = useState<{ username: string; role: string; balance: number }[]>([])
  const [financeForm, setFinanceForm] = useState<'recharge' | 'gift' | 'deduct' | null>(null)
  const [financeUsername, setFinanceUsername] = useState('')
  const [financeAmount, setFinanceAmount] = useState('')
  const [financeNote, setFinanceNote] = useState('')
  const [financeSubmitting, setFinanceSubmitting] = useState(false)
  // 【第52天新增】开方（中药材首字联想 + 药方结构化存储）
  // 【第69天新增】「患者姓名」初值改为当前面诊学生（selectedPatient），之后由下面的 useEffect 跟随 selectedPatient 同步
  const [prescriptionPatient, setPrescriptionPatient] = useState(selectedPatient)
  // 【第74天新增 / 开方九宫格改造】药材不再逐行手敲：由「九宫格点选」产生，初始为空。
  // 每条含 药材名 / 克数(string，默认留空) / role 君臣佐使(空串=未标注) / cooking_method 煎法(默认常规)
  const [prescriptionItems, setPrescriptionItems] = useState<{ herb_name: string; amount: string; role: string; cooking_method: string }[]>([])
  // 【第74天新增】九宫格顶部搜索框：输入药材名首字过滤九宫格（空 = 显示该老师全部药材）
  const [herbGridKeyword, setHerbGridKeyword] = useState('')
  // 【第74天新增】输入习惯 b：单味药点击后直接填分量 —— 用 ref 记下「点选后要聚焦到哪一行的克数框」
  // （用 ref 而不是 state：聚焦是纯 DOM 副作用，不需要触发额外渲染）
  const pendingFocusAmountHerb = useRef('')
  const prescriptionAmountRefs = useRef<{ [herbName: string]: HTMLInputElement | null }>({})
  const [savingPrescription, setSavingPrescription] = useState(false)
  // 【第53天新增】远程诊疗（勾选则不扣库存；默认当面诊疗，扣库存）
  const [prescriptionRemote, setPrescriptionRemote] = useState(false)
  // 【第69天新增】开方「患者姓名」默认填入当前面诊学生（selectedPatient）：
  // - selectedPatient 变化（面诊队列 / 搜索学生里换人）→ 输入框内容同步更新
  // - selectedPatient 不变时本 effect 不会触发，所以老师手动改过的姓名不会被覆盖
  useEffect(() => {
    setPrescriptionPatient(selectedPatient)
  }, [selectedPatient])

  // 【第74天新增】九宫格点选加药后，把光标自动送到新那一行的「克数」输入框（单味药点击即可直接填分量）；
  // 依赖里带上 prescriptionItems，保证那一行已经渲染出来、ref 已经挂上（这里只操作 DOM，不 setState）。
  useEffect(() => {
    const herbName = pendingFocusAmountHerb.current
    if (!herbName) return
    pendingFocusAmountHerb.current = ''
    const el = prescriptionAmountRefs.current[herbName]
    if (el) el.focus()
  }, [prescriptionItems])

  // 【第56天重构】智能体工作台三区块数据（老师端首页）：
  //   ① agentPendingTasks  ⏳ 待你确认（GET /api/agent_tasks?status=pending）
  //   ② agentDoneTasks     ✅ 已办汇报（GET /api/agent_tasks?status=approved，最近 5 条，按 created_at 倒序）
  //   ③ agentActionLogs    📜 行动日志（GET /api/agent_action_log?limit=10）
  const [agentPendingTasks, setAgentPendingTasks] = useState<any[]>([])
  const [agentDoneTasks, setAgentDoneTasks] = useState<any[]>([])
  const [agentActionLogs, setAgentActionLogs] = useState<any[]>([])
  const [scanningAgent, setScanningAgent] = useState(false)
  // 【第61天新增】首页「今日备忘录」时间轴：已完成事项（key 列表；点“完成”后从列表移除）+ 当前时间 + 本地记录日期
  const [memoDoneKeys, setMemoDoneKeys] = useState<string[]>([])
  const [memoNow, setMemoNow] = useState(() => Date.now())
  const [memoStoreDate, setMemoStoreDate] = useState('')
    // 【第50天新增】可视化排班网格
  const [calendarData, setCalendarData] = useState<any>(null)
  const [selectedDayIndex, setSelectedDayIndex] = useState(0)
  const yearOptions = Array.from({ length: currentYear - 1920 + 1 }, (_, i) => currentYear - i)
  const monthOptions = Array.from({ length: 12 }, (_, i) => i + 1).filter(m => {
    if (parseInt(newBirthYear) === currentYear) return m <= currentMonth
    return true
  })
  const getDayOptions = () => {
    const y = parseInt(newBirthYear) || currentYear
    const m = parseInt(newBirthMonth) || 1
    if (y === currentYear && m === currentMonth) {
      return Array.from({ length: currentDay }, (_, i) => i + 1)
    }
    const days = new Date(y, m, 0).getDate()
    return Array.from({ length: days }, (_, i) => i + 1)
  }

  const timeOptions = [
    { value: "", label: "时辰未知（选填）" },
    { value: "23:00", label: "子时 (23:00-01:00)" },
    { value: "01:00", label: "丑时 (01:00-03:00)" },
    { value: "03:00", label: "寅时 (03:00-05:00)" },
    { value: "05:00", label: "卯时 (05:00-07:00)" },
    { value: "07:00", label: "辰时 (07:00-09:00)" },
    { value: "09:00", label: "巳时 (09:00-11:00)" },
    { value: "11:00", label: "午时 (11:00-13:00)" },
    { value: "13:00", label: "未时 (13:00-15:00)" },
    { value: "15:00", label: "申时 (15:00-17:00)" },
    { value: "17:00", label: "酉时 (17:00-19:00)" },
    { value: "19:00", label: "戌时 (19:00-21:00)" },
    { value: "21:00", label: "亥时 (21:00-23:00)" }
  ]

  const extractImageUrls = (content: string): string[] => {
    const regex = /\/uploads\/[a-zA-Z0-9._-]+\.(?:jpg|jpeg|png|gif|webp)/g
    const matches = content.match(regex)
    return matches ? Array.from(new Set(matches)) : []
  }
  const extractAudioUrls = (content: string): string[] => {
    const regex = /\/uploads\/audio_[a-zA-Z0-9._-]+/g
    const matches = content.match(regex)
    return matches ? Array.from(new Set(matches)) : []
  }

  // ============== 【第73天新增】改动1：签字预览页渲染照片 / 改动2：标题动态化 / 改动3：归类下拉 ==============
  // 改动1：病历文本里出现 /uploads/xxx.jpg（例如【上传的图片】/uploads/xxx.jpg）时，在文本下方额外渲染缩略图。
  // 后端静态资源挂在 8000 端口，所以 <img src> 要拼成完整地址；页面本身仍保留 URL 文本（textarea 内容不动）。
  const toFullImageUrl = (url: string): string => (url.startsWith('http') ? url : IMAGE_ORIGIN + url)

  // 改动2：这张图是不是「本次会话老师现场拍的」？
  // uploadedImages 只在 📷 拍照 按钮上传成功时写入 → 命中即老师现场拍摄；
  // 未命中（如学生端提交陈述时上传的图片 / 刷新页面后的历史图片）保持原样，仍按「学生上传的图片」显示。
  const isTeacherLivePhoto = (url: string): boolean => uploadedImages.some(x => x.url === url)

  // 改动2：病历草案图片区的标题——老师现场拍的照片不再被误标成「学生上传的图片」
  const imageStripTitle = (content: string): string => {
    const urls = extractImageUrls(content)
    const teacherCount = urls.filter(u => isTeacherLivePhoto(u)).length
    if (teacherCount === 0) return '📷 学生上传的图片：'            // 全是学生端上传的 → 标题保持原样
    if (teacherCount === urls.length) return '📷 舌苔照 / 患处照'   // 全是老师现场拍的
    return '📷 图片（舌苔照 / 患处照 / 学生上传）'                   // 两种混在一起
  }

  // 改动3：缩略图下方的归类下拉（舌苔照 / 患处照 / 其他）。
  // 轻量版智能体判断 = 默认「患处照」，由老师在下拉里确认；状态只存在 uploadedImages 的每一条里，
  // 所以「📸 现场辅助记录的拍照区」与「📋 病历草案的图片区」两处共用同一份归类（改一处两处同步）。
  // url 不在本次会话拍照列表里（纯学生上传）→ 返回 null，不显示下拉，学生端零改动。
  const renderPhotoCategorySelect = (url: string, keySuffix: string) => {
    const idx = uploadedImages.findIndex(x => x.url === url)
    if (idx < 0) return null
    return (
      <select
        key={`photo-cat-${keySuffix}`}
        value={uploadedImages[idx].category}
        onChange={e => setUploadedImages(prev => prev.map((x, i) => (i === idx ? { ...x, category: e.target.value } : x)))}
        title="智能体判断归类（当前版本暂由老师确认）"
        style={{ width: '100%', marginTop: '4px', padding: '1px 2px', borderRadius: '6px', border: '1px solid #b8d8c0', background: '#fff', color: '#5a7d5a', fontSize: '11px', fontFamily: 'serif', cursor: 'pointer' }}
      >
        {PHOTO_CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
      </select>
    )
  }

  // ============== 初始化 ==============
  useEffect(() => {
    fetch('/api/huangli').then(r => r.json()).then(d => setHuangli(d)).catch(() => setHuangli(null))
    fetch('/api/teachers').then(r => r.json()).then(d => setTeachers(d)).catch(() => setTeachers([]))
    fetchPatients('张三')
    const urlParams = new URLSearchParams(window.location.search)
    const inviteCode = urlParams.get('invite')
    if (inviteCode) setPendingInviteCode(inviteCode)
    fetch('/api/patient-profile?patient_name=张三')
      .then(r => r.json())
      .then(d => {
        setGuardianLocation(d.location || '')
        setGuardianGender(d.gender || '')
        setGuardianBirthDate(d.birth_date || '')
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    fetch(`/api/patient-teachers?patient_name=${selectedPatient}`)
      .then(r => r.json())
      .then((list: string[]) => {
        setPatientTeachers(list)
        if (list.length > 0) setSelectedTeacher(list[0])
      })
      .catch(() => setPatientTeachers([]))
  }, [selectedPatient])

  useEffect(() => {
    if (currentRole === '李老师' || currentRole === '李老师智能体') {
      fetch(`/api/teacher-patients?teacher_name=${selectedTeacher}`)
        .then(r => r.json()).then(d => setTeacherPatients(d))
        .catch(() => setTeacherPatients([]))
      fetchSchedule()
      fetchHolidays()
      fetchCalendar()
      fetchHerbs()
    }
  }, [currentRole, selectedTeacher])

  // 【第75天新增 / 改动2】老师进入诊室页时拉一次该老师的「施治方案模板」：
  // GET /api/plan_template?teacher_name=李老师 → { content }（后端没有记录时返回空串，前端按“无模板”处理）。
  // 依赖 currentRole / teacherTab / selectedTeacher：切到诊室页、或换了老师时各拉一次；拉取失败就当没模板，不阻塞诊室记录。
  useEffect(() => {
    if (currentRole !== '李老师' && currentRole !== '李老师智能体') return
    if (teacherTab !== 'clinic') return
    fetch(`/api/plan_template?teacher_name=${selectedTeacher}`)
      .then(r => r.json())
      .then(d => setPlanTemplate(d && typeof d.content === 'string' ? d.content : ''))
      .catch(() => setPlanTemplate(''))
  }, [currentRole, teacherTab, selectedTeacher])

  // 【第56天重构】智能体工作台：进入老师端（含切换老师）时一次性拉取三个接口
  useEffect(() => {
    if (currentRole === '李老师' || currentRole === '李老师智能体') {
      fetchAgentWorkbench()
    }
  }, [currentRole, selectedTeacher])

  // 【第82天新增 / 老师端待处理陈述】进入「🩺 诊室」页签 / 切换老师时拉一次「待处理陈述」：
  // 与上面 plan_template 的依赖写法完全一致（切页签或换老师才重拉，不在诊室里输入时反复请求）。
  // 后端没这个接口时只会把列表置空 + complaintsMissing=true，不影响诊室其它功能。
  useEffect(() => {
    if (currentRole !== '李老师' && currentRole !== '李老师智能体') return
    if (teacherTab !== 'clinic') return
    fetchPendingComplaints()
  }, [currentRole, teacherTab, selectedTeacher])

  useEffect(() => {
    fetchRoleData()
    fetchDrafts()
    fetchPatientRecords()
    fetchPoints()
    fetchProfile()
    fetchHealthTrend()
    fetchDailyAdvice()
    fetchAppointments()
    fetchCalendar()
    setShowHistory(false)
  }, [currentRole, selectedPatient, selectedTeacher])

  // 【第70天修复 / 数据串台】切换当前就诊学生（selectedPatient）时，把所有“跟上一个学生绑定”的诊室 state 一次性清空，
  // 再按新学生重新从后端拉取病历草案；否则上一个学生的病历草案 / 施治方案 / 症状标签 / 开方 / 现场记录会串到下一位学生身上。
  // 依赖只有 selectedPatient：老师没切人时（例如只是手动改了开方患者姓名）不会被清掉。
  useEffect(() => {
    clinicPatientRef.current = selectedPatient   // 先让异步回调知道“现在是谁”（拍照上传播后返回时用它比对）
    // ① 现场辅助记录（工作台第一部分）：文本框内容 / 录音状态 / 原始转写缓冲 / 智能体清洗与整理标记 / 上传中标记
    //    先清缓冲区再停录音：stop() 会触发 onend → flush，缓冲区已空就不会把上一位学生的口述写回文本框
    teacherLiveRawRef.current = {}
    isUserStoppedRef.current = true   // 【第81天修复】切学生是程序主动停录音：onend 里不要再自动续录
    teacherLiveRecognition?.stop()
    setTeacherLiveRecognition(null)
    setTeacherLiveRecording(null)
    setTeacherLiveText({})
    setTeacherLiveCleaning({})
    setTeacherLiveStructurizing({})
    setLiveUploading({})
    // ② 病历标签（原「症状标签」）/ 辨证施治方案：工作台第三、第五部分
    setDraftTags({})
    setFinalPlans({})
    setPreviewDraft(null)
    // 【第75天新增 / 改动1】施治方案语音输入：与现场记录同样“先清缓冲区再停录音”（stop() 会触发 onend → flush，
    // 缓冲区已空就不会把上一位学生的口述追加回施治方案文本框）
    planRawRef.current = {}
    isUserStoppedRef.current = true   // 【第81天修复】切学生是程序主动停录音：onend 里不要再自动续录
    planRecognition?.stop()
    setPlanRecognition(null)
    setPlanRecording(null)
    setPlanCleaning({})
    // 【第75天新增 / 改动2】模板套用标记一起重置：新学生的方案为空时重新自动套用模板（模板本身是按老师存的，不清）
    planTemplateFilledRef.current = {}
    setPlanTemplateApplied({})
    // ③ 拍照：缩略图列表 / 「图片不够清晰」提示
    setUploadedImages([])
    setBlurryPhoto(null)
    // ④ 把脉记录输入（脉象 / 脉率 / 备注）
    setPulseTypes([])
    setPulseRate('')
    setPulseNote('')
    // ⑤ 开方：患者姓名对齐新学生，已选药材 / 九宫格搜索词 / 远程诊疗勾选全部清空
    setPrescriptionPatient(selectedPatient)
    setPrescriptionItems([])
    setHerbGridKeyword('')
    setPrescriptionRemote(false)
    // ⑥ 历史病历展开状态
    setShowHistory(false)
    // ⑦ 本地占位草案：新学生既没有后端草案、也没有本地占位草案时，补一条空的本地草案（让录音 / 拍照 / 把脉立刻可用）；
    //    其他学生未落库的本地草案保留（各自按 patient_name 存放，只在渲染自己的学生时才出现，互不串台）
    setLocalDrafts(prev => {
      if (prev.some(d => d.patient_name === selectedPatient)) return prev
      if (drafts.some(d => d.patient_name === selectedPatient)) return prev
      return [...prev, { id: -Date.now(), transcript_id: 0, patient_name: selectedPatient, content: '', signed: false }]
    })
    // ⑧ 病历草案重新从后端拉取（GET /api/drafts?teacher_name=...）。
    //    施治方案 / 症状标签 / 开方 / 上传图片 / 现场文本框在后端没有“未签字草稿”接口，因此只做清空；
    //    学生档案 / 积分 / 历史病历已由上面 [currentRole, selectedPatient, selectedTeacher] 的 effect 重新拉取（未改动）
    fetchDrafts()
  }, [selectedPatient])

  // 【第75天新增 / 改动2】模板套用：老师模板已拉到（planTemplate 非空）、且“当前选中学生”的施治方案为空时，自动填入模板内容。
  // ① 同一位学生只自动套用一次（planTemplateFilledRef 记录）→ 老师手动清空后不会被立刻填回，能真正改成别的写法；
  // ② 老师自己已经写过内容时（finalPlans 非空）绝不覆盖；
  // ③ 自动套用后置 planTemplateApplied[draftId] = true → 第五部分显示小灰字“已套用模板，可修改”。
  useEffect(() => {
    if (currentRole !== '李老师' && currentRole !== '李老师智能体') return
    if (teacherTab !== 'clinic') return
    if (!planTemplate.trim()) return
    const target = clinicPatientDrafts[0]
    if (!target) return
    if (planTemplateFilledRef.current[target.id]) return
    if ((finalPlans[target.id] || '').trim()) return
    planTemplateFilledRef.current[target.id] = true
    setFinalPlans(prev => ({ ...prev, [target.id]: planTemplate }))
    setPlanTemplateApplied(prev => ({ ...prev, [target.id]: true }))
  }, [currentRole, teacherTab, planTemplate, selectedPatient, clinicPatientDrafts.length, finalPlans])

  // ============== 数据获取 ==============
  const fetchPatients = (guardian: string) => {
    fetch(`/api/patients?guardian_name=${guardian}`).then(r => r.json()).then(d => setPatients(d)).catch(() => setPatients([]))
  }
  const fetchRoleData = () => {
    fetch(`/api/role-data?role=${currentRole}&patient_name=${selectedPatient}&teacher_name=${selectedTeacher}`)
      .then(r => r.json()).then(d => setRoleData(d)).catch(() => setRoleData(null))
  }
  const fetchDrafts = () => {
    fetch(`/api/drafts?teacher_name=${selectedTeacher}`)
      .then(r => r.json()).then(d => setDrafts(d)).catch(() => setDrafts([]))
  }
  const fetchPatientRecords = () => {
    fetch(`/api/patient-records?patient_name=${selectedPatient}&teacher_name=${selectedTeacher}`)
      .then(r => r.json()).then(d => {
        const sorted = [...d].sort((a: any, b: any) => b.id - a.id)
        setPatientRecords(sorted)
      }).catch(() => setPatientRecords([]))
  }
  const fetchPoints = () => {
    fetch(`/api/points?patient_name=${selectedPatient}`).then(r => r.json()).then(d => setPoints(d)).catch(() => setPoints(null))
  }
  // 【第66天新增】💰 财务管理：账户列表（顶部两个数字 + 充值/赠送/扣费表单的“学生姓名”下拉框都取自这里）
  const fetchFinanceAccounts = () => {
    fetch('/api/finance/accounts')
      .then(r => r.json())
      .then(d => setFinanceAccounts(d && Array.isArray(d.accounts) ? d.accounts : []))
      .catch(() => setFinanceAccounts([]))
  }

  // 【第66天新增】💰 财务管理：页面加载时自动拉取一次真实账户数据（老师端「管理」页顶部两个数字的数据来源）
  useEffect(() => {
    fetchFinanceAccounts()
  }, [])
  const fetchProfile = () => {
    fetch(`/api/patient-profile?patient_name=${selectedPatient}`).then(r => r.json()).then(d => setProfile(d)).catch(() => setProfile(null))
  }
  const fetchHealthTrend = () => {
    fetch(`/api/health-trend?patient_name=${selectedPatient}`)
      .then(r => r.json()).then(d => setHealthTrend(d && !d.error ? d : null))
      .catch(() => setHealthTrend(null))
  }
  const fetchDailyAdvice = () => {
    fetch(`/api/daily-advice?patient_name=${selectedPatient}`)
      .then(r => r.json()).then(d => setDailyAdvice(d && !d.error ? d : null))
      .catch(() => setDailyAdvice(null))
  }
  const fetchInvites = () => {
    fetch(`/api/invites?teacher_name=${selectedTeacher}`).then(r => r.json()).then(d => setInvites(d)).catch(() => setInvites([]))
  }

  // 老师工作时间
  const fetchSchedule = () => {
    fetch(`/api/teacher-schedule?teacher_name=${selectedTeacher}`)
      .then(r => r.json())
      .then(d => {
        setSchedule(d)
        setTempSchedule(JSON.parse(JSON.stringify(d)))
      })
      .catch(() => setSchedule(null))
  }

  const handleSaveSchedule = () => {
    fetch('/api/teacher-schedule', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ teacher_name: selectedTeacher, schedule: tempSchedule })
    }).then(() => {
      setSchedule(JSON.parse(JSON.stringify(tempSchedule)))
      setEditingSchedule(false)
      alert("工作时间已保存")
    })
  }

    // 【第49天新增】节假日
  const fetchHolidays = () => {
    fetch(`/api/teacher-holidays?teacher_name=${selectedTeacher}`)
      .then(r => r.json())
      .then(d => setHolidays(Array.isArray(d) ? d : []))
      .catch(() => setHolidays([]))
  }

  const handleAddHoliday = () => {
    if (!newHolidayDate) { alert("请选择日期"); return }
    if (holidays.includes(newHolidayDate)) { alert("该日期已在节假日列表"); return }
    const updated = [...holidays, newHolidayDate].sort()
    fetch('/api/teacher-holidays', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ teacher_name: selectedTeacher, holidays: updated })
    }).then(() => { setHolidays(updated); setNewHolidayDate('') })
  }

  const handleRemoveHoliday = (date: string) => {
    if (!confirm(`确定要移除【${date}】吗？`)) return
    const updated = holidays.filter(d => d !== date)
    fetch('/api/teacher-holidays', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ teacher_name: selectedTeacher, holidays: updated })
    }).then(() => setHolidays(updated))
  }

  
  // 【第51天新增】中药材库存
  const fetchHerbs = () => {
    fetch(`/api/herbs?teacher_name=${encodeURIComponent(selectedTeacher)}`)
      .then(res => res.json())
      .then(data => setHerbs(data))
  }

  const toggleLowOnly = () => {
    const next = !showLowOnly
    setShowLowOnly(next)
    const url = next
      ? `/api/herbs/low?teacher_name=${encodeURIComponent(selectedTeacher)}`
      : `/api/herbs?teacher_name=${encodeURIComponent(selectedTeacher)}`
    fetch(url).then(res => res.json()).then(data => setHerbs(data))
  }

  const handleSaveHerb = () => {
    // 【第55天新增】两个数字框留空时按默认值处理：库存量 0、预警阈值 50（显式填 0 则按 0）
    const numOr = (value: string, fallback: number) => {
      const trimmed = value.trim()
      if (trimmed === '') return fallback
      const parsed = parseFloat(trimmed)
      return Number.isNaN(parsed) ? fallback : parsed
    }
    const stockAmount = numOr(herbForm.stock_amount, 0)
    const warnThreshold = numOr(herbForm.warn_threshold, 50)
    fetch('/api/herbs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        teacher_name: selectedTeacher,
        herb_name: herbForm.herb_name,
        stock_amount: stockAmount,
        unit: herbForm.unit,
        warn_threshold: warnThreshold
      })
    })
      .then(res => res.json())
      .then(() => {
        setShowHerbForm(false)
        setHerbForm({ herb_name: '', stock_amount: '', unit: '克', warn_threshold: '' })
        fetchHerbs()
      })
  }

  const openAdjustModal = (herb: any) => {
    setAdjustingHerb(herb)
    setAdjustDelta(0)
  }

  const submitAdjust = () => {
    if (!adjustingHerb) return
    fetch(`/api/herbs/${adjustingHerb.id}/adjust`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ delta: adjustDelta })
    })
      .then(res => {
        if (!res.ok) {
          return res.json().then(err => { throw new Error(err.detail || '调整失败') })
        }
        return res.json()
      })
      .then(() => {
        setAdjustingHerb(null)
        setAdjustDelta(0)
        fetchHerbs()
      })
      .catch(err => alert(err.message))
  }

  const handleDeleteHerb = (herbId: number) => {
    if (!window.confirm('确定删除该药材记录吗？')) return
    fetch(`/api/herbs/${herbId}`, { method: 'DELETE' })
      .then(res => res.json())
      .then(() => fetchHerbs())
  }

  // 【第74天新增 / 开方九宫格改造】九宫格点选：已选中的格子再点一次 = 取消；未选中 = 加入下方「已选药材」列表。
  // 兼容两种输入习惯：a) 先连续点选多味药，再逐条填分量 / 选君臣佐使 / 选煎法；
  //                  b) 只点一味药，光标自动落到它那一行的克数输入框，直接填分量。
  const togglePrescriptionHerb = (herb: any) => {
    const herbName = herb.herb_name
    if (prescriptionItems.some(item => item.herb_name === herbName)) {
      setPrescriptionItems(prev => prev.filter(item => item.herb_name !== herbName))
      return
    }
    setPrescriptionItems(prev => [...prev, { herb_name: herbName, amount: '', role: '', cooking_method: DEFAULT_COOKING_METHOD }])
    pendingFocusAmountHerb.current = herbName   // 渲染完由上面的 effect 把光标送到这一行的克数框
  }

  // 【第74天新增】九宫格格子的选中态：以「已选药材列表」为准（点选 / 删除都即时反映到格子颜色上）
  const isPrescriptionHerbSelected = (herbName: string) => prescriptionItems.some(item => item.herb_name === herbName)

  // 【第74天新增】修改已选药材的某一列（克数 / 君臣佐使 / 煎法）；药材名不可编辑（由九宫格决定）
  const changePrescriptionItem = (index: number, field: 'amount' | 'role' | 'cooking_method', value: string) => {
    setPrescriptionItems(prev => prev.map((item, i) => {
      if (i !== index) return item
      if (field === 'amount') return { ...item, amount: value }
      if (field === 'role') return { ...item, role: value }
      return { ...item, cooking_method: value }
    }))
  }

  // 【第74天新增】删除已选药材（同时会让九宫格对应格子回到未选中状态）
  const removePrescriptionItem = (index: number) => {
    setPrescriptionItems(prev => prev.filter((_, i) => i !== index))
  }

  // 【第74天新增】九宫格里要展示的药材：按「药材名首字」过滤（与后端 /api/herbs/search 语义一致：只看首字），
  // 搜索框为空时展示该老师全部药材库存（herbs 由 fetchHerbs 从 /api/herbs 拉取）。
  const herbGridKeywordText = herbGridKeyword.trim()
  const herbGridList = herbGridKeywordText
    ? herbs.filter(h => String(h.herb_name || '').startsWith(herbGridKeywordText))
    : herbs

  const handleSavePrescription = () => {
    // 【第71天修复 / 开方校验】【第74天调整】九宫格改造后不再有空白行：
    //  - 一味药都没选 → 提示先选药；
    //  - 任一药材的克数不是大于 0 的数字 → 提示「请填写完整的分量」；
    //  - 药材名为空（理论上不会出现，作为兜底）→ 提示补全。
    // 以上任一条不通过都不调后端、不落库。
    if (prescriptionItems.length === 0) { alert('请至少选择一味药材'); return }
    const hasInvalidAmount = prescriptionItems.some(item => {
      const amount = Number(item.amount)   // 空串 / 非数字 → 0 / NaN，都会被下面拦下
      return !Number.isFinite(amount) || amount <= 0
    })
    if (hasInvalidAmount) { alert('请填写完整的分量'); return }
    if (prescriptionItems.some(item => !item.herb_name.trim())) { alert('请填写完整的药材名'); return }
    // 【第74天新增】每条药材把君臣佐使（role，空串=未标注）与煎法（cooking_method）一起提交给后端
    const items = prescriptionItems.map(item => ({
      herb_name: item.herb_name.trim(),
      amount: Number(item.amount),
      unit: '克',
      role: item.role || '',
      cooking_method: item.cooking_method || DEFAULT_COOKING_METHOD
    }))
    setSavingPrescription(true)
    fetch('/api/prescriptions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // 一期没有备注输入框，note 先传空串（后端/表结构已支持）
      body: JSON.stringify({ teacher_name: selectedTeacher, patient_name: prescriptionPatient, items, note: '', is_remote: prescriptionRemote })
    })
      .then(res => res.json())
      .then(data => {
        setSavingPrescription(false)
        // 当面诊疗扣库存失败 → 弹窗提示，不保存（表单保留，方便老师改数量）
        if (data.error) { alert(data.error); return }
        setPrescriptionPatient('')
        setPrescriptionItems([])
        setHerbGridKeyword('')
        setPrescriptionRemote(false)
        fetchHerbs()   // 【第74天新增】刷新九宫格里的库存数字（当面诊疗会扣减）
        if (prescriptionRemote) {
          alert('药方已保存（远程诊疗，库存未变）')
        } else {
          alert('药方已保存，库存已扣减')
        }
      })
      .catch(() => { setSavingPrescription(false); alert('保存失败，请重试') })
  }

  // 【第56天重构】智能体工作台：一次拉取三个接口，填满三个区块
  //   ① 待你确认 → GET /api/agent_tasks?teacher_name=当前老师&status=pending
  //   ② 已办汇报 → GET /api/agent_tasks?teacher_name=当前老师&status=approved（后端按 created_at 倒序，前端取最近 5 条）
  //   ③ 行动日志 → GET /api/agent_action_log?teacher_name=当前老师&limit=10
  // 任一接口失败只把对应区块置空，不影响其它区块；响应不是数组时同样按空处理（防止 .map 报错）。
  const fetchAgentWorkbench = () => {
    const teacher = encodeURIComponent(selectedTeacher)
    fetch(`/api/agent_tasks?teacher_name=${teacher}&status=pending`)
      .then(res => res.json())
      .then(data => setAgentPendingTasks(Array.isArray(data) ? data : []))
      .catch(() => setAgentPendingTasks([]))
    fetch(`/api/agent_tasks?teacher_name=${teacher}&status=approved`)
      .then(res => res.json())
      .then(data => setAgentDoneTasks(Array.isArray(data) ? data.slice(0, 5) : []))
      .catch(() => setAgentDoneTasks([]))
    fetch(`/api/agent_action_log?teacher_name=${teacher}&limit=10`)
      .then(res => res.json())
      .then(data => setAgentActionLogs(Array.isArray(data) ? data : []))
      .catch(() => setAgentActionLogs([]))
  }

  // 【第82天新增 / 老师端待处理陈述】📝 待处理陈述：拉取当前老师名下 status=pending 的学生陈述
  //   GET /api/complaints?teacher_name=李老师&status=pending
  // 期望返回：[{ id, teacher_name, patient_name, content, status, created_at }]
  //   （created_at 是后端 ISO 串，直接交给 formatAgentTime 显示成 MM-DD HH:mm；content 是整理后的「面诊前摘要」全文）
  // 容错：① 响应不是数组时兼容 { complaints: [...] }（取不到就按空列表处理，绝不 .map 报错）；
  //       ② 后端还没这个接口（404 / 非 2xx / 连不上）→ complaintsMissing=true，卡片按“暂无”渲染并提示待补接口，
  //          不弹窗、不影响诊室其它功能；后端补上接口后本卡片无需再改代码。
  const fetchPendingComplaints = () => {
    setComplaintsLoading(true)
    fetch(`/api/complaints?teacher_name=${encodeURIComponent(selectedTeacher)}&status=pending`)
      .then(res => {
        if (!res.ok) throw new Error(`complaints ${res.status}`)
        return res.json()
      })
      .then(data => {
        setComplaintsMissing(false)
        if (Array.isArray(data)) { setPendingComplaints(data); return }
        setPendingComplaints(data && Array.isArray(data.complaints) ? data.complaints : [])
      })
      .catch(() => { setComplaintsMissing(true); setPendingComplaints([]) })
      .finally(() => setComplaintsLoading(false))
  }

  // 【第82天新增 / 老师端待处理陈述】「查看详情」：只切本地的展开状态（不调后端），
  // 展开后显示完整内容（whiteSpace: pre-wrap 保留后端摘要里的换行）。
  const toggleComplaintDetail = (rowKey: string) => {
    setExpandedComplaintIds(prev => prev.includes(rowKey) ? prev.filter(x => x !== rowKey) : [...prev, rowKey])
  }

  // 【第82天新增 / 老师端待处理陈述】「已处理」：POST /api/complaints/{id}/process
  // （路径风格与现成的 POST /api/appointments/{id}/confirm、POST /api/drafts/{id}/sign 保持一致），
  // 后端把这条的 status 改成 processed；成功后本地直接把这条从列表里移除（不必等下一次刷新）。
  // 后端没这个接口时不静默失败：弹一句明确提示，列表保持原样。
  const handleProcessComplaint = (id: number, rowKey: string) => {
    if (!id) { alert('这条陈述缺少 id，无法标记已处理（后端接口字段待确认）。'); return }
    if (processingComplaintIds.includes(rowKey)) return
    setProcessingComplaintIds(prev => [...prev, rowKey])
    fetch(`/api/complaints/${id}/process`, { method: 'POST' })
      .then(res => {
        if (!res.ok) throw new Error(`process complaint ${res.status}`)
        return res.json()
      })
      .then(() => {
        setPendingComplaints(prev => prev.filter(c => String(c && c.id) !== String(id)))
        setExpandedComplaintIds(prev => prev.filter(x => x !== rowKey))
      })
      .catch(() => alert('标记「已处理」失败：后端暂未提供 POST /api/complaints/{id}/process 接口，需要后端新增后再试。'))
      .finally(() => setProcessingComplaintIds(prev => prev.filter(x => x !== rowKey)))
  }

  // 【行政化 B3 / 第56天新增】触发统一扫描：POST /api/agent/scan，请求体 { teacher_name }
  // 一次扫出三类学生请示（后端依次跑）：沉默关怀 send_care_notice + 欠费预存 send_billing_notice + 复诊提醒 send_recall_notice，
  // 都写进同一张 agent_tasks（status=pending，与上面三个接口读的是同一张表），所以扫完直接重拉工作台三区块。
  // 后端返回 { ok, created }；created 兼容老字段 new_tasks（都取不到时按 0 处理，避免 undefined 弹窗）。
  const handleAgentScan = () => {
    setScanningAgent(true)
    fetch('/api/agent/scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ teacher_name: selectedTeacher })
    })
      .then(res => res.json())
      .then(data => {
        setScanningAgent(false)
        fetchAgentWorkbench()
        const created = data.created ?? data.new_tasks ?? 0
        alert(created > 0 ? `智能体发现 ${created} 条新请示` : '没有发现新的待办')
      })
      .catch(() => { setScanningAgent(false); alert('扫描失败，请重试') })
  }

  // 【第56天重构】待确认区块 / ✅ 确认：POST /api/agent_tasks/approve  body { task_id }
  // 先本地移除（按钮立即消失、不卡）→ 无论成败都重拉三个接口，保证三个区块数据一致。
  const handleApproveAgentTask = (taskId: number) => {
    setAgentPendingTasks(prev => prev.filter(t => t.id !== taskId))
    fetch('/api/agent_tasks/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId })
    })
      .then(res => res.json())
      .then(() => fetchAgentWorkbench())
      .catch(() => { alert('处理失败，请重试'); fetchAgentWorkbench() })
  }

  // 【第56天重构】待确认区块 / ❌ 忽略：POST /api/agent_tasks/reject  body { task_id }（行为同上）
  const handleRejectAgentTask = (taskId: number) => {
    setAgentPendingTasks(prev => prev.filter(t => t.id !== taskId))
    fetch('/api/agent_tasks/reject', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId })
    })
      .then(res => res.json())
      .then(() => fetchAgentWorkbench())
      .catch(() => { alert('处理失败，请重试'); fetchAgentWorkbench() })
  }
    // 【第50天新增】拉取可视化排班数据
  const fetchCalendar = () => {
    fetch(`/api/appointments/calendar?teacher_name=${selectedTeacher}`)
      .then(r => r.json())
      .then(d => setCalendarData(d))
      .catch(() => setCalendarData(null))
  }
  
  // 切换某天某个时段
  const toggleSlot = (day: string, slot: string) => {
    setTempSchedule(prev => {
      const daySlots = prev[day] || []
      const newSlots = daySlots.includes(slot) ? daySlots.filter(s => s !== slot) : [...daySlots, slot].sort()
      return { ...prev, [day]: newSlots }
    })
  }

  // ============== 学生端行为 ==============
  const handleCheckIn = () => {
    fetch(`/api/check-in?patient_name=${selectedPatient}&teacher_name=${selectedTeacher}`, { method: 'POST' })
      .then(() => { fetchRoleData(); fetchPoints() })
  }
  const handleApprove = () => {
    fetch(`/api/approve?patient_name=${selectedPatient}&teacher_name=${selectedTeacher}`, { method: 'POST' })
      .then(() => fetchRoleData())
  }

  const startStudentRecording = async () => {
    if (isRecordingStudent) {
      isUserStoppedRef.current = true   // 【第81天修复】用户主动点停：onend 里不再自动续录
      mediaRecorder?.stop()
      recognitionStudent?.stop()
      setIsRecordingStudent(false)
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream)
      const chunks: Blob[] = []
      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data) }
      recorder.onstop = async () => {
        const blob = new Blob(chunks, { type: 'audio/webm' })
        const formData = new FormData()
        formData.append('file', blob, 'recording.webm')
        try {
          const r = await fetch('/api/upload-audio', { method: 'POST', body: formData })
          const d = await r.json()
          if (d.url) setPendingAudios(prev => [...prev, d.url])
        } catch (e) { console.error('音频上传失败', e) }
        stream.getTracks().forEach(t => t.stop())
      }
      const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
      if (SR) {
        const rec = new SR()
        rec.continuous = true
        rec.interimResults = false
        rec.lang = 'zh-CN'
        rec.onresult = (event: any) => {
          let finalTranscript = ''
          for (let i = event.resultIndex; i < event.results.length; i++) {
            if (event.results[i].isFinal) finalTranscript += event.results[i][0].transcript
          }
          if (finalTranscript) setInputText(prev => prev + finalTranscript)
        }
        // 【第81天修复】no-speech = 几秒没说话的静音超时（不是真错误），交给 onend 自动续录；其他错误才停
        rec.onerror = (e: any) => {
          if (e && e.error === 'no-speech') return
          isUserStoppedRef.current = true   // 无权限 / 无麦克风等真错误：标记成“用户停了”，避免 onend 反复重试成死循环
          console.error('语音识别错误:', e)
        }
        rec.onend = () => {
          // 【第81天修复】不是用户主动停的 → 说明是被静音打断，自动续上，录音不会提前结束
          if (!isUserStoppedRef.current) { try { rec.start() } catch { /* 实例已在运行，忽略 */ } return }
          // 用户主动停的：MediaRecorder 的停止与状态切换由上面的点击分支处理，这里无需再做
        }
        isUserStoppedRef.current = false   // 【第81天修复】开始录音：标记为“用户没停”
        rec.start()
        setRecognitionStudent(rec)
      }
      recorder.start()
      setMediaRecorder(recorder)
      setIsRecordingStudent(true)
    } catch (e) {
      alert("无法访问麦克风，请检查浏览器权限。")
    }
  }

  const handleTranscribe = () => {
    if (!inputText.trim() && pendingImages.length === 0 && pendingAudios.length === 0) {
      alert("请先输入文字、录音或上传图片"); return
    }
    fetch('/api/patient-structurize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ patient_name: selectedPatient, raw_text: inputText })
    })
      .then(r => r.json())
      .then(d => {
        const notes: string[] = []
        if (pendingImages.length > 0) notes.push(`${pendingImages.length} 张图片`)
        if (pendingAudios.length > 0) notes.push(`${pendingAudios.length} 段录音`)
        const attachText = notes.length > 0 ? `\n\n（本次将随附：${notes.join('、')}）` : ''
        const preview = `【学生自述】\n学生姓名：${selectedPatient}\n就诊时间：${now.getFullYear()}年${now.getMonth()+1}月${now.getDate()}日\n\n${d.structured}${attachText}\n\n（以上内容已经过学生智能体整理，待学生确认后发送给老师）`
        setStructuredPreview(preview)
      })
      .catch(() => {
        const preview = `【学生自述】\n学生姓名：${selectedPatient}\n就诊时间：${now.getFullYear()}年${now.getMonth()+1}月${now.getDate()}日\n主诉内容：${inputText}\n\n（以上为学生原话转述，未经智能体推断）`
        setStructuredPreview(preview)
      })
  }

  const handleConfirmSend = async () => {
    if (!structuredPreview) return
    const imagePart = pendingImages.length > 0
      ? '\n\n【学生上传的图片】\n' + pendingImages.map((url, i) => `图片${i+1}：${url}`).join('\n') : ''
    const audioPart = pendingAudios.length > 0
      ? '\n\n【学生上传的录音】\n' + pendingAudios.map((url, i) => `录音${i+1}：${url}`).join('\n') : ''
    const fullContent = structuredPreview + imagePart + audioPart

    await fetch('/api/transcribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ patient_name: selectedPatient, teacher_name: selectedTeacher, content: fullContent, data_type: 'text' })
    })

    setInputText(''); setPendingImages([]); setPendingAudios([]); setStructuredPreview(null)
    fetchDrafts()
  }

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    const formData = new FormData()
    formData.append('file', file)
    fetch(`/api/upload-temp`, { method: 'POST', body: formData })
      .then(r => r.json())
      .then(d => {
        setUploading(false)
        setPendingImages(prev => [...prev, d.url])
        if (fileInputRef.current) fileInputRef.current.value = ''
      })
      .catch(() => { setUploading(false); alert("图片上传失败") })
  }

  const handleRemovePendingImage = (url: string) => {
    setPendingImages(prev => prev.filter(u => u !== url))
  }

  // ============== 【第80天新增 / 改动3】🩺 面诊前准备：十问歌主动追问（学生端） ==============
  // 与后端的约定：current_answers 用「问：…⏎答：…」累积（见 INTAKE_QA_SEP 注释），第一次传空串。
  const intakeAskNext = (answers: string) => {
    setIntakeLoading(true)
    fetch('/api/agent/ask_next_question', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ patient_name: selectedPatient, current_answers: answers })
    })
      .then(r => { if (!r.ok) throw new Error('ask_next_question failed'); return r.json() })
      .then(d => {
        setIntakeLoading(false)
        const next = d && typeof d.question === 'string' ? d.question.trim() : ''
        if (!d || d.done || !next) { setIntakeQuestion(''); setIntakeDone(true); return }
        setIntakeQuestion(next)
        setIntakeDone(false)
      })
      .catch(() => { setIntakeLoading(false); alert('智能体追问失败，请稍后再试。') })
  }

  const handleStartIntake = () => {
    setShowIntake(true)
    setIntakeQuestion(''); setIntakeAnswer(''); setIntakeAnswers('')
    setIntakeRounds(0); setIntakeDone(false); setIntakeSent(false)
    intakeAskNext('')   // 第一次调用：current_answers 为空字符串（后端从十问歌第 1 项开始）
  }

  const handleNextIntakeQuestion = () => {
    const answer = intakeAnswer.trim()
    if (!answer) { alert('先写一句回答（或点 🎙️ 语音输入）再点“下一个问题”。'); return }
    const merged = (intakeAnswers ? intakeAnswers + INTAKE_QA_SEP : '')
      + '问：' + intakeQuestion + INTAKE_QA_SEP + '答：' + answer
    setIntakeAnswers(merged)
    setIntakeAnswer('')
    const rounds = intakeRounds + 1
    setIntakeRounds(rounds)
    if (rounds >= MAX_INTAKE_ROUNDS) {   // 兜底：拉满上限就直接进入「发送确认」，不让学生被卡住
      setIntakeQuestion(''); setIntakeDone(true); return
    }
    intakeAskNext(merged)                // 带着累积的回答去拉下一问
  }

  const handleSendIntake = () => {
    if (intakeSending) return
    setIntakeSending(true)
    fetch('/api/agent/save_intake', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        patient_name: selectedPatient,
        teacher_name: (intakeAppointment && intakeAppointment.teacher_name) || selectedTeacher,
        answers: intakeAnswers
      })
    })
      .then(r => { if (!r.ok) throw new Error('save_intake failed'); return r.json() })
      .then(() => { setIntakeSending(false); setIntakeSent(true) })
      .catch(() => { setIntakeSending(false); alert('发送失败，请稍后再试。') })
  }

  // 【复用现有录音逻辑】🎙️ 语音输入：与「🗣️ 学生智能体」卡片的 startStudentRecording 同一套
  // Web Speech API（zh-CN、边听边出最终结果、点第二次停止、拿不到麦克风就提示权限）——
  // 原有录音函数一行没动，这里只做两处裁剪：① 转写结果写进追问回答框；② 不上传音频（追问的答案是文本，
  // 图片 / 录音附件仍走「🗣️ 学生智能体」卡片原有流程）。
  const startIntakeRecording = () => {
    if (intakeRecording) {
      isUserStoppedRef.current = true   // 【第81天修复】用户主动点停：onend 里不再自动续录
      intakeRecognition?.stop()
      setIntakeRecording(false)
      return
    }
    try {
      const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
      if (!SR) { alert('当前浏览器不支持语音识别，请直接输入文字。'); return }
      const rec = new SR()
      rec.continuous = true
      rec.interimResults = false
      rec.lang = 'zh-CN'
      rec.onresult = (event: any) => {
        let finalTranscript = ''
        for (let i = event.resultIndex; i < event.results.length; i++) {
          if (event.results[i].isFinal) finalTranscript += event.results[i][0].transcript
        }
        if (finalTranscript) setIntakeAnswer(prev => prev + finalTranscript)
      }
      // 【第81天修复】no-speech = 几秒没说话的静音超时（不是真错误），交给 onend 自动续录；其他错误才停
      rec.onerror = (e: any) => {
        if (e && e.error === 'no-speech') return
        isUserStoppedRef.current = true   // 无权限 / 无麦克风等真错误：标记成“用户停了”，避免 onend 反复重试成死循环
        console.error('追问语音识别错误:', e)
      }
      rec.onend = () => {
        // 【第81天修复】不是用户主动停的 → 说明是被静音打断，自动续上，录音不会提前结束
        if (!isUserStoppedRef.current) { try { rec.start() } catch { /* 实例已在运行，忽略 */ } return }
        setIntakeRecording(false)   // 用户主动停的：走原有结束逻辑
      }
      isUserStoppedRef.current = false   // 【第81天修复】开始录音：标记为“用户没停”
      rec.start()
      setIntakeRecognition(rec)
      setIntakeRecording(true)
    } catch (e) {
      alert("无法访问麦克风，请检查浏览器权限。")
    }
  }

  // ============== 老师端行为 ==============
  // 【第68天新增】录音停止后：原始转写先送智能体清洗（去噪 / 提炼 / 结构化），再把 cleaned_text 追加到文本框。
  // 追加目标仍是“现场辅助记录”文本框（teachersLiveText），老师点“追加到病历”才进病历草案，原有流程不变。
  // 接口失败（网络错误 / 非 2xx）→ 降级追加原始文本，并提示“智能体处理失败，已追加原始文本”。
  const flushTeacherLiveTranscript = (draftId: number) => {
    const raw = (teacherLiveRawRef.current[draftId] || '').trim()
    teacherLiveRawRef.current[draftId] = ''   // 取走即清空，避免重复清洗
    if (!raw) return
    setTeacherLiveCleaning(prev => ({ ...prev, [draftId]: true }))
    const appendToLiveTextBox = (text: string) => setTeacherLiveText(prev => {
      const old = prev[draftId] || ''
      return { ...prev, [draftId]: old.trim() ? old + '\n\n' + text : text }
    })
    fetch('/api/agent/clean_transcript', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ raw_text: raw })
    })
      .then(r => { if (!r.ok) throw new Error('clean_transcript failed'); return r.json() })
      .then(d => {
        setTeacherLiveCleaning(prev => ({ ...prev, [draftId]: false }))
        const cleaned = (d && typeof d.cleaned_text === 'string' && d.cleaned_text.trim()) ? d.cleaned_text : raw
        appendToLiveTextBox(cleaned)
      })
      .catch(() => {
        setTeacherLiveCleaning(prev => ({ ...prev, [draftId]: false }))
        appendToLiveTextBox(raw)   // 降级：接口失败就直接追加原始文本，不阻塞老师
        alert('智能体处理失败，已追加原始文本')
      })
  }

  const startTeacherLiveRecording = (draftId: number) => {
    if (teacherLiveRecording === draftId) {
      isUserStoppedRef.current = true   // 【第81天修复】用户主动点停：onend 里不再自动续录
      teacherLiveRecognition?.stop(); setTeacherLiveRecording(null); return
    }
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SR) { alert("当前浏览器不支持语音识别。"); return }
    const rec = new SR()
    rec.continuous = true
    rec.interimResults = false
    rec.lang = 'zh-CN'
    // 【第68天新增】本轮录音只 flush 一次（停止按钮 / onend / onerror 可能都触发，避免重复清洗 + 重复追加）
    let flushed = false
    const flushOnce = () => { if (flushed) return; flushed = true; flushTeacherLiveTranscript(draftId) }
    teacherLiveRawRef.current[draftId] = ''   // 开新一段录音前清空缓冲区
    rec.onresult = (event: any) => {
      let finalTranscript = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) finalTranscript += event.results[i][0].transcript
      }
      // 【第68天新增】录音中不再直接写入文本框，先攒进缓冲区，等停止后统一交给智能体清洗
      if (finalTranscript) teacherLiveRawRef.current[draftId] = (teacherLiveRawRef.current[draftId] || '') + finalTranscript
    }
    // 【第81天修复】no-speech = 几秒没说话的静音超时（不是真错误）：不当作结束，交给 onend 自动续录；
    // 其他错误（无权限 / 无麦克风等）才收尾，并标记成“用户停了”，避免 onend 反复重试成死循环
    rec.onerror = (e: any) => {
      if (e && e.error === 'no-speech') return
      isUserStoppedRef.current = true
      setTeacherLiveRecording(null); flushOnce()
    }
    rec.onend = () => {
      // 【第81天修复】用户没点停 → 被静音打断的：自动续上（长口述不会中途断掉，转写继续攒进缓冲区）
      if (!isUserStoppedRef.current) { try { rec.start() } catch { /* 实例已在运行，忽略 */ } return }
      // 用户主动停的：走原有结束逻辑（清洗 → 追加到“现场辅助记录”文本框）
      setTeacherLiveRecording(null); flushOnce()
    }
    isUserStoppedRef.current = false   // 【第81天修复】开始录音：标记为“用户没停”
    rec.start()
    setTeacherLiveRecognition(rec)
    setTeacherLiveRecording(draftId)
  }

  // 【第72天明确化】“🤖 AI整理成病历格式”：原料 = 现场辅助记录文本框，成品 = 病历草案文本框。
  // ① 把现场辅助记录（teacherLiveText[draftId]）整段 POST /api/teacher-structurize（复用现有接口，后端零改动）；
  // ② 收到 structured 后【覆盖式】写入该学生的病历草案文本框（setClinicDraftById 直接把 content 换成整理结果，不是追加）；
  // ③ 原料文本框内容保留不动，方便老师对照 / 再次整理；要落库仍点第二部分的“保存病历修改”。
  const handleTeacherStructurize = (draftId: number) => {
    const raw = teacherLiveText[draftId]
    if (!raw || !raw.trim()) { alert("请先录音或输入内容"); return }
    setTeacherLiveStructurizing(prev => ({ ...prev, [draftId]: true }))
    fetch('/api/teacher-structurize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ raw_text: raw })
    })
      .then(r => r.json())
      .then(d => {
        setTeacherLiveStructurizing(prev => ({ ...prev, [draftId]: false }))
        if (d.structured) setClinicDraftById(draftId, item => ({ ...item, content: d.structured }))
      })
      .catch(() => { setTeacherLiveStructurizing(prev => ({ ...prev, [draftId]: false })); alert("AI 整理失败") })
  }

  // 【第71天修复 / 签字死锁】本地占位草案（id < 0）落库：先拿到一个“真实 draft_id”，再把老师编辑的内容 PUT 进去。
  //
  // 死锁根因（读后端代码确认，见 backend/database.py + backend/main.py）：
  // ① GET /api/transcriptions 只返回 processed = 0 的陈述（database.get_transcriptions 写死了条件）；
  // ② POST /api/generate-draft 也只能从 processed = 0 的陈述里找，找不到就返回 {"error": "找不到该转述"}；
  // ③ database.insert_draft 会把陈述标记 processed = 1，sign_draft 签字时更会把陈述整行 DELETE 掉。
  // 因此“第二次就诊 / 学生没发陈述”时永远找不到可用陈述：旧代码只能 keepLocal() 弹
  // “该学生还没有提交陈述…”，草案永远落不了库；而“确认签字”又提示要先落库 → 保存 ↔ 签字 互相踢皮球 = 死循环。
  //
  // 修复：找不到可用陈述时，改用 POST /api/transcribe 造一条“老师现场录入”的陈述
  // （后端在该接口里会自动生成病历草案），再用 GET /api/drafts 取回这个学生的真实 draft_id，
  // 最后 PUT 写入老师编辑的内容。这条临时陈述在签字时会被 sign_draft 一并删除，不会留下脏数据。
  const findDraftIdByPatient = (patientName: string): Promise<number | null> =>
    fetch(`/api/drafts?teacher_name=${encodeURIComponent(selectedTeacher)}`)
      .then(r => r.json())
      .then((list: any[]) => {
        if (!Array.isArray(list)) return null
        const mine = list.filter(d => d.patient_name === patientName).sort((a: any, b: any) => b.id - a.id)
        return mine.length > 0 ? Number(mine[0].id) : null
      })
      .catch(() => null)

  const createDraftViaTranscribe = (patientName: string): Promise<number | null> => {
    const now = new Date()
    const placeholder = `【老师现场录入】\n学生姓名：${patientName}\n就诊时间：${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日\n（本次由老师在诊室直接录入病历，学生未提交线上陈述）`
    return fetch('/api/transcribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ patient_name: patientName, teacher_name: selectedTeacher, content: placeholder, data_type: 'text' })
    })
      .then(() => findDraftIdByPatient(patientName))
      .catch(() => null)
  }

  // 返回落库后的真实 draft_id（失败返回 null）
  const saveLocalDraftToBackend = (localId: number, newContent: string): Promise<number | null> => {
    const local = localDrafts.find(d => d.id === localId)
    if (!local) return Promise.resolve(null)
    const patientName = local.patient_name
    setLocalDraftSaving(true)
    // 先更新本地显示，避免看起来“没保存”
    setLocalDrafts(prev => prev.map(d => d.id === localId ? { ...d, content: newContent } : d))
    return fetch(`/api/transcriptions?patient_name=${encodeURIComponent(patientName)}&teacher_name=${encodeURIComponent(selectedTeacher)}`)
      .then(r => r.json())
      .then((list: any[]) => {
        const latest = Array.isArray(list) && list.length > 0 ? list[0] : null
        if (!latest) return createDraftViaTranscribe(patientName)   // 没有待处理陈述 → 兜底：造临时陈述 + 让后端自动生成草案
        return fetch(`/api/generate-draft?transcript_id=${latest.id}`, { method: 'POST' })
          .then(r => r.json())
          .then((res: any) => (res && res.draft_id)
            ? Number(res.draft_id)
            : createDraftViaTranscribe(patientName))   // 陈述已被处理过（processed = 1）→ 同样走兜底
      })
      .catch(() => createDraftViaTranscribe(patientName))
      .then(draftId => {
        if (!draftId) return null
        return fetch(`/api/drafts/${draftId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: newContent })
        }).then(() => draftId).catch(() => null)
      })
      .then(draftId => {
        setLocalDraftSaving(false)
        if (draftId) fetchDrafts()   // 拉回后端草案：本地占位草案会被自动清理，编辑框换成真实草案
        return draftId
      })
  }

  // ============== 【第75天新增】施治方案：模板保存（改动2） + 语音输入（改动1） ==============

  // 【改动2】把当前施治方案存成该老师的新模板：POST /api/plan_template { teacher_name, content }（后端 upsert，越用越贴合老师写法）。
  // · 内容为空时直接跳过：避免把老师已有的模板抹成空串；
  // · 保存成功后同步更新本地 planTemplate：下一位学生（施治方案为空）进来即可套用新模板；
  // · 保存失败不打断老师（不弹窗），下次点“保存病历修改 / 预览完整病历”会再试一次。
  const savePlanTemplate = (content: string) => {
    const text = (content || '').trim()
    if (!text) return
    setPlanTemplate(text)
    fetch('/api/plan_template', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ teacher_name: selectedTeacher, content: text })
    }).catch(() => {})
  }

  // 【改动1】录音停止后：原始转写先送智能体清洗，再把 cleaned_text 追加到「辨证施治方案」文本框末尾。
  // 接口失败（网络错误 / 非 2xx / 返回空）→ 降级直接追加原始文本，并提示“智能体处理失败，已追加原始文本”。
  const flushPlanTranscript = (draftId: number) => {
    const raw = (planRawRef.current[draftId] || '').trim()
    planRawRef.current[draftId] = ''   // 取走即清空，避免重复清洗
    if (!raw) return
    setPlanCleaning(prev => ({ ...prev, [draftId]: true }))
    const appendToPlanTextBox = (text: string) => setFinalPlans(prev => {
      const old = prev[draftId] || ''
      return { ...prev, [draftId]: old.trim() ? old + '\n\n' + text : text }
    })
    fetch('/api/agent/clean_plan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ raw_text: raw })
    })
      .then(r => { if (!r.ok) throw new Error('clean_plan failed'); return r.json() })
      .then(d => {
        setPlanCleaning(prev => ({ ...prev, [draftId]: false }))
        const cleaned = (d && typeof d.cleaned_text === 'string' && d.cleaned_text.trim()) ? d.cleaned_text : raw
        appendToPlanTextBox(cleaned)
      })
      .catch(() => {
        setPlanCleaning(prev => ({ ...prev, [draftId]: false }))
        appendToPlanTextBox(raw)   // 降级：接口失败就直接追加原始文本，不阻塞老师
        alert('智能体处理失败，已追加原始文本')
      })
  }

  // 【改动1】🎙️ 语音输入按钮：未录音 → 开始录音（zh-CN）；正在录音（同一位学生）→ 停止录音（停止后触发上面的清洗）
  const startPlanRecording = (draftId: number) => {
    if (planRecording === draftId) {
      isUserStoppedRef.current = true   // 【第81天修复】用户主动点停：onend 里不再自动续录
      planRecognition?.stop(); setPlanRecording(null); return
    }
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SR) { alert("当前浏览器不支持语音识别。"); return }
    const rec = new SR()
    rec.continuous = true
    rec.interimResults = false
    rec.lang = 'zh-CN'
    // 本轮录音只 flush 一次（停止按钮 / onend / onerror 可能都触发，避免重复清洗 + 重复追加）
    let flushed = false
    const flushOnce = () => { if (flushed) return; flushed = true; flushPlanTranscript(draftId) }
    planRawRef.current[draftId] = ''   // 开新一段录音前清空缓冲区
    rec.onresult = (event: any) => {
      let finalTranscript = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) finalTranscript += event.results[i][0].transcript
      }
      // 录音中不直接写入文本框，先攒进缓冲区，等停止后统一交给智能体清洗（与“现场辅助记录”一致）
      if (finalTranscript) planRawRef.current[draftId] = (planRawRef.current[draftId] || '') + finalTranscript
    }
    // 【第81天修复】no-speech = 几秒没说话的静音超时（不是真错误）：不当作结束，交给 onend 自动续录；
    // 其他错误（无权限 / 无麦克风等）才收尾，并标记成“用户停了”，避免 onend 反复重试成死循环
    rec.onerror = (e: any) => {
      if (e && e.error === 'no-speech') return
      isUserStoppedRef.current = true
      setPlanRecording(null); flushOnce()
    }
    rec.onend = () => {
      // 【第81天修复】用户没点停 → 被静音打断的：自动续上（长口述不会中途断掉，转写继续攒进缓冲区）
      if (!isUserStoppedRef.current) { try { rec.start() } catch { /* 实例已在运行，忽略 */ } return }
      // 用户主动停的：走原有结束逻辑（清洗 → 追加到“辨证施治方案”文本框）
      setPlanRecording(null); flushOnce()
    }
    isUserStoppedRef.current = false   // 【第81天修复】开始录音：标记为“用户没停”
    rec.start()
    setPlanRecognition(rec)
    setPlanRecording(draftId)
  }

  const handleEditDraft = (draftId: number, newContent: string, silent = false) => {
    // 【第75天新增 / 改动2】老师点“保存病历修改”时，把当前「辨证施治方案」存成该老师的新模板。
    // silent = true 是“追加到病历”等自动保存通道，不写模板；方案为空时 savePlanTemplate 内部会直接跳过。
    if (!silent) savePlanTemplate(finalPlans[draftId] || '')
    // 【第59天修复】本地占位草案还没有后端 id，先走“落库”流程，不能直接 PUT
    // 【第71天修复】落库成功/失败都给老师明确反馈（原来成功时毫无提示，看起来像“点了没反应”）
    if (draftId < 0) {
      saveLocalDraftToBackend(draftId, newContent).then(id => {
        if (!id) { alert('落库失败：没能生成病历草案，请稍后重试'); return }
        // 草案 id 由负数变成真实 id：把老师已填的「症状标签 / 辨证施治方案」搬到新 id 下，避免看起来丢了
        setDraftTags(prev => prev[draftId] === undefined ? prev : { ...prev, [id]: prev[draftId] })
        setFinalPlans(prev => prev[draftId] === undefined ? prev : { ...prev, [id]: prev[draftId] })
        // 【第75天新增 / 改动2】“已套用模板，可修改”标记也跟着搬到真实 id 下，避免落库后提示凭空消失；
        // 自动套用标记同步搬过去，防止“已清空的方案”在换 id 后又被自动填回模板
        setPlanTemplateApplied(prev => prev[draftId] === undefined ? prev : { ...prev, [id]: prev[draftId] })
        if (planTemplateFilledRef.current[draftId]) planTemplateFilledRef.current[id] = true
        if (!silent) alert('病历已保存并落库（现在可以签字）')
      })
      return
    }
    fetch(`/api/drafts/${draftId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: newContent })
    }).then(() => fetchDrafts())
  }

  const handleAppendTeacherNote = (draftId: number) => {
    const text = teacherLiveText[draftId]
    if (!text || !text.trim()) { alert("请先录音或输入内容"); return }
    const draft = clinicDrafts.find(x => x.id === draftId)   // 【第59天修复】兼容本地占位草案
    if (draft) {
      handleEditDraft(draftId, draft.content + '\n\n【现场记录】\n' + text, true)   // silent：避免每次追加都弹“已落库”
      setTeacherLiveText(prev => ({ ...prev, [draftId]: '' }))
    }
  }

  // 【第59天重构】图片清晰度检测（纯前端，无依赖）：Canvas 画图 → 灰度 → 3x3 拉普拉斯卷积 → 求方差
  // 返回 true = 通过（或无法读取像素时放行），false = 可能模糊，交给老师决定是否继续使用
  const checkImageSharpness = (file: File): Promise<boolean> => {
    return new Promise(resolve => {
      const url = URL.createObjectURL(file)
      const img = new Image()
      img.onload = () => {
        try {
          // 缩放到最长边 1000px：兼顾速度与高频细节
          const scale = Math.min(1, 1000 / Math.max(img.width, img.height))
          const w = Math.max(3, Math.round(img.width * scale))
          const h = Math.max(3, Math.round(img.height * scale))
          const canvas = document.createElement('canvas')
          canvas.width = w
          canvas.height = h
          const ctx = canvas.getContext('2d')
          if (!ctx) { resolve(true); return }
          ctx.drawImage(img, 0, 0, w, h)
          const data = ctx.getImageData(0, 0, w, h).data
          // 1) 转灰度
          const gray = new Float64Array(w * h)
          for (let i = 0; i < w * h; i++) {
            gray[i] = 0.299 * data[i * 4] + 0.587 * data[i * 4 + 1] + 0.114 * data[i * 4 + 2]
          }
          // 2) 拉普拉斯卷积（跳过最外圈像素）：4g(i) - g(i-1) - g(i+1) - g(i-w) - g(i+w)
          const lap = new Float64Array(w * h)
          let lapSum = 0
          let count = 0
          for (let y = 1; y < h - 1; y++) {
            for (let x = 1; x < w - 1; x++) {
              const i = y * w + x
              const v = 4 * gray[i] - gray[i - 1] - gray[i + 1] - gray[i - w] - gray[i + w]
              lap[i] = v
              lapSum += v
              count++
            }
          }
          if (count === 0) { resolve(true); return }
          // 3) 拉普拉斯方差：越小越模糊
          const mean = lapSum / count
          let variance = 0
          for (let y = 1; y < h - 1; y++) {
            for (let x = 1; x < w - 1; x++) {
              const diff = lap[y * w + x] - mean
              variance += diff * diff
            }
          }
          resolve(variance / count >= IMAGE_SHARPNESS_THRESHOLD)
        } catch (e) {
          resolve(true)   // 取不到像素（如图片跨域）就不拦截
        } finally {
          URL.revokeObjectURL(url)
        }
      }
      img.onerror = () => { URL.revokeObjectURL(url); resolve(true) }
      img.src = url
    })
  }

  // 【第59天重构】清晰度检测通过（或老师点“继续使用”）后：上传 /api/upload-temp → URL 追加到文本框末尾
  const uploadLivePhoto = (draftId: number, file: File) => {
    setLiveUploading(prev => ({ ...prev, [draftId]: true }))
    // 【第70天修复 / 数据串台】记下这张照片属于哪个学生：上传返回时若老师已切到别的学生，就丢弃这次结果
    const uploadOwner = clinicDrafts.find(x => x.id === draftId)?.patient_name
    const formData = new FormData()
    formData.append('file', file)
    fetch('/api/upload-temp', { method: 'POST', body: formData })
      .then(r => r.json())
      .then(d => {
        setLiveUploading(prev => ({ ...prev, [draftId]: false }))
        // 【第69天新增】上传成功 → 同时记入缩略图列表（≠ 写入文本的 URL，移除缩略图不影响文本）
        if (d && d.url) {
          if (clinicPatientRef.current !== uploadOwner) return   // 【第70天修复】学生已切换 → 不写进缩略图列表，也不追加到文本框
          // 【第73天改动3】结构改为 { url, category }，默认归类「患处照」（老师可在缩略图下方下拉里切换）
          setUploadedImages(prev => [...prev, { url: d.url, category: DEFAULT_PHOTO_CATEGORY }])
          setTeacherLiveText(prev => ({ ...prev, [draftId]: (prev[draftId] || '') + '\n\n【上传的图片】' + d.url }))
        } else {
          alert('图片上传失败，请重试')
        }
      })
      .catch(() => { setLiveUploading(prev => ({ ...prev, [draftId]: false })); alert('图片上传失败，请重试') })
  }

  // 【第59天重构】拍照/上传（诊室页签内唯一拍照入口）：
  // 先用 Canvas 检测清晰度 → 通过则直接上传；不清晰则弹「重拍 / 继续使用」，由老师决定
  const handleLivePhotoUpload = async (draftId: number, e: React.ChangeEvent<HTMLInputElement>) => {
    const input = e.target
    const file = input.files?.[0]
    input.value = ''   // 立刻清空：同一张图片再次拍/选也能触发 onChange（“重拍”复用同一个 input）
    if (!file) return
    const sharp = await checkImageSharpness(file)
    if (!sharp) { setBlurryPhoto({ draftId, file }); return }
    uploadLivePhoto(draftId, file)
  }

  // 清晰度提示：点“继续使用” → 照常上传；“重拍” → 关掉提示并再次唤起相机
  const handleUseBlurryPhoto = () => {
    const pending = blurryPhoto
    setBlurryPhoto(null)
    if (pending) uploadLivePhoto(pending.draftId, pending.file)
  }
  const handleRetakePhoto = () => {
    setBlurryPhoto(null)
    clinicPhotoInputRef.current?.click()
  }

  const handlePreviewFullRecord = (draftId: number) => {
    const draft = clinicDrafts.find(x => x.id === draftId)   // 【第59天修复】兼容本地占位草案
    if (!draft) return
    const plan = finalPlans[draftId] || ''
    if (!plan.trim()) { alert("请先填写施治方案，再预览完整病历"); return }
    // 【第75天新增 / 改动2】老师点“预览完整病历”时，同样把当前施治方案存成该老师的新模板（POST /api/plan_template）
    savePlanTemplate(plan)
    const fullContent = draft.content + '\n\n【辨证施治方案】\n' + plan + '\n\n【签字】\n' + selectedTeacher + ' · ' + currentYear + '年' + currentMonth + '月' + currentDay + '日'
    setPreviewDraft({ id: draftId, content: fullContent })
  }

  const handleFinalSign = () => {
    if (!previewDraft) return
    const currentPreview = previewDraft
    // 【第71天修复 / 签字死锁】本地新建草案（id < 0）不再弹“请先点保存病历修改落库”把老师踢回上一步，
    // 而是当场自动落库拿到真实 draft_id 后再签字：写草案 → 保存 → 签字 → 落库 一步到底。
    const localDraft = currentPreview.id < 0 ? localDrafts.find(d => d.id === currentPreview.id) : undefined
    const ensureDraftId: Promise<number | null> = currentPreview.id < 0
      ? saveLocalDraftToBackend(currentPreview.id, localDraft ? localDraft.content : currentPreview.content)
      : Promise.resolve(currentPreview.id)
    const plan = finalPlans[currentPreview.id] || ''
    ensureDraftId.then(realId => {
      if (!realId) { alert('落库失败：没能生成病历草案，无法签字，请稍后重试'); return }
      const tagData = draftTags[realId] || draftTags[currentPreview.id]
      const saveTags = (): Promise<any> => {
        const tags: any[] = []
        if (tagData?.area?.trim()) tags.push({ tag_type: '部位', tag_value: tagData.area.trim() })
        if (tagData?.symptom?.trim()) tags.push({ tag_type: '症状', tag_value: tagData.symptom.trim() })
        if (tags.length === 0) return Promise.resolve()
        return fetch('/api/tags', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ record_id: realId, teacher_name: selectedTeacher, tags })
        })
      }
      return saveTags().then(() => {
        return fetch(`/api/drafts/${realId}/sign`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ final_plan: plan, final_content: currentPreview.content })
        })
          .then(r => r.json())
          .then((res: any) => {
            // 【第71天修复】签字失败（草案不存在等）不再静默关窗，原样弹出后端报错，方便定位
            if (res && res.error) { alert('签字失败：' + res.error); return }
            setPreviewDraft(null)
            setDraftTags(prev => ({ ...prev, [realId]: { area: '', symptom: '' }, [currentPreview.id]: { area: '', symptom: '' } }))
            setFinalPlans(prev => ({ ...prev, [realId]: '', [currentPreview.id]: '' }))
            fetchDrafts(); fetchPatientRecords(); fetchPoints()
          })
      })
    })
  }

  // ============== 档案 ==============
  const handleSaveProfile = () => {
    if (!draftProfile) return
    fetch('/api/patient-profile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(draftProfile)
    }).then(() => { setEditingProfile(false); fetchProfile() })
  }

  const handleRelationChange = (value: string) => {
    setNewRelation(value)
    if (['父亲', '儿子'].includes(value)) setNewGender('男')
    else if (['母亲', '女儿'].includes(value)) setNewGender('女')
    else if (value === '配偶') {
      if (guardianGender === '男') setNewGender('女')
      else if (guardianGender === '女') setNewGender('男')
      else { setNewGender(''); alert("请先填写您的性别。") }
    } else setNewGender('')
  }

  const handleToggleAddFamily = () => {
    if (!showAddFamily) {
      setNewLocation(guardianLocation)
      setNewBirthPlace(guardianLocation)
    }
    setShowAddFamily(!showAddFamily)
  }

  const handleAddFamily = () => {
    if (patients.length >= 5) { alert("最多只能添加 5 位家庭成员（含本人）。"); return }
    if (!newFamilyName.trim() || !newRelation.trim() || !newGender || !newBirthYear || !newBirthMonth || !newBirthDay) {
      alert("请至少填写姓名、关系、性别和完整的出生年月日！"); return
    }
    if (patients.some(p => p.name === newFamilyName.trim())) { alert(`家属【${newFamilyName.trim()}】已存在。`); return }
    if (['父亲', '母亲'].includes(newRelation) && guardianBirthDate) {
      const mm = String(newBirthMonth).padStart(2, '0')
      const dd = String(newBirthDay).padStart(2, '0')
      const familyDate = `${newBirthYear}-${mm}-${dd}`
      if (familyDate >= guardianBirthDate) { alert(`【${newRelation}】的出生日期应早于您的出生日期。`); return }
    }
    const mm = String(newBirthMonth).padStart(2, '0')
    const dd = String(newBirthDay).padStart(2, '0')
    const birthDate = `${newBirthYear}-${mm}-${dd}`
    fetch('/api/patients/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: newFamilyName, guardian_name: '张三', relation: newRelation,
        gender: newGender, birth_date: birthDate, birth_time: newBirthTime,
        birth_place: newBirthPlace, location: newLocation
      })
    }).then(() => {
      setNewFamilyName(''); setNewRelation(''); setNewGender('')
      setNewBirthYear(''); setNewBirthMonth(''); setNewBirthDay('')
      setNewBirthTime(''); setNewBirthPlace(''); setNewLocation('')
      setShowAddFamily(false)
      fetchPatients('张三')
    })
  }

  const handleDeleteFamily = (name: string) => {
    if (name === '张三') { alert("本人档案不可删除！"); return }
    if (!confirm(`确定要删除亲友【${name}】吗？`)) return
    fetch(`/api/patients/${name}`, { method: 'DELETE' }).then(() => {
      if (selectedPatient === name) setSelectedPatient('张三')
      fetchPatients('张三')
    })
  }

  // ============== 老师/邀请码 ==============
  const handleAddTeacher = (teacherName: string) => {
    fetch('/api/patient-teachers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ patient_name: selectedPatient, teacher_name: teacherName })
    }).then(r => r.json()).then(d => {
      if (d.error) { alert(d.error); return }
      fetch(`/api/patient-teachers?patient_name=${selectedPatient}`).then(r => r.json()).then((list: string[]) => setPatientTeachers(list))
    })
  }

  const handleRemoveTeacher = (teacherName: string) => {
    if (!confirm(`确定要退出老师【${teacherName}】的咨询吗？`)) return
    fetch(`/api/patient-teachers?patient_name=${selectedPatient}&teacher_name=${teacherName}`, { method: 'DELETE' })
      .then(() => {
        fetch(`/api/patient-teachers?patient_name=${selectedPatient}`).then(r => r.json()).then((list: string[]) => {
          setPatientTeachers(list)
          if (selectedTeacher === teacherName && list.length > 0) setSelectedTeacher(list[0])
        })
      })
  }

  const handleCreateInvite = () => {
    fetch('/api/invites', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ teacher_name: selectedTeacher })
    }).then(r => r.json()).then(d => {
      if (d.code) { fetchInvites(); alert(`邀请码已生成：${d.code}`) }
    })
  }

  const handleCopyInviteLink = (code: string) => {
    const link = `${window.location.origin}/?invite=${code}`
    navigator.clipboard.writeText(link).then(() => alert(`已复制：\n${link}`)).catch(() => alert(`请手动复制：\n${link}`))
  }

  const handleAcceptInvite = () => {
    if (!newStudentNameFromInvite.trim()) { alert("请输入您的姓名"); return }
    fetch('/api/invites/accept', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: pendingInviteCode, student_name: newStudentNameFromInvite.trim() })
    }).then(r => r.json()).then(d => {
      if (d.error) { alert(d.error); return }
      alert(`欢迎加入！您已加入 ${d.teacher_name} 的学习小组。`)
      setPendingInviteCode(''); setNewStudentNameFromInvite('')
      window.history.replaceState({}, '', '/')
      window.location.reload()
    })
  }

  // ============== 预约 ==============
  const fetchAppointments = () => {
    const url = currentRole.includes('老师')
      ? `/api/appointments?teacher_name=${selectedTeacher}`
      : `/api/appointments?patient_name=${selectedPatient}`
    fetch(url).then(r => r.json()).then(d => setAppointments(d)).catch(() => setAppointments([]))
  }

  const handleCreateAppointment = () => {
    if (!apptDate || !apptTime || !apptReason.trim()) {
      alert("请填写完整的预约信息（日期、时间、原因）")
      return
    }
    const initiator = currentRole.includes('老师') ? 'teacher' : 'student'
    fetch('/api/appointments', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        patient_name: selectedPatient,
        teacher_name: selectedTeacher,
        initiator,
        scheduled_date: apptDate,
        scheduled_time: apptTime,
        reason: apptReason.trim()
      })
    }).then(() => {
      setShowApptForm(false)
      setApptDate(''); setApptTime(''); setApptReason('')
      fetchAppointments()
    })
  }

  const handleConfirmAppt = (id: number) => {
    fetch(`/api/appointments/${id}/confirm`, { method: 'POST' }).then(() => fetchAppointments())
  }

  const handleCancelAppt = (id: number) => {
    if (!confirm("确定要取消这个预约吗？")) return
    fetch(`/api/appointments/${id}/cancel`, { method: 'POST' }).then(() => fetchAppointments())
  }

  const roleBtnStyle = (role: string): React.CSSProperties => ({
    padding: '8px 16px', margin: '5px', borderRadius: '20px', border: '1px solid #8b4513',
    cursor: 'pointer', fontFamily: 'serif', fontSize: '14px',
    backgroundColor: currentRole === role ? '#8b4513' : '#fdfcf0',
    color: currentRole === role ? '#fff' : '#8b4513', transition: 'all 0.2s'
  })
  const patientBtnStyle = (name: string): React.CSSProperties => ({
    padding: '6px 14px', margin: '4px', borderRadius: '15px', border: '1px solid #5a7d5a',
    cursor: 'pointer', fontFamily: 'serif', fontSize: '13px',
    backgroundColor: selectedPatient === name ? '#5a7d5a' : '#f7fcf9',
    color: selectedPatient === name ? '#fff' : '#5a7d5a', transition: 'all 0.2s'
  })
  const teacherBtnStyle = (name: string): React.CSSProperties => ({
    padding: '6px 14px', margin: '4px', borderRadius: '15px', border: '1px solid #8b4513',
    cursor: 'pointer', fontFamily: 'serif', fontSize: '13px',
    backgroundColor: selectedTeacher === name ? '#8b4513' : '#fdfcf0',
    color: selectedTeacher === name ? '#fff' : '#8b4513', transition: 'all 0.2s'
  })

  const needGender = !profile?.gender
  const needBirthDate = !profile?.birth_date
  const needBirthTime = !profile?.birth_time
  const needBirthPlace = !profile?.birth_place

  // 时间段分组
  const morningSlots = ['08:00','08:30','09:00','09:30','10:00','10:30','11:00','11:30']
  const afternoonSlots = ['12:00','12:30','13:00','13:30','14:00','14:30','15:00','15:30','16:00','16:30','17:00','17:30']
  const eveningSlots = ['18:00','18:30','19:00','19:30','20:00']

  const formatSlots = (slots: string[]) => {
    if (!slots || slots.length === 0) return '休息'
    return slots.map(s => s).join('、')
  }

  // 【第57天新增 / 第62天调整】老师端页签定义：首页 / 诊室 / 管理（原「学生」+「库存」合并为 1 个页签） / 设置
  const isTeacherRole = currentRole === '李老师' || currentRole === '李老师智能体'
  // 【第66天新增】💰 财务管理：账户数据派生值（后端按 username 排序，取第一个 role='student' / 'teacher' 的账户，如 张三 / 李老师）
  const financeStudentAccount = financeAccounts.find(a => a.role === 'student') || null
  const financeTeacherAccount = financeAccounts.find(a => a.role === 'teacher') || null
  // 充值 / 赠送 / 扣费 表单的“学生姓名”下拉框只列学生账户
  const financeStudentOptions = financeAccounts.filter(a => a.role === 'student')
  const teacherTabs: { key: TeacherTab; label: string }[] = [
    { key: 'home', label: '🏠 首页' },
    { key: 'clinic', label: '🩺 诊室' },
    { key: 'manage', label: '🗂️ 管理' },
    { key: 'settings', label: '⚙️ 设置' }
  ]
  const teacherTabBtnStyle = (key: TeacherTab): React.CSSProperties => ({
    flex: 1, padding: '10px 4px', borderRadius: '10px', border: '1px solid #8b4513',
    cursor: 'pointer', fontFamily: 'serif', fontSize: '13px', whiteSpace: 'nowrap',
    backgroundColor: teacherTab === key ? '#8b4513' : '#fdfcf0',
    color: teacherTab === key ? '#fff' : '#8b4513', transition: 'all 0.2s'
  })

  // 【第57天新增】诊室：面诊队列（已确认 + 今天及以后，按日期时间升序）
  const todayStr = `${currentYear}-${String(currentMonth).padStart(2, '0')}-${String(currentDay).padStart(2, '0')}`
  const clinicQueue = appointments
    .filter((a: any) => a.status === 'confirmed' && a.scheduled_date >= todayStr)
    .sort((a: any, b: any) => (a.scheduled_date + a.scheduled_time).localeCompare(b.scheduled_date + b.scheduled_time))

  // 【第71天新增 / 面诊队列整合】🩺 诊室队列双列的筛选逻辑（数据源就是上面的 clinicQueue，不新增接口）：
  // ① 左列「📅 预约面诊」= clinicQueue 里预约原因未命中远程关键词的；② 右列「💻 远程问诊」= 命中的。
  // clinicQueue 已按 scheduled_date + scheduled_time 升序排好，filter 保持原顺序，所以两列天然都是“今天及以后、时间升序”。
  const isRemoteAppointment = (a: any) => REMOTE_APPT_KEYWORDS.some(k => (a.reason || '').includes(k))
  const clinicInPersonQueue = clinicQueue.filter((a: any) => !isRemoteAppointment(a))
  const clinicRemoteQueue = clinicQueue.filter((a: any) => isRemoteAppointment(a))
  // ③ 临时加插候选：当前学生名单里「今天及以后没有任何未取消预约」且「本次会话还没加插过」的学生
  const bookedPatientNames = appointments
    .filter((a: any) => a.status !== 'cancelled' && a.scheduled_date >= todayStr)
    .map((a: any) => a.patient_name)
  const tempInsertCandidates = teacherPatients.filter((s: any) =>
    !bookedPatientNames.includes(s.name) && !tempQueue.some(t => t.name === s.name))

  // ============== 【第80天新增 / 改动3】🩺 面诊前准备：卡片状态派生值（学生端首页） ==============
  // 数据只复用现有 state（appointments / selectedTeacher），不新增接口、老师端不涉及。
  // 「有预约」判定：该学生未取消的预约里优先取今天及以后最近的一条；都在过去就取最近的一条历史预约（仍算有预约）。
  const intakeActiveAppointments = appointments.filter((a: any) => a.status !== 'cancelled')
  const intakeAppointment = intakeActiveAppointments
    .filter((a: any) => a.scheduled_date >= todayStr)
    .sort((a: any, b: any) => (a.scheduled_date + a.scheduled_time).localeCompare(b.scheduled_date + b.scheduled_time))[0]
    || intakeActiveAppointments
      .sort((a: any, b: any) => (b.scheduled_date + b.scheduled_time).localeCompare(a.scheduled_date + a.scheduled_time))[0]
    || null
  // 状态文案：无预约「暂无预约，可以照镜子或打卡」；有预约「您有预约：X月X日 X点 与 李老师」
  const intakeApptText = (() => {
    if (!intakeAppointment) return '暂无预约，可以照镜子或打卡'
    const dateParts = String(intakeAppointment.scheduled_date || '').split('-')
    const dateText = dateParts.length >= 3
      ? `${Number(dateParts[1])}月${Number(dateParts[2])}日`
      : String(intakeAppointment.scheduled_date || '')
    const timeParts = String(intakeAppointment.scheduled_time || '').split(':')
    const timeText = timeParts[0]
      ? `${Number(timeParts[0])}点${Number(timeParts[1] || 0) > 0 ? `${Number(timeParts[1])}分` : ''}`
      : ''
    return `您有预约：${dateText} ${timeText} 与 ${intakeAppointment.teacher_name || selectedTeacher}`.replace(/\s+/g, ' ').trim()
  })()

  // ============== 【第61天新增】📋 今日备忘录（老师端首页）：时间轴 + 未排期事项 ==============
  // 数据全部来自现有 state + 静态模拟（roleData / appointments / teacherPatients / drafts / habitList / holidays / huangli），不新增后端接口
  const tomorrow = new Date(currentYear, currentMonth - 1, currentDay + 1)
  const tomorrowStr = `${tomorrow.getFullYear()}-${String(tomorrow.getMonth() + 1).padStart(2, '0')}-${String(tomorrow.getDate()).padStart(2, '0')}`
  // 今日工作提醒：优先复用老师端 roleData（如“张三尚未打卡。”），沿用原“李老师的任务”卡片的数据源
  const memoWorkHint = roleData ? roleData.detail : '正在获取任务数据...'
  // 今日生活提醒：优先用现有习惯列表，兜底静态提示
  const memoLifeHint = (habitList.length > 0 ? habitList : ['多喝水', '揉太渊', '早睡']).join('、')
  // “HH:MM” → 分钟数（统一按分钟比较，兼容未补零的历史数据；时间轴排序与逾期判断都用它）
  const memoMinutes = (hm: string) => {
    const [h, m] = (hm || '').split(':')
    return (parseInt(h || '0', 10) || 0) * 60 + (parseInt(m || '0', 10) || 0)
  }
  const memoNowHM = `${String(new Date(memoNow).getHours()).padStart(2, '0')}:${String(new Date(memoNow).getMinutes()).padStart(2, '0')}`
  const memoNowMinutes = memoMinutes(memoNowHM)

  // ① 有明确时间的今日事项：静态模拟项 + 现有 appointments（今日已确认），统一按时间升序排列
  const memoTodayAppointments = appointments.filter((a: any) => a.status === 'confirmed' && a.scheduled_date === todayStr)
  const memoTimedItems = [
    { key: 'fixed-0830', time: '08:30', text: '吃药 / 晨起生活提醒：多喝温水' },
    ...memoTodayAppointments.map((a: any) => ({ key: `appt-${a.id}`, time: a.scheduled_time, text: `面诊 ${a.patient_name}${a.reason ? `（${a.reason}）` : ''}` })),
    { key: 'fixed-2100', time: '21:00', text: `晚间生活提醒：${memoLifeHint}` }
  ].sort((a, b) => memoMinutes(a.time) - memoMinutes(b.time))

  // ② 没有明确时间的事项：单独进“未排期事项”列，不混入时间轴
  const memoUnscheduledItems: { key: string; text: string }[] = [
    { key: 'work-hint', text: `今日工作提醒：${memoWorkHint}` }
  ]
  if (roleData && roleData.detail.includes('已打卡')) memoUnscheduledItems.push({ key: 'approve-hint', text: `${selectedPatient} 的作业待签字确认` })
  drafts.filter(d => !d.signed).forEach(d => memoUnscheduledItems.push({ key: `draft-${d.id}`, text: `${d.patient_name} 的病历草案待签字` }))
  teacherPatients.filter((s: any) => s.status_label !== '活跃').slice(0, 3).forEach((s: any) => memoUnscheduledItems.push({ key: `student-${s.name}`, text: `${s.name} 未提交周报（${s.status_label}）` }))
  // 明日预备提示：明日预约 + 明日是否落在老师自己设置的节假日
  const memoTomorrowAppointments = appointments.filter((a: any) => a.status === 'confirmed' && a.scheduled_date === tomorrowStr)
  const memoTomorrowHint = memoTomorrowAppointments.length === 1
    ? `明日有一位学生预约：${memoTomorrowAppointments[0].patient_name} ${memoTomorrowAppointments[0].scheduled_time}`
    : memoTomorrowAppointments.length > 1
      ? `明日有 ${memoTomorrowAppointments.length} 位学生预约：` + memoTomorrowAppointments.map((a: any) => `${a.patient_name} ${a.scheduled_time}`).join('、')
      : (holidays.includes(tomorrowStr) ? '明日是您设置的节假日，暂无预约，好好休息。' : '明日暂无学生预约，可整理病历或休息。')
  memoUnscheduledItems.push({ key: 'tomorrow-hint', text: `明日预备提示：${memoTomorrowHint}` })

  // ③ 状态：已被标记“已处理”（点过完成按钮）的事项，直接从两个列表里移除
  const memoTimedVisible = memoTimedItems.filter(it => !memoDoneKeys.includes(it.key))
  const memoUnscheduledVisible = memoUnscheduledItems.filter(it => !memoDoneKeys.includes(it.key))

  // 【第61天新增】每日更新与清理：读 localStorage 里的完成记录，存的不是今天就自动清空（前端模拟“每日 00:00 后台智能体重置清理”）
  useEffect(() => {
    if (memoStoreDate === todayStr) return   // 今天已初始化过（跨天时 todayStr 变化会重新走下面的清理流程）
    let keys: string[] = []
    try {
      const raw = localStorage.getItem(MEMO_DONE_STORE_KEY)
      const parsed = raw ? JSON.parse(raw) : null
      if (parsed && parsed.date === todayStr && Array.isArray(parsed.keys)) keys = parsed.keys
    } catch (e) { /* 忽略解析错误，按空处理 */ }
    setMemoDoneKeys(keys)                                             // 存的不是今天 → keys = []，等于自动清空
    setMemoStoreDate(todayStr)
    localStorage.setItem(MEMO_DONE_STORE_KEY, JSON.stringify({ date: todayStr, keys }))
  }, [memoStoreDate, todayStr])

  // 完成状态持久化（当日记录一经初始化，之后每次变更都写回 localStorage）
  useEffect(() => {
    if (memoStoreDate !== todayStr) return
    localStorage.setItem(MEMO_DONE_STORE_KEY, JSON.stringify({ date: todayStr, keys: memoDoneKeys }))
  }, [memoDoneKeys, memoStoreDate, todayStr])

  // 每分钟刷新一次“当前时间”，让逾期事项到点自动变灰，无需刷新页面
  useEffect(() => {
    const timer = setInterval(() => setMemoNow(Date.now()), 60 * 1000)
    return () => clearInterval(timer)
  }, [])

  // 点“完成”：标记为已处理 → 从时间轴 / 未排期列表移除（同时写入 localStorage）
  const handleMemoDone = (key: string) => {
    setMemoDoneKeys(prev => prev.includes(key) ? prev : [...prev, key])
  }

  // 逾期判断：未处理 且 当前时间已过该事项时间 → 文字变灰（见渲染处的 overdue 分支）
  const isMemoOverdue = (time: string) => memoMinutes(time) < memoNowMinutes

  // 【第57天新增】诊室：老师搜索学生（前端过滤 teacherPatients，不做后端接口）
  const studentSearchResults = studentSearch.trim()
    ? teacherPatients.filter((s: any) => s.name.includes(studentSearch.trim()))
    : []

  // 【第57天新增】诊室：当前就诊学生信息（上次就诊时间 + 当前状态）
  const currentStudentInfo = teacherPatients.find((s: any) => s.name === selectedPatient)
  const lastVisitDate = patientRecords.length > 0 ? `第 ${patientRecords[0].id} 号病历` : '首次就诊'

  // ============== 【第59天新增】诊室二期：老师工作状态（录音转文字 / 拍照上传 / 把脉记录） ==============
  // 【第70天修复 / 数据串台】目标病历草案只看“当前就诊学生”的草案（含本地占位草案）：
  // 该学生没有草案时返回 null（控件置灰），绝不再回退到 clinicDrafts[0]——那会把现场记录写进别的学生的病历里
  const clinicTargetDraft = clinicPatientDrafts[0] || null
  // 【第59天重构】“现场辅助记录”卡片统一用这个 id 作为读写目标（null = 暂无草案，控件置灰）
  const clinicTargetId: number | null = clinicTargetDraft ? clinicTargetDraft.id : null
  const speechSupported = !!((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition)

  // 【第59天修复】按 id 更新编辑框内容：id < 0 = 本地占位草案（只改 state），id > 0 = 后端草案
  const setClinicDraftById = (draftId: number, updater: (d: Draft) => Draft) => {
    if (draftId < 0) setLocalDrafts(prev => prev.map(d => d.id === draftId ? updater(d) : d))
    else setDrafts(prev => prev.map(d => d.id === draftId ? updater(d) : d))
  }

  // 【第59天修复】诊室里选中学生（面诊队列 / 搜索结果）：
  // 该学生没有“正在编辑的草案”时，前端本地生成一条空草案（不调后端），让录音/拍照/把脉立刻可用
  const selectClinicPatient = (name: string) => {
    setSelectedPatient(name)
    setLocalDrafts(prev => {
      if (drafts.some(d => d.patient_name === name)) return prev   // 后端已有草案
      if (prev.some(d => d.patient_name === name)) return prev     // 本地已有占位草案
      return [...prev, { id: -Date.now(), transcript_id: 0, patient_name: name, content: '', signed: false }]
    })
  }

  // 【第71天新增 / 面诊队列整合】🩺 诊室队列：➕ 临时加插
  // 从「当前学生列表里没预约的学生」中选一位后：① 复用 selectClinicPatient 切到该学生（自动生成本地占位草案，
  // 录音 / 拍照 / 把脉立刻可用）；② 在左列「📅 预约面诊」顶部插一条「【临时】学生名 · 刚刚」（同一学生重复加插先移除旧的那条，保证只出现一次且置顶）。
  // 只写 tempQueue 这个独立 state，不落库、不调任何后端接口，刷新页面即清空。
  const handleTempInsert = (name: string) => {
    selectClinicPatient(name)
    setTempQueue(prev => [{ name, time: '刚刚' }, ...prev.filter(t => t.name !== name)])
    setShowTempInsertPicker(false)
  }

  // （【第59天重构】原 appendToClinicDraft / stopClinicRecording 已随“三卡合一”移除：
  //   把脉、拍照改为先写入“现场辅助记录”文本框，录音复用卡片自带的 startTeacherLiveRecording）





  // 功能3：把脉记录（纯前端，格式化成一段文字追加到“现场辅助记录”上方文本框末尾）
  const handlePulseRecord = () => {
    if (pulseTypes.length === 0 && !pulseRate.trim() && !pulseNote.trim()) { alert('请先选择脉象或填写脉率'); return }
    if (!clinicTargetDraft) { alert('暂无待处理病历草案，请先在“诊室队列”里选一位学生'); return }
    const parts: string[] = ['脉象：' + (pulseTypes.length > 0 ? pulseTypes.join('、') : '未填写')]
    if (pulseRate.trim()) parts.push('脉率：' + pulseRate.trim() + '次/分')
    if (pulseNote.trim()) parts.push('备注：' + pulseNote.trim())
    const id = clinicTargetDraft.id
    setTeacherLiveText(prev => ({ ...prev, [id]: (prev[id] || '') + '\n\n【把脉记录】' + parts.join('；') }))
    setPulseTypes([])
    setPulseRate('')
    setPulseNote('')
  }

  // ============== 【第58天新增】学生智能体一期：照镜子 + 习惯追踪 + 周报 ==============
  // 从 localStorage 读取（首次挂载时）
  useEffect(() => {
    try {
      const m = localStorage.getItem('zh_mirror_log')
      if (m) setMirrorLog(JSON.parse(m))
      const h = localStorage.getItem('zh_habit_log')
      if (h) setHabitLog(JSON.parse(h))
      const hl = localStorage.getItem('zh_habit_list')
      if (hl) setHabitList(JSON.parse(hl))
      const f = localStorage.getItem('zh_reminder_frequency')
      if (f === 'A' || f === 'B' || f === 'C') setReminderFrequency(f)
    } catch (e) { /* 忽略解析错误 */ }
  }, [])

  // 写入 localStorage（变化时）
  useEffect(() => { localStorage.setItem('zh_mirror_log', JSON.stringify(mirrorLog)) }, [mirrorLog])
  useEffect(() => { localStorage.setItem('zh_habit_log', JSON.stringify(habitLog)) }, [habitLog])
  useEffect(() => { localStorage.setItem('zh_habit_list', JSON.stringify(habitList)) }, [habitList])
  useEffect(() => { localStorage.setItem('zh_reminder_frequency', reminderFrequency) }, [reminderFrequency])

  // 当前小时：<12 视为早间，否则晚间
  const isMorning = now.getHours() < 12
  const mirrorPeriod: 'morning' | 'evening' = isMorning ? 'morning' : 'evening'
  const todayMirror = mirrorLog[selectedPatient]?.[todayStr] || { morning: false, evening: false }
  const mirrorDone = todayMirror[mirrorPeriod]

  // 照镜子提示语
  const mirrorTip = isMorning
    ? '观察面色，是否红润？观察舌苔，是否白腻？'
    : '回顾今日饮食起居，是否早睡？是否心平气和？'

  // 点击"我已完成"：记录今日该时段已完成
  const handleMirrorDone = () => {
    setMirrorLog(prev => {
      const patientLog = prev[selectedPatient] || {}
      const dayLog = patientLog[todayStr] || { morning: false, evening: false }
      return { ...prev, [selectedPatient]: { ...patientLog, [todayStr]: { ...dayLog, [mirrorPeriod]: true } } }
    })
  }

  // 提醒频率 → 今日是否需要打卡
  // A 每天：总是需要；B 隔天：按日期奇偶；C 每周：仅周一
  const shouldRemindToday = (() => {
    if (reminderFrequency === 'A') return true
    const dayOfMonth = currentDay
    if (reminderFrequency === 'B') return dayOfMonth % 2 === 1
    // C：每周一
    return now.getDay() === 1
  })()
  const frequencyLabel = reminderFrequency === 'A' ? 'A · 每天提醒' : reminderFrequency === 'B' ? 'B · 隔天提醒' : 'C · 每周提醒'

  // 今日习惯打卡状态
  const todayHabits = habitLog[selectedPatient]?.[todayStr] || {}
  const handleToggleHabit = (habit: string) => {
    setHabitLog(prev => {
      const patientLog = prev[selectedPatient] || {}
      const dayLog = patientLog[todayStr] || {}
      return { ...prev, [selectedPatient]: { ...patientLog, [todayStr]: { ...dayLog, [habit]: !dayLog[habit] } } }
    })
  }
  const handleAddHabit = () => {
    const name = newHabitName.trim()
    if (!name) { alert('请输入习惯名称'); return }
    if (habitList.includes(name)) { alert('该习惯已存在'); return }
    setHabitList(prev => [...prev, name])
    setNewHabitName('')
  }
  const handleRemoveHabit = (habit: string) => {
    if (!confirm(`确定删除习惯【${habit}】吗？`)) return
    setHabitList(prev => prev.filter(h => h !== habit))
  }

  // 本周（周一至周日）打卡统计
  const weekStats = (() => {
    const patientLog = habitLog[selectedPatient] || {}
    const day = now.getDay() // 0=周日
    const mondayOffset = day === 0 ? -6 : 1 - day
    const monday = new Date(now)
    monday.setDate(now.getDate() + mondayOffset)
    let done = 0
    let total = 0
    for (let i = 0; i < 7; i++) {
      const d = new Date(monday)
      d.setDate(monday.getDate() + i)
      const ds = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
      const dayLog = patientLog[ds] || {}
      habitList.forEach(h => { total += 1; if (dayLog[h]) done += 1 })
    }
    const rate = total > 0 ? Math.round((done / total) * 100) : 0
    let summary = ''
    if (total === 0) summary = '本周还没有习惯记录，从今天开始吧！'
    else if (rate >= 80) summary = '本周坚持得不错，继续加油！'
    else if (rate >= 50) summary = '本周完成过半，再坚持一下会更好。'
    else if (rate > 0) summary = '本周打卡偏少，明天试着多完成一项吧。'
    else summary = '本周还没有打卡，今天就从一项开始吧！'
    return { done, total, rate, summary }
  })()

  // ============== 【第66天接入真实接口】💰 财务管理面板：预存 / 赠送 / 扣费 ==============
  // 数据来源：顶部两个数字 = GET /api/finance/accounts；三个按钮提交 = POST /api/finance/recharge | gift | deduct
  const financeLabels: { recharge: string; gift: string; deduct: string } = { recharge: '充值', gift: '赠送', deduct: '扣费' }

  // 点按钮展开内联小表单（再点同一个按钮则收起）；默认选中第一个学生账户
  const openFinanceForm = (mode: 'recharge' | 'gift' | 'deduct') => {
    if (financeForm === mode) { closeFinanceForm(); return }
    setFinanceForm(mode)
    setFinanceUsername(financeStudentOptions.length > 0 ? financeStudentOptions[0].username : '')
    setFinanceAmount('')
    setFinanceNote('')
  }

  const closeFinanceForm = () => {
    setFinanceForm(null)
    setFinanceUsername('')
    setFinanceAmount('')
    setFinanceNote('')
  }

  // 提交：成功后关闭表单 → 重新拉取账户数据 → 弹成功提示（如“充值成功，当前余额 150”）
  const submitFinance = () => {
    if (!financeForm || financeSubmitting) return
    const mode = financeForm
    const label = financeLabels[mode]
    const amount = parseInt(financeAmount, 10)
    if (!financeUsername) { alert('请选择学生。'); return }
    if (!Number.isFinite(amount) || amount <= 0) { alert('请输入大于 0 的整数金额。'); return }
    setFinanceSubmitting(true)
    fetch(`/api/finance/${mode}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: financeUsername, amount, note: financeNote.trim() })
    })
      .then(res => res.json().then(body => ({ ok: res.ok, body })).catch(() => ({ ok: res.ok, body: {} as any })))
      .then(({ ok, body }) => {
        if (!ok) throw new Error(body.detail || `${label}失败`)
        if (body.ok === false) throw new Error(body.error || `${label}失败`)
        setFinanceSubmitting(false)
        closeFinanceForm()
        fetchFinanceAccounts()
        alert(`${label}成功，当前余额 ${body.balance}`)
      })
      .catch(err => {
        setFinanceSubmitting(false)
        const msg = err && err.message ? err.message : `${label}失败`
        // 扣费时后端返回 { ok: false, error: '余额不足' } 且不扣款，这里单独提示
        alert(msg === '余额不足' ? '余额不足，未扣款' : msg)
      })
  }

  // 【第66天新增】三个按钮共用的内联小表单：学生姓名（下拉，只列 role='student'）+ 金额 + 备注（可空）+ 确认 / 取消
  const renderFinanceForm = (mode: 'recharge' | 'gift' | 'deduct') => {
    if (financeForm !== mode) return null
    const label = financeLabels[mode]
    return (
      <div style={{ background: '#f7f3e8', border: '1px dashed #d4c8a8', borderRadius: '8px', padding: '12px', marginBottom: '10px' }}>
        <div style={{ fontSize: '14px', color: '#8b4513', fontWeight: 'bold', marginBottom: '8px' }}>{label}</div>
        <label style={{ fontSize: '12px', color: '#888' }}>学生姓名</label>
        <select value={financeUsername} onChange={e => setFinanceUsername(e.target.value)} style={inputStyle}>
          <option value="">{financeStudentOptions.length === 0 ? '暂无学生账户' : '请选择学生'}</option>
          {financeStudentOptions.map(a => (
            <option key={a.username} value={a.username}>{a.username}（当前余额 {a.balance}）</option>
          ))}
        </select>
        <label style={{ fontSize: '12px', color: '#888' }}>金额</label>
        <input type="number" min="1" value={financeAmount} onChange={e => setFinanceAmount(e.target.value)} placeholder="请输入金额（大于 0 的整数）" style={inputStyle} />
        <label style={{ fontSize: '12px', color: '#888' }}>备注（可空）</label>
        <input value={financeNote} onChange={e => setFinanceNote(e.target.value)} placeholder="备注（可空）" style={inputStyle} />
        <div style={{ display: 'flex', gap: '10px' }}>
          <button onClick={submitFinance} disabled={financeSubmitting} style={{ flex: 1, padding: '8px', borderRadius: '20px', border: 'none', background: financeSubmitting ? '#c9b79a' : '#8b4513', color: '#fff', cursor: financeSubmitting ? 'default' : 'pointer', fontFamily: 'serif', fontSize: '14px' }}>{financeSubmitting ? '提交中…' : `确认${label}`}</button>
          <button onClick={closeFinanceForm} style={{ flex: 1, padding: '8px', borderRadius: '20px', border: '1px solid #999', background: 'transparent', color: '#666', cursor: 'pointer', fontFamily: 'serif', fontSize: '14px' }}>取消</button>
        </div>
      </div>
    )
  }

  // ============== 渲染 ==============
  return (
    <div style={{ minHeight: '100vh', background: '#f5f1e6', padding: '40px 20px', fontFamily: 'serif' }}>
      <div style={{ maxWidth: '600px', margin: '0 auto' }}>

        {pendingInviteCode && (
          <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999 }}>
            <div style={{ background: '#fdfcf0', padding: '24px', borderRadius: '12px', maxWidth: '400px', width: '90%', border: '2px solid #8b4513' }}>
              <div style={{ fontSize: '18px', color: '#8b4513', fontWeight: 'bold', marginBottom: '10px', textAlign: 'center' }}>🎫 接受老师邀请</div>
              <div style={{ fontSize: '13px', color: '#666', marginBottom: '15px', textAlign: 'center' }}>邀请码：<span style={{ fontFamily: 'monospace', color: '#8b4513', fontWeight: 'bold' }}>{pendingInviteCode}</span></div>
              <input placeholder="请输入您的姓名" value={newStudentNameFromInvite} onChange={e => setNewStudentNameFromInvite(e.target.value)} style={inputStyle} />
              <div style={{ display: 'flex', gap: '10px' }}>
                <button onClick={() => { setPendingInviteCode(''); window.history.replaceState({}, '', '/') }} style={{ flex: 1, padding: '10px', borderRadius: '20px', border: '1px solid #999', background: 'transparent', color: '#666', cursor: 'pointer' }}>取消</button>
                <button onClick={handleAcceptInvite} style={{ flex: 1, padding: '10px', borderRadius: '20px', border: 'none', background: '#8b4513', color: '#fff', cursor: 'pointer' }}>加入</button>
              </div>
            </div>
          </div>
        )}

        {previewDraft && (
          <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999 }}>
            <div style={{ background: '#fdfcf0', padding: '24px', borderRadius: '12px', maxWidth: '700px', width: '90%', maxHeight: '85vh', overflowY: 'auto', border: '2px solid #8b4513' }}>
              <div style={{ fontSize: '18px', color: '#8b4513', fontWeight: 'bold', marginBottom: '10px', textAlign: 'center' }}>📄 完整病历预览</div>
              <div style={{ fontSize: '13px', color: '#666', marginBottom: '15px', textAlign: 'center', lineHeight: '1.6' }}>
                请审核，可再编辑一次；<br />
                <span style={{ color: '#c0392b', fontWeight: 'bold' }}>确认签字后，AI 原草案将销毁，音频文件将删除。</span>
              </div>
              <textarea value={previewDraft.content} onChange={e => setPreviewDraft({ ...previewDraft, content: e.target.value })} style={{ width: '100%', minHeight: '400px', padding: '12px', borderRadius: '8px', border: '1px solid #d4c8a8', fontFamily: 'serif', fontSize: '14px', marginBottom: '15px', boxSizing: 'border-box', whiteSpace: 'pre-wrap', lineHeight: '1.6' }} />
              {/* 【第73天改动1】签字预览页渲染照片：病历文本里出现 /uploads/xxx.jpg（如【上传的图片】/uploads/xxx.jpg）时，
                  在文本框下方额外渲染缩略图（宽度 120px、圆角）；URL 文本本身仍保留在文本框里（不删、不改）。
                  src 用 http://localhost:8000 + URL 拼完整地址；点缩略图 → window.open(完整URL, '_blank') 看原图。 */}
              {extractImageUrls(previewDraft.content).length > 0 && (
                <div style={{ marginBottom: '15px', padding: '10px', background: '#fff', borderRadius: '8px', border: '1px dashed #d4c8a8' }}>
                  <div style={{ fontSize: '12px', color: '#8b4513', fontWeight: 'bold', marginBottom: '8px' }}>📷 病历内附照片（点击缩略图看原图）</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
                    {extractImageUrls(previewDraft.content).map((url, i) => {
                      const fullUrl = toFullImageUrl(url)
                      return (
                        <div key={`${url}-${i}`} style={{ textAlign: 'center', width: '120px' }}>
                          <img
                            src={fullUrl}
                            alt={`病历照片${i + 1}`}
                            onClick={() => window.open(fullUrl, '_blank')}
                            title="点击查看原图"
                            style={{ width: '120px', height: '120px', objectFit: 'cover', borderRadius: '8px', border: '1px solid #d4c8a8', display: 'block', cursor: 'zoom-in' }}
                          />
                          <div style={{ fontSize: '11px', color: '#999', marginTop: '4px' }}>点击查看原图</div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
              <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                <button onClick={() => setPreviewDraft(null)} style={{ padding: '8px 20px', borderRadius: '20px', border: '1px solid #999', background: 'transparent', color: '#666', cursor: 'pointer' }}>取消（返回修改）</button>
                <button onClick={handleFinalSign} style={{ padding: '8px 24px', borderRadius: '20px', border: 'none', background: '#5a7d5a', color: '#fff', cursor: 'pointer', fontWeight: 'bold' }}>✅ 确认签字</button>
              </div>
            </div>
          </div>
        )}

        <h1 style={{ textAlign: 'center', color: '#8b4513', borderBottom: '2px solid #d4c8a8', paddingBottom: '15px', marginBottom: '30px', fontSize: '28px', letterSpacing: '2px' }}>知衡 · 中医治未病社区</h1>

        {/* 【第57天新增 / 第62天调整】老师端 4 页签导航（首页/诊室/管理/设置；学生端不显示） */}
        {isTeacherRole && (
          <div style={{ display: 'flex', gap: '6px', marginBottom: '20px', background: '#fdfcf0', border: '1px solid #d4c8a8', borderRadius: '12px', padding: '6px', boxShadow: '0 4px 12px rgba(0,0,0,0.06)' }}>
            {teacherTabs.map(t => (
              <button key={t.key} style={teacherTabBtnStyle(t.key)} onClick={() => setTeacherTab(t.key)}>{t.label}</button>
            ))}
          </div>
        )}

        {/* 【第62天调整】黄历卡片只在首页显示（老师端切到诊室/管理/设置时隐藏；学生端始终显示） */}
        {(huangli && (!isTeacherRole || teacherTab === 'home')) && (
          <div style={boxStyle}>
            <div style={{ textAlign: 'center', fontSize: '18px', color: '#333', marginBottom: '5px' }}>
              <span style={{ fontWeight: 'bold' }}>{huangli.date}</span> · {huangli.lunar}
            </div>
            {huangli.solar_term_tip && huangli.solar_term_tip !== '无' && (
              <div style={{ textAlign: 'center', color: '#8b4513', fontSize: '14px', marginBottom: '15px' }}>🌿 {huangli.solar_term_tip}</div>
            )}
            <div style={{ textAlign: 'center', color: '#5a7d5a', fontSize: '16px', marginBottom: '10px' }}>🌿 {huangli.solar_term}：{huangli.health_trend}</div>
            <div style={{ textAlign: 'center', background: '#fff8e7', padding: '15px', borderRadius: '8px', color: '#8b4513' }}>📝 今日作业：{huangli.homework}</div>
          </div>
        )}

        {/* 【第80天新增 / 改动3】🩺 面诊前准备（学生端首页 · 黄历卡片下方；老师端不渲染，页签结构不变）
            流程：开始 → POST /api/agent/ask_next_question（首次 current_answers 传空串）拿到一个问题
                 → 学生回答（可点 🎙️ 语音输入，复用现有录音逻辑）→「下一个问题」把问答累积进 current_answers 再拉下一问
                 → 后端 done=true 后提示「已收集完整，是否发送给老师？」→ POST /api/agent/save_intake 落库。 */}
        {(currentRole === '学生' || currentRole === '学生智能体') && (
          <div style={{ ...boxStyle, background: '#f3f8ff' }}>
            <div style={{ fontSize: '18px', color: '#3b6ea5', fontWeight: 'bold', marginBottom: '12px' }}>🩺 面诊前准备</div>
            <div style={{ padding: '12px', background: '#fff', borderRadius: '8px', border: '1px dashed #b9cde4', fontSize: '14px', color: '#333', lineHeight: '1.7', marginBottom: '12px' }}>
              {intakeAppointment ? '📅 ' : '🪞 '}{intakeApptText}
            </div>
            {intakeAppointment && !showIntake && (
              <button onClick={handleStartIntake} style={{ padding: '8px 24px', borderRadius: '20px', border: 'none', background: '#3b6ea5', color: '#fff', cursor: 'pointer', fontSize: '14px', fontFamily: 'serif' }}>开始面诊前准备</button>
            )}
            {intakeAppointment && showIntake && intakeSent && (
              <div style={{ textAlign: 'center', padding: '16px', background: '#fff', borderRadius: '8px', border: '1px solid #b9cde4', color: '#3b6ea5', fontSize: '15px' }}>
                ✅ 已发送，老师面诊时会看到
                <div style={{ marginTop: '10px' }}>
                  <button onClick={() => setShowIntake(false)} style={{ padding: '6px 16px', borderRadius: '20px', border: '1px solid #999', background: 'transparent', color: '#666', cursor: 'pointer', fontSize: '13px' }}>收起</button>
                </div>
              </div>
            )}
            {intakeAppointment && showIntake && !intakeSent && intakeDone && (
              <div>
                <div style={{ fontSize: '15px', color: '#3b6ea5', fontWeight: 'bold', marginBottom: '8px' }}>已收集完整，是否发送给老师？</div>
                <textarea value={intakeAnswers} readOnly style={{ width: '100%', height: '150px', padding: '10px', borderRadius: '8px', border: '1px solid #b9cde4', background: '#fff', fontFamily: 'serif', fontSize: '13px', marginBottom: '10px', boxSizing: 'border-box' }} />
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                  <button onClick={() => setShowIntake(false)} style={{ padding: '6px 16px', borderRadius: '20px', border: '1px solid #999', background: 'transparent', color: '#666', cursor: 'pointer', fontSize: '13px' }}>先不发送</button>
                  <button onClick={handleSendIntake} disabled={intakeSending} style={{ padding: '6px 20px', borderRadius: '20px', border: 'none', background: intakeSending ? '#8aa2bb' : '#3b6ea5', color: '#fff', cursor: intakeSending ? 'default' : 'pointer', fontSize: '13px' }}>{intakeSending ? '发送中...' : '发送'}</button>
                </div>
              </div>
            )}
            {intakeAppointment && showIntake && !intakeSent && !intakeDone && (
              <div>
                <div style={{ fontSize: '12px', color: '#8aa2bb', marginBottom: '6px' }}>十问歌 · 已答 {intakeRounds} 问（共十问）</div>
                <div style={{ padding: '12px', background: '#fff', borderRadius: '8px', border: '1px solid #b9cde4', fontSize: '16px', color: '#333', lineHeight: '1.7', marginBottom: '10px', minHeight: '26px' }}>
                  {intakeLoading ? '智能体正在想下一个问题...' : intakeQuestion}
                </div>
                <textarea value={intakeAnswer} onChange={e => setIntakeAnswer(e.target.value)} placeholder="用您自己的话说说，或点下方 🎙️ 语音输入..." style={{ width: '100%', height: '80px', padding: '10px', borderRadius: '8px', border: '1px solid #b9cde4', fontFamily: 'serif', marginBottom: '10px', boxSizing: 'border-box' }} />
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '10px' }}>
                  <button onClick={startIntakeRecording} style={{ padding: '8px 20px', borderRadius: '30px', border: 'none', background: intakeRecording ? '#c0392b' : '#5a7d5a', color: '#fff', cursor: 'pointer', fontSize: '14px', fontFamily: 'serif' }}>
                    {intakeRecording ? '⏹ 停止录音（点击结束）' : '🎙️ 语音输入'}
                  </button>
                  <button onClick={handleNextIntakeQuestion} disabled={intakeLoading} style={{ padding: '8px 24px', borderRadius: '30px', border: 'none', background: intakeLoading ? '#8aa2bb' : '#3b6ea5', color: '#fff', cursor: intakeLoading ? 'default' : 'pointer', fontSize: '14px', fontFamily: 'serif' }}>
                    {intakeLoading ? '处理中...' : '下一个问题'}
                  </button>
                </div>
                {intakeRecording && (<div style={{ fontSize: '12px', color: '#c0392b', marginTop: '5px' }}>● 正在录音，请说话...（说完再点一次停止）</div>)}
              </div>
            )}
          </div>
        )}

        {/* 【第56天重构】🤖 智能体工作台（老师端 🏠 首页，位置：黄历卡片下方、今日备忘录卡片上方）
            三个区块：⏳ 待你确认（浅黄底强调） / ✅ 已办汇报（最近 5 条） / 📜 行动日志（最近 10 条）；
            「立即扫描」走统一扫描接口 POST /api/agent/scan（请求体 { teacher_name }），一次扫出三类学生请示：
            沉默关怀 send_care_notice + 欠费预存 send_billing_notice + 复诊提醒 send_recall_notice。 */}
        {(currentRole === '李老师' || currentRole === '李老师智能体') && teacherTab === 'home' && (
          <div style={boxStyle}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <div style={{ fontSize: '18px', color: '#8b4513', fontWeight: 'bold' }}>🤖 智能体工作台</div>
              <button
                onClick={handleAgentScan}
                disabled={scanningAgent}
                style={{ padding: '4px 12px', borderRadius: '15px', border: '1px solid #8b4513', background: 'transparent', color: '#8b4513', cursor: 'pointer', fontSize: '12px', fontFamily: 'serif' }}
              >{scanningAgent ? '扫描中…' : '🔍 立即扫描'}</button>
            </div>

            {/* 区块1：⏳ 待你确认（浅黄底强调） */}
            <div style={{ background: '#fffbe8', border: '1px solid #f0e2b6', borderRadius: '8px', padding: '12px' }}>
              <div style={{ fontSize: '14px', color: '#8b4513', fontWeight: 'bold', marginBottom: '8px' }}>⏳ 待你确认（{agentPendingTasks.length}）</div>
              {agentPendingTasks.length === 0 ? (
                <div style={{ textAlign: 'center', color: '#999', fontSize: '13px', padding: '6px' }}>暂无待办</div>
              ) : (
                agentPendingTasks.map(task => (
                  <div key={task.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px', background: '#fff', border: '1px solid #f0e2b6', borderRadius: '8px', marginBottom: '8px' }}>
                    <div style={{ flex: 1, marginRight: '10px' }}>
                      <div style={{ fontSize: '14px', color: '#8b4513', fontWeight: 'bold', marginBottom: '4px' }}>{task.title}</div>
                      <div style={{ fontSize: '12px', color: '#666', lineHeight: '1.5' }}>{task.content}</div>
                    </div>
                    <div style={{ whiteSpace: 'nowrap' }}>
                      <button onClick={() => handleApproveAgentTask(task.id)} style={{ marginRight: '6px', padding: '4px 10px', borderRadius: '4px', border: 'none', background: '#5a7d5a', color: '#fdfcf0', cursor: 'pointer', fontSize: '12px', fontFamily: 'serif' }}>✅ 确认</button>
                      <button onClick={() => handleRejectAgentTask(task.id)} style={{ padding: '4px 10px', borderRadius: '4px', border: 'none', background: '#d4c8a8', color: '#333', cursor: 'pointer', fontSize: '12px', fontFamily: 'serif' }}>❌ 忽略</button>
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* 区块2：✅ 已办汇报（最近 5 条：标题 + 处理时间 resolved_at） */}
            <div style={{ borderTop: '1px solid #f0e9d6', marginTop: '12px', paddingTop: '12px' }}>
              <div style={{ fontSize: '14px', color: '#8b4513', fontWeight: 'bold', marginBottom: '8px' }}>✅ 已办汇报（最近 5 条）</div>
              {agentDoneTasks.length === 0 ? (
                <div style={{ textAlign: 'center', color: '#999', fontSize: '13px', padding: '6px' }}>暂无</div>
              ) : (
                agentDoneTasks.map(task => (
                  <div key={task.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 0', borderBottom: '1px dashed #f0e9d6' }}>
                    <div style={{ flex: 1, fontSize: '13px', color: '#333', marginRight: '8px' }}>· {task.title}</div>
                    <div style={{ fontSize: '11px', color: '#999', whiteSpace: 'nowrap' }}>{formatAgentTime(task.resolved_at)}</div>
                  </div>
                ))
              )}
            </div>

            {/* 区块3：📜 行动日志（最近 10 条：[action] + detail + created_at） */}
            <div style={{ borderTop: '1px solid #f0e9d6', marginTop: '12px', paddingTop: '12px' }}>
              <div style={{ fontSize: '14px', color: '#8b4513', fontWeight: 'bold', marginBottom: '8px' }}>📜 行动日志（最近 10 条）</div>
              {agentActionLogs.length === 0 ? (
                <div style={{ textAlign: 'center', color: '#999', fontSize: '13px', padding: '6px' }}>暂无</div>
              ) : (
                agentActionLogs.map(log => (
                  <div key={log.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', padding: '6px 0', borderBottom: '1px dashed #f0e9d6' }}>
                    <div style={{ flex: 1, fontSize: '13px', color: '#333', marginRight: '8px', lineHeight: '1.6' }}>
                      <span style={{ color: '#5a7d5a', fontWeight: 'bold', marginRight: '6px' }}>[{log.action}]</span>{log.detail}
                    </div>
                    <div style={{ fontSize: '11px', color: '#999', whiteSpace: 'nowrap' }}>{formatAgentTime(log.created_at)}</div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* 【第61天新增】老师端：📋 今日备忘录（动态时间轴 + 未排期事项列；已完成移除、逾期变灰、跨天自动清空） */}
        {(currentRole === '李老师' || currentRole === '李老师智能体') && teacherTab === 'home' && (
          <div style={{ ...boxStyle, background: '#fffdf5' }}>
            <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', fontWeight: 'bold', marginBottom: '12px' }}>📋 今日备忘录</div>

            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'flex-start' }}>
              {/* 左列：时间轴（有明确时间的事项，按时间升序；已处理的移除，逾期的变灰） */}
              <div style={{ flex: '1 1 320px', padding: '12px', background: '#fff8e7', borderRadius: '8px', border: '1px solid #f0e9d6' }}>
                <div style={{ fontSize: '13px', color: '#8b4513', fontWeight: 'bold', marginBottom: '8px' }}>⏱ 今日时间轴（按时间升序）</div>
                {memoTimedVisible.length === 0 ? (
                  <div style={{ fontSize: '13px', color: '#5a7d5a' }}>今日事项已全部处理 🎉</div>
                ) : (
                  memoTimedVisible.map(it => {
                    const overdue = isMemoOverdue(it.time)   // 未处理 且 已过事项时间 → 逾期
                    return (
                      <div key={it.key} style={{ display: 'flex', alignItems: 'center', padding: '6px 0', borderBottom: '1px dashed #f0e9d6' }}>
                        <div style={{ width: '46px', fontSize: '12px', color: overdue ? '#999' : '#8b4513', fontWeight: 'bold' }}>{it.time}</div>
                        <div style={{ flex: 1, fontSize: '13px', color: overdue ? '#999' : '#333', textDecoration: overdue ? 'line-through' : 'none' }}>
                          {it.text}{overdue ? ' · 已逾期' : ''}
                        </div>
                        <button onClick={() => handleMemoDone(it.key)} style={{ padding: '2px 10px', borderRadius: '12px', border: '1px solid #5a7d5a', background: 'transparent', color: '#5a7d5a', cursor: 'pointer', fontSize: '11px', fontFamily: 'serif', whiteSpace: 'nowrap' }}>完成</button>
                      </div>
                    )
                  })
                )}
              </div>

              {/* 右列：未排期事项（没有明确时间的事项，不混入时间轴） */}
              <div style={{ flex: '1 1 220px', padding: '12px', background: '#f0f4f8', borderRadius: '8px', border: '1px solid #dde5ee' }}>
                <div style={{ fontSize: '13px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '8px' }}>🗂 未排期事项（无明确时间）</div>
                {memoUnscheduledVisible.length === 0 ? (
                  <div style={{ fontSize: '13px', color: '#5a7d5a' }}>暂无未排期事项 🎉</div>
                ) : (
                  memoUnscheduledVisible.map(it => (
                    <div key={it.key} style={{ display: 'flex', alignItems: 'flex-start', padding: '6px 0', borderBottom: '1px dashed #dde5ee' }}>
                      <div style={{ flex: 1, fontSize: '13px', color: '#333', lineHeight: '1.7' }}>· {it.text}</div>
                      <button onClick={() => handleMemoDone(it.key)} style={{ marginLeft: '8px', padding: '2px 10px', borderRadius: '12px', border: '1px solid #5a7d5a', background: 'transparent', color: '#5a7d5a', cursor: 'pointer', fontSize: '11px', fontFamily: 'serif', whiteSpace: 'nowrap' }}>完成</button>
                    </div>
                  ))
                )}
                {currentRole === '李老师' && roleData?.task === '待审核' && roleData?.detail.includes('已打卡') && (
                  <div style={{ textAlign: 'center', marginTop: '10px' }}>
                    <button onClick={handleApprove} style={{ padding: '6px 16px', borderRadius: '20px', border: 'none', background: '#5a7d5a', color: '#fff', fontSize: '13px', cursor: 'pointer', fontFamily: 'serif' }}>签字确认</button>
                  </div>
                )}
              </div>
            </div>

            {/* 每日重置占位提示（尚未接后端，仅 UI 占位 + 前端跨天自动清空） */}
            <div style={{ textAlign: 'center', fontSize: '11px', color: '#999', marginTop: '10px' }}>
              ℹ️ 每日 00:00 由后台智能体自动重置清理（当前未接后端，此处为界面占位提示；前端已做跨天自动清空）
            </div>
          </div>
        )}

        {/* 【第58天新增】学生端：照镜子卡片（黄历下方） */}
        {(currentRole === '学生' || currentRole === '学生智能体') && (
          <div style={{ ...boxStyle, background: '#f7fcf9' }}>
            <div style={{ fontSize: '18px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '12px' }}>
              🪞 {isMorning ? '早间照镜子' : '晚间照镜子'}
            </div>
            <div style={{ padding: '12px', background: '#fff', borderRadius: '8px', border: '1px dashed #b8d8c0', marginBottom: '12px' }}>
              <div style={{ fontSize: '14px', color: '#333', lineHeight: '1.8' }}>💡 {mirrorTip}</div>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ fontSize: '12px', color: '#999' }}>
                今日：早间 {todayMirror.morning ? '✅' : '⬜'} · 晚间 {todayMirror.evening ? '✅' : '⬜'}
              </div>
              <button
                onClick={handleMirrorDone}
                disabled={mirrorDone}
                style={{
                  padding: '8px 24px', borderRadius: '20px', border: 'none',
                  background: mirrorDone ? '#b8d8c0' : '#5a7d5a', color: '#fff',
                  cursor: mirrorDone ? 'default' : 'pointer', fontSize: '14px', fontFamily: 'serif'
                }}
              >{mirrorDone ? '✅ 已完成' : '我已完成'}</button>
            </div>
          </div>
        )}

        {/* 【第58天新增】学生端：习惯追踪 + A/B/C 提醒频率 */}
        {(currentRole === '学生' || currentRole === '学生智能体') && (
          <div style={{ ...boxStyle, background: '#fdf8f0' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <div style={{ fontSize: '18px', color: '#8b4513', fontWeight: 'bold' }}>🌱 习惯追踪</div>
              <div style={{ fontSize: '12px', color: '#8b4513', padding: '3px 10px', borderRadius: '12px', background: '#fff8e7', border: '1px solid #d4c8a8' }}>{frequencyLabel}</div>
            </div>
            {!shouldRemindToday && (
              <div style={{ fontSize: '12px', color: '#999', marginBottom: '10px', textAlign: 'center' }}>今日按频率无需打卡，仍可自愿完成 ✅</div>
            )}
            {habitList.length === 0 ? (
              <div style={{ textAlign: 'center', color: '#999', fontSize: '13px', padding: '10px' }}>暂无习惯，请在下方添加</div>
            ) : (
              habitList.map(h => (
                <div key={h} style={{ display: 'flex', alignItems: 'center', padding: '10px', marginBottom: '6px', background: todayHabits[h] ? '#e8f4e8' : '#fff', border: todayHabits[h] ? '1px solid #5a7d5a' : '1px solid #e0e0e0', borderRadius: '8px' }}>
                  <div style={{ flex: 1, fontSize: '14px', color: '#333' }}>{todayHabits[h] ? '✅' : '⬜'} {h}</div>
                  <button
                    onClick={() => handleToggleHabit(h)}
                    style={{ padding: '4px 14px', borderRadius: '15px', border: '1px solid #5a7d5a', background: todayHabits[h] ? '#5a7d5a' : 'transparent', color: todayHabits[h] ? '#fff' : '#5a7d5a', cursor: 'pointer', fontSize: '12px', fontFamily: 'serif' }}
                  >{todayHabits[h] ? '已打卡 +1' : '打卡 +1'}</button>
                  <button onClick={() => handleRemoveHabit(h)} style={{ marginLeft: '6px', padding: '2px 8px', borderRadius: '12px', border: '1px solid #c0392b', background: 'transparent', color: '#c0392b', cursor: 'pointer', fontSize: '11px' }}>✕</button>
                </div>
              ))
            )}
            <div style={{ display: 'flex', gap: '8px', marginTop: '10px' }}>
              <input
                placeholder="添加新习惯（如：散步）"
                value={newHabitName}
                onChange={e => setNewHabitName(e.target.value)}
                style={{ flex: 1, padding: '8px', borderRadius: '6px', border: '1px solid #d4c8a8', fontFamily: 'serif', boxSizing: 'border-box' }}
              />
              <button onClick={handleAddHabit} style={{ padding: '8px 16px', borderRadius: '6px', border: 'none', background: '#8b4513', color: '#fff', cursor: 'pointer', fontFamily: 'serif' }}>+ 添加</button>
            </div>
          </div>
        )}

        {/* 【第58天新增】学生端：习惯追踪周报 */}
        {(currentRole === '学生' || currentRole === '学生智能体') && (
          <div style={{ ...boxStyle, background: '#fffdf5' }}>
            <div style={{ fontSize: '18px', color: '#8b4513', fontWeight: 'bold', marginBottom: '12px' }}>📊 本周习惯周报</div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', color: '#666', marginBottom: '6px' }}>
              <span>本周打卡</span>
              <span style={{ color: '#8b4513', fontWeight: 'bold' }}>{weekStats.done} / {weekStats.total} 次（{weekStats.rate}%）</span>
            </div>
            <div style={{ height: '16px', background: '#f0f0f0', borderRadius: '8px', overflow: 'hidden', marginBottom: '12px' }}>
              <div style={{ width: `${weekStats.rate}%`, height: '100%', background: weekStats.rate >= 80 ? '#5a7d5a' : weekStats.rate >= 50 ? '#8b4513' : '#c0392b', borderRadius: '8px', transition: 'width 0.5s' }} />
            </div>
            <div style={{ padding: '12px', background: '#f7fcf9', borderRadius: '8px', border: '1px dashed #b8d8c0', fontSize: '14px', color: '#333', lineHeight: '1.6' }}>
              📝 本周小结：{weekStats.summary}
            </div>
          </div>
        )}

        {/* 【第56天重构】原「智能体工作台」卡片已上移到黄历卡片下方（三区块：待你确认 / 已办汇报 / 行动日志），此处不再重复渲染 */}

        {(currentRole === '学生' || currentRole === '学生智能体') && healthTrend && (
          <div style={boxStyle}>
            <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', fontWeight: 'bold', marginBottom: '15px' }}>📊 我的健康趋势</div>
            <div style={{ textAlign: 'center', fontSize: '13px', color: '#666', marginBottom: '12px' }}>八字：{healthTrend.bazi}</div>
            <div style={{ marginBottom: '15px' }}>
              <div style={{ fontSize: '13px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '8px' }}>五行分布：</div>
              {(['木', '火', '土', '金', '水'] as const).map((el) => {
                const count = healthTrend.counts[el]
                const barWidth = Math.min(count * 20, 100)
                const isWeakest = el === healthTrend.weakest
                return (
                  <div key={el} style={{ display: 'flex', alignItems: 'center', marginBottom: '6px' }}>
                    <div style={{ width: '30px', fontSize: '14px', color: isWeakest ? '#c0392b' : '#333', fontWeight: isWeakest ? 'bold' : 'normal' }}>{el}</div>
                    <div style={{ flex: 1, height: '16px', background: '#f0f0f0', borderRadius: '8px', overflow: 'hidden', margin: '0 8px' }}>
                      <div style={{ width: `${barWidth}%`, height: '100%', background: isWeakest ? '#c0392b' : '#8b4513', borderRadius: '8px', transition: 'width 0.5s' }} />
                    </div>
                    <div style={{ width: '20px', fontSize: '13px', color: '#666', textAlign: 'right' }}>{count}</div>
                  </div>
                )
              })}
            </div>
            <div style={{ textAlign: 'center', padding: '10px', background: '#fff8e7', borderRadius: '8px', marginBottom: '12px' }}>
              <span style={{ fontSize: '14px', color: '#8b4513', fontWeight: 'bold' }}>☯ 阴阳状态：{healthTrend.yinyang}</span>
            </div>
            <div style={{ padding: '12px', background: '#f7fcf9', borderRadius: '8px', border: '1px dashed #b8d8c0' }}>
              <div style={{ fontSize: '13px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '5px' }}>💡 体质参考：</div>
              <div style={{ fontSize: '14px', color: '#333', lineHeight: '1.6' }}>{healthTrend.tendency}</div>
            </div>
            <div style={{ textAlign: 'center', fontSize: '11px', color: '#999', marginTop: '10px', fontStyle: 'italic' }}>基于出生八字的先天体质参考，具体辨证请以老师当面问诊为准</div>
          </div>
        )}

        {(currentRole === '学生' || currentRole === '学生智能体') && dailyAdvice && (
          <div style={boxStyle}>
            <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', fontWeight: 'bold', marginBottom: '15px' }}>🌤️ 今日建议 · {dailyAdvice.solar_term}</div>
            {dailyAdvice.tendency_note && (
              <div style={{ textAlign: 'center', padding: '8px', background: '#fff8e7', borderRadius: '8px', marginBottom: '15px', fontSize: '13px', color: '#8b4513' }}>💡 {dailyAdvice.tendency_note}</div>
            )}
            <div style={{ display: 'flex', gap: '10px', marginBottom: '10px' }}>
              <div style={{ flex: 1, padding: '12px', background: '#f0f7f0', borderRadius: '8px' }}>
                <div style={{ fontSize: '14px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '6px' }}>🥗 宜食</div>
                <div style={{ fontSize: '13px', color: '#333', lineHeight: '1.6' }}>{dailyAdvice.eat}</div>
              </div>
              <div style={{ flex: 1, padding: '12px', background: '#fdf0f0', borderRadius: '8px' }}>
                <div style={{ fontSize: '14px', color: '#c0392b', fontWeight: 'bold', marginBottom: '6px' }}>🚫 忌口</div>
                <div style={{ fontSize: '13px', color: '#333', lineHeight: '1.6' }}>{dailyAdvice.avoid}</div>
              </div>
            </div>
            <div style={{ padding: '12px', background: '#f0f4f8', borderRadius: '8px' }}>
              <div style={{ fontSize: '14px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '6px' }}>👕 衣着起居</div>
              <div style={{ fontSize: '13px', color: '#333', lineHeight: '1.6' }}>{dailyAdvice.wear}</div>
            </div>
          </div>
        )}

        {(currentRole === '学生' || currentRole === '学生智能体') && (
          <div style={{ ...boxStyle, background: '#fdf8f0' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <div style={{ fontSize: '18px', color: '#8b4513', fontWeight: 'bold' }}>🧑‍⚕️ 我的老师（{patientTeachers.length}/3）</div>
              <button onClick={() => setShowTeacherPicker(!showTeacherPicker)} style={{ padding: '4px 12px', borderRadius: '15px', border: '1px solid #8b4513', background: 'transparent', color: '#8b4513', cursor: 'pointer', fontSize: '12px' }}>
                {showTeacherPicker ? '收起' : '管理'}
              </button>
            </div>
            <div style={{ fontSize: '13px', color: '#666', marginBottom: '8px' }}>当前咨询：<span style={{ color: '#8b4513', fontWeight: 'bold' }}>{selectedTeacher}</span></div>
            <div style={{ display: 'flex', flexWrap: 'wrap' }}>
              {patientTeachers.map(t => (
                <div key={t} style={{ display: 'flex', alignItems: 'center', margin: '4px' }}>
                  <button style={teacherBtnStyle(t)} onClick={() => setSelectedTeacher(t)}>👨‍⚕️ {t}</button>
                  {patientTeachers.length > 1 && (
                    <button onClick={() => handleRemoveTeacher(t)} style={{ marginLeft: '4px', padding: '2px 8px', borderRadius: '12px', border: '1px solid #c0392b', background: 'transparent', color: '#c0392b', cursor: 'pointer', fontSize: '11px' }}>✕</button>
                  )}
                </div>
              ))}
            </div>
            {showTeacherPicker && (
              <div style={{ marginTop: '12px', borderTop: '1px dashed #d4c8a8', paddingTop: '12px' }}>
                <div style={{ fontSize: '13px', color: '#666', marginBottom: '8px' }}>可选老师：</div>
                {teachers.filter(t => !patientTeachers.includes(t.name)).map(t => (
                  <button key={t.name} onClick={() => handleAddTeacher(t.name)} style={{ padding: '6px 14px', margin: '4px', borderRadius: '15px', border: '1px dashed #8b4513', background: 'transparent', color: '#8b4513', cursor: 'pointer', fontSize: '13px' }}>+ {t.name}</button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* 【第62天调整】管理页签 · 学生（在上）：学生管理 */}
        {(currentRole === '李老师' || currentRole === '李老师智能体') && teacherTab === 'manage' && (
          <div style={{ ...boxStyle, background: '#f0f7f0' }}>
            <div style={{ fontSize: '18px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '10px' }}>👥 学生管理（{teacherPatients.length}人）</div>
            {/* 【第58天新增】老师端设置学生提醒频率（A 每天 / B 隔天 / C 每周），与学生端 localStorage 共享 */}
            <div style={{ marginBottom: '12px', padding: '10px', background: '#fff', borderRadius: '8px', border: '1px dashed #b8d8c0' }}>
              <div style={{ fontSize: '13px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '8px' }}>⏰ 提醒频率设置（当前学生：{selectedPatient}）</div>
              <div style={{ display: 'flex', gap: '6px' }}>
                {([['A', 'A · 每天'], ['B', 'B · 隔天'], ['C', 'C · 每周']] as const).map(([key, label]) => (
                  <button
                    key={key}
                    onClick={() => setReminderFrequency(key)}
                    style={{ flex: 1, padding: '6px 4px', borderRadius: '8px', border: '1px solid #5a7d5a', background: reminderFrequency === key ? '#5a7d5a' : 'transparent', color: reminderFrequency === key ? '#fff' : '#5a7d5a', cursor: 'pointer', fontSize: '12px', fontFamily: 'serif' }}
                  >{label}</button>
                ))}
              </div>
            </div>
            <div style={{ display: 'flex', gap: '8px', marginBottom: '15px' }}>
              <input id="newStudentInput" placeholder="输入学生姓名，添加为新学生" style={{ flex: 1, padding: '8px', borderRadius: '6px', border: '1px solid #b8d8c0', fontFamily: 'serif' }} />
              <button onClick={() => {
                const input = document.getElementById('newStudentInput') as HTMLInputElement
                const name = input?.value.trim()
                if (!name) { alert("请输入学生姓名"); return }
                fetch('/api/teacher/add-student', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ teacher_name: selectedTeacher, student_name: name }) })
                  .then(() => { input.value = ''; fetch(`/api/teacher-patients?teacher_name=${selectedTeacher}`).then(r => r.json()).then(d => setTeacherPatients(d)); fetchPatients('张三') })
              }} style={{ padding: '8px 16px', borderRadius: '6px', border: 'none', background: '#5a7d5a', color: '#fff', cursor: 'pointer' }}>+ 添加学生</button>
              <button onClick={handleCreateInvite} style={{ padding: '8px 16px', borderRadius: '6px', border: '1px solid #8b4513', background: 'transparent', color: '#8b4513', cursor: 'pointer' }}>🎫 生成邀请码</button>
            </div>

            {invites.length > 0 && (
              <div style={{ marginBottom: '15px', padding: '10px', background: '#fef8f0', borderRadius: '8px', border: '1px dashed #d4c8a8' }}>
                <div style={{ fontSize: '13px', color: '#8b4513', fontWeight: 'bold', marginBottom: '8px' }}>📮 已生成的邀请码（7天有效）</div>
                {invites.map((inv: any) => (
                  <div key={inv.code} style={{ display: 'flex', alignItems: 'center', padding: '6px', background: '#fff', borderRadius: '6px', marginBottom: '5px', fontSize: '13px' }}>
                    <div style={{ flex: 1, color: '#8b4513', fontWeight: 'bold', fontFamily: 'monospace' }}>{inv.code}</div>
                    <div style={{ flex: 1, fontSize: '11px', color: '#999' }}>{inv.used_by ? `已使用：${inv.used_by}` : '未使用'}</div>
                    {!inv.used_by && (
                      <button onClick={() => handleCopyInviteLink(inv.code)} style={{ padding: '3px 10px', borderRadius: '12px', border: '1px solid #5a7d5a', background: 'transparent', color: '#5a7d5a', cursor: 'pointer', fontSize: '11px' }}>复制链接</button>
                    )}
                  </div>
                ))}
              </div>
            )}

            <div style={{ background: '#fff', borderRadius: '8px', border: '1px solid #d4e8d4', overflow: 'hidden' }}>
              <div style={{ display: 'flex', padding: '10px', background: '#e8f4e8', fontSize: '13px', fontWeight: 'bold', color: '#5a7d5a' }}>
                <div style={{ flex: 2 }}>学生姓名</div>
                <div style={{ flex: 1, textAlign: 'center' }}>状态</div>
                <div style={{ flex: 1, textAlign: 'right' }}>操作</div>
              </div>
              {teacherPatients.length === 0 ? (
                <div style={{ padding: '20px', textAlign: 'center', color: '#999', fontSize: '13px' }}>暂无学生，请在上方添加</div>
              ) : (
                teacherPatients.map((s: any) => (
                  <div key={s.name} style={{ display: 'flex', alignItems: 'center', padding: '10px', borderTop: '1px solid #f0f0f0', fontSize: '14px' }}>
                    <div style={{ flex: 2, color: '#333' }}>👤 {s.name}</div>
                    <div style={{ flex: 1, textAlign: 'center' }}>
                      <span style={{ padding: '2px 10px', borderRadius: '12px', fontSize: '12px', background: `${s.status_color}15`, color: s.status_color, fontWeight: 'bold', border: `1px solid ${s.status_color}40` }}>{s.status_label}</span>
                    </div>
                    <div style={{ flex: 1, textAlign: 'right' }}>
                      <button style={{ padding: '4px 10px', borderRadius: '12px', border: '1px solid #5a7d5a', background: 'transparent', color: '#5a7d5a', cursor: 'pointer', fontSize: '12px', marginRight: '6px' }} onClick={() => setSelectedPatient(s.name)}>查看</button>
                      {s.name !== '张三' && s.name !== '李四' && (
                        <button onClick={() => {
                          if (!confirm(`确定要将学生【${s.name}】从您的名单中移除吗？`)) return
                          fetch(`/api/patient-teachers?patient_name=${s.name}&teacher_name=${selectedTeacher}`, { method: 'DELETE' })
                            .then(() => fetch(`/api/teacher-patients?teacher_name=${selectedTeacher}`).then(r => r.json()).then(d => setTeacherPatients(d)))
                        }} style={{ padding: '4px 10px', borderRadius: '12px', border: '1px solid #c0392b', background: 'transparent', color: '#c0392b', cursor: 'pointer', fontSize: '12px' }}>移除</button>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {(currentRole === '学生' || currentRole === '学生智能体') && (
          <div style={{ ...boxStyle, background: '#f0f7f5' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <div style={{ fontSize: '18px', color: '#5a7d5a', fontWeight: 'bold' }}>🏠 我的家庭（{patients.length}人）</div>
              <button onClick={handleToggleAddFamily} style={{ padding: '4px 12px', borderRadius: '15px', border: '1px solid #5a7d5a', background: 'transparent', color: '#5a7d5a', cursor: 'pointer', fontSize: '12px' }}>{showAddFamily ? '取消' : '+ 添加亲友'}</button>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center' }}>
              {patients.map(p => (
                <div key={p.name} style={{ display: 'flex', alignItems: 'center', margin: '4px' }}>
                  <button style={patientBtnStyle(p.name)} onClick={() => setSelectedPatient(p.name)}>
                    {p.relation === '本人' ? `👤 ${p.name}` : `👨‍👩‍👧 ${p.name}（${p.relation}）`}
                  </button>
                  {p.relation !== '本人' && (
                    <button onClick={() => handleDeleteFamily(p.name)} style={{ marginLeft: '4px', padding: '2px 8px', borderRadius: '12px', border: '1px solid #c0392b', background: 'transparent', color: '#c0392b', cursor: 'pointer', fontSize: '11px' }}>✕</button>
                  )}
                </div>
              ))}
            </div>
            {showAddFamily && (
              <div style={{ marginTop: '15px', borderTop: '1px dashed #b8d8c0', paddingTop: '15px' }}>
                <div style={{ fontSize: '14px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '10px' }}>📝 亲友基础信息</div>
                <input value={newFamilyName} onChange={(e) => setNewFamilyName(e.target.value)} placeholder="姓名（必填）" style={inputStyle} />
                <select value={newRelation} onChange={(e) => handleRelationChange(e.target.value)} style={inputStyle}>
                  <option value="">与您的关系（必填）</option>
                  <option value="父亲">父亲</option>
                  <option value="母亲">母亲</option>
                  <option value="儿子">儿子</option>
                  <option value="女儿">女儿</option>
                  <option value="配偶">配偶</option>
                  <option value="其他">其他</option>
                </select>
                <select value={newGender} onChange={(e) => setNewGender(e.target.value)} style={inputStyle}>
                  <option value="">性别（必填，选关系后自动联动）</option>
                  <option value="男">男</option>
                  <option value="女">女</option>
                </select>
                <label style={{ fontSize: '12px', color: '#888' }}>出生日期（按 年-月-日 顺序选择）</label>
                <div style={{ display: 'flex', flexWrap: 'wrap', marginBottom: '8px' }}>
                  <select value={newBirthYear} onChange={(e) => setNewBirthYear(e.target.value)} style={dateSelectStyle}>
                    <option value="">年</option>
                    {yearOptions.map(y => <option key={y} value={y}>{y}</option>)}
                  </select>
                  <select value={newBirthMonth} onChange={(e) => setNewBirthMonth(e.target.value)} style={dateSelectStyle}>
                    <option value="">月</option>
                    {monthOptions.map(m => <option key={m} value={m}>{m}</option>)}
                  </select>
                  <select value={newBirthDay} onChange={(e) => setNewBirthDay(e.target.value)} style={dateSelectStyle}>
                    <option value="">日</option>
                    {getDayOptions().map(d => <option key={d} value={d}>{d}</option>)}
                  </select>
                </div>
                <label style={{ fontSize: '12px', color: '#888' }}>出生时间（选填）</label>
                <select value={newBirthTime} onChange={(e) => setNewBirthTime(e.target.value)} style={inputStyle}>
                  {timeOptions.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                </select>
                <label style={{ fontSize: '12px', color: '#888' }}>出生地（选填）</label>
                <input value={newBirthPlace} onChange={(e) => setNewBirthPlace(e.target.value)} placeholder="例如：浙江省绍兴市" style={inputStyle} />
                <label style={{ fontSize: '12px', color: '#888' }}>现居住地（默认继承您的居住地）</label>
                <input value={newLocation} onChange={(e) => setNewLocation(e.target.value)} placeholder="例如：广东省广州市" style={inputStyle} />
                <div style={{ textAlign: 'right', marginTop: '10px' }}>
                  <button onClick={handleAddFamily} style={{ padding: '6px 20px', borderRadius: '20px', border: 'none', background: '#5a7d5a', color: '#fff', cursor: 'pointer' }}>确认添加亲友</button>
                </div>
              </div>
            )}
          </div>
        )}

        {(currentRole === '学生' || currentRole === '学生智能体') && profile && (
          <div style={{ ...boxStyle, background: '#fffaf0' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
              <div style={{ fontSize: '18px', color: '#8b4513', fontWeight: 'bold' }}>📋 {selectedPatient} 的基础档案</div>
              {editingProfile ? (
                <div>
                  <button onClick={() => setEditingProfile(false)} style={{ padding: '4px 12px', borderRadius: '15px', border: '1px solid #8b4513', background: 'transparent', color: '#8b4513', cursor: 'pointer', fontSize: '12px', marginRight: '6px' }}>取消</button>
                  <button onClick={handleSaveProfile} style={{ padding: '4px 12px', borderRadius: '15px', border: 'none', background: '#5a7d5a', color: '#fff', cursor: 'pointer', fontSize: '12px' }}>保存档案</button>
                </div>
              ) : (
                <button onClick={() => { setDraftProfile({ ...profile }); setEditingProfile(true) }} style={{ padding: '4px 12px', borderRadius: '15px', border: '1px solid #8b4513', background: 'transparent', color: '#8b4513', cursor: 'pointer', fontSize: '12px' }}>编辑/补充</button>
              )}
            </div>
            {editingProfile && draftProfile ? (
              <div>
                <label style={{ fontSize: '13px', color: '#666' }}>性别</label>
                {needGender ? (
                  <select value={draftProfile.gender} onChange={e => setDraftProfile({ ...draftProfile, gender: e.target.value })} style={inputStyle}>
                    <option value="">请选择</option>
                    <option value="男">男</option>
                    <option value="女">女</option>
                  </select>
                ) : (<div style={{ fontSize: '14px', color: '#333', marginBottom: '8px' }}>{profile.gender}</div>)}
                <label style={{ fontSize: '13px', color: '#666' }}>出生日期</label>
                {needBirthDate ? (
                  <div style={{ display: 'flex', flexWrap: 'wrap', marginBottom: '8px' }}>
                    <select value={draftProfile.birth_date ? draftProfile.birth_date.split('-')[0] : ''} onChange={e => {
                      const y = e.target.value
                      const m = draftProfile.birth_date ? draftProfile.birth_date.split('-')[1] : '01'
                      const d = draftProfile.birth_date ? draftProfile.birth_date.split('-')[2] : '01'
                      setDraftProfile({ ...draftProfile, birth_date: `${y}-${m}-${d}` })
                    }} style={dateSelectStyle}>
                      <option value="">年</option>
                      {yearOptions.map(y => <option key={y} value={y}>{y}</option>)}
                    </select>
                    <select value={draftProfile.birth_date ? draftProfile.birth_date.split('-')[1] : ''} onChange={e => {
                      const y = draftProfile.birth_date ? draftProfile.birth_date.split('-')[0] : currentYear
                      const m = e.target.value
                      const d = draftProfile.birth_date ? draftProfile.birth_date.split('-')[2] : '01'
                      setDraftProfile({ ...draftProfile, birth_date: `${y}-${m}-${d}` })
                    }} style={dateSelectStyle}>
                      <option value="">月</option>
                      {monthOptions.map(m => <option key={m} value={m}>{m}</option>)}
                    </select>
                    <select value={draftProfile.birth_date ? draftProfile.birth_date.split('-')[2] : ''} onChange={e => {
                      const y = draftProfile.birth_date ? draftProfile.birth_date.split('-')[0] : currentYear
                      const m = draftProfile.birth_date ? draftProfile.birth_date.split('-')[1] : '01'
                      const d = e.target.value
                      setDraftProfile({ ...draftProfile, birth_date: `${y}-${m}-${d}` })
                    }} style={dateSelectStyle}>
                      <option value="">日</option>
                      {getDayOptions().map(d => <option key={d} value={d}>{d}</option>)}
                    </select>
                  </div>
                ) : (<div style={{ fontSize: '14px', color: '#333', marginBottom: '8px' }}>{profile.birth_date}</div>)}
                <label style={{ fontSize: '13px', color: '#666' }}>出生时间</label>
                {needBirthTime ? (
                  <select value={draftProfile.birth_time} onChange={e => setDraftProfile({ ...draftProfile, birth_time: e.target.value })} style={inputStyle}>
                    {timeOptions.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                  </select>
                ) : (<div style={{ fontSize: '14px', color: '#333', marginBottom: '8px' }}>{timeOptions.find(t => t.value === profile.birth_time)?.label || profile.birth_time}</div>)}
                <label style={{ fontSize: '13px', color: '#666' }}>出生地</label>
                {needBirthPlace ? (
                  <input type="text" value={draftProfile.birth_place} onChange={e => setDraftProfile({ ...draftProfile, birth_place: e.target.value })} placeholder="例如：浙江省绍兴市" style={inputStyle} />
                ) : (<div style={{ fontSize: '14px', color: '#333', marginBottom: '8px' }}>{profile.birth_place}</div>)}
                <label style={{ fontSize: '13px', color: '#666' }}>现居住地（可修改）</label>
                <input type="text" value={draftProfile.location} onChange={e => setDraftProfile({ ...draftProfile, location: e.target.value })} placeholder="例如：广东省广州市" style={inputStyle} />
              </div>
            ) : (
              <div style={{ fontSize: '14px', color: '#333', lineHeight: '2' }}>
                <div>性别：{profile.gender || '未填写'}</div>
                <div>出生日期：{profile.birth_date || '未填写'}</div>
                <div>出生时间：{profile.birth_time ? (timeOptions.find(t => t.value === profile.birth_time)?.label || profile.birth_time) : '未填写'}</div>
                <div>出生地：{profile.birth_place || '未填写'}</div>
                <div>现居住地：{profile.location || '未填写'}</div>
              </div>
            )}
          </div>
        )}

        {/* 【第67天重构】⚙️ 设置页签：老师端四大分区（① 💊 药材入库 / ② 🕐 作息与节假日 / ③ 📅 预约与通知 / ④ 💰 财务规则）
            组织方式：每个分区用「大标题 + 分隔线」，自上而下依次排列
            - ② ③ 中的「我的工作时间 / 节假日设置 / 排班与预约日历 / 待处理预约」全部是原有卡片，state 与接口逻辑一字未改，只是重新归入分区
            - ① ③ ④ 中的规则类内容为纯前端只读占位（未接后端，后续版本开发）
            - 学生端：仍是原来的「预约」卡片（标题、日历、我的预约记录、预约表单均保持不变） */}
        {(currentRole === '学生' || currentRole === '学生智能体' || (isTeacherRole && teacherTab === 'settings')) && (
          <div style={isTeacherRole ? { marginBottom: '20px' } : boxStyle}>
            {/* 原卡片标题：仅学生端显示（老师端改为四大分区的分区标题，「排班与预约管理」标题移到分区③内） */}
            {!isTeacherRole && (
              <div style={{ fontSize: '18px', color: '#8b4513', fontWeight: 'bold', marginBottom: '12px' }}>
                📅 预约 {selectedTeacher}
              </div>
            )}

            {/* ============ 分区 ① 💊 药材入库（老师端设置页签） ============ */}
            {isTeacherRole && (
              <>
                <div style={sectionTitleStyle}>💊 药材入库</div>
                <div style={sectionCardStyle}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
                    <button onClick={() => alert('药材入库功能开发中')} style={{ padding: '8px 26px', borderRadius: '20px', border: 'none', background: '#5a7d5a', color: '#fff', cursor: 'pointer', fontSize: '14px', fontFamily: 'serif' }}>💊 入库</button>
                    <div style={{ fontSize: '13px', color: '#666' }}>老师或智能体录入新到药材</div>
                  </div>
                </div>

                {/* ============ 分区 ② 🕐 作息与节假日（老师端设置页签） ============ */}
                <div style={sectionTitleStyle}>🕐 作息与节假日</div>
              </>
            )}

            {/* ===== 分区 ② 内容：以下两张为原有卡片（我的工作时间 / 节假日设置），功能不变 ===== */}
            {isTeacherRole ? (
              <div style={sectionCardStyle}>
            {/* 老师工作时间设置 */}
            {currentRole.includes('老师') && schedule && (
              <div style={{ marginBottom: '12px', padding: '10px', background: '#f0f7f0', borderRadius: '8px', border: '1px dashed #5a7d5a' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                  <div style={{ fontSize: '13px', color: '#5a7d5a', fontWeight: 'bold' }}>⚙️ 我的工作时间</div>
                  <button onClick={() => setEditingSchedule(!editingSchedule)} style={{ padding: '2px 10px', borderRadius: '12px', border: '1px solid #5a7d5a', background: 'transparent', color: '#5a7d5a', cursor: 'pointer', fontSize: '11px' }}>
                    {editingSchedule ? '取消' : '修改'}
                  </button>
                </div>
                {!editingSchedule ? (
                  <div style={{ fontSize: '12px', color: '#666', lineHeight: '1.8' }}>
                    {[1,2,3,4,5,6,0].map(d => (
                      <div key={d}>周{['日','一','二','三','四','五','六'][d]}：{formatSlots(schedule[String(d)] || [])}</div>
                    ))}
                  </div>
                ) : (
                  <div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginBottom: '10px' }}>
                      {[1,2,3,4,5,6,0].map(d => (
                        <button key={d} onClick={() => setScheduleEditDay(String(d))} style={{ padding: '4px 12px', borderRadius: '12px', border: '1px solid #5a7d5a', background: scheduleEditDay === String(d) ? '#5a7d5a' : 'transparent', color: scheduleEditDay === String(d) ? '#fff' : '#5a7d5a', cursor: 'pointer', fontSize: '12px' }}>
                          周{['日','一','二','三','四','五','六'][d]}
                        </button>
                      ))}
                    </div>
                    {[
                      { label: '🌅 上午', slots: morningSlots },
                      { label: '☀️ 下午', slots: afternoonSlots },
                      { label: '🌙 晚间', slots: eveningSlots }
                    ].map(group => (
                      <div key={group.label}>
                        <div style={{ fontSize: '12px', color: '#666', fontWeight: 'bold', marginBottom: '4px' }}>{group.label}</div>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '3px', marginBottom: '8px' }}>
                          {group.slots.map(s => (
                            <button key={s} onClick={() => toggleSlot(scheduleEditDay, s)} style={{ padding: '3px 8px', borderRadius: '10px', border: '1px solid #8b4513', background: (tempSchedule[scheduleEditDay] || []).includes(s) ? '#8b4513' : 'transparent', color: (tempSchedule[scheduleEditDay] || []).includes(s) ? '#fff' : '#8b4513', cursor: 'pointer', fontSize: '11px' }}>{s}</button>
                          ))}
                        </div>
                      </div>
                    ))}
                    <div style={{ textAlign: 'right' }}>
                      <button onClick={handleSaveSchedule} style={{ padding: '6px 20px', borderRadius: '20px', border: 'none', background: '#5a7d5a', color: '#fff', cursor: 'pointer', fontSize: '13px' }}>保存工作时间</button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* 节假日管理 */}
            {currentRole.includes('老师') && (
              <div style={{ marginBottom: '12px', padding: '10px', background: '#fff5f5', borderRadius: '8px', border: '1px dashed #c0392b' }}>
                <div style={{ fontSize: '13px', color: '#c0392b', fontWeight: 'bold', marginBottom: '8px' }}>🎌 节假日设置</div>
                <div style={{ display: 'flex', gap: '6px', marginBottom: '8px' }}>
                  <input type="date" value={newHolidayDate} onChange={e => setNewHolidayDate(e.target.value)} style={{ flex: 1, padding: '6px', borderRadius: '6px', border: '1px solid #c0392b', fontSize: '13px', fontFamily: 'serif' }} />
                  <button onClick={handleAddHoliday} style={{ padding: '6px 14px', borderRadius: '6px', border: 'none', background: '#c0392b', color: '#fff', cursor: 'pointer', fontSize: '13px' }}>+ 添加</button>
                </div>
                {holidays.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                    {holidays.map(d => (
                      <div key={d} style={{ display: 'flex', alignItems: 'center', padding: '3px 8px', borderRadius: '12px', background: '#fff', border: '1px solid #c0392b', fontSize: '12px' }}>
                        <span style={{ color: '#c0392b' }}>{d}</span>
                        <button onClick={() => handleRemoveHoliday(d)} style={{ marginLeft: '6px', border: 'none', background: 'transparent', color: '#c0392b', cursor: 'pointer', fontSize: '14px', padding: 0 }}>×</button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
              </div>
            ) : null}

            {/* ============ 分区 ③ 📅 预约与通知（老师端设置页签） ============ */}
            {isTeacherRole && (
              <>
                <div style={sectionTitleStyle}>📅 预约与通知</div>

                {/* 预约规则（只读占位，后续开发） */}
                <div style={sectionCardStyle}>
                  <div style={{ fontSize: '15px', color: '#8b4513', fontWeight: 'bold', marginBottom: '8px' }}>📋 预约规则</div>
                  <div style={{ fontSize: '13px', color: '#666', lineHeight: '2' }}>
                    <div>· 可预约提前时间：学生最多提前 7 天发起预约（只读占位）</div>
                    <div>· 最长预约时长：单次面诊默认 30 分钟（只读占位）</div>
                    <div>· 取消 / 改期：面诊开始前 2 小时可自行取消（只读占位）</div>
                    <div>· 号源粒度：与分区②「我的工作时间」的 30 分钟时段保持一致</div>
                  </div>
                  <div style={{ fontSize: '11px', color: '#999', marginTop: '6px' }}>（后续开发：以上规则暂为只读占位，未接后端）</div>
                </div>

                {/* 通知条件（只读占位，后续开发） */}
                <div style={sectionCardStyle}>
                  <div style={{ fontSize: '15px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '8px' }}>🔔 通知条件</div>
                  <div style={{ fontSize: '13px', color: '#666', lineHeight: '2' }}>
                    <div>· 沉默学生提醒阈值：连续 7 天无打卡 / 无记录 → 提醒老师（占位）</div>
                    <div>· 余额预警阈值：账户余额低于 100 元 → 提醒学生与老师（占位）</div>
                    <div>· 提醒频率：A 每天 / B 隔天 / C 每周（已在【🗂️ 管理 → 学生管理】中按学生设置）</div>
                    <div>· 提醒方式：站内卡片 + 智能体工作台请示（占位）</div>
                  </div>
                  <div style={{ fontSize: '11px', color: '#999', marginTop: '6px' }}>（后续开发：以上阈值暂为只读占位，未接后端）</div>
                </div>

                {/* 原有卡片：排班与预约日历（功能不变，仅归入本分区） */}
                <div style={{ fontSize: '15px', color: '#8b4513', fontWeight: 'bold', margin: '4px 0 10px' }}>🗓 排班与预约管理</div>
              </>
            )}

            {/* ===== 分区 ③ 内容：以下为原有卡片（排班日历 / 待处理预约 / 我的预约记录 / 预约表单），功能不变 ===== */}
            <div style={isTeacherRole ? boxStyle : undefined}>
            {/* 7 天 tab 切换 */}
            {calendarData && calendarData.days && (
              <div>
                <div style={{ display: 'flex', gap: '4px', marginBottom: '12px', overflowX: 'auto' }}>
                  {calendarData.days.map((d: any, i: number) => (
                    <button
                      key={d.date}
                      onClick={() => setSelectedDayIndex(i)}
                      style={{
                        flex: 1, minWidth: '64px', padding: '8px 4px', borderRadius: '8px',
                        border: selectedDayIndex === i ? '1px solid #8b4513' : '1px solid #d4c8a8',
                        background: selectedDayIndex === i ? '#8b4513' : '#fff',
                        color: selectedDayIndex === i ? '#fff' : '#333',
                        cursor: 'pointer', fontSize: '12px', fontFamily: 'serif'
                      }}
                    >
                      <div style={{ fontWeight: 'bold' }}>周{['日','一','二','三','四','五','六'][d.weekday]}</div>
                      <div style={{ fontSize: '10px', opacity: 0.8, marginTop: '2px' }}>{d.date.slice(5)}</div>
                    </button>
                  ))}
                </div>

                {/* 时段网格 */}
                {(() => {
                  const day = calendarData.days[selectedDayIndex]
                  if (!day) return null
                  if (day.is_holiday) {
                    return <div style={{ textAlign: 'center', padding: '20px', color: '#c0392b', background: '#fff5f5', borderRadius: '8px' }}>🎌 老师今日休息</div>
                  }
                  if (!day.slots || day.slots.length === 0) {
                    return <div style={{ textAlign: 'center', padding: '20px', color: '#999', background: '#f5f5f5', borderRadius: '8px' }}>老师今日无排班</div>
                  }
                  return (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '6px' }}>
                      {[...day.slots].sort().map((slot: string) => {
                        const booked = day.booked[slot]
                        const isTeacher = currentRole.includes('老师')
                        return (
                          <button
                            key={slot}
                            onClick={() => {
                              if (booked) return
                              setApptDate(day.date)
                              setApptTime(slot)
                              setShowApptForm(true)
                            }}
                            disabled={!!booked}
                            style={{
                              padding: '10px 4px', borderRadius: '6px',
                              border: booked ? '1px solid #c0392b' : '1px solid #5a7d5a',
                              background: booked ? '#fdf0f0' : '#f7fcf9',
                              color: booked ? '#c0392b' : '#5a7d5a',
                              cursor: booked ? 'not-allowed' : 'pointer',
                              fontSize: '12px', fontFamily: 'serif', textAlign: 'center'
                            }}
                          >
                            <div style={{ fontWeight: 'bold' }}>{slot}</div>
                            <div style={{ fontSize: '10px', marginTop: '2px' }}>
                              {booked ? `${booked.patient_name} ${booked.status === 'confirmed' ? '✅' : '⏳'}` : (isTeacher ? '空闲' : '可约')}
                            </div>
                          </button>
                        )
                      })}
                    </div>
                  )
                })()}

                {/* 老师端待处理 */}
                {currentRole.includes('老师') && (
                  <div style={{ marginTop: '15px' }}>
                    <div style={{ fontSize: '13px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '8px' }}>📋 待处理预约</div>
                    {appointments.filter((a: any) => a.status === 'pending').length === 0 ? (
                      <div style={{ fontSize: '12px', color: '#999', textAlign: 'center', padding: '10px' }}>暂无</div>
                    ) : (
                      appointments.filter((a: any) => a.status === 'pending').map((a: any) => (
                        <div key={a.id} style={{ padding: '10px', background: '#fff8e7', borderRadius: '6px', marginBottom: '6px', fontSize: '12px' }}>
                          <div style={{ color: '#8b4513', fontWeight: 'bold' }}>{a.scheduled_date} · {a.scheduled_time}</div>
                          <div style={{ color: '#666', marginTop: '3px' }}>患者：{a.patient_name} · 原因：{a.reason}</div>
                          <div style={{ display: 'flex', gap: '6px', marginTop: '6px', justifyContent: 'flex-end' }}>
                            <button onClick={() => handleConfirmAppt(a.id)} style={{ padding: '3px 12px', borderRadius: '12px', border: 'none', background: '#5a7d5a', color: '#fff', cursor: 'pointer', fontSize: '11px' }}>确认</button>
                            <button onClick={() => handleCancelAppt(a.id)} style={{ padding: '3px 12px', borderRadius: '12px', border: '1px solid #c0392b', background: 'transparent', color: '#c0392b', cursor: 'pointer', fontSize: '11px' }}>取消</button>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                )}

                {/* 学生端预约记录 */}
                {!currentRole.includes('老师') && appointments.length > 0 && (
                  <div style={{ marginTop: '15px' }}>
                    <div style={{ fontSize: '13px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '8px' }}>📋 我的预约记录</div>
                    {appointments.map((a: any) => (
                      <div key={a.id} style={{ padding: '8px', background: '#fff', borderRadius: '6px', marginBottom: '5px', fontSize: '12px', border: '1px solid #e0e0e0' }}>
                        <span style={{ color: '#8b4513', fontWeight: 'bold' }}>{a.scheduled_date} · {a.scheduled_time}</span>
                        <span style={{ float: 'right' }}>
                          {a.status === 'confirmed' ? '✅ 已确认' : a.status === 'cancelled' ? '❌ 已取消' : '⏳ 待确认'}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* 预约表单 */}
            {showApptForm && (
              <div style={{ marginTop: '15px', padding: '12px', background: '#fffaf0', borderRadius: '8px', border: '1px dashed #d4c8a8' }}>
                <div style={{ fontSize: '13px', color: '#8b4513', fontWeight: 'bold', marginBottom: '8px' }}>
                  确认预约：{apptDate} · {apptTime}
                </div>
                <textarea
                  placeholder="预约原因（如：复诊/症状变化/家人新症状...）"
                  value={apptReason}
                  onChange={e => setApptReason(e.target.value)}
                  style={{ width: '100%', height: '60px', padding: '8px', borderRadius: '6px', border: '1px solid #d4c8a8', fontFamily: 'serif', fontSize: '13px', marginBottom: '8px', boxSizing: 'border-box' }}
                />
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                  <button onClick={() => { setShowApptForm(false); setApptDate(''); setApptTime(''); setApptReason('') }} style={{ padding: '6px 16px', borderRadius: '20px', border: '1px solid #999', background: 'transparent', color: '#666', cursor: 'pointer', fontSize: '12px' }}>取消</button>
                  <button onClick={handleCreateAppointment} style={{ padding: '6px 20px', borderRadius: '20px', border: 'none', background: '#8b4513', color: '#fff', cursor: 'pointer', fontSize: '12px' }}>提交预约</button>
                </div>
              </div>
            )}
            </div>

            {/* ============ 分区 ④ 💰 财务规则（老师端设置页签） ============ */}
            {isTeacherRole && (
              <>
                <div style={sectionTitleStyle}>💰 财务规则</div>
                <div style={sectionCardStyle}>
                  <div style={{ fontSize: '14px', color: '#8b4513', fontWeight: 'bold', marginBottom: '6px' }}>💳 余额门限设置</div>
                  <div style={{ fontSize: '13px', color: '#666', lineHeight: '2', marginBottom: '14px' }}>
                    <div>· 余额下限：账户余额低于 100 元时，暂停新增预约（占位）</div>
                    <div>· 单次扣费上限：单次面诊扣费不超过 500 元（占位）</div>
                  </div>
                  <div style={{ fontSize: '14px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '6px' }}>🎁 积分赠送规则</div>
                  <div style={{ fontSize: '13px', color: '#666', lineHeight: '2', marginBottom: '14px' }}>
                    <div>· 打卡赠送：连续打卡 7 天赠送 10 积分（占位）</div>
                    <div>· 预存赠送：预存满 1000 元赠送 100 积分（占位）</div>
                    <div>· 邀请赠送：新学生首次面诊完成后赠送 20 积分（占位）</div>
                  </div>
                  <div style={{ padding: '10px', background: '#fff8e7', borderRadius: '8px', border: '1px dashed #d4c8a8', fontSize: '13px', color: '#8b4513', lineHeight: '1.8' }}>
                    ℹ️ 余额门限与积分赠送目前仅为规则占位（后续开发）。实际的钱款操作（充值 / 赠送 / 扣费 / 账户余额）在【🗂️ 管理】页签的「💰 财务管理」面板，本分区只放规则。
                  </div>
                  <div style={{ fontSize: '11px', color: '#999', marginTop: '6px' }}>（后续开发：以上规则暂为只读占位，未接后端）</div>
                </div>
              </>
            )}
          </div>
        )}

        {/* 【第62天调整】管理页签 · 学生（在上）：基础档案（原「学生」页签卡片，并入学生管理区，排在库存上方） */}
        {isTeacherRole && teacherTab === 'manage' && profile && (
          <div style={{ ...boxStyle, background: '#fffaf0' }}>
            <div style={{ fontSize: '18px', color: '#8b4513', fontWeight: 'bold', marginBottom: '15px' }}>📋 {selectedPatient} 的基础档案（供辨证参考）</div>
            <div style={{ fontSize: '14px', color: '#333', lineHeight: '2' }}>
              <div>性别：{profile.gender || '未填写'}</div>
              <div>出生日期：{profile.birth_date || '未填写'}</div>
              <div>出生时间：{profile.birth_time ? (timeOptions.find(t => t.value === profile.birth_time)?.label || profile.birth_time) : '未填写（时辰未知，按子时推算）'}</div>
              <div>出生地：{profile.birth_place || '未填写'}</div>
              <div>现居住地：{profile.location || '未填写'}</div>
              <div style={{ marginTop: '8px', paddingTop: '8px', borderTop: '1px dashed #d4c8a8', color: '#8b4513', fontWeight: 'bold' }}>八字：{profile.bazi || '缺少出生日期，无法推算'}</div>
              {profile.wuxing && (<div style={{ color: '#5a7d5a', fontWeight: 'bold' }}>五行体质参考：{profile.wuxing}</div>)}
            </div>
          </div>
        )}

        {/* 【第51天新增 / 第62天调整】中药材库存（合并进「管理」页签，排在学生卡片下方） */}
        {(currentRole === '李老师' || currentRole === '李老师智能体') && teacherTab === 'manage' && (
          <div style={boxStyle}>
            <h3 style={{ color: '#8b4513', textAlign: 'center', marginBottom: '12px' }}>💊 中药材库存</h3>
            <div style={{ marginBottom: '12px' }}>
              <button
                onClick={() => setShowHerbForm(true)}
                style={{ marginRight: '8px', background: '#8b4513', color: '#fdfcf0', border: 'none', padding: '6px 12px', borderRadius: '4px', cursor: 'pointer', fontFamily: 'serif' }}
              >+ 新增药材</button>
              <button
                onClick={toggleLowOnly}
                style={{ background: showLowOnly ? '#c0392b' : '#5a7d5a', color: '#fdfcf0', border: 'none', padding: '6px 12px', borderRadius: '4px', cursor: 'pointer', fontFamily: 'serif' }}
              >{showLowOnly ? '显示全部' : '查看预警'}</button>
            </div>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'serif' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #d4c8a8' }}>
                  <th style={{ textAlign: 'left', padding: '6px' }}>药材名</th>
                  <th style={{ textAlign: 'left', padding: '6px' }}>库存</th>
                  <th style={{ textAlign: 'left', padding: '6px' }}>单位</th>
                  <th style={{ textAlign: 'left', padding: '6px' }}>预警</th>
                  <th style={{ textAlign: 'left', padding: '6px' }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {herbs.map(h => (
                  <tr key={h.id} style={{ borderBottom: '1px solid #d4c8a8', color: h.is_low ? '#c0392b' : 'inherit' }}>
                    <td style={{ padding: '6px' }}>{h.is_low ? '⚠️ ' : ''}{h.herb_name}</td>
                    <td style={{ padding: '6px' }}>{h.stock_amount}</td>
                    <td style={{ padding: '6px' }}>{h.unit}</td>
                    <td style={{ padding: '6px' }}>{h.warn_threshold}</td>
                    <td style={{ padding: '6px' }}>
                      <button onClick={() => openAdjustModal(h)} style={{ marginRight: '6px', cursor: 'pointer' }}>调整</button>
                      <button onClick={() => handleDeleteHerb(h.id)} style={{ cursor: 'pointer' }}>删除</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {showHerbForm && (
          <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999 }}>
            <div style={{ ...boxStyle, width: '320px' }}>
              <h4 style={{ color: '#8b4513' }}>新增 / 更新药材</h4>
              <input style={inputStyle} placeholder="药材名" value={herbForm.herb_name} onChange={e => setHerbForm({ ...herbForm, herb_name: e.target.value })} />
              <input style={inputStyle} type="number" placeholder="库存量" value={herbForm.stock_amount} onChange={e => setHerbForm({ ...herbForm, stock_amount: e.target.value })} />
              <input style={inputStyle} placeholder="单位" value={herbForm.unit} onChange={e => setHerbForm({ ...herbForm, unit: e.target.value })} />
              <input style={inputStyle} type="number" placeholder="预警阈值" value={herbForm.warn_threshold} onChange={e => setHerbForm({ ...herbForm, warn_threshold: e.target.value })} />
              <div style={{ marginTop: '12px' }}>
                <button onClick={handleSaveHerb} style={{ marginRight: '8px', background: '#8b4513', color: '#fdfcf0', border: 'none', padding: '6px 12px', borderRadius: '4px', cursor: 'pointer', fontFamily: 'serif' }}>保存</button>
                <button onClick={() => setShowHerbForm(false)} style={{ background: '#d4c8a8', border: 'none', padding: '6px 12px', borderRadius: '4px', cursor: 'pointer', fontFamily: 'serif' }}>取消</button>
              </div>
            </div>
          </div>
        )}

        {adjustingHerb && (
          <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999 }}>
            <div style={{ ...boxStyle, width: '280px' }}>
              <h4 style={{ color: '#8b4513' }}>调整库存：{adjustingHerb.herb_name}</h4>
              <p>当前库存：{adjustingHerb.stock_amount} {adjustingHerb.unit}</p>
              <input style={inputStyle} type="number" placeholder="入库填正数，出库填负数" value={adjustDelta} onChange={e => setAdjustDelta(parseFloat(e.target.value) || 0)} />
              <div style={{ marginTop: '12px' }}>
                <button onClick={submitAdjust} style={{ marginRight: '8px', background: '#8b4513', color: '#fdfcf0', border: 'none', padding: '6px 12px', borderRadius: '4px', cursor: 'pointer', fontFamily: 'serif' }}>确认</button>
                <button onClick={() => setAdjustingHerb(null)} style={{ background: '#d4c8a8', border: 'none', padding: '6px 12px', borderRadius: '4px', cursor: 'pointer', fontFamily: 'serif' }}>取消</button>
              </div>
            </div>
          </div>
        )}

        {/* 【第59天重构】【第72天改名】开方已移入“诊室 → 🩺 诊室工作台 第四部分”（与病历草案 / 病历标签 / 辨证施治方案同框），此处不再单独显示 */}

        {/* 【第63天调整】🧑‍⚕️ 角色切换卡片（调试模块）：已从页面顶部附近迁至整页最底部（所有页签内容的最下方），代码见本 return 末尾 */}

        {/* 【第66天接入真实接口】💰 财务管理面板：老师端只在「🗂️管理」页签显示（🏠首页 / 🩺诊室 / ⚙️设置 均不显示）。
            数据来源：顶部两个数字取自 GET /api/finance/accounts（学生取第一个 role='student' 的账户，老师取第一个 role='teacher' 的账户）；
                  三个按钮各自展开内联小表单，分别 POST /api/finance/recharge | gift | deduct，成功后重新拉取账户数据。 */}
        {isTeacherRole && teacherTab === 'manage' && (
          <div style={{ ...boxStyle, background: '#fffdf5' }}>
            {/* 卡片标题 */}
            <div style={{ fontSize: '18px', color: '#8b4513', fontWeight: 'bold', marginBottom: '15px' }}>💰 财务管理</div>

            {/* 顶部一行：两个核心数字（学生账户总额 / 老师账户总额），数据来自 /api/finance/accounts 的真实余额 */}
            <div style={{ display: 'flex', justifyContent: 'space-around', textAlign: 'center', paddingBottom: '15px', borderBottom: '1px solid #e6dcc2', marginBottom: '15px' }}>
              <div>
                <div style={{ fontSize: '12px', color: '#999' }}>学生账户总额（{financeStudentAccount ? financeStudentAccount.username : '—'}）</div>
                <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#8b4513' }}>{financeStudentAccount ? financeStudentAccount.balance : '—'}</div>
              </div>
              <div>
                <div style={{ fontSize: '12px', color: '#999' }}>老师账户总额（{financeTeacherAccount ? financeTeacherAccount.username : '—'}）</div>
                <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#5a7d5a' }}>{financeTeacherAccount ? financeTeacherAccount.balance : '—'}</div>
              </div>
            </div>

            {/* 功能区 a：预存（充值）→ 内联表单 */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 0' }}>
              <button onClick={() => openFinanceForm('recharge')} style={{ padding: '8px 20px', borderRadius: '20px', border: 'none', background: '#8b4513', color: '#fff', cursor: 'pointer', fontFamily: 'serif', fontSize: '14px' }}>💵 预存（充值）</button>
              <div style={{ fontSize: '13px', color: '#666', textAlign: 'right' }}>学生预交学费充进账户，余额可跨次就诊使用</div>
            </div>
            {renderFinanceForm('recharge')}

            {/* 功能区 b：赠送 → 内联表单 */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 0' }}>
              <button onClick={() => openFinanceForm('gift')} style={{ padding: '8px 20px', borderRadius: '20px', border: 'none', background: '#5a7d5a', color: '#fff', cursor: 'pointer', fontFamily: 'serif', fontSize: '14px' }}>🎁 赠送</button>
              <div style={{ fontSize: '13px', color: '#666', textAlign: 'right' }}>活动或答谢时，额外赠送金额到学生账户</div>
            </div>
            {renderFinanceForm('gift')}

            {/* 功能区 c：扣费 → 内联表单（余额不足时后端不扣款，前端弹提示） */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 0' }}>
              <button onClick={() => openFinanceForm('deduct')} style={{ padding: '8px 20px', borderRadius: '20px', border: 'none', background: '#c0392b', color: '#fff', cursor: 'pointer', fontFamily: 'serif', fontSize: '14px' }}>💸 扣费</button>
              <div style={{ fontSize: '13px', color: '#666', textAlign: 'right' }}>面诊 / 开方后，从学生账户扣除对应金额</div>
            </div>
            {renderFinanceForm('deduct')}

            {/* 底部灰色小字：后续版本功能预告 */}
            <div style={{ fontSize: '12px', color: '#999', textAlign: 'center', marginTop: '15px' }}>催缴、统计、报表将在后续版本上线</div>
          </div>
        )}

        {/* 【第63天调整】积分卡片：学生端保持原样（老师端已升级为上方「💰 财务管理」面板，不再重复显示） */}
        {points && !isTeacherRole && (
          <div style={{ ...boxStyle, display: 'flex', justifyContent: 'space-around', textAlign: 'center', background: '#fffdf5' }}>
            <div>
              <div style={{ fontSize: '12px', color: '#999' }}>{selectedPatient} 积分</div>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#8b4513' }}>{points.patient_points}</div>
            </div>
            <div>
              <div style={{ fontSize: '12px', color: '#999' }}>{selectedTeacher} 积分</div>
              <div style={{ fontSize: '24px', fontWeight: 'bold', color: '#5a7d5a' }}>{points.teacher_points}</div>
            </div>
          </div>
        )}

        {/* 【第60天新增】角色任务卡：老师端已迁至首页「📋 今日备忘录」（移走不复制），这里只保留学生端原有卡片（内容与样式不变） */}
        {(currentRole === '学生' || currentRole === '学生智能体') && (
          <div style={{ ...boxStyle, background: '#fdfcf0' }}>
            <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', marginBottom: '10px' }}>{roleData ? `📋 ${roleData.name} 的任务` : '加载中...'}</div>
            <div style={{ textAlign: 'center', color: '#555', lineHeight: '1.8' }}>{roleData ? roleData.detail : '正在获取数据...'}</div>
            {currentRole === '学生' && roleData?.detail.includes('请记得') && (
              <div style={{ textAlign: 'center', marginTop: '20px' }}>
                <button onClick={handleCheckIn} style={{ padding: '10px 24px', borderRadius: '30px', border: 'none', background: '#8b4513', color: '#fff', fontSize: '16px', cursor: 'pointer' }}>立即打卡（+10积分）</button>
              </div>
            )}
          </div>
        )}

        {(currentRole === '李老师' || currentRole === '李老师智能体') && teacherTab === 'clinic' && (
          <div style={{ ...boxStyle, background: '#fff9f0' }}>
            <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', fontWeight: 'bold', cursor: 'pointer', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '5px' }} onClick={() => setShowHistory(!showHistory)}>
              📂 {selectedPatient} 的历史病历 {showHistory ? '▲' : '▼'}
            </div>
            {showHistory && (
              <div style={{ marginTop: '15px' }}>
                {patientRecords.length === 0 ? (
                  <div style={{ textAlign: 'center', color: '#999' }}>暂无历史病历记录</div>
                ) : (
                  patientRecords.map(r => (
                    <div key={r.id} style={{ padding: '12px', border: '1px dashed #d4c8a8', borderRadius: '8px', marginBottom: '15px', background: '#fdfcf0' }}>
                      <div style={{ color: '#5a7d5a', fontSize: '12px', marginBottom: '8px', fontWeight: 'bold' }}>✅ 由 {r.doctor} 签字确认</div>
                      <div style={{ fontSize: '13px', color: '#999', marginBottom: '3px' }}>【智能体原始草案】</div>
                      <div style={{ whiteSpace: 'pre-wrap', fontSize: '13px', color: '#666', background: '#f5f5f5', padding: '8px', borderRadius: '6px', marginBottom: '8px' }}>{r.ai_draft}</div>
                      <div style={{ fontSize: '13px', color: '#8b4513', marginBottom: '3px' }}>【老师最终决策】</div>
                      <div style={{ whiteSpace: 'pre-wrap', fontSize: '14px', color: '#333', background: '#fff8e7', padding: '8px', borderRadius: '6px' }}>{r.final_plan}</div>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        )}

        {(currentRole === '学生' || currentRole === '学生智能体') && (
          <div style={boxStyle}>
            <div style={{ textAlign: 'center', fontSize: '18px', color: '#8b4513', marginBottom: '15px' }}>🗣️ 学生智能体（先结构化，再发送）</div>
            <textarea value={inputText} onChange={(e) => setInputText(e.target.value)} placeholder="在此输入您的感受、症状，或点下方🎤录音..." style={{ width: '100%', height: '80px', padding: '10px', borderRadius: '8px', border: '1px solid #d4c8a8', fontFamily: 'serif', marginBottom: '10px', boxSizing: 'border-box' }} />
            <div style={{ marginBottom: '15px', textAlign: 'center' }}>
              <button onClick={startStudentRecording} style={{ padding: '8px 24px', borderRadius: '30px', border: 'none', background: isRecordingStudent ? '#c0392b' : '#8b4513', color: '#fff', cursor: 'pointer', fontSize: '14px', fontFamily: 'serif' }}>
                {isRecordingStudent ? '⏹ 停止录音（点击结束）' : '🎤 开始录音'}
              </button>
              {isRecordingStudent && (<div style={{ fontSize: '12px', color: '#c0392b', marginTop: '5px' }}>● 正在录音，请说话...（说完再点一次停止）</div>)}
            </div>
            {pendingAudios.length > 0 && (
              <div style={{ marginBottom: '15px', padding: '10px', border: '1px dashed #b8d8c0', borderRadius: '8px', background: '#f7fcf9' }}>
                <div style={{ fontSize: '13px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '8px' }}>🎙️ 待发送的录音（{pendingAudios.length}段）</div>
                {pendingAudios.map((url, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', marginBottom: '5px' }}>
                    <audio src={url} controls style={{ flex: 1, height: '30px' }} />
                    <button onClick={() => setPendingAudios(prev => prev.filter(u => u !== url))} style={{ marginLeft: '8px', padding: '2px 8px', borderRadius: '12px', border: '1px solid #c0392b', background: 'transparent', color: '#c0392b', cursor: 'pointer', fontSize: '11px' }}>删除</button>
                  </div>
                ))}
              </div>
            )}
            {pendingImages.length > 0 && (
              <div style={{ marginBottom: '15px', padding: '10px', border: '1px dashed #b8d8c0', borderRadius: '8px', background: '#f7fcf9' }}>
                <div style={{ fontSize: '13px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '8px' }}>📎 待发送的图片（{pendingImages.length}张）</div>
                <div style={{ display: 'flex', flexWrap: 'wrap' }}>
                  {pendingImages.map((url, i) => (
                    <div key={i} style={{ position: 'relative', margin: '4px' }}>
                      <img src={url} alt={`待发送${i + 1}`} style={{ width: '100px', height: '100px', objectFit: 'cover', borderRadius: '8px', border: '1px solid #b8d8c0' }} />
                      <button onClick={() => handleRemovePendingImage(url)} style={{ position: 'absolute', top: '2px', right: '2px', width: '22px', height: '22px', borderRadius: '50%', border: 'none', background: '#c0392b', color: '#fff', cursor: 'pointer', fontSize: '12px', lineHeight: '22px', padding: 0 }}>✕</button>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div style={{ display: 'flex', justifyContent: 'center', gap: '10px', marginBottom: '15px' }}>
              <button onClick={handleTranscribe} style={{ padding: '10px 24px', borderRadius: '30px', border: 'none', background: '#8b4513', color: '#fff', fontSize: '16px', cursor: 'pointer' }}>整理成结构化陈述</button>
              <button onClick={() => fileInputRef.current?.click()} style={{ padding: '10px 24px', borderRadius: '30px', border: '1px solid #8b4513', background: '#fdfcf0', color: '#8b4513', fontSize: '16px', cursor: 'pointer' }} disabled={uploading}>
                {uploading ? '上传中...' : '📷 添加图片'}
              </button>
              <input type="file" ref={fileInputRef} onChange={handleImageUpload} accept="image/*" style={{ display: 'none' }} />
            </div>
            {structuredPreview && (
              <div style={{ marginTop: '15px', borderTop: '1px dashed #d4c8a8', paddingTop: '15px' }}>
                <div style={{ fontSize: '14px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '8px' }}>📋 请确认以下内容后发送：</div>
                <textarea value={structuredPreview} onChange={(e) => setStructuredPreview(e.target.value)} style={{ width: '100%', height: '150px', padding: '10px', borderRadius: '8px', border: '1px solid #b8d8c0', background: '#f7fcf9', fontFamily: 'serif', fontSize: '13px', marginBottom: '10px', boxSizing: 'border-box' }} />
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                  <button onClick={() => setStructuredPreview(null)} style={{ padding: '6px 16px', borderRadius: '20px', border: '1px solid #999', background: 'transparent', color: '#666', cursor: 'pointer', fontSize: '13px' }}>取消</button>
                  <button onClick={handleConfirmSend} style={{ padding: '6px 20px', borderRadius: '20px', border: 'none', background: '#8b4513', color: '#fff', cursor: 'pointer', fontSize: '13px' }}>确认发送给 {selectedTeacher}</button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* 【第71天新增 / 面诊队列整合】🩺 诊室队列：把原「🩺 面诊队列」+「🔍 搜索学生」+「👤 当前就诊学生」三张卡片合并成一张大卡片，
            内部分三部分（① 队列双列 ② 搜索 + 临时加插 ③ 当前就诊学生），部分之间用虚线分隔。
            数据全部复用现有 state（appointments / teacherPatients / selectedPatient / clinicQueue），不新增接口、不改后端。 */}
        {isTeacherRole && teacherTab === 'clinic' && (
          <div style={{ ...boxStyle, background: '#f7fcf9', width: '100%' }}>
            <div style={{ fontSize: '20px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '6px', paddingBottom: '12px', borderBottom: '2px solid #d8e8d8' }}>🩺 诊室队列</div>
            <div style={{ fontSize: '12px', color: '#999', marginTop: '10px', marginBottom: '16px' }}>
              队列双列（📅 预约面诊 / 💻 远程问诊）｜ 搜索 + 临时加插 ｜ 当前就诊学生
            </div>

            {/* ===== 第一部分：队列双列（左 = 预约面诊，右 = 远程问诊；两列都是“今天及以后 + 已确认 + 日期时间升序”） ===== */}
            <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-start' }}>
              {/* 左列：📅 预约面诊（本次会话的临时加插条目置顶显示） */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: '15px', color: '#8b4513', fontWeight: 'bold', marginBottom: '8px' }}>📅 预约面诊</div>
                <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
                  {tempQueue.length === 0 && clinicInPersonQueue.length === 0 ? (
                    <div style={{ textAlign: 'center', color: '#999', fontSize: '13px', padding: '10px' }}>暂无</div>
                  ) : (
                    <>
                      {tempQueue.map(t => (
                        <div
                          key={`temp-${t.name}`}
                          onClick={() => selectClinicPatient(t.name)}
                          style={{
                            display: 'flex', alignItems: 'center', padding: '10px', marginBottom: '6px',
                            background: selectedPatient === t.name ? '#fdeee8' : '#fff8e7',
                            border: selectedPatient === t.name ? '1px solid #c0392b' : '1px solid #e8d4a8',
                            borderRadius: '8px', cursor: 'pointer', fontSize: '13px'
                          }}
                        >
                          <div style={{ flex: 1, color: '#c0392b', fontWeight: 'bold' }}>【临时】{t.name} · {t.time}</div>
                          <div style={{ color: '#8b4513', fontSize: '12px' }}>➕ 已加插</div>
                        </div>
                      ))}
                      {clinicInPersonQueue.map((a: any) => (
                        <div
                          key={`appt-${a.id}`}
                          onClick={() => selectClinicPatient(a.patient_name)}
                          style={{
                            display: 'flex', alignItems: 'center', padding: '10px', marginBottom: '6px',
                            background: selectedPatient === a.patient_name ? '#e8f4e8' : '#fff',
                            border: selectedPatient === a.patient_name ? '1px solid #5a7d5a' : '1px solid #d4e8d4',
                            borderRadius: '8px', cursor: 'pointer', fontSize: '13px'
                          }}
                        >
                          <div style={{ flex: 1, color: '#8b4513', fontWeight: 'bold' }}>{a.scheduled_date} · {a.scheduled_time}</div>
                          <div style={{ flex: 1, color: '#333' }}>👤 {a.patient_name}</div>
                          <div style={{ color: '#5a7d5a', fontSize: '12px' }}>✅ 已确认</div>
                        </div>
                      ))}
                    </>
                  )}
                </div>
              </div>
              {/* 右列：💻 远程问诊（同上排序，仅取预约原因命中远程关键词的预约） */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: '15px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '8px' }}>💻 远程问诊</div>
                <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
                  {clinicRemoteQueue.length === 0 ? (
                    <div style={{ textAlign: 'center', color: '#999', fontSize: '13px', padding: '10px' }}>暂无</div>
                  ) : (
                    clinicRemoteQueue.map((a: any) => (
                      <div
                        key={`remote-${a.id}`}
                        onClick={() => selectClinicPatient(a.patient_name)}
                        style={{
                          display: 'flex', alignItems: 'center', padding: '10px', marginBottom: '6px',
                          background: selectedPatient === a.patient_name ? '#e8eef4' : '#fff',
                          border: selectedPatient === a.patient_name ? '1px solid #5a7d9a' : '1px solid #d4dde8',
                          borderRadius: '8px', cursor: 'pointer', fontSize: '13px'
                        }}
                      >
                        <div style={{ flex: 1, color: '#8b4513', fontWeight: 'bold' }}>{a.scheduled_date} · {a.scheduled_time}</div>
                        <div style={{ flex: 1, color: '#333' }}>👤 {a.patient_name}</div>
                        <div style={{ color: '#5a7d5a', fontSize: '12px' }}>✅ 已确认</div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
            {/* ===== 第二部分：搜索 + 临时加插（搜索沿用旧「🔍 搜索学生」的前端过滤逻辑；临时加插只写 tempQueue 会话 state） ===== */}
            <div style={{ borderTop: '1px dashed #d4c8a8', margin: '18px 0' }} />
            <div>
              <div style={{ display: 'flex', gap: '10px', alignItems: 'flex-start' }}>
                <div style={{ flex: 1, position: 'relative' }}>
                  <input
                    style={{ ...inputStyle, marginBottom: 0 }}
                    placeholder="输入学生名首字"
                    value={studentSearch}
                    onChange={e => setStudentSearch(e.target.value)}
                  />
                  {studentSearchResults.length > 0 && (
                    <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, background: '#fffdf5', border: '1px solid #d4c8a8', borderRadius: '4px', zIndex: 20, maxHeight: '200px', overflowY: 'auto' }}>
                      {studentSearchResults.map((s: any) => (
                        <div
                          key={s.name}
                          onClick={() => { selectClinicPatient(s.name); setStudentSearch('') }}
                          style={{ padding: '8px', cursor: 'pointer', fontFamily: 'serif', borderBottom: '1px solid #f0e9d6', fontSize: '14px' }}
                        >
                          👤 {s.name}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                <button
                  onClick={() => setShowTempInsertPicker(v => !v)}
                  style={{
                    padding: '8px 16px', borderRadius: '20px', border: '1px solid #8b4513', cursor: 'pointer',
                    fontFamily: 'serif', fontSize: '13px', whiteSpace: 'nowrap',
                    background: showTempInsertPicker ? '#8b4513' : '#fffdf5',
                    color: showTempInsertPicker ? '#fff' : '#8b4513'
                  }}
                >
                  ➕ 临时加插
                </button>
              </div>
              {studentSearch.trim() && studentSearchResults.length === 0 && (
                <div style={{ fontSize: '12px', color: '#999', marginTop: '8px' }}>未找到匹配的学生</div>
              )}
              {showTempInsertPicker && (
                <div style={{ marginTop: '10px', padding: '10px 12px', background: '#fffdf5', border: '1px dashed #d4c8a8', borderRadius: '8px' }}>
                  <div style={{ fontSize: '12px', color: '#999', marginBottom: '8px' }}>
                    从当前学生列表里选一位“今天及以后没有预约”的学生加插（仅本次会话有效，不落库、不调后端）：
                  </div>
                  {tempInsertCandidates.length === 0 ? (
                    <div style={{ fontSize: '12px', color: '#999' }}>暂无没预约的学生</div>
                  ) : (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                      {tempInsertCandidates.map((s: any) => (
                        <button
                          key={s.name}
                          onClick={() => handleTempInsert(s.name)}
                          style={{ padding: '6px 14px', borderRadius: '15px', border: '1px solid #8b4513', cursor: 'pointer', fontFamily: 'serif', fontSize: '13px', background: '#fdfcf0', color: '#8b4513' }}
                        >
                          👤 {s.name}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
              {tempQueue.length > 0 && (
                <div style={{ fontSize: '12px', color: '#c0392b', marginTop: '8px' }}>
                  本次已临时加插：{tempQueue.map(t => t.name).join('、')}（刷新页面后自动清空）
                </div>
              )}
            </div>
            {/* ===== 第三部分：当前就诊学生（沿用旧「👤 当前就诊学生」卡片的展示逻辑，纯展示） ===== */}
            <div style={{ borderTop: '1px dashed #d4c8a8', margin: '18px 0' }} />
            <div style={{ background: '#fffaf0', border: '1px solid #f0e4cc', borderRadius: '10px', padding: '14px' }}>
              <div style={{ fontSize: '17px', color: '#8b4513', fontWeight: 'bold', marginBottom: '8px' }}>👤 当前就诊学生：{selectedPatient}</div>
              <div style={{ fontSize: '14px', color: '#333', lineHeight: '2' }}>
                <div>上次就诊：{lastVisitDate}</div>
                <div>当前状态：{currentStudentInfo ? currentStudentInfo.status_label : '未在您的学生名单中'}</div>
              </div>
            </div>
          </div>
        )}

        {/* 【第82天新增 / 老师端待处理陈述】📝 待处理陈述：位置在「🩺 诊室队列」下方、「🩺 诊室工作台」上方（只在老师端 🩺 诊室页签显示）。
            数据来源：GET /api/complaints?teacher_name=…&status=pending —— 即学生完成「十问歌」面诊前准备后
            由 POST /api/agent/save_intake 写进 complaints 表的记录（status='pending'）。
            每条：学生名 + 提交时间（MM-DD HH:mm）+ 内容摘要（超 80 字截断加 "..."）→「查看详情」展开全文（expandedComplaintIds 控制展开/收起）
            →「已处理」POST /api/complaints/{id}/process，后端改 status 后本地移除该条。
            后端若缺这两个接口：只显示“暂无 + 后端接口待补”灰字提示，不弹窗、不影响诊室的其它功能。 */}
        {isTeacherRole && teacherTab === 'clinic' && (
          <div style={{ ...boxStyle, background: '#fffdf6', width: '100%' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px', paddingBottom: '12px', borderBottom: '2px solid #efe3c8' }}>
              <div style={{ fontSize: '20px', color: '#8b4513', fontWeight: 'bold' }}>📝 待处理陈述（{pendingComplaints.length}）</div>
              <button
                onClick={fetchPendingComplaints}
                disabled={complaintsLoading}
                style={{ padding: '4px 12px', borderRadius: '15px', border: '1px solid #8b4513', background: 'transparent', color: '#8b4513', cursor: complaintsLoading ? 'default' : 'pointer', fontSize: '12px', fontFamily: 'serif', opacity: complaintsLoading ? 0.6 : 1 }}
              >{complaintsLoading ? '刷新中…' : '🔄 刷新'}</button>
            </div>
            <div style={{ fontSize: '12px', color: '#999', marginTop: '10px', marginBottom: '16px' }}>
              来源：学生「十问歌」面诊前准备（POST /api/agent/save_intake 写入 complaints）｜ 接口：{'GET /api/complaints?teacher_name='}{selectedTeacher}{'&status=pending'}
            </div>

            {pendingComplaints.length === 0 ? (
              <div>
                <div style={{ textAlign: 'center', color: '#999', fontSize: '13px', padding: '8px' }}>暂无待处理陈述，学生完成问诊前准备后会显示在这里</div>
                {complaintsMissing && (
                  <div style={{ textAlign: 'center', color: '#c0392b', fontSize: '12px', marginTop: '6px' }}>
                    （后端接口待补：GET /api/complaints；补上后本卡片无需再改代码）
                  </div>
                )}
              </div>
            ) : (
              pendingComplaints.map((c: any, i: number) => {
                const hasId = c && c.id !== undefined && c.id !== null
                const rowKey = String(hasId ? c.id : `idx-${i}`)
                const realId = hasId ? Number(c.id) : null
                const expanded = expandedComplaintIds.includes(rowKey)
                const processing = processingComplaintIds.includes(rowKey)
                return (
                  <div key={rowKey} style={{ padding: '10px', background: '#fff', border: '1px solid #efe3c8', borderRadius: '8px', marginBottom: '8px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                      <div style={{ fontSize: '14px', color: '#8b4513', fontWeight: 'bold' }}>👤 {c && c.patient_name ? c.patient_name : '（未署名）'}</div>
                      <div style={{ fontSize: '11px', color: '#999', whiteSpace: 'nowrap' }}>🕒 {formatAgentTime(c && c.created_at)}</div>
                    </div>
                    {expanded ? (
                      <div style={{ whiteSpace: 'pre-wrap', fontSize: '13px', color: '#333', lineHeight: '1.7', background: '#fffaf0', border: '1px dashed #e6dcc2', borderRadius: '6px', padding: '8px', marginBottom: '8px' }}>{c && c.content ? c.content : '（无内容）'}</div>
                    ) : (
                      <div style={{ fontSize: '13px', color: '#666', lineHeight: '1.6', marginBottom: '8px' }}>{summarizeComplaint(c && c.content)}</div>
                    )}
                    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                      <button
                        onClick={() => toggleComplaintDetail(rowKey)}
                        style={{ padding: '4px 12px', borderRadius: '15px', border: '1px solid #8b4513', background: 'transparent', color: '#8b4513', cursor: 'pointer', fontSize: '12px', fontFamily: 'serif' }}
                      >{expanded ? '收起详情' : '查看详情'}</button>
                      <button
                        onClick={() => { if (realId === null) { alert('这条陈述缺少 id，无法标记已处理（后端接口字段待确认）。'); return } handleProcessComplaint(realId, rowKey) }}
                        disabled={processing}
                        style={{ padding: '4px 12px', borderRadius: '15px', border: 'none', background: processing ? '#d4c8a8' : '#5a7d5a', color: '#fdfcf0', cursor: processing ? 'default' : 'pointer', fontSize: '12px', fontFamily: 'serif' }}
                      >{processing ? '处理中…' : '已处理'}</button>
                    </div>
                  </div>
                )
              })
            )}
          </div>
        )}

        {/* 【第71天整合】原「🔍 搜索学生」与「👤 当前就诊学生」两张卡片已合并进上方「🩺 诊室队列」大卡片的第二 / 第三部分，此处不再单独渲染。 */}

        {/* 【第72天整合】🩺 诊室工作台：原「📸 现场辅助记录」卡片与「📋 诊疗记录区」容器合并为**一张**撑满宽度的大卡片（单一外边框，不再有第二层卡片 / 第二层标题）。
            内部自上而下五个部分，各部分之间只用虚线分隔：
              第一部分：现场辅助记录（原料：🎙️录音 / 打字 / 📷拍照 / 💓把脉 → 全部先写进本区文本框）
              第二部分：📋 病历草案（成品：AI 整理结果覆盖式写入，老师可继续编辑后保存）
              第三部分：🏷️ 病历标签（部位 + 症状）
              第四部分：📝 开方（患者姓名默认当前学生 / 远程诊疗 / 药材 + 克数）
              第五部分：📝 辨证施治方案（+ 预览完整病历）
            所有原有按钮、接口、state 逻辑保持不变，只是重新排列（仅诊室页签显示）。 */}
        {(currentRole === '李老师' || currentRole === '李老师智能体') && teacherTab === 'clinic' && (
          <div style={{ ...boxStyle, background: '#fcfdfa', border: '1px solid #d4c8a8', width: '100%' }}>
            <div style={{ textAlign: 'center', fontSize: '20px', color: '#8b4513', fontWeight: 'bold', marginBottom: '6px', paddingBottom: '12px', borderBottom: '2px solid #e6dcc2' }}>🩺 诊室工作台</div>
            <div style={{ textAlign: 'center', fontSize: '12px', color: '#999', marginBottom: '16px' }}>
              现场辅助记录（原料）→ 病历草案（AI 整理成品）→ 病历标签 → 开方 → 辨证施治方案（五部分共用一个外边框，部分之间虚线分隔）
            </div>

            {/* ===== 第一部分：现场辅助记录（原料区，去掉自己的子卡片边框，直接贴在大卡片里） ===== */}
            <div>
              <div style={{ fontSize: '16px', color: '#8b4513', fontWeight: 'bold', marginBottom: '6px' }}>📸 现场辅助记录（原料：录音 / 打字 / 拍照 / 把脉）</div>
              <div style={{ fontSize: '12px', color: '#999', marginBottom: '12px' }}>
                写入目标：{clinicTargetDraft ? `${clinicTargetDraft.patient_name} 的病历草案` : '（暂无待处理病历草案，请先在“诊室队列”里选一位学生）'}
                <br />
                流程：本区是原料（录音 / 打字 / 拍照 / 把脉）→ 点 🤖 AI整理成病历格式 → 结果【覆盖式】写入下方第二部分「📋 病历草案」
              </div>
              {/* a) 文本输入 / 显示区 */}
              <textarea
                placeholder="点击下方 🎙️ 开始录音口述望闻问切（停止后由智能体清洗再写入这里），或直接打字；拍照、把脉也会先追加到这里..."
                value={clinicTargetId !== null ? (teacherLiveText[clinicTargetId] || '') : ''}
                onChange={e => { if (clinicTargetId !== null) setTeacherLiveText(prev => ({ ...prev, [clinicTargetId]: e.target.value })) }}
                disabled={clinicTargetId === null}
                style={{ width: '100%', minHeight: '110px', padding: '10px', borderRadius: '8px', border: '1px solid #b8d8c0', background: '#fff', fontFamily: 'serif', fontSize: '13px', marginBottom: '10px', boxSizing: 'border-box' }}
              />
              {/* b) 按钮行：🎙️ 录音 | 🤖 AI整理 | 📷 拍照（诊室页签内唯一拍照入口） */}
              <div style={{ display: 'flex', gap: '8px', marginBottom: '10px' }}>
                <button
                  onClick={() => { if (clinicTargetId !== null) startTeacherLiveRecording(clinicTargetId) }}
                  disabled={clinicTargetId === null || !speechSupported}
                  style={{ flex: 1, padding: '8px', borderRadius: '20px', border: 'none', background: (clinicTargetId === null || !speechSupported) ? '#ccc' : (teacherLiveRecording === clinicTargetId ? '#c0392b' : '#8b4513'), color: '#fff', cursor: (clinicTargetId === null || !speechSupported) ? 'not-allowed' : 'pointer', fontSize: '13px' }}
                >
                  {clinicTargetId !== null && teacherLiveCleaning[clinicTargetId]
                    ? '🔄 智能体处理中...'
                    : (clinicTargetId !== null && teacherLiveRecording === clinicTargetId ? '⏹ 停止录音' : '🎙️ 开始录音')}
                </button>
                <button
                  onClick={() => { if (clinicTargetId !== null) handleTeacherStructurize(clinicTargetId) }}
                  disabled={clinicTargetId === null || !!teacherLiveStructurizing[clinicTargetId]}
                  style={{ flex: 1, padding: '8px', borderRadius: '20px', border: '1px solid #5a7d5a', background: 'transparent', color: '#5a7d5a', cursor: clinicTargetId === null ? 'not-allowed' : 'pointer', fontSize: '13px' }}
                >
                  {(clinicTargetId !== null && teacherLiveStructurizing[clinicTargetId]) ? 'AI整理中...' : '🤖 AI整理成病历格式'}
                </button>
                <label style={{ flex: 1, padding: '8px', borderRadius: '20px', border: '1px solid #8b4513', background: 'transparent', color: '#8b4513', cursor: clinicTargetId === null ? 'not-allowed' : 'pointer', fontSize: '13px', textAlign: 'center' }}>
                  {(clinicTargetId !== null && liveUploading[clinicTargetId]) ? '上传中...' : '📷 拍照'}
                  <input
                    ref={clinicPhotoInputRef}
                    type="file"
                    accept="image/*"
                    capture="environment"
                    disabled={clinicTargetId === null}
                    onChange={(e) => { if (clinicTargetId !== null) { handleLivePhotoUpload(clinicTargetId, e) } }}
                    style={{ display: 'none' }}
                  />
                </label>
              </div>

              {!speechSupported && (
                <div style={{ fontSize: '12px', color: '#c0392b', marginBottom: '8px' }}>当前浏览器不支持语音识别，请使用 Chrome 或 Edge</div>
              )}
              {clinicTargetId !== null && teacherLiveRecording === clinicTargetId && (
                <div style={{ fontSize: '12px', color: '#c0392b', marginBottom: '8px' }}>🔴 正在录音，停止后由智能体清洗（去噪 + 提炼 + 结构化）再写入上面的文本框</div>
              )}
              {/* 【第68天新增】清洗进行中的提示：录音已停，正在等 POST /api/agent/clean_transcript 返回 */}
              {clinicTargetId !== null && teacherLiveCleaning[clinicTargetId] && (
                <div style={{ fontSize: '12px', color: '#8b4513', marginBottom: '8px' }}>🔄 智能体处理中...（处理完成后自动写入上面的文本框）</div>
              )}
              {/* c) 把脉记录子区域：脉象 / 脉率 / 备注 → 追加到上方文本框 */}
              <div style={{ marginTop: '12px', padding: '12px', background: '#f7f4fd', borderRadius: '8px', border: '1px dashed #c9bde0' }}>
                <div style={{ fontSize: '14px', color: '#8b4513', fontWeight: 'bold', marginBottom: '10px' }}>💓 把脉记录</div>
                <div style={{ fontSize: '13px', color: '#333', marginBottom: '6px' }}>脉象（可多选）</div>
                <div style={{ marginBottom: '10px' }}>
                  {PULSE_TYPES.map(p => {
                    const active = pulseTypes.includes(p)
                    return (
                      <button
                        key={p}
                        onClick={() => setPulseTypes(prev => prev.includes(p) ? prev.filter(x => x !== p) : [...prev, p])}
                        style={{ padding: '6px 16px', borderRadius: '20px', border: active ? '1px solid #8b4513' : '1px solid #d4c8a8', background: active ? '#8b4513' : '#fff', color: active ? '#fff' : '#8b4513', cursor: 'pointer', fontSize: '14px', fontFamily: 'serif', marginRight: '6px', marginBottom: '6px' }}
                      >
                        {p}
                      </button>
                    )
                  })}
                </div>
                <div style={{ display: 'flex', gap: '12px', marginBottom: '10px' }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: '13px', color: '#333', marginBottom: '6px' }}>脉率（次/分钟）</div>
                    <input type="number" min="0" placeholder="如：78" value={pulseRate} onChange={e => setPulseRate(e.target.value)} style={{ ...inputStyle, marginBottom: 0 }} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: '13px', color: '#333', marginBottom: '6px' }}>备注</div>
                    <input placeholder="如：左关沉细" value={pulseNote} onChange={e => setPulseNote(e.target.value)} style={{ ...inputStyle, marginBottom: 0 }} />
                  </div>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                  <div style={{ fontSize: '12px', color: '#999' }}>
                    预览：{`【把脉记录】脉象：${pulseTypes.length > 0 ? pulseTypes.join('、') : '未填写'}${pulseRate.trim() ? `；脉率：${pulseRate.trim()}次/分` : ''}${pulseNote.trim() ? `；备注：${pulseNote.trim()}` : ''}`}
                  </div>
                  <button onClick={handlePulseRecord} disabled={clinicTargetId === null} style={{ padding: '6px 18px', borderRadius: '20px', border: 'none', background: clinicTargetId === null ? '#ccc' : '#8b4513', color: '#fff', cursor: clinicTargetId === null ? 'not-allowed' : 'pointer', fontSize: '13px', whiteSpace: 'nowrap' }}>把脉记录追加到上方文本框</button>
                </div>
              </div>
              {/* d) 拍照缩略图区（每上传成功一张图片显示一张 80px 小图 + 缩略图下方归类下拉） */}
              {/* 【第73天改动2】uploadedImages 只由「📷 拍照」按钮上传成功时写入 → 本区图片必然都是老师现场拍的，
                  所以标题从“学生上传的图片：”改成“📷 舌苔照 / 患处照”，并在标题下加一行小灰字说明归类规则。 */}
              {uploadedImages.length > 0 && (
                <div style={{ marginTop: '10px', marginBottom: '10px', padding: '10px', background: '#f7fcf9', borderRadius: '8px', border: '1px dashed #b8d8c0' }}>
                  <div style={{ fontSize: '12px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '4px' }}>📷 舌苔照 / 患处照</div>
                  <div style={{ fontSize: '11px', color: '#999', marginBottom: '8px' }}>老师拍照后由智能体判断归类（当前版本暂由老师确认）</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                    {uploadedImages.map((item, i) => (
                      <div key={`${item.url}-${i}`} style={{ position: 'relative', width: '80px' }}>
                        {/* 点缩略图 → 新标签页打开原图 */}
                        <img
                          src={item.url}
                          alt={`现场图片${i + 1}`}
                          onClick={() => window.open(item.url, '_blank')}
                          title="点击在新标签页查看原图"
                          style={{ width: '80px', height: '80px', objectFit: 'cover', borderRadius: '8px', border: '1px solid #b8d8c0', cursor: 'zoom-in', display: 'block' }}
                        />
                        {/* 右上角 ×：只从缩略图列表移除，已追加到文本框的 URL 不受影响 */}
                        <button
                          onClick={() => setUploadedImages(prev => prev.filter((_, idx) => idx !== i))}
                          title="从预览区移除（已追加到文本框的内容不受影响）"
                          style={{ position: 'absolute', top: '-6px', right: '-6px', width: '18px', height: '18px', padding: 0, lineHeight: '16px', borderRadius: '50%', border: '1px solid #fff', background: '#c0392b', color: '#fff', fontSize: '12px', cursor: 'pointer' }}
                        >×</button>
                        {/* 【第73天改动3】缩略图下方归类下拉：舌苔照 / 患处照 / 其他（默认「患处照」，老师可手动切换） */}
                        {renderPhotoCategorySelect(item.url, `live-${i}`)}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {/* e) 追加到病历：把文本框内容写入病历草案（手工打字时的备用通道；AI整理走上面的 🤖 按钮） */}
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '12px' }}>
                <button onClick={() => { if (clinicTargetId !== null) handleAppendTeacherNote(clinicTargetId) }} disabled={clinicTargetId === null} style={{ padding: '8px 24px', borderRadius: '20px', border: 'none', background: clinicTargetId === null ? '#ccc' : '#5a7d5a', color: '#fff', cursor: clinicTargetId === null ? 'not-allowed' : 'pointer', fontSize: '13px', fontWeight: 'bold' }}>追加到病历</button>
              </div>
            </div>

            {/* ===== 分界 1/4（虚线）：第一部分 现场辅助记录（原料）↑ ｜ 第二部分 病历草案（成品）↓ ===== */}
            <div style={{ margin: '20px 0', borderTop: '1px dashed #c9bde0' }} />

            {/* ===== 第二部分：AI 生成的病历草案（AI 整理结果覆盖式写入下方文本框，老师可继续编辑） ===== */}
            {/* 【第70天修复 / 数据串台】只渲染“当前就诊学生”的草案，其他学生的草案不再出现在本屏 */}
            {clinicPatientDrafts.length === 0 && (
              <div style={{ textAlign: 'center', color: '#999', marginBottom: '16px' }}>暂无待处理病历（在“诊室队列”里选一位学生即可开始记录）</div>
            )}

            {/* 第二部分标题：病历草案（成品区，覆盖式写入） */}
            <div style={{ fontSize: '16px', color: '#8b4513', fontWeight: 'bold', marginBottom: '10px' }}>📋 病历草案（AI 整理结果，老师可编辑）</div>
            {clinicPatientDrafts.map(d => (
                <div key={d.id} style={{ paddingBottom: '12px', marginBottom: '12px', borderBottom: '1px dashed #ece3cd' }}>
                  <div style={{ color: '#8b4513', fontWeight: 'bold', marginBottom: '5px' }}>
                    学生：{d.patient_name}
                    {d.id < 0 && <span style={{ marginLeft: '8px', fontSize: '12px', color: '#e67e22', fontWeight: 'normal' }}>🆕 本地新建（点“保存病历修改”落库）</span>}
                  </div>
                  <textarea value={d.content} onChange={(e) => { setClinicDraftById(d.id, item => ({ ...item, content: e.target.value })) }} style={{ width: '100%', height: '180px', padding: '10px', borderRadius: '8px', border: '1px solid #d4c8a8', fontFamily: 'serif', fontSize: '13px', marginBottom: '10px', boxSizing: 'border-box', whiteSpace: 'pre-wrap' }} />
                  <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '10px' }}>
                    <button onClick={() => handleEditDraft(d.id, d.content)} disabled={localDraftSaving && d.id < 0} style={{ padding: '6px 16px', borderRadius: '20px', border: '1px solid #8b4513', background: 'transparent', color: '#8b4513', cursor: 'pointer' }}>{localDraftSaving && d.id < 0 ? '落库中...' : '保存病历修改'}</button>
                  </div>

                  {extractImageUrls(d.content).length > 0 && (
                    <div style={{ marginBottom: '15px', padding: '10px', background: '#f7fcf9', borderRadius: '8px', border: '1px dashed #b8d8c0' }}>
                      {/* 【第73天改动2】标题动态化：本次会话老师现场拍的照片（出现在 uploadedImages 里）不再被误标成
                          “📷 学生上传的图片：”；纯学生端上传时标题保持原样（学生端零改动）。 */}
                      <div style={{ fontSize: '12px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '8px' }}>{imageStripTitle(d.content)}</div>
                      {/* 【第73天改动2】小灰字：仅当本区含老师现场拍的照片时才提示归类规则 */}
                      {extractImageUrls(d.content).some(u => isTeacherLivePhoto(u)) && (
                        <div style={{ fontSize: '11px', color: '#999', marginBottom: '8px' }}>老师拍照后由智能体判断归类（当前版本暂由老师确认）</div>
                      )}
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                        {extractImageUrls(d.content).map((url, i) => (
                          <div key={`${url}-${i}`} style={{ width: '150px' }}>
                            <img src={url} alt={`病历图片${i + 1}`} style={{ maxWidth: '150px', maxHeight: '150px', objectFit: 'cover', borderRadius: '8px', border: '1px solid #b8d8c0', display: 'block' }} />
                            {/* 【第73天改动3】老师现场拍的照片 → 缩略图下方归类下拉（与拍照区共用 uploadedImages 里同一份归类） */}
                            {renderPhotoCategorySelect(url, `draft-${d.id}-${i}`)}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {extractAudioUrls(d.content).length > 0 && (
                    <div style={{ marginBottom: '15px', padding: '10px', background: '#f7fcf9', borderRadius: '8px', border: '1px dashed #b8d8c0' }}>
                      <div style={{ fontSize: '12px', color: '#5a7d5a', fontWeight: 'bold', marginBottom: '8px' }}>🎙️ 学生录音：</div>
                      {extractAudioUrls(d.content).map((url, i) => (
                        <audio key={i} src={url} controls style={{ width: '100%', marginBottom: '5px' }} />
                      ))}
                    </div>
                  )}
                </div>
              ))}

            {/* ===== 分界 2/4（虚线）：第二部分 病历草案 ↑ ｜ 第三部分 病历标签 ↓（原「症状标签」，字段 / 接口不变） ===== */}
            {clinicPatientDrafts.length > 0 && (
              <div style={{ borderTop: '1px dashed #c9bde0', paddingTop: '15px', marginBottom: '16px' }}>
                <div style={{ fontSize: '16px', color: '#8b4513', fontWeight: 'bold', marginBottom: '10px' }}>🏷️ 病历标签（部位 + 症状）</div>
                {clinicPatientDrafts.map(d => (
                  <div key={d.id} style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
                    <span style={{ alignSelf: 'center', minWidth: '60px', fontSize: '13px', fontWeight: 'bold', color: '#8b4513' }}>{d.patient_name}</span>
                    <input placeholder="部位（如：舌苔/皮肤/面色）" value={draftTags[d.id]?.area || ''} onChange={e => setDraftTags(prev => ({ ...prev, [d.id]: { area: e.target.value, symptom: prev[d.id]?.symptom || '' } }))} style={{ flex: 1, padding: '6px', borderRadius: '6px', border: '1px solid #d4c8a8', fontSize: '13px', fontFamily: 'serif' }} />
                    <input placeholder="症状（如：湿/热/虚/瘀）" value={draftTags[d.id]?.symptom || ''} onChange={e => setDraftTags(prev => ({ ...prev, [d.id]: { area: prev[d.id]?.area || '', symptom: e.target.value } }))} style={{ flex: 1, padding: '6px', borderRadius: '6px', border: '1px solid #d4c8a8', fontSize: '13px', fontFamily: 'serif' }} />
                  </div>
                ))}
              </div>
            )}

            {/* ===== 分界 3/4（虚线）：第三部分 病历标签 ↑ ｜ 第四部分 开方 ↓（从“库存”页签移入，字段与接口逻辑保持不变） ===== */}
            <div style={{ borderTop: '1px dashed #c9bde0', paddingTop: '15px', marginBottom: '16px' }}>
              <div style={{ fontSize: '16px', color: '#8b4513', fontWeight: 'bold', marginBottom: '10px' }}>📝 开方</div>
              <input
                style={inputStyle}
                placeholder="患者姓名"
                value={prescriptionPatient}
                onChange={e => setPrescriptionPatient(e.target.value)}
              />
              {/* 【第53天新增】远程诊疗开关：勾选则不扣老师库存 */}
              <label style={{ display: 'flex', alignItems: 'center', fontFamily: 'serif', color: '#5a7d5a', marginBottom: '12px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={prescriptionRemote}
                  onChange={e => setPrescriptionRemote(e.target.checked)}
                  style={{ marginRight: '6px' }}
                />
                远程诊疗（学生自采，不扣库存）
              </label>
              {/* 【第74天新增 / 开方九宫格改造】九宫格选药：顶部搜索框（输入药材名首字）+ 3 列 × N 行格子（超高滚动）。
                  未选中 = 灰白底 + 浅色边框；已选中 = 棕色底（主色 #8b4513）白字。点格子切换选中状态。 */}
              <input
                style={{ ...inputStyle, marginBottom: '8px' }}
                placeholder="输入药材名首字"
                value={herbGridKeyword}
                onChange={e => setHerbGridKeyword(e.target.value)}
              />
              {herbGridList.length === 0 ? (
                <div style={{ fontFamily: 'serif', fontSize: '13px', color: '#999', marginBottom: '12px' }}>
                  {herbs.length === 0 ? '暂时没有药材库存记录，请先到「库存」页添加药材' : '没有匹配的药材，换个首字试试'}
                </div>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px', maxHeight: '240px', overflowY: 'auto', padding: '2px', marginBottom: '12px' }}>
                  {herbGridList.map(h => {
                    const selected = isPrescriptionHerbSelected(h.herb_name)
                    return (
                      <button
                        key={h.id}
                        onClick={() => togglePrescriptionHerb(h)}
                        title={`${h.herb_name} 库存 ${h.stock_amount}${h.unit}`}
                        style={{
                          ...HERB_GRID_CELL_BASE,
                          background: selected ? '#8b4513' : '#f7f5ef',
                          color: selected ? '#fdfcf0' : '#5a4a3a',
                          border: selected ? '1px solid #8b4513' : '1px solid #d4c8a8'
                        }}
                      >
                        <div style={{ fontWeight: 'bold' }}>{h.herb_name}</div>
                        <div style={{ fontSize: '12px', opacity: 0.85 }}>{h.stock_amount}{h.unit}</div>
                      </button>
                    )
                  })}
                </div>
              )}

              {/* 【第74天新增】已选药材列表：药材名 | 克数输入框 | 君臣佐使下拉 | 煎法下拉 | 删除按钮 */}
              {prescriptionItems.length === 0 ? (
                <div style={{ fontFamily: 'serif', fontSize: '13px', color: '#999', marginBottom: '12px' }}>点上面的九宫格选药（可先连点几味，再逐条填分量和标注）</div>
              ) : (
                <div style={{ marginBottom: '8px' }}>
                  {prescriptionItems.map((item, index) => (
                    <div key={item.herb_name} style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '8px' }}>
                      <span style={{ flex: '0 0 72px', fontFamily: 'serif', fontWeight: 'bold', color: '#8b4513' }}>{item.herb_name}</span>
                      <input
                        ref={el => { prescriptionAmountRefs.current[item.herb_name] = el }}
                        style={{ ...inputStyle, marginBottom: 0, flex: '0 0 84px' }}
                        type="number"
                        placeholder="克数"
                        value={item.amount}
                        onChange={e => changePrescriptionItem(index, 'amount', e.target.value)}
                      />
                      {/* 【第54天新增】固定单位标签（暂不支持切换单位） */}
                      <span style={{ color: '#999', fontSize: '13px', fontFamily: 'serif' }}>克</span>
                      {/* 【第74天新增】君臣佐使：君 / 臣 / 佐 / 使 / 未标注（'' 落库为未标注） */}
                      <select
                        style={{ ...inputStyle, marginBottom: 0, flex: '0 0 92px' }}
                        title="君臣佐使"
                        value={item.role}
                        onChange={e => changePrescriptionItem(index, 'role', e.target.value)}
                      >
                        <option value="">{ROLE_UNMARKED_LABEL}</option>
                        {HERB_ROLES.map(role => <option key={role} value={role}>{role}</option>)}
                      </select>
                      {/* 【第74天新增】煎法：常规 / 先煎 / 后下 / 包煎 / 烊化 / 另煎 / 冲服 */}
                      <select
                        style={{ ...inputStyle, marginBottom: 0, flex: '0 0 92px' }}
                        title="煎法"
                        value={COOKING_METHODS.includes(item.cooking_method) ? item.cooking_method : DEFAULT_COOKING_METHOD}
                        onChange={e => changePrescriptionItem(index, 'cooking_method', e.target.value)}
                      >
                        {COOKING_METHODS.map(method => <option key={method} value={method}>{method}</option>)}
                      </select>
                      <button
                        onClick={() => removePrescriptionItem(index)}
                        style={{ flex: '0 0 auto', background: '#d4c8a8', border: 'none', padding: '6px 10px', borderRadius: '4px', cursor: 'pointer', fontFamily: 'serif' }}
                      >删除</button>
                    </div>
                  ))}
                </div>
              )}

              <div style={{ marginTop: '12px' }}>
                {/* 【第74天修改】原有「+ 添加一味药」按钮去掉：选药能力已由上面的九宫格承担 */}
                <button
                  onClick={handleSavePrescription}
                  disabled={savingPrescription}
                  style={{ background: '#8b4513', color: '#fdfcf0', border: 'none', padding: '6px 12px', borderRadius: '4px', cursor: 'pointer', fontFamily: 'serif' }}
                >{savingPrescription ? '保存中...' : '保存药方'}</button>
              </div>
            </div>

            {/* ===== 分界 4/4（虚线）：第四部分 开方 ↑ ｜ 第五部分 辨证施治方案 ↓ ===== */}
            {clinicPatientDrafts.length > 0 && (
              <div style={{ borderTop: '1px dashed #c9bde0', paddingTop: '15px' }}>
                <div style={{ fontSize: '16px', color: '#8b4513', fontWeight: 'bold', marginBottom: '10px' }}>📝 辨证施治方案</div>
                {clinicPatientDrafts.map(d => (
                  <div key={d.id} style={{ marginBottom: '14px' }}>
                    <div style={{ color: '#5a7d5a', fontWeight: 'bold', marginBottom: '8px' }}>📝 给 {d.patient_name} 的辨证施治方案（学生会看到这里的内容）</div>
                    {/* 【第75天新增 / 改动1】施治方案语音输入按钮：点一下开始录音（zh-CN），再点一下停止 → 智能体清洗后追加到下面文本框末尾 */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap', marginBottom: '6px' }}>
                      <button
                        onClick={() => startPlanRecording(d.id)}
                        disabled={!speechSupported}
                        style={{ padding: '6px 16px', borderRadius: '20px', border: 'none', background: !speechSupported ? '#ccc' : (planRecording === d.id ? '#c0392b' : '#8b4513'), color: '#fff', cursor: !speechSupported ? 'not-allowed' : 'pointer', fontSize: '13px', fontFamily: 'serif' }}
                      >
                        {planCleaning[d.id] ? '🔄 智能体处理中...' : (planRecording === d.id ? '⏹ 停止录音' : '🎙️ 语音输入')}
                      </button>
                      {/* 【第75天新增 / 改动2】自动套用模板后的提示（小灰字） */}
                      {planTemplateApplied[d.id] && (
                        <span style={{ fontSize: '11px', color: '#999' }}>已套用模板，可修改</span>
                      )}
                    </div>
                    {!speechSupported && (
                      <div style={{ fontSize: '12px', color: '#c0392b', marginBottom: '6px' }}>当前浏览器不支持语音识别，请使用 Chrome 或 Edge</div>
                    )}
                    {planRecording === d.id && (
                      <div style={{ fontSize: '12px', color: '#c0392b', marginBottom: '6px' }}>🔴 正在录音，停止后由智能体清洗再追加到下面的文本框</div>
                    )}
                    {planCleaning[d.id] && (
                      <div style={{ fontSize: '12px', color: '#8b4513', marginBottom: '6px' }}>🔄 智能体处理中...（处理完成后自动追加到下面的文本框）</div>
                    )}
                    <textarea value={finalPlans[d.id] || ''} onChange={(e) => setFinalPlans({ ...finalPlans, [d.id]: e.target.value })} placeholder="例：抓药xxx，三碗水煲成一碗，饭后服；或今日宜喝姜茶，多休息..." style={{ width: '100%', height: '80px', padding: '10px', borderRadius: '8px', border: '1px solid #b8d8c0', background: '#f7fcf9', fontFamily: 'serif', fontSize: '14px', marginBottom: '10px', boxSizing: 'border-box' }} />
                    <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                      <button onClick={() => handlePreviewFullRecord(d.id)} style={{ padding: '8px 20px', borderRadius: '20px', border: 'none', background: '#5a7d5a', color: '#fff', cursor: 'pointer', fontWeight: 'bold' }}>📄 预览完整病历</button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* 【第69天整合】拍照清晰度不足提示：只提供「重拍 / 继续使用」两个选项（纯前端，无新依赖）
            fixed 定位的模态框，已从「诊室工作台」卡片内部移到卡片之后，行为不变（重拍 → 再次唤起相机 / 继续使用 → 照常上传） */}
        {blurryPhoto && (
          <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999 }}>
            <div style={{ background: '#fdfcf0', padding: '24px', borderRadius: '12px', maxWidth: '400px', width: '90%', border: '2px solid #8b4513' }}>
              <div style={{ fontSize: '18px', color: '#8b4513', fontWeight: 'bold', marginBottom: '10px', textAlign: 'center' }}>📷 清晰度提示</div>
              <div style={{ fontSize: '14px', color: '#666', marginBottom: '20px', textAlign: 'center', lineHeight: '1.6' }}>
                图片可能不够清晰，建议重拍。是否仍要使用？
              </div>
              <div style={{ display: 'flex', gap: '10px' }}>
                <button onClick={handleRetakePhoto} style={{ flex: 1, padding: '10px', borderRadius: '20px', border: '1px solid #8b4513', background: 'transparent', color: '#8b4513', cursor: 'pointer' }}>重拍</button>
                <button onClick={handleUseBlurryPhoto} style={{ flex: 1, padding: '10px', borderRadius: '20px', border: 'none', background: '#5a7d5a', color: '#fff', cursor: 'pointer' }}>继续使用</button>
              </div>
            </div>
          </div>
        )}

        {(currentRole === '学生' || currentRole === '学生智能体') && (
          <div style={{ ...boxStyle, background: '#f7fcf9' }}>
            <div style={{ textAlign: 'center', fontSize: '18px', color: '#5a7d5a', marginBottom: '15px' }}>💬 {selectedTeacher}的回应</div>
            <div style={{ textAlign: 'center', fontSize: '13px', color: '#999', fontStyle: 'italic', lineHeight: '1.8', marginBottom: '15px' }}>
              您的病历数据归您所有，由老师签字确认。<br />
              如有疑问，请在下一次问诊时向老师咨询。
            </div>
            {patientRecords.length > 0 ? (
              <div style={{ padding: '15px', border: '1px solid #b8d8c0', borderRadius: '8px', background: '#fff' }}>
                <div style={{ color: '#5a7d5a', fontWeight: 'bold', marginBottom: '8px' }}>📌 最近一次回复</div>
                <div style={{ whiteSpace: 'pre-wrap', fontSize: '14px', color: '#333', lineHeight: '1.6' }}>{patientRecords[0].final_plan}</div>
              </div>
            ) : (
              <div style={{ textAlign: 'center', color: '#999', padding: '20px' }}>暂无回复，等待老师签字确认。</div>
            )}
          </div>
        )}

        {/* 【第63天调整】🧑‍⚕️ 角色切换卡片（调试模块）：从页面顶部附近迁至整页最底部（位于所有页签内容的最下方，不显眼） */}
        <div style={boxStyle}>
          <div style={{ textAlign: 'center', marginBottom: '15px', color: '#8b4513', fontWeight: 'bold' }}>🧑‍⚕️ 角色切换</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center' }}>
            {['李老师', '李老师智能体', '学生', '学生智能体'].map((role) => (
              <button key={role} style={roleBtnStyle(role)} onClick={() => setCurrentRole(role)}>{role}</button>
            ))}
          </div>
        </div>

      </div>
    </div>
  )
}