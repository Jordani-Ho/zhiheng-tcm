import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// 【D-065 前端测试框架】
// 背景：此前前端**零测试框架、无 jsdom、无浏览器面板** → 任何前端改动的验证上限只有
// `tsc` + `vite build` + 模块加载，**证明不了「页面上点一下真的对」**（D-060）。
// 本文件为 vitest 配置；`npm test` 即可跑 `src/**/*.test.ts(x)`。
//
// 与 `vite.config.ts` 的关系：本文件是**测试专用**配置（含 vite 的 plugins 与 resolve），
// 生产构建仍走 `vite.config.ts`，两者互不影响。
export default defineConfig({
  plugins: [react()],
  test: {
    // jsdom：让 React 组件能在真实 DOM 语义下渲染（不是字符串比对）
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.test.{ts,tsx}'],
    // 不跑 e2e / 不联网：全部用例须自带 fetch 桩
    restoreMocks: true,
    // 【React 19 必需】告诉 React「当前是 act 环境」，否则每次状态更新都会打印
    // "The current testing environment is not configured to support act(...)"。
    // 测试用例会断言 console.error 未被调用（防渲染错误），故该标志必须设对。
    setupFiles: ['./src/test-setup.ts'],
  },
})
