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
  cli_names?: string[]  // 支持的 CLI 命令名列表（来自 detect，用于判断是否支持 CLI 维度）
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
  vscode?: { method: string; url?: string; extension_id?: string; note?: string; [k: string]: any }
  idea?: { method: string; url?: string; extension_id?: string; note?: string; [k: string]: any }
  acp?: { method: string; url?: string; cmd?: string; note?: string; [k: string]: any }
  web?: { method: string; url?: string; cmd?: string; note?: string; [k: string]: any }
  homepage?: string
  // 新分类字段：品牌 + 顶层 Code/Work + 形式子集
  brand?: string       // 'Kimi' | 'Claude' | 'Codex' | 'Trae' | 'Qoder' | 'JetBrains' | ...
  category?: string    // 'code' | 'work'
  forms?: string[]     // ['cli', 'app', 'vscode', 'idea']
  // 兼容旧字段
  categories?: string[]
}

// 品牌元数据（厂商、品牌色、Logo 字符）
export const BRAND_META: Record<string, { vendor: string; color: string; logo: string }> = {
  Kimi:      { vendor: 'Moonshot AI · 月之暗面',  color: '#1a1a2e', logo: 'K' },
  CherryStudio: { vendor: 'Cherry Studio',        color: '#e11d48', logo: 'CS' },
  Claude:    { vendor: 'Anthropic',                color: '#c75d3a', logo: 'Cl' },
  Codex:     { vendor: 'OpenAI',                   color: '#0a8a6a', logo: 'Co' },
  Trae:      { vendor: '字节跳动 · ByteDance',     color: '#e6492d', logo: 'Tr' },
  'Trae CN': { vendor: '字节跳动 · ByteDance (国内版)', color: '#3d4fd6', logo: 'Tr' },
  Qoder:     { vendor: '阿里云 · 通义灵码',        color: '#0a93b3', logo: 'Qo' },
  'Qoder CN': { vendor: '阿里云 · 通义灵码 (国内版)', color: '#0a6b8d', logo: 'QC' },
  ZCode:     { vendor: '智谱 ADE',                 color: '#047857', logo: 'ZC' },
  JetBrains: { vendor: 'JetBrains s.r.o.',         color: '#0a5fc7', logo: 'JB' },
  OpenCode:  { vendor: 'anomalyco',               color: '#4f5cd9', logo: 'OO' },
  OpenClaw:  { vendor: '开源社区',                 color: '#7c5cf0', logo: 'OC' },
  Hermes:    { vendor: '内部 Agent 平台',          color: '#6b7280', logo: 'He' },
  WorkBuddy: { vendor: '腾讯 CodeBuddy · AI 工作台', color: '#dc2626', logo: 'WB' },
  CodeBuddy: { vendor: '腾讯云 · Tencent',          color: '#0052d9', logo: 'CB' },
  Pi:        { vendor: 'earendil-works',           color: '#7c3aed', logo: 'Pi' },
  'Trae Work': { vendor: '字节跳动 · ByteDance',   color: '#f59e0b', logo: 'TW' },
  'Command Code': { vendor: 'Command Code',       color: '#0891b2', logo: 'CC' },
  DeepSeek:  { vendor: 'DeepSeek AI · 深度求索',  color: '#4D6BFE', logo: 'DS' },
}

// 形式徽章配色
export const FORM_META: Record<string, { label: string; color: string; bg: string; border: string }> = {
  cli:       { label: 'CLI',            color: '#c4b5fd', bg: 'rgba(124,92,240,0.15)',  border: 'rgba(124,92,240,0.3)' },
  app:       { label: 'App',            color: '#93c5fd', bg: 'rgba(59,130,246,0.15)',  border: 'rgba(59,130,246,0.3)' },
  vscode:    { label: 'VSCode 插件',    color: '#6ee7b7', bg: 'rgba(16,185,129,0.15)',  border: 'rgba(16,185,129,0.3)' },
  idea: { label: 'IDEA 插件', color: '#fca5a5', bg: 'rgba(239,68,68,0.15)',  border: 'rgba(239,68,68,0.3)' },
  acp:       { label: 'ACP',            color: '#fcd34d', bg: 'rgba(245,158,11,0.15)',  border: 'rgba(245,158,11,0.3)' },
  remote:    { label: 'Remote Web',       color: '#34d399', bg: 'rgba(52,211,153,0.15)',  border: 'rgba(52,211,153,0.3)' },
}

