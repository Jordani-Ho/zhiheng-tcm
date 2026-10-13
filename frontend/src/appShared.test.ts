import { describe, it, expect, beforeEach } from 'vitest'
import {
  roleIsStudent,
  roleIsTeacher,
  ROLE_OPTIONS,
  formatAgentTime,
  summarizeComplaint,
  COMPLAINT_SUMMARY_LIMIT,
  loadIntakeSession,
  saveIntakeSession,
  clearIntakeSession,
  loadLineageView,
  saveLineageView,
  LINEAGE_ALL_VIEW,
  intakeSessionKey,
} from './appShared'

/**
 * 【D-065 前端测试框架第一批】纯逻辑守护。
 *
 * 存在理由（D-059 / D-060）：
 *   · `roleIsTeacher` 是「去掉单用户锁」的核心判据 —— 全仓 23 处依赖它；
 *   · 它曾有过一次**回归**：`currentRole.includes('老师')` 的写法在新角色名
 *     （「王医生」等不含「老师」二字）下判错，把老师端身份判成学生（D-062 修复）。
 *     本文件把这个判据钉死，防止再犯。
 */

describe('角色判定（D-059 核心判据）', () => {
  it('学生端两种角色 -> 学生', () => {
    expect(roleIsStudent('学生')).toBe(true)
    expect(roleIsStudent('学生智能体')).toBe(true)
    expect(roleIsTeacher('学生')).toBe(false)
    expect(roleIsTeacher('学生智能体')).toBe(false)
  })

  it('**任意姓名**的老师角色 -> 老师端（不依赖姓名里有没有「老师」二字）', () => {
    // 这正是 D-062 修掉的那类 bug：旧写法 currentRole.includes('老师') 在下面这些名字上全部判错
    for (const name of ['王医生', '李医生', '张三丰', 'Dr.Wang', '内测医生甲']) {
      expect(roleIsTeacher(name)).toBe(true)
      expect(roleIsStudent(name)).toBe(false)
      expect(roleIsTeacher(`${name}智能体`)).toBe(true)
    }
  })

  it('原硬编码姓名「李老师」仍判为老师端（向后兼容演示数据）', () => {
    expect(roleIsTeacher('李老师')).toBe(true)
    expect(roleIsTeacher('李老师智能体')).toBe(true)
  })

  it('学生 / 老师两组**互斥且穷尽**（任一角色必落一组）', () => {
    const roles = [...ROLE_OPTIONS, '王医生', '王医生智能体', '某某', '某某智能体']
    for (const r of roles) {
      expect(roleIsStudent(r) !== roleIsTeacher(r)).toBe(true)
    }
  })
})

describe('formatAgentTime（智能体工作台时间显示）', () => {
  it('ISO 串 -> 「MM-DD HH:mm」', () => {
    expect(formatAgentTime('2026-09-24T10:30:00.123456')).toBe('09-24 10:30')
  })
  it('空值 -> 「—」', () => {
    expect(formatAgentTime(null)).toBe('—')
    expect(formatAgentTime(undefined)).toBe('—')
    expect(formatAgentTime('')).toBe('—')
  })
  it('长度不足的异常串 -> 原样返回（绝不抛错，否则卡片渲染崩）', () => {
    expect(formatAgentTime('2026-09')).toBe('2026-09')
    expect(formatAgentTime('abc')).toBe('abc')
  })
})

describe('summarizeComplaint（待处理陈述摘要）', () => {
  it('折叠换行与连续空白', () => {
    expect(summarizeComplaint('头痛\n\n  三天   怕冷')).toBe('头痛 三天 怕冷')
  })
  it('超长截断到上限 + 省略号', () => {
    const long = '症'.repeat(COMPLAINT_SUMMARY_LIMIT + 20)
    const out = summarizeComplaint(long)
    expect(out.length).toBe(COMPLAINT_SUMMARY_LIMIT + 3)
    expect(out.endsWith('...')).toBe(true)
  })
  it('空内容 -> 中性占位（避免卡片空白块）', () => {
    expect(summarizeComplaint('')).toBe('（无内容）')
    expect(summarizeComplaint(null)).toBe('（无内容）')
    expect(summarizeComplaint('   \n  ')).toBe('（无内容）')
  })
})

