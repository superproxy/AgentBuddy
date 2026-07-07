/**
 * 统一 API 封装（从 config_ui.html L1262-1265 迁移）。
 *
 * 后端统一信封：{ ok: boolean, data?, error?, path? }。
 * 错误时 HTTP 非 200 + { ok:false, error }；成功 { ok:true, ... }。
 *
 * 保持与旧 api() 一致的行为：返回整个 body（不抛错），调用方自行检查 r.ok。
 * 这样迁移时业务函数几乎不用改判断逻辑。
 */
export async function api<T = any>(url: string, opts?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  // 合并调用方传入的 headers（如需覆盖）
  if (opts?.headers) Object.assign(headers, opts.headers)
  const r = await fetch(url, { ...opts, headers })
  return (await r.json()) as T
}
