/**
 * 统一 API 封装（从 config_ui.html L1262-1265 迁移）。
 *
 * 后端统一信封：{ ok: boolean, data?, error?, path? }。
 * 错误时 HTTP 非 200 + { ok:false, error }；成功 { ok:true, ... }。
 *
 * 保持与旧 api() 一致的行为：返回整个 body（不抛错），调用方自行检查 r.ok。
 * 这样迁移时业务函数几乎不用改判断逻辑。
 */

const SERVER_URL_KEY = 'agentbuddy-server-url'
const DEFAULT_SERVER_URL = 'http://123.60.75.27:5001'
const TOKEN_KEY = 'agentbuddy-token'

/** 获取远程 server 地址（marketplace + AI 生成服务） */
export function getServerUrl(): string {
  return localStorage.getItem(SERVER_URL_KEY) || DEFAULT_SERVER_URL
}

/** 设置远程 server 地址 */
export function setServerUrl(url: string): void {
  if (url) {
    localStorage.setItem(SERVER_URL_KEY, url)
  } else {
    localStorage.removeItem(SERVER_URL_KEY)
  }
}

/** 拼接远程 server API 地址（无 server URL 时返回空字符串） */
export function serverApi(path: string): string {
  const base = getServerUrl()
  if (!base) return ''
  return base.replace(/\/+$/, '') + path
}

/** 获取登录 token */
export function getAuthToken(): string | null {
  const stored = localStorage.getItem(TOKEN_KEY)
  if (stored) {
    try {
      return JSON.parse(stored).token || null
    } catch {
      return null
    }
  }
  return null
}

export async function api<T = any>(url: string, opts?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {}
  // FormData 时让浏览器自动设置 Content-Type（含 boundary），不手动覆盖
  if (!(opts?.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }
  // 添加登录 token
  const token = getAuthToken()
  if (token) {
    headers['Authorization'] = 'Bearer ' + token
  }
  // 合并调用方传入的 headers（如需覆盖）
  if (opts?.headers) Object.assign(headers, opts.headers)
  const r = await fetch(url, { ...opts, headers })
  const text = await r.text()
  try {
    return JSON.parse(text) as T
  } catch {
    // 后端返回非 JSON（如旧后端 404/500 的 HTML 页面）：
    // 返回可读错误而不是抛浏览器原生报错（Safari: The string did not match the expected pattern）
    const hint = r.status === 404
      ? `接口不存在 (HTTP 404)，运行中的后端可能是旧版本，请重启应用`
      : `后端返回非 JSON 响应 (HTTP ${r.status})`
    return { ok: false, error: hint, status: r.status, body: text.slice(0, 200) } as any
  }
}

/** LLM 配置 API 封装（读取/保存 llm.yaml） */
export const llmApi = {
  fetch: () => api('/api/llm'),
  save: (data: unknown) =>
    api('/api/llm', { method: 'POST', body: JSON.stringify({ data }) }),
}
