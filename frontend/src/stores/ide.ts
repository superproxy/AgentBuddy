/**
 * IDE 管理 store —— 从 config_ui.html L1984-2294 迁移。
 *
 * 含：IDE 检测、会话浏览/启动/恢复/导出导入共享、安装/卸载/重装、
 * 配置同步、cli/app 子 tab。依赖 useUiStore（toast）和 useSyncStore（ideList 沉底）。
 */
import { defineStore } from 'pinia'
import { ref, reactive, computed } from 'vue'
import { api } from '../api/client'
import { useUiStore } from './ui'
import { useSyncStore } from './sync'

// ===== 类型 =====
export interface IdeDetect {
  key: string
  label: string
  installed: boolean
  exe_path: string
  app_path: string
  version: string
  config_paths: string[]
  sessions_dir: string
  is_tui?: boolean
  type?: string  // 'ide'（默认）| 'non-ide'（非 IDE，仅配置目录）
}

export interface IdeSession {
  id: string
  title?: string
  messages_count: number
  size_bytes: number
  cwd?: string
  updated_at: string
  tool_calls?: number
  file_path?: string
}

export interface IdeInstallInfo {
  ide: string
  available: boolean
  cli?: { method: string; package?: string; url?: string; script_url?: string; [k: string]: any }
  app?: { method: string; package?: string; url?: string; [k: string]: any }
  homepage?: string
}

