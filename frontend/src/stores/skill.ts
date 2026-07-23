import { defineStore } from 'pinia'
import { ref, reactive, computed } from 'vue'
import * as yaml from 'js-yaml'
import { api } from '../api/client'
import { runSse } from '../api/sse'
import { useUiStore } from './ui'
import { useSyncStore } from './sync'

export interface InstalledSkill {
  name: string
  path: string
  skill_md_exists: boolean
  enabled: boolean
  /** GitHub 作者（来自 skills-index.csv 的 source=owner/repo） */
  author?: string
  /** GitHub 仓库名 */
  repo?: string
  /** GitHub 仓库 URL（可点击跳转） */
  github_url?: string
  /** 来源类型：remote / local */
  source_type?: string
  /** 安装来源字符串（owner/repo 或 local:xxx） */
  source?: string
  /** 安装时间 UTC ISO */
  installed_at?: string
  /** 安装时的 commit SHA */
  installed_sha?: string
  /** 安装时的分支/tag */
  installed_ref?: string
}

export interface SkillUpdateInfo {
  name: string
  source: string
  owner: string
  repo: string
  installed_sha: string
  latest_sha: string
  has_update: boolean
  latest_ref?: string
  latest_message?: string
  latest_checked_at: string
  message?: string
}

export type SkillSourceId = 'skillssh' | 'smithery' | 'modelscope' | 'skillsmp' | 'clawhub' | 'anthropics' | 'github'

export const SKILL_SOURCE_ORDER: SkillSourceId[] = [
  'skillssh', 'smithery', 'modelscope', 'skillsmp', 'clawhub', 'anthropics', 'github',
]
export const SKILL_SOURCE_LABELS: Record<SkillSourceId, string> = {
  skillssh: 'skills.sh',
  smithery: 'Smithery',
  modelscope: 'ModelScope',
  skillsmp: 'SkillsMP',
  clawhub: 'ClawHub',
  anthropics: 'Anthropic',
  github: 'GitHub',
}

