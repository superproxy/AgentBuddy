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

/** agentctl / Flask 行可能带 ANSI；纯 [DONE] 或 [DONE] Synced… 均表示流结束 */
function isStreamDoneLine(data: string): boolean {
  const plain = data.replace(/\u001b\[[\d;]*m/g, '').trim()
  return plain === '[DONE]' || plain.startsWith('[DONE]')
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
    let finished = false
    const finish = (errored: boolean) => {
      if (finished) return
      finished = true
      evt.close()
      if (errored) {
        onLine('[连接中断]')
        opts?.onError?.()
      } else {
        opts?.onDone?.()
      }
      resolve()
    }
    evt.onmessage = (e: MessageEvent) => {
      onLine(e.data)
      if (isStreamDoneLine(e.data)) {
        finish(false)
      }
    }
    evt.onerror = () => {
      // 正常结束时常会先收到 [DONE] 再触发 onerror，不能误判为失败
      finish(!finished)
    }
  })
}
