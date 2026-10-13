/**
 * 【D-076】病历草案落库的**兜底决策**与请求体构造 —— 从 App.tsx 抽出的可测部分。
 *
 * 为什么值得抽（这段是「非预约面诊」的关键路径）：
 *   · 老师现场录入、学生没提交线上陈述时，走 `createDraftViaTranscribe` 造一条临时陈述，
 *     再由后端自动生成草案。这是内测**场景 3「非预约面诊」**的兜底。
 *   · 该路径原先**不检查 `/api/transcribe` 的响应**，也不带 `lineage_id`
 *     → flag on 时后端 400 `lineage_required`，而前端继续往下走、最终返回 null，
 *       老师看到的是「落库失败：没能生成病历草案，无法签字」。
 *   · `lineage_required` 的契约是「必须带**非空合法** lineage_id，不许退化为全量」
 *     （见 `lineage_service.lineage_read_scope` 的五条 fail-loud 路径）——
 *     故请求体构造必须显式带上它，不能靠"后端有默认值"。
 */

/** 老师现场录入的占位陈述正文（后端会据此自动生成草案）。 */
export function buildOnsitePlaceholder(patientName: string, now: Date = new Date()): string {
  return `【老师现场录入】\n学生姓名：${patientName}\n就诊时间：`
    + `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日\n`
    + `（本次由老师在诊室直接录入病历，学生未提交线上陈述）`
}

export type TranscribeBody = {
  patient_name: string
  teacher_name: string
  content: string
  data_type: string
  /** flag on 时**必须**为非空合法 id；flag off 时传空串（后端忽略） */
  lineage_id: string
}

/**
 * 构造 `/api/transcribe` 的请求体。
 *
 * ⚠️ `lineage_id` **必须**进 body：`/api/transcribe` 后端按 `lineage_read_scope` 校验，
 * 空 / 缺失 → 400 `lineage_required`，**不会**退化为全量（§5.2「漏改必 4xx」）。
 */
export function buildTranscribeBody(
  patientName: string,
  teacherName: string,
  lineageId: string,
  now: Date = new Date(),
): TranscribeBody {
  return {
    patient_name: patientName,
    teacher_name: teacherName,
    content: buildOnsitePlaceholder(patientName, now),
    data_type: 'text',
    lineage_id: lineageId || '',
  }
}

/**
 * 兜底决策：本地占位草案要落库时，下一步该做什么。
 *
 * 从 `saveLocalDraftToBackend` 的实际分支提取（行为逐字等价）：
 *   ① 该学生有未处理陈述 → 直接对它 `generate-draft`
 *   ② 没有未处理陈述 → 走「老师现场录入」兜底（造陈述 → 让后端生成草案）
 *   ③ 有陈述但已被处理过（`generate-draft` 拿不到 draft_id）→ 同样走兜底
 */
export type DraftFallbackStep =
  | { step: 'generate-from-transcript'; transcriptId: number }
  | { step: 'create-via-transcribe' }

export function decideDraftFallback(latestTranscriptId: number | null | undefined,
                                     generateDraftYieldedId: boolean): DraftFallbackStep {
  if (latestTranscriptId == null) return { step: 'create-via-transcribe' }
  if (!generateDraftYieldedId) return { step: 'create-via-transcribe' }
  return { step: 'generate-from-transcript', transcriptId: latestTranscriptId }
}

/**
 * 判定一次 `/api/transcribe` 兜底是否**真的成功**。
 *
 * 缺陷根因就在这里：原实现 `fetch(...).then(() => findDraftIdByPatient(...))`
 * **完全不看响应**，400 也当成功 → 后续拿到 null，报「落库失败」但**原因说不清**。
 * 现在显式判定，失败时把后端的错误码带出来（便于定位）。
 */
export function evaluateTranscribeResult(
  status: number,
  body: unknown,
): { ok: boolean; errorCode: string; message: string } {
  const detail = (body && typeof body === 'object' ? (body as { detail?: unknown }).detail : undefined) as
    | { error?: string; msg?: string }
    | string
    | undefined

  if (status >= 200 && status < 300) return { ok: true, errorCode: '', message: '' }

  if (detail && typeof detail === 'object') {
    return {
      ok: false,
      errorCode: String(detail.error || `http_${status}`),
      message: String(detail.msg || ''),
    }
  }
  return { ok: false, errorCode: `http_${status}`, message: typeof detail === 'string' ? detail : '' }
}
