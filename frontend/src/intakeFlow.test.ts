import { describe, it, expect } from 'vitest'
import {
  mergeIntakeQA,
  countIntakeRounds,
  decideIntakeRoundOutcome,
  buildIntakeSessionPersist,
  planIntakeStart,
} from './intakeFlow'
import { INTAKE_QA_SEP, MAX_INTAKE_ROUNDS } from './appShared'

/**
 * 【D-071】面诊前准备（十问歌）纯逻辑守护。
 *
 * 最高危的一条：**问答串格式是前后端契约** —— 后端 `agent.py:470` 用
 * `answers_text.count("答：")` 判断已答轮次（LLM 失败时的兜底也靠它算轮次），
 * 前端只在 `mergeIntakeQA` 一处拼串。格式错一位 → 轮次判断整体错位。
 * 本文件的 `countIntakeRounds` 用例即与后端口径对齐的**跨端契约钉**。
 */

describe('mergeIntakeQA（问答串拼接 —— 前后端契约）', () => {
  it('第一轮：不加前置分隔符，格式为「问：…⏎答：…」', () => {
    expect(mergeIntakeQA('', '哪里不舒服？', '头痛')).toBe(`问：哪里不舒服？${INTAKE_QA_SEP}答：头痛`)
  })

  it('多轮：前置已有内容时先补分隔符，保持每问一行', () => {
    const r1 = mergeIntakeQA('', 'Q1', 'A1')
    const r2 = mergeIntakeQA(r1, 'Q2', 'A2')
    expect(r2).toBe(`问：Q1${INTAKE_QA_SEP}答：A1${INTAKE_QA_SEP}问：Q2${INTAKE_QA_SEP}答：A2`)
  })

  it('**与后端口径一致**：拼接后的「答：」条数 == 已答轮数', () => {
    let s = ''
    for (let i = 1; i <= 5; i++) {
      s = mergeIntakeQA(s, `问${i}`, `答内容${i}`)
      expect(countIntakeRounds(s)).toBe(i)          // 后端 answers_text.count("答：") 同值
    }
  })

  it('答案里若含「答：」二字，会被后端一并计入 —— 这是既有口径，不得擅自"修"（钉住现状）', () => {
    const s = mergeIntakeQA('', 'Q', '我回答：是的')
    expect(countIntakeRounds(s)).toBe(2)            // 「答：」在答案正文里也计数
  })
})

describe('countIntakeRounds（轮次计数，对齐 agent.py:470）', () => {
  it('空串 -> 0', () => {
    expect(countIntakeRounds('')).toBe(0)
    expect(countIntakeRounds(null as unknown as string)).toBe(0)
  })
  it('只数「答：」，不数「问：」', () => {
    expect(countIntakeRounds('问：a\n问：b')).toBe(0)
    expect(countIntakeRounds('问：a\n答：b')).toBe(1)
  })
})

describe('decideIntakeRoundOutcome（轮数上限兜底）', () => {
  it('未到上限 -> 不封顶，继续问', () => {
    expect(decideIntakeRoundOutcome(0)).toEqual({ nextRounds: 1, capped: false })
    expect(decideIntakeRoundOutcome(9)).toEqual({ nextRounds: 10, capped: false })
  })

  it('**恰好到上限 -> 封顶**（`>=` 而非 `>`；学生不得被卡住）', () => {
    expect(decideIntakeRoundOutcome(MAX_INTAKE_ROUNDS - 1)).toEqual({ nextRounds: MAX_INTAKE_ROUNDS, capped: true })
  })

  it('超过上限 -> 仍封顶（幂等，不越拉越长）', () => {
    expect(decideIntakeRoundOutcome(MAX_INTAKE_ROUNDS + 5).capped).toBe(true)
  })

  it('前端上限比后端十问歌条数大（兜底而非主控）', () => {
    // 后端 TEN_QUESTIONS = 10，前端 MAX_INTAKE_ROUNDS = 12：正常情况下后端先 done，
    // 前端这只是防「LLM 绕圈」的兜底。若两者关系反转，说明口径被改坏了。
    expect(MAX_INTAKE_ROUNDS).toBeGreaterThan(10)
  })
})

describe('buildIntakeSessionPersist（会话持久化条件）', () => {
  it('已答内容为空 -> **不写**（避免把空会话存成"进行中"）', () => {
    expect(buildIntakeSessionPersist('', 'Q', 0)).toBeNull()
    expect(buildIntakeSessionPersist('   \n  ', 'Q', 0)).toBeNull()
  })

  it('拿到下一问 -> 写下一问 + 已答内容 + 轮数', () => {
    const s = buildIntakeSessionPersist('问：a\n答：b', 'Q2', 1, 'T')
    expect(s).toEqual({ currentQuestion: 'Q2', answers: '问：a\n答：b', questionIndex: 1, updatedAt: 'T' })
  })

  it('已问全（下一问为空串）-> 仍写，currentQuestion 为空（下次进来回「发送确认」可补发）', () => {
    const s = buildIntakeSessionPersist('问：a\n答：b', '', 1, 'T')
    expect(s).not.toBeNull()
    expect(s!.currentQuestion).toBe('')
  })
})

describe('planIntakeStart（打开卡片时从哪开始）', () => {
  it('无会话 -> fresh（从第一问开始，current_answers 传空串）', () => {
    expect(planIntakeStart(null)).toEqual({ mode: 'fresh' })
  })

  it('有会话且停在某一问 -> resume（接着问）', () => {
    const plan = planIntakeStart({ currentQuestion: 'Q3', answers: '问：a\n答：b', questionIndex: 1, updatedAt: 'T' })
    expect(plan).toEqual({ mode: 'resume', question: 'Q3', answers: '问：a\n答：b', rounds: 1 })
  })

  it('有会话但上次已问全 -> finalize（带着完整回答再问一次拿 done）', () => {
    const plan = planIntakeStart({ currentQuestion: '', answers: '问：a\n答：b', questionIndex: 1, updatedAt: 'T' })
    expect(plan).toEqual({ mode: 'finalize', answers: '问：a\n答：b', rounds: 1 })
  })
})
