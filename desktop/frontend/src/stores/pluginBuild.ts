import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import { api } from '../api/client'
import { runSse } from '../api/sse'
import { useUiStore } from './ui'
import { useSyncStore } from './sync'
import { useSkillStore } from './skill'
import { useMcpStore } from './mcp'
import { useEnvStore } from './env'
import { usePluginStore } from './plugin'
import { useKeysStore } from './keys'

export const wizardSteps = [
  { title: '扫描 IDE', desc: '一键扫描本地 IDE 已配置的 LLM / MCP / Skill' },
  { title: 'LLM', desc: '选择要导入的 LLM Provider' },
  { title: 'MCP', desc: '选择要导入的 MCP 服务' },
  { title: 'Skills', desc: '选择要导入的技能' },
  { title: 'Subagent', desc: '选择要打包的 Subagent 角色' },
  { title: 'Rules/Cmd', desc: '选择 Rules 和 Commands，配置 Hooks' },
  { title: '命名生成', desc: '填写插件名称并生成' },
]

export const usePluginBuildStore = defineStore('pluginBuild', () => {
  const ui = useUiStore()
  const sync = useSyncStore()
  const skill = useSkillStore()
  const mcp = useMcpStore()
  const env = useEnvStore()
  const plugin = usePluginStore()
  const keysStore = useKeysStore()

  const pluginForm = reactive({ name: '', version: '1.0.0', description: '', author: 'AgentBuddy', install_script: '' })
  // 已加载插件的标准元数据（load → edit → save 时保留，避免丢失 license/keywords/categories 等字段）
  const loadedMeta = ref<Record<string, any>>({})
  const selectedSkills = ref<string[]>([])
  const selectedMcp = ref<string[]>([])
  const selectedLlm = ref<string[]>([])
  // 新增：Subagent / Rules / Commands / Hooks
  const selectedSubagents = ref<string[]>([])
  const selectedRules = ref<string[]>([])
  const selectedCommands = ref<string[]>([])
  const selectedKeys = ref<string[]>([])
  const hooksEnabled = ref(false)
  const memoryEnabled = ref(false)
  // 源数据
  const availableSubagents = ref<any[]>([])
  const availableRules = ref<any[]>([])
  const availableCommands = ref<any[]>([])

  const ideImport = ref<any>({})
  const ideImportStats = ref<any>(null)
  const importedIdeMcp = ref<string[]>([])
  const importedIdeSkills = ref<string[]>([])
  const wizardStep = ref(0)
  const buildMode = ref('local')
  const mcpFilterText = ref('')
  const importing = ref(false)

  function toggleSkill(name: string) {
    const i = selectedSkills.value.indexOf(name)
    if (i >= 0) selectedSkills.value.splice(i, 1); else selectedSkills.value.push(name)
  }
  function toggleMcp(name: string) {
    const i = selectedMcp.value.indexOf(name)
    if (i >= 0) selectedMcp.value.splice(i, 1); else selectedMcp.value.push(name)
  }
  function toggleLlm(key: string) {
    const i = selectedLlm.value.indexOf(key)
    if (i >= 0) selectedLlm.value.splice(i, 1); else selectedLlm.value.push(key)
  }
  function toggleSubagent(name: string) {
    const i = selectedSubagents.value.indexOf(name)
    if (i >= 0) selectedSubagents.value.splice(i, 1); else selectedSubagents.value.push(name)
  }
  function toggleRule(path: string) {
    const i = selectedRules.value.indexOf(path)
    if (i >= 0) selectedRules.value.splice(i, 1); else selectedRules.value.push(path)
  }
  function toggleCommand(name: string) {
    const i = selectedCommands.value.indexOf(name)
    if (i >= 0) selectedCommands.value.splice(i, 1); else selectedCommands.value.push(name)
  }
  function toggleKey(key: string) {
    const i = selectedKeys.value.indexOf(key)
    if (i >= 0) selectedKeys.value.splice(i, 1); else selectedKeys.value.push(key)
  }
  function llmKey(l: any) { return l.provider + '@' + l.protocol }
  function wizardNext() { if (wizardStep.value < wizardSteps.length - 1) wizardStep.value++ }
  function wizardPrev() { if (wizardStep.value > 0) wizardStep.value-- }
  function wizardGoto(i: number) { wizardStep.value = i }
  function newPlugin() {
    plugin.selectedPluginFile = ''
    pluginForm.name = ''; pluginForm.version = '1.0.0'; pluginForm.description = ''
    pluginForm.author = 'AgentBuddy'; pluginForm.install_script = ''
    loadedMeta.value = {}
    selectedSkills.value = []; selectedMcp.value = []; selectedLlm.value = []
    selectedSubagents.value = []; selectedRules.value = []; selectedCommands.value = []
    selectedKeys.value = []
    hooksEnabled.value = false
    memoryEnabled.value = false
    wizardStep.value = 0
  }
  /** 加载 Subagent / Rules / Commands 源数据（并行） */
  async function loadBuildSources() {
    const [saRes, rulesRes, cmdRes] = await Promise.all([
      api<any>('/api/subagent'),
      api<any>('/api/rules'),
      api<any>('/api/cmd'),
    ])
    if (saRes.ok) availableSubagents.value = saRes.data?.subagents || []
    if (rulesRes.ok) availableRules.value = rulesRes.data || []
    if (cmdRes.ok) availableCommands.value = cmdRes.data?.commands || []
    // 加载密钥库（供构建页选择要打包的密钥）
    await keysStore.loadKeys()
  }
  async function importFromIde() {
    if (importing.value) return
    importing.value = true
    try {
      const r = await api<any>('/api/plugin/import-from-ide')
      if (!r.ok) { ui.toast('扫描失败: ' + (r.error || '未知错误'), 'err'); return }
      ideImport.value = r
      ideImportStats.value = r.stats || {}
      importedIdeMcp.value = []
      importedIdeSkills.value = []
      ui.toast(`扫描完成: ${ideImportStats.value.mcp_count || 0} MCP、${ideImportStats.value.skill_count || 0} skill、${ideImportStats.value.llm_count || 0} LLM`)
    } catch (e: any) {
      ui.toast('扫描失败: ' + e.message, 'err')
    } finally {
      importing.value = false
    }
  }
  function importAllIdeMcp() {
    const all = Object.keys(ideImport.value.mcpServers || {})
    importedIdeMcp.value = importedIdeMcp.value.length === all.length ? [] : all
  }
  function importAllIdeSkills() {
    const all = (ideImport.value.skills || []).map((s: any) => s.name)
    importedIdeSkills.value = importedIdeSkills.value.length === all.length ? [] : all
  }
  function applyImportedMcp() {
    const existing = mcp.mcpTemplate.mcpServers || {}
    const ideMcp = ideImport.value.mcpServers || {}
    let added = 0
    for (const name of importedIdeMcp.value) {
      if (!(name in existing)) { existing[name] = ideMcp[name]; added++ }
    }
    mcp.mcpTemplate.mcpServers = existing
    selectedMcp.value = Object.keys(existing)
    ui.toast(`已导入 ${importedIdeMcp.value.length} 个 MCP（新增 ${added}）`)
  }
  function applyImportedSkills() {
    const set = new Set(selectedSkills.value)
    let added = 0
    for (const name of importedIdeSkills.value) {
      if (!set.has(name)) { set.add(name); added++ }
    }
    selectedSkills.value = Array.from(set)
    ui.toast(`已导入 ${importedIdeSkills.value.length} 个 Skill（新增 ${added}）`)
  }
  function applyImportedLlm() {
    const set = new Set(selectedLlm.value)
    let added = 0
    for (const l of (ideImport.value.llm_providers || [])) {
      const k = llmKey(l)
      if (!set.has(k)) { set.add(k); added++ }
    }
    selectedLlm.value = Array.from(set)
    ui.toast(`已导入 ${added} 个 LLM 配置`)
  }
  async function loadExistingPlugin() {
    if (!plugin.selectedPluginFile) { ui.toast('请选择插件', 'warn'); return }
    const r = await api<any>('/api/plugin/load?file=' + encodeURIComponent(plugin.selectedPluginFile))
    if (!r.ok) { ui.toast('加载失败: ' + r.error, 'err'); return }
    const d = r.data
    pluginForm.name = d.name || ''; pluginForm.version = d.version || '1.0.0'
    pluginForm.description = d.description || ''; pluginForm.author = d.author || 'AgentBuddy'
    // 兼容 scripts.install（新格式 npm 生命周期）/ scripts.init（旧格式，等价 postinstall）
    pluginForm.install_script = (d.scripts && (d.scripts.install || d.scripts.postinstall || d.scripts.init)) || ''
    selectedSkills.value = [...(d.skills || [])].map((s:any) => typeof s === 'string' ? s : s.name || s.skill || '')
    selectedMcp.value = Object.keys(d.mcpServers || {})
    selectedLlm.value = (d.llm || []).map((l:any) => l.provider + '@' + l.protocol)
    selectedSubagents.value = [...(d.subagents || [])]
    selectedRules.value = [...(d.rules || [])]
    selectedCommands.value = [...(d.commands || [])]
    selectedKeys.value = [...(d.keys || [])]
    hooksEnabled.value = !!d.hooks
    memoryEnabled.value = !!d.memory
    // 保留标准元数据字段（load → edit → save 不丢失）
    const metaKeys = ['license', 'keywords', 'categories', 'homepage', 'repository', 'icon',
                      'defaultEnabled', 'dependencies', 'userConfig', 'interface', 'apps', 'channels']
    loadedMeta.value = {}
    for (const k of metaKeys) if (d[k] !== undefined) loadedMeta.value[k] = d[k]
    ui.toast('已加载: ' + d.name)
  }
  function buildPluginConfig() {
    const llmList = selectedLlm.value.map(key => {
      const [provider, protocol] = key.split('@')
      const found = (ideImport.value.llm_providers || []).find((l:any) => l.provider === provider && l.protocol === protocol)
      let base_url = found ? found.base_url : ''
      let models = found ? (found.models || []) : []
      if (!found) {
        const cfg = env.envData.llm && env.envData.llm[provider] && env.envData.llm[provider][protocol]
        if (cfg) {
          base_url = cfg.base_url || ''
          models = Object.keys(cfg.models || {}).map((m:string) => ({ id: m, name: (cfg.models[m] && cfg.models[m].name) || m }))
        }
      }
      return { provider, protocol, base_url, models }
    }).filter((l:any) => l.provider)
    const skillsOut = selectedSkills.value.map(name => {
      const meta = skill.localSkills.find((s:any) => s.skill_name === name) || {}
      const entry: any = { name, description: meta.description || '' }
      const st = (meta.source_type || '').toLowerCase()
      if (st === 'remote' && meta.source) { entry.source = meta.source; if (meta.url) entry.url = meta.url }
      else if (st === 'local' || !st) { entry.source = meta.source || name }
      else if (meta.source) { entry.source = meta.source }
      return entry
    })
    return {
      name: pluginForm.name.trim(), version: pluginForm.version.trim() || '1.0.0',
      description: pluginForm.description.trim(), author: pluginForm.author.trim() || 'AgentBuddy',
      ...loadedMeta.value,  // 保留 license/keywords/categories/homepage/repository 等标准字段
      mcpServers: Object.fromEntries(selectedMcp.value.map(n => [n, mcp.mcpTemplate.mcpServers[n]])),
      skills: skillsOut, llm: llmList,
      subagents: selectedSubagents.value,
      rules: selectedRules.value,
      commands: selectedCommands.value,
      keys: selectedKeys.value,
      hooks: hooksEnabled.value,
      memory: memoryEnabled.value,
      scripts: pluginForm.install_script.trim() ? { install: pluginForm.install_script.trim() } : {},
    }
  }
  function previewPlugin() {
    const cfg = buildPluginConfig()
    if (!cfg.name) { ui.toast('name 必填', 'warn'); return }
    ui.showModal('plugin.yaml 预览', JSON.stringify(cfg, null, 2))
  }
  async function savePluginFile() {
    const cfg = buildPluginConfig()
    if (!cfg.name) { ui.toast('name 必填', 'warn'); return }
    const r = await api<any>('/api/plugin/save', { method: 'POST', body: JSON.stringify(cfg) })
    r.ok ? ui.toast('已保存: ' + r.path) : ui.toast('保存失败: ' + r.error, 'err')
    plugin.refreshPluginList()
  }
  async function installPluginFile() {
    const cfg = buildPluginConfig()
    if (!cfg.name) { ui.toast('name 必填', 'warn'); return }
    const sr = await api('/api/plugin/save', { method: 'POST', body: JSON.stringify(cfg) })
    if (!sr.ok) { ui.toast('保存失败', 'err'); return }
    const safe = cfg.name.replace(/[^a-zA-Z0-9_-]/g, '')
    const ides = sync.syncTargetIdes.join(',')
    ui.clearLog()
    await runSse('/api/plugin/install?file=' + encodeURIComponent(safe + '.plugin.yaml') + '&ide=' + encodeURIComponent(ides),
      (line) => ui.appendLog(line),
      { onDone: () => { skill.loadInstalledSkills(); plugin.refreshPluginList() } })
  }

  return {
    pluginForm, selectedSkills, selectedMcp, selectedLlm,
    selectedSubagents, selectedRules, selectedCommands, selectedKeys, hooksEnabled, memoryEnabled,
    availableSubagents, availableRules, availableCommands,
    ideImport, ideImportStats, importedIdeMcp, importedIdeSkills, wizardStep, buildMode, mcpFilterText, importing,
    toggleSkill, toggleMcp, toggleLlm, toggleSubagent, toggleRule, toggleCommand, toggleKey,
    llmKey, wizardNext, wizardPrev, wizardGoto, newPlugin, loadBuildSources,
    importFromIde, importAllIdeMcp, importAllIdeSkills, applyImportedMcp, applyImportedSkills, applyImportedLlm,
    loadExistingPlugin, buildPluginConfig, previewPlugin, savePluginFile, installPluginFile,
  }
})
