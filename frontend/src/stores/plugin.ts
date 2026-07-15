import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import { api } from '../api/client'
import { runSse } from '../api/sse'
import { useUiStore } from './ui'
import { useSyncStore } from './sync'
import { useSkillStore } from './skill'
import { useMarketplaceStore } from './marketplace'

export interface PluginItem {
  file: string
  name: string
  version: string
  description: string
  installed: boolean
  skills_count: number
  mcp_count: number
}

export const usePluginStore = defineStore('plugin', () => {
  const ui = useUiStore()
  const sync = useSyncStore()
  const skill = useSkillStore()
  const marketplace = useMarketplaceStore()
  const plugins = ref<PluginItem[]>([])
  const selectedPluginFile = ref('')
  const installingPlugin = ref('')
  const importPluginInput = ref<HTMLInputElement | null>(null)
  // 导出选中相关
  const selectedForExport = ref<Set<string>>(new Set())

  /**
   * 通用下载：pywebview 下用 JS-Python 桥接弹出原生保存对话框；浏览器回退到 location.href。
   * pywebview 不处理 Content-Disposition: attachment，必须走桥接才能触发下载。
   */
  async function doDownload(url: string, filename: string) {
    const pw = (window as any).pywebview
    if (pw?.api?.save_file) {
      try {
        const r = await fetch(url)
        if (!r.ok) { ui.toast('导出失败: HTTP ' + r.status, 'err'); return }
        const blob = await r.blob()
        const b64 = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader()
          reader.onload = () => resolve((reader.result as string).split(',')[1])
          reader.onerror = reject
          reader.readAsDataURL(blob)
        })
        // pywebview JS bridge 返回值可能是 {result: {...}} 或直接返回 dict
        const raw = await pw.api.save_file(filename, b64)
        const res = raw?.result ?? raw
        if (res?.ok) ui.toast(`已保存到: ${res.path}`)
        else if (res?.error !== 'cancelled') ui.toast('保存失败: ' + (res?.error || JSON.stringify(raw)), 'err')
      } catch (e: any) {
        ui.toast('导出失败: ' + (e?.message || e), 'err')
      }
    } else {
      // 浏览器模式：用 a 标签触发下载（比 location.href 更可靠）
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
    }
  }

  async function refreshPluginList() {
    const r = await api<{ ok: boolean; data?: PluginItem[] }>('/api/plugins')
    if (r.ok) plugins.value = r.data || []
  }
  function exportPlugin(file: string, format: 'zip' | 'yaml' = 'zip') {
    doDownload('/api/plugin/export?file=' + encodeURIComponent(file) + '&format=' + format,
               format === 'zip' ? `${file.replace('.plugin.yaml', '')}.zip` : file)
  }
  function toggleSelectForExport(file: string) {
    const s = new Set(selectedForExport.value)
    if (s.has(file)) s.delete(file)
    else s.add(file)
    selectedForExport.value = s
  }
  function toggleSelectAllForExport() {
    if (selectedForExport.value.size === plugins.value.length) {
      selectedForExport.value = new Set()
    } else {
      selectedForExport.value = new Set(plugins.value.map(p => p.file))
    }
  }
  function selectFilesForExport(files: string[]) {
    selectedForExport.value = new Set(files)
  }
  function clearExportSelection() {
    selectedForExport.value = new Set()
  }
  async function exportSelectedPlugins() {
    const files = Array.from(selectedForExport.value)
    if (!files.length) {
      ui.toast('请先勾选要导出的插件', 'warn')
      return
    }
    const params = files.map(f => 'files=' + encodeURIComponent(f)).join('&')
    await doDownload('/api/plugin/export-selected?' + params, 'plugins-selected.zip')
  }
  function triggerImportPlugin() {
    importPluginInput.value && importPluginInput.value.click()
  }
  async function importPluginFile(f: File) {
    // 统一用 FormData 上传（支持 .zip 含 skills 包 和 .yaml 单文件）
    const fd = new FormData()
    fd.append('file', f)
    const r = await fetch('/api/plugin/import', { method: 'POST', body: fd })
    const res = await r.json() as {
      ok: boolean; name?: string; error?: string; msg?: string
      plugin_count?: number; skill_count?: number; skipped?: any[]
    }
    if (res.ok) {
      const parts: string[] = []
      if (res.plugin_count) parts.push(`${res.plugin_count} 个插件`)
      if (res.skill_count) parts.push(`${res.skill_count} 个技能`)
      const detail = parts.length ? '：' + parts.join('、') : ''
      const skippedNote = res.skipped?.length ? `，跳过 ${res.skipped.length} 项` : ''
      ui.toast('导入成功' + detail + skippedNote)
      refreshPluginList()
      skill.loadInstalledSkills()
    } else if (res.error === 'exists') {
      if (confirm(res.msg || '已存在，是否覆盖？')) {
        const fd2 = new FormData()
        fd2.append('file', f)
        fd2.append('overwrite', 'true')
        const r2 = await fetch('/api/plugin/import', { method: 'POST', body: fd2 })
        const res2 = await r2.json() as { ok: boolean; error?: string; plugin_count?: number; skill_count?: number }
        if (res2.ok) {
          const parts: string[] = []
          if (res2.plugin_count) parts.push(`${res2.plugin_count} 个插件`)
          if (res2.skill_count) parts.push(`${res2.skill_count} 个技能`)
          ui.toast('已覆盖导入' + (parts.length ? '：' + parts.join('、') : ''))
          refreshPluginList()
          skill.loadInstalledSkills()
        } else ui.toast('导入失败: ' + (res2.error || ''), 'err')
      }
    } else ui.toast('导入失败: ' + (res.error || ''), 'err')
  }
  async function onImportPluginFile(e: Event) {
    const input = e.target as HTMLInputElement
    const f = input.files && input.files[0]
    if (!f) return
    input.value = ''
    await importPluginFile(f)
  }
  async function onTogglePlugin(p: PluginItem, checked: boolean) {
    if (installingPlugin.value) { ui.toast('正在安装其他插件，请稍候', 'warn'); return }
    if (checked) {
      installingPlugin.value = p.name
      p.installed = true
      const ides = sync.syncTargetIdes.join(',')
      ui.clearLog()
      await runSse('/api/plugin/install?file=' + encodeURIComponent(p.file) + '&ide=' + encodeURIComponent(ides),
        (line) => ui.appendLog(line),
        { onDone: () => { skill.loadInstalledSkills(); refreshPluginList() } })
      installingPlugin.value = ''
    } else {
      if (!confirm('卸载插件 ' + p.name + '?')) { p.installed = true; return }
      const r = await api<{ ok: boolean; error?: string }>('/api/plugin/uninstall', {
        method: 'POST', body: JSON.stringify({ name: p.name }),
      })
      if (r.ok) { p.installed = false; ui.toast('已卸载: ' + p.name); refreshPluginList() }
      else { p.installed = true; ui.toast('卸载失败: ' + (r.error || '未知错误'), 'err') }
    }
  }
  function editPlugin(file: string) {
    selectedPluginFile.value = file
    ui.toast('已打开「插件构建」继续编辑')
  }
  async function publishToMarketplace(file: string) {
    const tags = prompt('请输入标签（逗号分隔，可留空）：', '')
    const tagList = tags ? tags.split(/[,，]/).map((t: string) => t.trim()).filter(Boolean) : []
    await marketplace.publish(file, tagList)
  }

  return {
    plugins, selectedPluginFile, installingPlugin, importPluginInput,
    selectedForExport,
    refreshPluginList, exportPlugin, triggerImportPlugin,
    toggleSelectForExport, toggleSelectAllForExport, selectFilesForExport, clearExportSelection,
    exportSelectedPlugins,
    importPluginFile, onImportPluginFile, onTogglePlugin, editPlugin, publishToMarketplace,
  }
})
