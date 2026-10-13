/**
 * 【D-069】身份引导（identity bootstrap）—— 从后端数据解析「当前是谁」。
 *
 * 为什么把这段从 App.tsx 抽出来：
 *   · 它是**决定「我是谁」的运行时逻辑**（D-059 去掉单例锁的核心），此前**零测试覆盖**；
 *   · 它原本嵌在约 4600 行的 `App()` 里，既拆不出也测不了 —— 抽成纯函数后可用 vitest 覆盖；
 *   · 顺带减少 `App()` 体积（呼应「拆出 App.tsx」的目标）。
 *
 * 解析口径（与抽取前的 App.tsx 行为**逐字保持一致**）：
 *   1. 先问「该学生归属哪些老师」（`GET /api/patient-teachers?patient_name=`，学生端最准）；
 *      有结果 → 用它；空 / 失败 → 退回 `GET /api/teachers`（老师列表）。
 *   2. 老师取**第一个**（若调用方已选定老师则沿用调用方的）。
 *   3. 学生取该老师名下第一个（`GET /api/teacher-patients?teacher_name=`）；
 *      调用方已有学生则不动。
 *   4. 全程**不抛错**：任何一步失败都退化为「保持原值」，绝不让首屏白屏。
 *
 * 依赖注入：`fetchImpl` 默认用全局 fetch；测试传桩即可，无需联网。
 */

export type IdentityBootstrapResult = {
  /** 解析出的老师名（空串 = 没解析出来） */
  teacherName: string
  /** 解析出的学生名（空串 = 没解析出来） */
  patientName: string
  /** `GET /api/teachers` 的原始列表（仅当走老师列表分支时非空），供 UI 渲染老师选择器 */
  teachers: Array<{ name: string; description?: string }>
  /** 来源：学生归属 / 老师列表 / 都没有 */
  source: 'patient-teachers' | 'teachers' | 'none'
  /** 是否发生了兜底（学生归属为空 -> 退回老师列表） */
  fellBackToTeachers: boolean
}

type FetchImpl = (input: string) => Promise<Response>

const EMPTY: IdentityBootstrapResult = {
  teacherName: '', patientName: '', teachers: [], source: 'none', fellBackToTeachers: false,
}

/** 安全取 JSON：非 2xx 或解析失败都返回 null，绝不抛错 */
async function safeJson(res: Response): Promise<unknown> {
  try {
    if (!res || !res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}

/**
 * 解析身份。**永不抛错**——失败一律退化为保持调用方原值。
 *
 * @param currentTeacher 调用方当前已选定的老师（非空则沿用，不再问老师列表）
 * @param currentPatient 调用方当前已选定的学生（非空则沿用）
 * @param fetchImpl      注入的 fetch（测试用桩）
 */
export async function bootstrapIdentity(
  currentTeacher: string,
  currentPatient: string,
  fetchImpl?: FetchImpl,
): Promise<IdentityBootstrapResult> {
  const doFetch: FetchImpl = fetchImpl
    || ((input: string) => fetch(input) as unknown as Promise<Response>)

  let teachers: IdentityBootstrapResult['teachers'] = []
  let source: IdentityBootstrapResult['source'] = 'none'
  let fellBackToTeachers = false
  let teacherName = ''

  // ---- 步骤 1：老师来源（学生归属优先，退回老师列表）----
  try {
    const listRaw = await safeJson(
      await doFetch(`/api/patient-teachers?patient_name=${encodeURIComponent(currentPatient || '')}`),
    )
    const list: string[] = Array.isArray(listRaw)
      ? listRaw.map((x: unknown) => (typeof x === 'string' ? x : String((x as { name?: unknown })?.name ?? '')))
      : []

    if (list.length > 0) {
      source = 'patient-teachers'
      teacherName = currentTeacher || list[0] || ''
    } else {
      // 空 → 退回老师列表
      fellBackToTeachers = true
      const raw = await safeJson(await doFetch('/api/teachers'))
      if (Array.isArray(raw)) {
        teachers = raw as IdentityBootstrapResult['teachers']
        source = 'teachers'
        teacherName = currentTeacher || teachers[0]?.name || ''
      }
    }
  } catch {
    // 保持 EMPTY 语义
  }

  // ---- 步骤 2：学生来源（该老师名下第一个；调用方已有学生则不动）----
  let patientName = currentPatient || ''
  if (teacherName && !patientName) {
    try {
      const psRaw = await safeJson(
        await doFetch(`/api/teacher-patients?teacher_name=${encodeURIComponent(teacherName)}`),
      )
      if (Array.isArray(psRaw) && psRaw.length > 0) {
        const first = (psRaw[0] as { name?: unknown })?.name
        if (first) patientName = String(first)
      }
    } catch { /* 取不到就保持空 */ }
  }

  if (!teacherName && !patientName) {
    return { ...EMPTY, teachers, source, fellBackToTeachers }
  }
  return { teacherName, patientName, teachers, source, fellBackToTeachers }
}