export const useSkillStore = defineStore('skill', () => {
  const ui = useUiStore()
  const sync = useSyncStore()
  const localSkills = ref<any[]>([])
  const skillFilter = reactive({ cat: '', role: '', text: '' })
  const skillTab = ref<'market' | 'local' | 'manual'>('market')
  const skillMarketSources = ref<SkillSourceId[]>(['skillssh', 'smithery', 'modelscope', 'skillsmp'])
  const skillSearchQ = ref('')
  const skillSearchResults = ref<any[]>([])
  const skillSearchHint = ref('')
  const skillSearched = ref(false)
  const skillSearching = ref(false)
  const skillSearchMeta = ref<any>(null)
  const manualSkillInput = ref('')
  const manualPreview = ref<{
    source: string
    skill_filter: string
    skills: { name: string; description?: string; path?: string }[]
    method: string
    count: number
  } | null>(null)
  const manualSelected = ref<string[]>([])
  const manualPreviewing = ref(false)
  const manualInstalling = ref(false)
  const installedSkills = ref<InstalledSkill[]>([])
  const listFilter = ref<'all' | 'on' | 'off'>('all')
  const listQuery = ref('')
  const localFilterQ = ref('')
  const _togglingSkills = reactive(new Set<string>())

  // ===== 升级检查 =====
  const updateChecking = ref(false)
  const updateList = ref<SkillUpdateInfo[]>([])
  const updateCheckedAt = ref('')

  /** @deprecated 兼容旧模板；请用 skillMarketSources */
  const skillSources = reactive({ modelscope: true, skillssh: true })

  const skillCategories = computed(() => [...new Set(localSkills.value.map((s) => s.category).filter(Boolean))].sort())
  const skillRoles = computed(() => [...new Set(localSkills.value.flatMap((s) => (s.role || '').split('|')).filter(Boolean))].sort())
  const filteredLocalSkills = computed(() => {
    const q = localFilterQ.value.trim().toLowerCase() || skillFilter.text.trim().toLowerCase()
    return localSkills.value.filter((s) => {
      if (skillFilter.cat && s.category !== skillFilter.cat) return false
      if (skillFilter.role && !(s.role || '').includes(skillFilter.role)) return false
      if (q) {
        if (!(s.skill_name || '').toLowerCase().includes(q) && !(s.description || '').toLowerCase().includes(q)) return false
      }
      return true
    })
  })
  const enabledInstalledCount = computed(() => installedSkills.value.filter((s) => s.enabled).length)
  const disabledInstalledCount = computed(() => installedSkills.value.length - enabledInstalledCount.value)
  const filteredInstalled = computed(() => {
    const q = listQuery.value.trim().toLowerCase()
    return installedSkills.value.filter((s) => {
      if (listFilter.value === 'on' && !s.enabled) return false
      if (listFilter.value === 'off' && s.enabled) return false
      if (!q) return true
      return (
        s.name.toLowerCase().includes(q) ||
        (s.path || '').toLowerCase().includes(q) ||
        (s.author || '').toLowerCase().includes(q) ||
        (s.repo || '').toLowerCase().includes(q)
      )
    })
  })

  async function loadLocalSkills() {
    if (localSkills.value.length) return
    const r = await api<{ ok: boolean; data?: any[] }>('/api/skills/local')
    if (r.ok) localSkills.value = r.data || []
  }
  function toggleSkillSource(src: SkillSourceId) {
    const cur = skillMarketSources.value
    if (cur.includes(src)) {
      if (cur.length === 1) { ui.toast('请至少保留一个搜索源', 'warn'); return }
      skillMarketSources.value = cur.filter((s) => s !== src)
    } else {
      skillMarketSources.value = [...cur, src]
    }
  }
  async function searchSkills() {
    const q = skillSearchQ.value.trim()
    if (!q) return
    const srcs = skillMarketSources.value
    if (!srcs.length) { ui.toast('请至少勾选一个搜索源', 'warn'); return }
    skillSearched.value = true
    skillSearching.value = true
    skillSearchHint.value = '搜索中...'
    skillSearchMeta.value = null
    try {
      const r = await api<{
        ok: boolean
        data?: any[]
        errors?: string[]
        meta?: any
        error?: string
      }>('/api/skills/search?q=' + encodeURIComponent(q) + '&sources=' + encodeURIComponent(srcs.join(',')) + '&limit=12')
      if (r.ok) {
        skillSearchResults.value = r.data || []
        skillSearchMeta.value = r.meta || null
        if (r.errors && r.errors.length) ui.toast('部分源失败: ' + r.errors.join('; '), 'warn')
      } else {
        skillSearchResults.value = []
        ui.toast('搜索失败: ' + (r.error || '未知错误'), 'err')
      }
    } finally {
      skillSearching.value = false
      skillSearchHint.value = ''
    }
  }
  async function installFromSearch(s: any, force: boolean = false) {
    const forceParam = force ? '&force=1' : ''
    // 本地预置技能：直接从 template/skills/ 复制
    if (s.source === 'local' || (s.install_command === '' && s.source === 'local')) {
      ui.clearLog()
      await runSse('/api/skills/install?source=local:' + encodeURIComponent(s.name) + forceParam, (line) => ui.appendLog(line), { onDone: () => loadInstalledSkills() })
      return
    }
    let cmd = s.install_command || ''
    if (cmd && /^\s*npx\b/.test(cmd)) {
      // 仅对 skills add 补 --copy / npx --yes；clawhub 等其它 CLI 不改写
      if (/\bskills\s+add\b/.test(cmd)) {
        // 避免 npx 交互提示 Need to install the following packages: skills@...
        if (!/\bnpx\s+(-y|--yes)\b/.test(cmd)) cmd = cmd.replace(/^\s*npx\b/, 'npx --yes')
        if (!cmd.includes('--copy')) cmd = cmd.replace(/ -y$/, '').trimEnd() + ' --copy -y'
        if (!/\s-y(\s|$)/.test(cmd)) cmd += ' -y'
      }
      ui.clearLog()
      await runSse('/api/skills/install?command=' + encodeURIComponent(cmd) + forceParam, (line) => ui.appendLog(line), { onDone: () => loadInstalledSkills() })
      return
    }
    const src = s.author ? s.author + '/' + s.name : s.name
    ui.clearLog()
    await runSse('/api/skills/install?source=' + encodeURIComponent(src) + forceParam, (line) => ui.appendLog(line), { onDone: () => loadInstalledSkills() })
  }
  async function installManualSkill(force: boolean = false) {
    if (!manualSkillInput.value.trim()) return
    ui.clearLog()
    const forceParam = force ? '&force=1' : ''
    await runSse('/api/skills/install?source=' + encodeURIComponent(manualSkillInput.value.trim()) + forceParam, (line) => ui.appendLog(line), { onDone: () => loadInstalledSkills() })
  }

  function clearManualPreview() {
    manualPreview.value = null
    manualSelected.value = []
  }

  async function previewManualSource() {
    const raw = manualSkillInput.value.trim()
    if (!raw) { ui.toast('请输入安装源', 'warn'); return }
    manualPreviewing.value = true
    clearManualPreview()
    try {
      const r = await api<{
        ok: boolean
        error?: string
        source?: string
        skill_filter?: string
        skills?: { name: string; description?: string; path?: string }[]
        method?: string
        count?: number
      }>('/api/skills/preview?source=' + encodeURIComponent(raw))
      if (!r.ok) {
        ui.toast('解析失败: ' + (r.error || '未知错误'), 'err')
        return
      }
      const skills = r.skills || []
      manualPreview.value = {
        source: r.source || raw,
        skill_filter: r.skill_filter || '',
        skills,
        method: r.method || '',
        count: r.count ?? skills.length,
      }
      // 单技能或已指定 @skill：默认全选；多技能默认不全选，避免误装全部
      if (skills.length <= 1 || r.skill_filter) {
        manualSelected.value = skills.map((s) => s.name)
      } else {
        manualSelected.value = []
      }
      if (!skills.length) ui.toast('该源下未发现可安装技能', 'warn')
    } finally {
      manualPreviewing.value = false
    }
  }

  function toggleManualSkill(name: string) {
    const set = new Set(manualSelected.value)
    if (set.has(name)) set.delete(name)
    else set.add(name)
    manualSelected.value = [...set]
  }

  function selectAllManualSkills(on: boolean) {
    if (!manualPreview.value) return
    manualSelected.value = on ? manualPreview.value.skills.map((s) => s.name) : []
  }

  async function installSelectedManualSkills(force: boolean = false) {
    if (!manualPreview.value) {
      await previewManualSource()
      return
    }
    const src = manualPreview.value.source
    const selected = manualSelected.value
    if (!selected.length) {
      ui.toast('请至少勾选一个技能', 'warn')
      return
    }
    manualInstalling.value = true
    ui.clearLog()
    try {
      const qs =
        '/api/skills/install?source=' + encodeURIComponent(src) +
        '&skills=' + encodeURIComponent(selected.join(',')) +
        (force ? '&force=1' : '')
      await runSse(qs, (line) => ui.appendLog(line), { onDone: () => loadInstalledSkills() })
      ui.toast(`已提交安装 ${selected.length} 个技能`)
    } finally {
      manualInstalling.value = false
    }
  }
  async function loadInstalledSkills() {
    const r = await api<{ ok: boolean; data?: InstalledSkill[] }>('/api/skills/installed')
    if (r.ok) installedSkills.value = r.data || []
  }

  /** 可升级的 skill 数量（有 GitHub 来源记录且检查出有更新） */
  const updatableCount = computed(() => updateList.value.filter((u) => u.has_update).length)
  /** 已记录来源的 skill 数量 */
  const trackedCount = computed(() => updateList.value.length)

  /** 检查所有已记录来源的 skill 是否有新版本 */
  async function checkUpdates(names?: string[]) {
    updateChecking.value = true
    try {
      const qs = names && names.length
        ? '?names=' + encodeURIComponent(names.join(','))
        : ''
      const r = await api<{ ok: boolean; data?: SkillUpdateInfo[]; error?: string }>('/api/skills/check-updates' + qs)
      if (r.ok) {
        updateList.value = r.data || []
        updateCheckedAt.value = new Date().toISOString()
      } else {
        ui.toast('检查升级失败: ' + (r.error || '未知错误'), 'err')
      }
    } finally {
      updateChecking.value = false
    }
  }

  /** 升级单个 skill（SSE 流式） */
  async function upgradeSkill(name: string) {
    ui.clearLog()
    await runSse(
      '/api/skills/upgrade?name=' + encodeURIComponent(name),
      (line) => ui.appendLog(line),
      { onDone: () => loadInstalledSkills() },
    )
  }

  /** 批量升级所有有更新的 skill */
  async function upgradeAll() {
    const targets = updateList.value.filter((u) => u.has_update).map((u) => u.name)
    if (!targets.length) { ui.toast('没有可升级的技能', 'warn'); return }
    ui.clearLog()
    for (const name of targets) {
      ui.appendLog(`--- 升级 ${name} ---`)
      await runSse(
        '/api/skills/upgrade?name=' + encodeURIComponent(name),
        (line) => ui.appendLog(line),
      )
    }
    await loadInstalledSkills()
    await checkUpdates()
    ui.toast(`已升级 ${targets.length} 个技能`)
  }

  /** 通过市场搜索为无来源记录的 skill 补全来源 */
  async function fillSources(names?: string[]) {
    ui.clearLog()
    const qs = names && names.length
      ? '?names=' + encodeURIComponent(names.join(','))
      : ''
    let successCount = 0
    await runSse(
      '/api/skills/fill-sources' + qs,
      (line) => {
        ui.appendLog(line)
        if (line.startsWith('[OK]')) successCount++
      },
      { onDone: () => loadInstalledSkills() },
    )
    return successCount
  }
  async function viewSkillMd(name: string) {
    const r = await api<{ ok: boolean; content?: string; error?: string }>('/api/skills/' + encodeURIComponent(name) + '/skillmd')
    if (r.ok) ui.showModal(name + ' / SKILL.md', r.content || '')
    else ui.toast('读取失败: ' + r.error, 'err')
  }
  async function uninstallSkill(name: string) {
    const ok = await ui.askConfirm({
      title: '卸载此技能？',
      message: '将从本地技能目录移除，此操作不可撤销。',
      detail: name,
      confirmText: '确认卸载',
      tone: 'danger',
    })
    if (!ok) return
    const r = await api<{ ok: boolean; error?: string; removed?: string[] }>('/api/skills/' + encodeURIComponent(name), { method: 'DELETE' })
    if (r.ok) {
      ui.toast('已卸载 ' + name)
      await loadInstalledSkills()
    } else {
      ui.toast('卸载失败: ' + (r.error || '未知错误'), 'err')
    }
  }
  async function syncToIde() {
    ui.clearLog()
    await runSse('/api/init-ide?ide=All&scope=skill', (line) => ui.appendLog(line))
  }
  async function onToggleSkill(s: InstalledSkill, enabled: boolean) {
    if (_togglingSkills.has(s.name)) return
    _togglingSkills.add(s.name)
    s.enabled = enabled
    try {
      const r = await api<{ ok: boolean; error?: string }>('/api/skills/' + encodeURIComponent(s.name) + '/toggle', {
        method: 'POST', body: JSON.stringify({ enabled, ides: sync.syncTargetIdes }),
      })
      if (r.ok) ui.toast(enabled ? `已启用 ${s.name} 并同步` : `已禁用 ${s.name}`)
      else { s.enabled = !enabled; ui.toast('切换失败: ' + (r.error || '未知错误'), 'err') }
    } catch (e: any) {
      s.enabled = !enabled
      ui.toast('切换失败: ' + e.message, 'err')
    } finally {
      _togglingSkills.delete(s.name)
    }
  }
  async function toggleAllInstalled(enabled: boolean) {
    const targets = installedSkills.value.filter((s) => s.enabled !== enabled)
    if (!targets.length) return
    if (!confirm(enabled ? `启用全部 ${targets.length} 个技能并同步?` : `禁用全部 ${targets.length} 个技能并同步?`)) return
    targets.forEach((s) => (s.enabled = enabled))
    for (const s of targets) {
      try {
        await api('/api/skills/' + encodeURIComponent(s.name) + '/toggle', {
          method: 'POST', body: JSON.stringify({ enabled, ides: sync.syncTargetIdes }),
        })
      } catch { /* 忽略单个失败 */ }
    }
    ui.toast(`已${enabled ? '启用' : '禁用'} ${targets.length} 个技能`)
  }

  /** 批量切换指定名称的启用状态（基于勾选） */
  async function toggleSkillList(names: string[], enabled: boolean) {
    if (!names.length) { ui.toast('请先勾选技能', 'warn'); return }
    const targets = installedSkills.value.filter((s) => names.includes(s.name) && s.enabled !== enabled)
    if (!targets.length) { ui.toast('没有需要变更的技能', 'warn'); return }
    targets.forEach((s) => (s.enabled = enabled))
    for (const s of targets) {
      try {
        await api('/api/skills/' + encodeURIComponent(s.name) + '/toggle', {
          method: 'POST', body: JSON.stringify({ enabled, ides: sync.syncTargetIdes }),
        })
      } catch { /* 忽略单个失败 */ }
    }
    ui.toast(`已${enabled ? '启用' : '禁用'} ${targets.length} 个技能`)
  }

  /** 批量卸载（基于勾选） */
  async function deleteSkillList(names: string[]) {
    if (!names.length) { ui.toast('请先勾选技能', 'warn'); return }
    const ok = await ui.askConfirm({
      title: `卸载 ${names.length} 个技能？`,
      message: '将从本地技能目录移除，此操作不可撤销。',
      detail: names.join(' · '),
      confirmText: '确认卸载',
      tone: 'danger',
    })
    if (!ok) return
    let removed = 0
    for (const name of names) {
      try {
        const r = await api<{ ok: boolean }>('/api/skills/' + encodeURIComponent(name), { method: 'DELETE' })
        if (r.ok) removed++
      } catch { /* 忽略单个失败 */ }
    }
    await loadInstalledSkills()
    ui.toast(`已卸载 ${removed} 个技能`)
  }

  /** 导出技能清单 JSON：{ skills: { name: { enabled, path, author, repo, github_url } } }
   *  - onlySelected: 仅导出选中项
   *  - includeDisabled: 包含已禁用（默认 true，因为 skill 清单通常需完整导出）
   */
  function exportSkills(opts: { onlySelected?: string[]; includeDisabled?: boolean } = {}): string {
    const onlySelected = opts.onlySelected && opts.onlySelected.length ? new Set(opts.onlySelected) : null
    const includeDisabled = opts.includeDisabled !== false
    const out: Record<string, any> = {}
    for (const s of installedSkills.value) {
      if (onlySelected && !onlySelected.has(s.name)) continue
      if (!includeDisabled && !s.enabled) continue
      const cfg: any = { enabled: s.enabled }
      if (s.path) cfg.path = s.path
      if (s.author) cfg.author = s.author
      if (s.repo) cfg.repo = s.repo
      if (s.github_url) cfg.github_url = s.github_url
      if (s.source_type) cfg.source_type = s.source_type
      out[s.name] = cfg
    }
    return JSON.stringify({ skills: out }, null, 2)
  }

  /** 导入技能清单：自动识别 JSON / YAML
   *  支持格式：
   *    { skills: { name: {...} } }   标准格式
   *    { enabled: [name, ...] }      skill.yaml 原生格式（仅启用清单）
   *    { name: {...} }               直接 key->cfg 结构
   *  导入语义：
   *    - 仅写入 skill.yaml 的启用清单（对 enabled:true 的名称调用 enable_skill）
   *    - 不安装新技能，不卸载已存在技能
   *    - mode=merge: 追加；mode=overwrite: 清空后追加
   */
  async function importSkills(text: string, mode: 'merge' | 'overwrite' = 'merge') {
    const raw = text.trim()
    if (!raw) { ui.toast('请输入或粘贴配置', 'warn'); return { ok: false, added: 0, skipped: 0 } }
    let parsed: any = null
    try { parsed = JSON.parse(raw) }
    catch {
      try { parsed = yaml.load(raw) }
      catch (e: any) { ui.toast('解析失败（JSON/YAML 均无效）: ' + e.message, 'err'); return { ok: false, added: 0, skipped: 0 } }
    }
    if (!parsed || typeof parsed !== 'object') {
      ui.toast('配置格式不正确', 'err'); return { ok: false, added: 0, skipped: 0 }
    }

    // 提取目标启用的技能名集合
    let enabledNames: string[] = []
    let extraMeta: Record<string, any> = {}
    if (Array.isArray(parsed.enabled)) {
      // skill.yaml 原生格式：{ enabled: [name, ...] }
      enabledNames = parsed.enabled.filter((n: any) => typeof n === 'string' && n)
    } else if (parsed.skills && typeof parsed.skills === 'object') {
      // 标准导出格式：{ skills: { name: { enabled, ... } } }
      for (const [name, cfg] of Object.entries(parsed.skills)) {
        const c: any = cfg
        if (c && typeof c === 'object') {
          if (c.enabled !== false) enabledNames.push(name)
          if (c.author || c.repo || c.github_url || c.path) extraMeta[name] = c
        }
      }
    } else {
      // 直接 { name: {...} } 结构
      for (const [name, cfg] of Object.entries(parsed)) {
        const c: any = cfg
        if (c && typeof c === 'object') {
          if (c.enabled !== false) enabledNames.push(name)
          if (c.author || c.repo || c.github_url || c.path) extraMeta[name] = c
        }
      }
    }

    if (!enabledNames.length) {
      ui.toast('未发现任何可启用的技能条目', 'warn')
      return { ok: false, added: 0, skipped: 0 }
    }

    // 已安装技能名集合（用于跳过未安装的）
    const installed = new Set(installedSkills.value.map((s) => s.name))

    const r = await api<{
      ok: boolean
      error?: string
      added?: number
      skipped?: number
      not_installed?: string[]
    }>('/api/skills/import', {
      method: 'POST',
      body: JSON.stringify({
        names: enabledNames,
        mode,
        ides: sync.syncTargetIdes,
      }),
    })

    if (r.ok) {
      const added = r.added ?? 0
      const skipped = r.skipped ?? 0
      const notInstalled = r.not_installed ?? []
      let msg = `已导入 ${added} 个`
      if (skipped) msg += ` · 跳过 ${skipped} 个`
      if (notInstalled.length) msg += ` · ${notInstalled.length} 个未安装已忽略`
      ui.toast(msg)
      await loadInstalledSkills()
    } else {
      ui.toast('导入失败: ' + (r.error || '未知错误'), 'err')
    }
    return {
      ok: r.ok,
      added: r.added ?? 0,
      skipped: r.skipped ?? 0,
    }
  }

  return {
    localSkills, skillFilter, skillTab, skillSources, skillMarketSources,
    skillSearchQ, skillSearchResults, skillSearchHint, skillSearched, skillSearching, skillSearchMeta,
    manualSkillInput, manualPreview, manualSelected, manualPreviewing, manualInstalling,
    installedSkills,
    listFilter, listQuery, localFilterQ,
    skillCategories, skillRoles, filteredLocalSkills, enabledInstalledCount, disabledInstalledCount,
    filteredInstalled,
    // 升级检查
    updateChecking, updateList, updateCheckedAt, updatableCount, trackedCount,
    checkUpdates, upgradeSkill, upgradeAll, fillSources,
    loadLocalSkills, searchSkills, toggleSkillSource, installFromSearch, installManualSkill,
    previewManualSource, clearManualPreview, toggleManualSkill, selectAllManualSkills, installSelectedManualSkills,
    loadInstalledSkills,
    viewSkillMd, uninstallSkill, syncToIde, onToggleSkill, toggleAllInstalled,
    toggleSkillList, deleteSkillList, exportSkills, importSkills,
  }
})
