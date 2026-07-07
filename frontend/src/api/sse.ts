/**
 * SSE 封装（从 config_ui.html L1277-1287 迁移）。
 *
 * 后端 SSE 协议：
 *   data: <一行内容>\n\n
 *   data: [DONE]\n\n   ← 流结束标记
 *
 * EventSource 限制：只支持 GET、不能带 body、不能自定义 header，
 * 所以所有 SSE 端点都是 GET + query 参数。
 *
 * 特殊前缀（e.data 开头）：[CMD] [EXIT] [TIMEOUT] [ERROR] [DONE]
 * [PLUGIN] [STEP] [OK] [FAIL] [!] [-] [i/N] [WARN]
 */

export interface SseOptions {
  onDone?: () => void
  onError?: () => void
}

/**
 * 运行 SSE：逐行回调，遇 [DONE] 收尾。
 * 返回 Promise，流结束（[DONE] 或 error）时 resolve。
 */
export function runSse(
  url: string,
  onLine: (data: string) => void,
  opts?: SseOptions,
): Promise<void> {
  return new Promise((resolve) => {
    const evt = new EventSource(url)
    evt.onmessage = (e: MessageEvent) => {
      onLine(e.data)
      if (e.data.startsWith('[DONE]')) {
        evt.close()
        opts?.onDone?.()
        resolve()
      }
    }
    evt.onerror = () => {
      onLine('[连接中断]')
      evt.close()
      opts?.onError?.()
      resolve()
    }
  })
}