// 顶层分类配色
export const CATEGORY_META: Record<string, { label: string; color: string; bg: string; border: string }> = {
  code: { label: 'Code', color: '#c4b5fd', bg: 'linear-gradient(135deg, rgba(124,92,240,0.2), rgba(79,92,217,0.2))', border: 'rgba(124,92,240,0.4)' },
  work: { label: 'Work', color: '#fbbf24', bg: 'linear-gradient(135deg, rgba(251,191,36,0.2), rgba(217,119,6,0.2))', border: 'rgba(251,191,36,0.4)' },
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

  // ===== AIDE 选中状态持久化（expandedIde / expandedIdeCard / ideCardTab）=====
  // 通过后端 /api/ui-state 持久化到 config/ui/ui-state.json，与 sync store 一致
  const ideUiLoaded = ref(false)
  let ideUiSaveTimer: ReturnType<typeof setTimeout> | null = null

  function persistIdeUi(patch: Record<string, unknown>) {
    if (!ideUiLoaded.value) return
    if (ideUiSaveTimer) clearTimeout(ideUiSaveTimer)
    ideUiSaveTimer = setTimeout(() => {
      api('/api/ui-state', {
        method: 'POST',
        body: JSON.stringify(patch),
      }).catch(() => { /* 静默失败 */ })
    }, 200)
  }

  function saveIdeUiState() {
    persistIdeUi({
      expandedIde: expandedIde.value,
      expandedIdeCard: expandedIdeCard.value,
      ideCardTab: { ...ideCardTab },
    })
  }

  async function loadIdeUiState() {
    try {
      const state = await api<Record<string, any>>('/api/ui-state')
      if (typeof state.expandedIde === 'string') expandedIde.value = state.expandedIde
      if (typeof state.expandedIdeCard === 'string') expandedIdeCard.value = state.expandedIdeCard
      if (state.ideCardTab && typeof state.ideCardTab === 'object') {
        Object.assign(ideCardTab, state.ideCardTab)
      }
    } catch { /* 静默失败 */ }
    ideUiLoaded.value = true
  }

  // 异步加载（不阻塞渲染，加载完成前先用默认值）
  loadIdeUiState()

  // ===== computed =====
  /** 已安装 IDE，按 sync.ideList 的用户自定义顺序排序（支持拖拽排序） */
  const installedIdes = computed(() => {
    const installed = ideDetects.value.filter((i) => i.installed)
    const order = sync.ideList.map((i) => i.key)
    return installed.sort((a, b) => {
      const ia = order.indexOf(a.key)
      const ib = order.indexOf(b.key)
      return (ia < 0 ? 999 : ia) - (ib < 0 ? 999 : ib)
    })
  })
  /** 未安装 IDE，同样按 sync.ideList 顺序排序 */
  const notInstalledIdes = computed(() => {
    const notInstalled = ideDetects.value.filter((i) => !i.installed)
    const order = sync.ideList.map((i) => i.key)
    return notInstalled.sort((a, b) => {
      const ia = order.indexOf(a.key)
      const ib = order.indexOf(b.key)
      return (ia < 0 ? 999 : ia) - (ib < 0 ? 999 : ib)
    })
  })
  /** 有会话目录的已安装 IDE（用于右侧会话面板的 IDE 选择器） */
  const sessionableIdes = computed(() => ideDetects.value.filter((i) => i.installed && i.sessions_dir))
  const shareTargetIdes = computed(() => {
    const source = shareModalSession.value?._source_ide
    return ideDetects.value.filter((i) => i.installed && i.sessions_dir && i.key !== source)
  })

  // ===== 品牌 × Code/Work 形式分组（用于 AIDE 管理页卡片化展示）=====
  /** 单个 IDE 项的品牌+分类信息（合并 detect + installInfo） */
  type IdeWithBrand = IdeDetect & {
    brand: string
    category: string
    forms: string[]
    vendor: string
    brandColor: string
    brandLogo: string
  }

  /** 按 brand 分组，组内按 category(code/work) → forms(cli/app/vscode/idea) 二级嵌套 */
  type BrandGroup = {
    brand: string
    vendor: string
    brandColor: string
    brandLogo: string
    total: number
    installedCount: number
    // 按 category 分组：code / work
    categories: Array<{
      category: string  // 'code' | 'work'
      // 按 form 分组：cli / app / vscode / jetbrains
      forms: Array<{
        form: string  // 'cli' | 'app' | 'vscode' | 'idea'
        items: IdeWithBrand[]
      }>
    }>
  }

  /** 品牌分组 computed —— 用于 AIDE 管理页按品牌卡片化展示 */
  const brandGroups = computed<BrandGroup[]>(() => {
    // 1. 合并 detect + installInfo，得到每个 IDE 的 brand/category/forms
    const items: IdeWithBrand[] = ideDetects.value.map((d) => {
      const info = ideInstallInfo[d.key] || {}
      const brand = (info.brand as string) || ''
      const category = (info.category as string) || ''
      const forms = (info.forms as string[]) || (info.categories as string[]) || []
      const bm = BRAND_META[brand] || { vendor: '', color: '#6b7280', logo: d.key.slice(0, 2) }
      return {
        ...d,
        brand,
        category,
        forms,
        vendor: bm.vendor,
        brandColor: bm.color,
        brandLogo: bm.logo,
      }
    })

    // 2. 过滤掉没有 brand 的（如 Agents 占位符）
    const branded = items.filter((i) => i.brand)

    // 3. 按 brand 分组
    const brandMap = new Map<string, IdeWithBrand[]>()
    for (const item of branded) {
      if (!brandMap.has(item.brand)) brandMap.set(item.brand, [])
      brandMap.get(item.brand)!.push(item)
    }

    // 4. 构造 BrandGroup 列表
    const FORM_ORDER = ['cli', 'app', 'vscode', 'idea', 'acp', 'remote']
    const CAT_ORDER = ['code', 'work']

    const groups: BrandGroup[] = []
    for (const [brand, brandItems] of brandMap) {
      const bm = BRAND_META[brand] || { vendor: '', color: '#6b7280', logo: brand.slice(0, 2) }
      const total = brandItems.length
      const installedCount = brandItems.filter((i) => i.installed).length

      // 按 category 分组
      const catMap = new Map<string, IdeWithBrand[]>()
      for (const item of brandItems) {
        const cat = item.category || 'code'
        if (!catMap.has(cat)) catMap.set(cat, [])
        catMap.get(cat)!.push(item)
      }

      const catList: BrandGroup['categories'] = []
      for (const cat of CAT_ORDER) {
        const catItems = catMap.get(cat)
        if (!catItems || catItems.length === 0) continue

        // 按 form 分组
        const formMap = new Map<string, IdeWithBrand[]>()
        for (const item of catItems) {
          for (const f of item.forms) {
            if (!formMap.has(f)) formMap.set(f, [])
            formMap.get(f)!.push(item)
          }
        }

        const formList: BrandGroup['categories'][0]['forms'] = []
        for (const f of FORM_ORDER) {
          const fItems = formMap.get(f)
          if (!fItems || fItems.length === 0) continue
          // 同 form 内去重（一个 IDE 可能出现在多个 form 中？不，每个 IDE 只出现在自己的 forms 列表中）
          // 但多个 IDE 可能映射到同 form（如 KimiCLI + KimiCode 都在 Kimi/code/cli）
          // 直接列出即可
          formList.push({ form: f, items: fItems })
        }
        catList.push({ category: cat, forms: formList })
      }

      groups.push({
        brand,
        vendor: bm.vendor,
        brandColor: bm.color,
        brandLogo: bm.logo,
        total,
        installedCount,
        categories: catList,
      })
    }

    return groups
  })

  // ===== 函数 =====
  /** 打开外部 URL（下载页/官网等）。
   * pywebview 桌面模式下 window.open / <a download> 对外部 URL 均无效，
   * 走 JS-Python 桥接调用系统默认浏览器打开；浏览器模式回退 window.open。
   */
  async function openExternal(url?: string) {
    if (!url) return
    const pw = (window as any).pywebview
    if (pw?.api?.open_external) {
      try {
        await pw.api.open_external(url)
        return
      } catch { /* 回退 */ }
    }
    window.open(url, '_blank')
  }

  /** 打开 URL 或 deep link 协议（vscode: / idea: / https: 等）。
   * pywebview 桌面模式下 openExternal 对 deep link 协议无效（系统浏览器不识别 vscode: 协议），
   * 通过后端 /api/ide/open-url 用系统命令打开（macOS: open, Windows: start, Linux: xdg-open）。
   * 用于 VSCode 扩展（vscode:extension/xxx）、IDEA 插件（jetbrains://plugin/xxx）等 deep link。
   */
  async function openIdeUrl(url?: string) {
    if (!url) return
    try {
      const r = await api<{ ok: boolean; error?: string }>('/api/ide/open-url', {
        method: 'POST',
        body: JSON.stringify({ url }),
      })
      if (!r.ok) {
        // 后端失败，回退到 openExternal（浏览器模式或老版本后端）
        openExternal(url)
      }
    } catch {
      // 网络错误等，回退到 openExternal
      openExternal(url)
    }
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

  async function launchIde(ideKey: string, session: IdeSession | null = null, mode?: string, cwd?: string) {
    const key = session ? `${ideKey}:${session.id}` : ideKey
    if (ideLaunching.value || ideResuming.value) return
    if (session) ideResuming.value = key
    else ideLaunching.value = ideKey
    try {
      const body: Record<string, string> = session
        ? { ide: ideKey, session_id: session.id, cwd: session.cwd || '' }
        : { ide: ideKey }
      if (cwd) body.cwd = cwd
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
        // vscode/idea/acp 等 deep link 协议走 openIdeUrl（后端用系统命令打开）
        // https/http 普通链接也走 openIdeUrl（统一入口，后端会自动处理）
        openIdeUrl(r.url)
      } else {
        ui.toast(`安装 ${ideKey} ${mode.toUpperCase()} 失败: ${r.message || r.error || ''}`, 'err')
      }
    } finally {
      ideInstalling.value = ''
    }
  }

  async function uninstallIde(ideKey: string, mode: string, force: boolean = false) {
    const key = `${ideKey}:${mode}${force ? ':force' : ''}`
    if (ideUninstalling.value) return
    const action = force ? '强制卸载' : '卸载'
    const warn = force ? '（跳过系统卸载程序，直接强删目录）' : ''
    if (!confirm(`确定${action} ${ideKey} ${mode.toUpperCase()}？${warn}`)) return
    ideUninstalling.value = key
    try {
      const r = await api<{ ok: boolean; message?: string; error?: string }>('/api/ide/uninstall', {
        method: 'POST',
        body: JSON.stringify({ ide: ideKey, mode, force }),
      })
      if (r.ok) {
        ui.toast(`${action} ${ideKey} ${mode.toUpperCase()} 成功`, 'ok')
        await loadIdeDetect()
      } else {
        ui.toast(`${action} ${ideKey} ${mode.toUpperCase()} 失败: ${r.message || r.error || ''}`, 'err')
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
        openIdeUrl(r.url)
      } else {
        ui.toast(`重装 ${ideKey} ${mode.toUpperCase()} 失败: ${r.message || r.error || ''}`, 'err')
      }
    } finally {
      ideReinstalling.value = ''
    }
  }

  function toggleIdeCard(ideKey: string) {
    if (expandedIdeCard.value === ideKey) {
      expandedIdeCard.value = ''
      expandedIde.value = ''
    } else {
      expandedIdeCard.value = ideKey
      expandedIde.value = ideKey
    }
    saveIdeUiState()
  }

  function setIdeCardTab(ideKey: string, tab: string) {
    ideCardTab[ideKey] = tab
    saveIdeUiState()
  }

  async function syncIdeConfig(ideKey: string) {
    if (ideSyncing.value) return
    ideSyncing.value = ideKey
    try {
      const resp = await fetch(
        `/api/sync?ide=${encodeURIComponent(ideKey)}&scope=llm,mcp,skill,rules`,
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
    brandGroups,
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
    openExternal,
    openIdeUrl,
    loadIdeUiState,
  }
})
