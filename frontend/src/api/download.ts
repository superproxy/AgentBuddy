/**
 * 文件下载/导出统一封装。
 *
 * pywebview 桌面窗口不处理 Content-Disposition: attachment 下载（`<a download>` + Blob
 * 会被直接打开显示内容），必须走 JS-Python 桥接 `window.pywebview.api.save_file` 弹原生
 * 保存对话框写盘；浏览器环境下回退为 `<a download>` 触发下载。
 *
 * @param url      后端导出接口地址（返回文件内容）
 * @param filename 下载/保存的文件名
 * @returns 是否成功触发保存/下载
 */
export async function downloadFile(url: string, filename: string): Promise<boolean> {
  const pw = (window as any).pywebview
  try {
    const resp = await fetch(url)
    if (!resp.ok) return false
    const blob = await resp.blob()
    if (pw?.api?.save_file) {
      // pywebview 桌面模式：blob → base64 → 桥接原生保存对话框
      const b64 = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => resolve(String(reader.result).split(',')[1])
        reader.onerror = reject
        reader.readAsDataURL(blob)
      })
      const raw = await pw.api.save_file(filename, b64)
      const res = raw?.result ?? raw
      if (res?.ok) return true
      if (res?.error === 'cancelled') return false
      return false
    }
    // 浏览器模式：用 a 标签触发下载
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(a.href)
    return true
  } catch {
    return false
  }
}