describe('localStorage 读写（问答会话 / 师门视图）', () => {
  beforeEach(() => { localStorage.clear() })

  it('问答会话：存 -> 取 -> 清', () => {
    const now = new Date().toISOString()
    saveIntakeSession('学生甲', '王医生', {
      currentQuestion: 'q', answers: '问：头痛吗\n答：痛', questionIndex: 1, updatedAt: now,
    })
    const got = loadIntakeSession('学生甲', '王医生')
    expect(got).not.toBeNull()
    expect(got!.questionIndex).toBe(1)
    expect(got!.answers).toContain('答：痛')

    clearIntakeSession('学生甲', '王医生')
    expect(loadIntakeSession('学生甲', '王医生')).toBeNull()
  })

  it('会话拒绝规则①：一条答案都没有 -> null 且清掉脏数据', () => {
    saveIntakeSession('学生甲', '王医生', {
      currentQuestion: 'q', answers: '', questionIndex: 0, updatedAt: new Date().toISOString(),
    } as never)
    expect(loadIntakeSession('学生甲', '王医生')).toBeNull()
    expect(localStorage.getItem(intakeSessionKey('学生甲', '王医生'))).toBeNull()
  })

  it('会话拒绝规则②：超过 24 小时 -> null 且清掉脏数据', () => {
    const stale = new Date(Date.now() - (24 * 60 * 60 * 1000) - 60_000).toISOString()
    saveIntakeSession('学生甲', '王医生', {
      currentQuestion: 'q', answers: '问：a\n答：b', questionIndex: 1, updatedAt: stale,
    })
    expect(loadIntakeSession('学生甲', '王医生')).toBeNull()
    expect(localStorage.getItem(intakeSessionKey('学生甲', '王医生'))).toBeNull()
  })

  it('会话拒绝规则③：updatedAt 缺失/不可解析 -> null（不得当成「未过期」）', () => {
    saveIntakeSession('学生甲', '王医生', {
      currentQuestion: 'q', answers: '问：a\n答：b', questionIndex: 1, updatedAt: '不是时间',
    } as never)
    expect(loadIntakeSession('学生甲', '王医生')).toBeNull()
  })

  it('恰好未过期（23h）-> 仍可读到', () => {
    const fresh = new Date(Date.now() - 23 * 60 * 60 * 1000).toISOString()
    saveIntakeSession('学生甲', '王医生', {
      currentQuestion: 'q', answers: '问：a\n答：b', questionIndex: 2, updatedAt: fresh,
    })
    expect(loadIntakeSession('学生甲', '王医生')?.questionIndex).toBe(2)
  })

  it('问答会话按「学生+老师」隔离（不同老师不串）', () => {
    saveIntakeSession('学生甲', '王医生', {
      currentQuestion: 'q1', answers: '问：a\n答：b', questionIndex: 1, updatedAt: new Date().toISOString(),
    })
    expect(loadIntakeSession('学生甲', '李医生')).toBeNull()
  })

  it('损坏的 JSON -> 返回 null，不抛错（防白屏）', () => {
    localStorage.setItem(intakeSessionKey('学生甲', '王医生'), '{不是合法JSON')
    expect(() => loadIntakeSession('学生甲', '王医生')).not.toThrow()
    expect(loadIntakeSession('学生甲', '王医生')).toBeNull()
  })

  it('师门视图：存 -> 取；含「全部师门」特殊值', () => {
    saveLineageView('学生甲', 'lin-abc')
    expect(loadLineageView('学生甲')).toBe('lin-abc')

    saveLineageView('学生甲', LINEAGE_ALL_VIEW)
    expect(loadLineageView('学生甲')).toBe(LINEAGE_ALL_VIEW)
  })

  it('师门视图按学生隔离', () => {
    saveLineageView('学生甲', 'lin-abc')
    expect(loadLineageView('学生乙')).toBe('')
  })
})