export const useIdeStore = defineStore('ide', () => {
  const ui = useUiStore()
  const sync = useSyncStore()

  // ===== 状态 =====
  const ideDetects = ref<IdeDetect[]>([])
  const ideDetectStats = ref({ total: 0, installed: 0, not_installed: 0 })
  const ideDetecting = ref(false)
  const ideSessionsMap = reactive<Record<string, IdeSession[]>>({})
  const ideSessionsStatsMap = reactive<Record<string, { total: number; truncated?: boolean }>>({})
  const ideLoadingSessions = ref('')
  const ideLaunching = ref('')
  const ideResuming = ref('')
  const ideOpeningConfig = ref('')
  const expandedIde = ref('')
  const sessionDrawerOpen = ref(false)
  const exportingSession = ref('')
  const shareModalOpen = ref(false)
  const shareModalSession = ref<(IdeSession & { _source_ide?: string }) | null>(null)
  const shareTargetIde = ref('')
  const shareImporting = ref(false)
  const ideInstallInfo = reactive<Record<string, IdeInstallInfo>>({})
  const ideInstallInfoLoaded = ref(false)
  const ideInstalling = ref('')
  const ideUninstalling = ref('')
  const ideReinstalling = ref('')
  const ideSyncing = ref('')
  const expandedIdeCard = ref('')
  const ideCardTab = reactive<Record<string, string>>({})
  const showNotInstalled = ref(false)

  // ===== computed =====
  const installedIdes = computed(() => ideDetects.value.filter((i) => i.installed))
  const notInstalledIdes = computed(() => ideDetects.value.filter((i) => !i.installed))
  /** 有会话目录的已安装 IDE（用于右侧会话面板的 IDE 选择器） */
  const sessionableIdes = computed(() => ideDetects.value.filter((i) => i.installed && i.sessions_dir))
  const shareTargetIdes = computed(() => {
    const source = shareModalSession.value?._source_ide
    return ideDetects.value.filter((i) => i.installed && i.sessions_dir && i.key !== source)
  })

  // ===== 函数 =====
  /** 直接下载（不跳转新窗口）：用 <a download> 触发，浏览器处理 */
  function downloadUrl(url: string) {
    const a = document.createElement('a')
    a.href = url
    a.download = ''
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }

  async function loadIdeDetect() {
    if (ideDetecting.value) return
    ideDetecting.value = true
    try {
      const r = await api<{ ok: boolean; ides?: IdeDetect[]; stats?: any; error?: string }>('/api/ide/detect')
      if (!r.ok) {
        ui.toast('IDE 检测失败: ' + (r.error || ''), 'err')
        return
      }
      ideDetects.value = r.ides || []
      ideDetectStats.value = r.stats || {}
      sinkNotInstalledIdes()
      ui.toast(`检测完成: ${ideDetectStats.value.installed}/${ideDetectStats.value.total} 已安装`, 'ok')
      loadIdeInstallInfo()
    } finally {
      ideDetecting.value = false
    }
  }

  /** 按 installed 状态对 ideList 做 stable 分区：已安装在前，未安装在后 */
  function sinkNotInstalledIdes() {
    if (!ideDetects.value.length) return
    const installedSet = new Set(ideDetects.value.filter((i) => i.installed).map((i) => i.key))
    const installed = sync.ideList.filter((i) => installedSet.has(i.key))
    const notInstalled = sync.ideList.filter((i) => !installedSet.has(i.key))
    if (installed.length + notInstalled.length !== sync.ideList.length) return
    const newOrder = [...installed, ...notInstalled]
    const changed = newOrder.some((ide, idx) => ide.key !== sync.ideList[idx]?.key)
    if (changed) {
      sync.ideList.splice(0, sync.ideList.length, ...newOrder)
      sync.saveIdeOrder()
    }
  }

  async function loadIdeSessions(ideKey: string) {
    if (ideLoadingSessions.value) return
    ideLoadingSessions.value = ideKey
    try {
      const r = await api<{ ok: boolean; sessions?: IdeSession[]; stats?: any; error?: string }>(
        `/api/ide/sessions?ide=${encodeURIComponent(ideKey)}&limit=50`,
      )
      if (!r.ok) {
        ui.toast(`加载 ${ideKey} 会话失败: ` + (r.error || ''), 'err')
        return
      }
      ideSessionsMap[ideKey] = r.sessions || []
      ideSessionsStatsMap[ideKey] = r.stats || {}
    } finally {
      ideLoadingSessions.value = ''
    }
  }

  function toggleIdeSessions(ideKey: string) {
    expandedIde.value = ideKey
    sessionDrawerOpen.value = true
    if (!ideSessionsMap[ideKey]) loadIdeSessions(ideKey)
  }

  function closeSessionDrawer() {
    sessionDrawerOpen.value = false
  }

  async function launchIde(ideKey: string, session: IdeSession | null = null, mode?: string) {
    const key = session ? `${ideKey}:${session.id}` : ideKey
    if (ideLaunching.value || ideResuming.value) return
    if (session) ideResuming.value = key
    else ideLaunching.value = ideKey
    try {
      const body: Record<string, string> = session
        ? { ide: ideKey, session_id: session.id, cwd: session.cwd || '' }
        : { ide: ideKey }
      if (mode) body.mode = mode
      const r = await api<{ ok: boolean; mode?: string; pid?: number; error?: string }>(
        '/api/ide/launch',
        {
          method: 'POST',
          body: JSON.stringify(body),
        },
      )
      if (!r.ok) {
        ui.toast(`${session ? '恢复会话' : '启动'} ${ideKey} 失败: ` + (r.error || ''), 'err')
        return
      }
      const launchMode = r.mode === 'cli' ? 'CLI' : r.mode === 'app' ? 'App' : ''
      ui.toast(`${session ? '恢复会话' : '启动'} ${ideKey} ${launchMode} (pid=${r.pid})`, 'ok')
    } finally {
      ideLaunching.value = ''
      ideResuming.value = ''
    }
  }

  async function openIdeConfig(ideKey: string) {
    if (ideOpeningConfig.value) return
    ideOpeningConfig.value = ideKey
    try {
      const r = await api<{ ok: boolean; error?: string }>('/api/ide/open-config', {
        method: 'POST',
        body: JSON.stringify({ ide: ideKey }),
      })
      if (!r.ok) {
        ui.toast(`打开 ${ideKey} 配置目录失败: ` + (r.error || ''), 'err')
        return
      }
      ui.toast(`已打开 ${ideKey} 配置目录`, 'ok')
    } finally {
      ideOpeningConfig.value = ''
    }
  }

  async function loadIdeInstallInfo() {
    try {
      const r = await api<{ ok: boolean; infos?: IdeInstallInfo[] }>('/api/ide/install-info')
      if (!r.ok) return
      for (const info of r.infos || []) {
        ideInstallInfo[info.ide] = info
      }
      ideInstallInfoLoaded.value = true
    } catch {
      /* ignore */
    }
  }

  async function installIde(ideKey: string, mode: string) {
    const key = `${ideKey}:${mode}`
    if (ideInstalling.value) return
    ideInstalling.value = key
    try {
      const r = await api<{ ok: boolean; url?: string; message?: string; error?: string }>(
        '/api/ide/install',
        { method: 'POST', body: JSON.stringify({ ide: ideKey, mode }) },
      )
      if (r.ok) {
        ui.toast(`安装 ${ideKey} ${mode.toUpperCase()} 成功`, 'ok')
        await loadIdeDetect()
      } else if (r.url) {
        ui.toast(`${r.message || '需手动安装'}：${r.url}`, 'warn')
        downloadUrl(r.url)
      } else {
        ui.toast(`安装 ${ideKey} ${mode.toUpperCase()} 失败: ${r.message || r.error || ''}`, 'err')
      }
    } finally {
      ideInstalling.value = ''
    }
  }

  async function uninstallIde(ideKey: string, mode: string) {
    const key = `${ideKey}:${mode}`
    if (ideUninstalling.value) return
    if (!confirm(`确定卸载 ${ideKey} ${mode.toUpperCase()}？`)) return
    ideUninstalling.value = key
    try {
      const r = await api<{ ok: boolean; message?: string; error?: string }>('/api/ide/uninstall', {
        method: 'POST',
        body: JSON.stringify({ ide: ideKey, mode }),
      })
      if (r.ok) {
        ui.toast(`卸载 ${ideKey} ${mode.toUpperCase()} 成功`, 'ok')
        await loadIdeDetect()
      } else {
        ui.toast(`卸载 ${ideKey} ${mode.toUpperCase()} 失败: ${r.message || r.error || ''}`, 'err')
      }
    } finally {
      ideUninstalling.value = ''
    }
  }

  async function reinstallIde(ideKey: string, mode: string) {
    const key = `${ideKey}:${mode}`
    if (ideReinstalling.value) return
    if (!confirm(`确定重装 ${ideKey} ${mode.toUpperCase()}？（先卸载再安装）`)) return
    ideReinstalling.value = key
    try {
      const r = await api<{ ok: boolean; url?: string; message?: string; error?: string }>(
        '/api/ide/reinstall',
        { method: 'POST', body: JSON.stringify({ ide: ideKey, mode }) },
      )
      if (r.ok) {
        ui.toast(`重装 ${ideKey} ${mode.toUpperCase()} 成功`, 'ok')
        await loadIdeDetect()
      } else if (r.url) {
        ui.toast(`${r.message || '需手动安装'}：${r.url}`, 'warn')
        downloadUrl(r.url)
      } else {
        ui.toast(`重装 ${ideKey} ${mode.toUpperCase()} 失败: ${r.message || r.error || ''}`, 'err')
      }
    } finally {
      ideReinstalling.value = ''
    }
  }

  function toggleIdeCard(ideKey: string) {
    expandedIdeCard.value = expandedIdeCard.value === ideKey ? '' : ideKey
  }

  function setIdeCardTab(ideKey: string, tab: string) {
    ideCardTab[ideKey] = tab
  }

  async function syncIdeConfig(ideKey: string) {
    if (ideSyncing.value) return
    ideSyncing.value = ideKey
    try {
      const resp = await fetch(
        `/api/init-ide?ide=${encodeURIComponent(ideKey)}&scope=llm,mcp,skill,rules`,
        { method: 'GET', headers: { Accept: 'text/event-stream' } },
      )
      if (!resp.ok) {
        ui.toast(`同步 ${ideKey} 配置请求失败 (HTTP ${resp.status})`, 'err')
        return
      }
      const reader = resp.body!.getReader()
      const decoder = new TextDecoder()
      let lastLine = ''
      let ok = true
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const text = decoder.decode(value, { stream: true })
        const lines = (lastLine + text).split('\n')
        lastLine = lines.pop() || ''
        for (const line of lines) {
          if (!line.startsWith('data:')) continue
          const payload = line.slice(5).trim()
          if (!payload) continue
          try {
            const obj = JSON.parse(payload)
            if (obj.error) ok = false
          } catch {
            /* 非 JSON payload，忽略 */
          }
        }
      }
      ui.toast(
        ok ? `同步 ${ideKey} 配置完成` : `同步 ${ideKey} 配置完成（含警告）`,
        ok ? 'ok' : 'warn',
      )
    } catch (e: any) {
      ui.toast(`同步 ${ideKey} 配置失败: ${e?.message || e}`, 'err')
    } finally {
      ideSyncing.value = ''
    }
  }

  async function exportSession(ideKey: string, session: IdeSession) {
    if (exportingSession.value) return
    exportingSession.value = session.id
    try {
      const r = await api<{ ok: boolean; session?: any; download_filename?: string; error?: string }>(
        `/api/ide/session/export?ide=${encodeURIComponent(ideKey)}&session_id=${encodeURIComponent(session.id)}`,
      )
      if (!r.ok) {
        ui.toast('导出会话失败: ' + (r.error || ''), 'err')
        return
      }
      const blob = new Blob([JSON.stringify(r.session, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = r.download_filename || `session-${ideKey}-${session.id.slice(0, 8)}.json`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      ui.toast(`已导出 ${r.session?.messages_count || 0} 条消息`, 'ok')
    } finally {
      exportingSession.value = ''
    }
  }

  function openShareModal(ideKey: string, session: IdeSession) {
    shareModalSession.value = { ...session, _source_ide: ideKey }
    shareTargetIde.value = ''
    shareModalOpen.value = true
  }

  async function importSession() {
    if (!shareModalSession.value || !shareTargetIde.value) {
      ui.toast('请选择目标 IDE', 'warn')
      return
    }
    if (shareImporting.value) return
    shareImporting.value = true
    try {
      const sourceIde = shareModalSession.value._source_ide!
      const sid = shareModalSession.value.id
      const exp = await api<{ ok: boolean; session?: any; error?: string }>(
        `/api/ide/session/export?ide=${encodeURIComponent(sourceIde)}&session_id=${encodeURIComponent(sid)}`,
      )
      if (!exp.ok) {
        ui.toast('导出失败: ' + (exp.error || ''), 'err')
        return
      }
      const r = await api<{ ok: boolean; messages_count?: number; error?: string }>(
        '/api/ide/session/import',
        { method: 'POST', body: JSON.stringify({ session: exp.session, target_ide: shareTargetIde.value }) },
      )
      if (!r.ok) {
        ui.toast('共享失败: ' + (r.error || ''), 'err')
        return
      }
      ui.toast(`已共享 ${r.messages_count} 条消息到 ${shareTargetIde.value}`, 'ok')
      shareModalOpen.value = false
    } finally {
      shareImporting.value = false
    }
  }

  return {
    // 状态
    ideDetects,
    ideDetectStats,
    ideDetecting,
    ideSessionsMap,
    ideSessionsStatsMap,
    ideLoadingSessions,
    ideLaunching,
    ideResuming,
    ideOpeningConfig,
    expandedIde,
    sessionDrawerOpen,
    exportingSession,
    shareModalOpen,
    shareModalSession,
    shareTargetIde,
    shareImporting,
    ideInstallInfo,
    ideInstallInfoLoaded,
    ideInstalling,
    ideUninstalling,
    ideReinstalling,
    ideSyncing,
    expandedIdeCard,
    ideCardTab,
    showNotInstalled,
    // computed
    installedIdes,
    notInstalledIdes,
    sessionableIdes,
    shareTargetIdes,
    // 函数
    loadIdeDetect,
    sinkNotInstalledIdes,
    loadIdeSessions,
    toggleIdeSessions,
    closeSessionDrawer,
    launchIde,
    openIdeConfig,
    loadIdeInstallInfo,
    installIde,
    uninstallIde,
    reinstallIde,
    toggleIdeCard,
    setIdeCardTab,
    syncIdeConfig,
    exportSession,
    openShareModal,
    importSession,
  }
})
