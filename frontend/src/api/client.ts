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

export async function api<T = any>(url: string, opts?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {}
  // FormData 时让浏览器自动设置 Content-Type（含 boundary），不手动覆盖
  if (!(opts?.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }
  // 合并调用方传入的 headers（如需覆盖）
  if (opts?.headers) Object.assign(headers, opts.headers)
  const r = await fetch(url, { ...opts, headers })
  return (await r.json()) as T
}
