/**
 * vitest 全局启动（D-065）。
 *
 * 唯一职责：告诉 React「当前是 act 环境」。
 * React 19 在没有这个标志时，任何 `act(...)` 内的状态更新都会打印
 * 「The current testing environment is not configured to support act(...)」,
 * 而组件测试会断言 `console.error` 未被调用（用来发现真实渲染错误）——标志设错会导致误报。
 */
declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean
}

globalThis.IS_REACT_ACT_ENVIRONMENT = true

export {}
