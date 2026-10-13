/**
 * 【D-071】面诊前准备（十问歌）流程的纯逻辑 —— 从 App.tsx 抽出的可测部分。
 *
 * 为什么值得抽：这段逻辑有三处**高危、但此前零测试**的特性：
 *   ① **问答串格式是前后端契约**：后端按 `答：` 的条数判断学生已答几轮
 *      （LLM 失败时的兜底也靠它算），格式错一位 → 轮次判断整体错位；
 *   ② **轮数上限兜底**（`MAX_INTAKE_ROUNDS`）：拉满必须直接进入「发送确认」，
 *      不能让学生被卡住（这是明文的设计要求，不是优化）；
 *   ③ **会话持久化条件**：只有「已答内容非空」才写 localStorage —— 写早了会把
 *      空会话存成"进行中"，写晚了会丢已答内容。
 *
 * 三者都是纯计算，全部可测；抽出来也让 `App()` 减负（呼应「拆出 App.tsx」）。
 */

import { INTAKE_QA_SEP, MAX_INTAKE_ROUNDS, type IntakeSession } from './appShared'

/** 把「当前这一问 + 学生这次的回答」并入累积的问答串。 */
export function mergeIntakeQA(prevAnswers: string, question: string, answer: string): string {
  return (prevAnswers ? prevAnswers + INTAKE_QA_SEP : '')
    + '问：' + question + INTAKE_QA_SEP + '答：' + answer
}

/**
 * 后端算轮次的依据：问答串里 `答：` 出现几次 = 学生答了几轮。
 * 本函数与后端口径**必须一致** —— 被测用例直接钉住这个数字。
 */
export function countIntakeRounds(answers: string): number {
  return (String(answers || '').match(/答：/g) || []).length
}

/**
 * 答完一题之后的**轮数决策**（纯函数）。
 *
 * @returns `capped` = 是否已拉到上限（true → 调用方应直接进「发送确认」并落会话，不再请求下一问）
 */
export function decideIntakeRoundOutcome(
  currentRounds: number,
  maxRounds: number = MAX_INTAKE_ROUNDS,
): { nextRounds: number; capped: boolean } {
  const nextRounds = currentRounds + 1
  return { nextRounds, capped: nextRounds >= maxRounds }
}

/**
 * 会话持久化决策（纯函数）：**什么情况下该写 localStorage，写什么**。
 *
 * 与抽取前 App.tsx 的行为逐字一致：
 *   · 已答内容为空（`answers` 去空白后为空）→ **不写**（避免把空会话存成"进行中"）
 *   · 已问全（`currentQuestion` 为空）→ 写 `currentQuestion: ''`，
 *     下次进来自动回到「发送确认」，可以补发
 *   · 拿到下一问 → 写下一问
 */
export function buildIntakeSessionPersist(
  answers: string,
  currentQuestion: string,
  questionIndex: number,
  now: string = new Date().toISOString(),
): IntakeSession | null {
  if (!String(answers || '').trim()) return null
  return {
    currentQuestion: String(currentQuestion || ''),
    answers,
    questionIndex,
    updatedAt: now,
  }
}

/**
 * 打开「面诊前准备」时，决定**从哪开始**（纯函数）。
 *
 * 三种情况（与抽取前一致）：
 *   · 无有效会话 → `fresh`：从第一问开始（`current_answers` 传空串）
 *   · 有会话且停在某一问 → `resume`：恢复该问接着问
 *   · 有会话但上次已问全（`currentQuestion` 为空）→ `finalize`：带着完整回答再问一次拿 done
 */
export type IntakeStartPlan =
  | { mode: 'fresh' }
  | { mode: 'resume'; question: string; answers: string; rounds: number }
  | { mode: 'finalize'; answers: string; rounds: number }

export function planIntakeStart(session: IntakeSession | null): IntakeStartPlan {
  if (!session) return { mode: 'fresh' }
  if (session.currentQuestion) {
    return { mode: 'resume', question: session.currentQuestion, answers: session.answers, rounds: session.questionIndex }
  }
  return { mode: 'finalize', answers: session.answers, rounds: session.questionIndex }
}
