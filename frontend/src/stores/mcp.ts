import { defineStore } from 'pinia'
import { ref, reactive, computed } from 'vue'
import { api } from '../api/client'
import { runSse } from '../api/sse'
import { useUiStore } from './ui'
import { useSyncStore } from './sync'

export const useMcpStore = defineStore('mcp', () => {
  const ui = useUiStore()
  const sync = useSyncStore()
  const mcpTemplate = reactive<any>({ mcpServers: {} })
  const mcpConfigData = reactive<any>({ mcp: {} })
  const mcpTab = ref('market')
  const mcpMarketQ = ref('')
  const mcpMarketResults = ref<any[]>([])
  const mcpSearched = ref(false)
  const mcpForm = reactive({ name:'', type:'', command:'', args:'', url:'', headers:'', env:'', paste:'' })
  const editingMcp = ref('')
  const editMcpForm = reactive({ type:'', command:'', args:'', url:'', headers:'', env:'' })
  const mcpEnabledCount = computed(() =>
    Object.values(mcpTemplate.mcpServers || {}).filter((c:any) => !(c.disabled === true || c.disabled === 'true')).length
  )

  async function loadMcpCatalog() {
    const r = await api<{ ok: boolean; data?: any }>('/api/mcp/list')
    if (r.ok) Object.assign(mcpTemplate, r.data)
  }
  async function loadMcpConfig() {
    const r = await api<{ ok: boolean; data?: any }>('/api/mcp-config')
    if (r.ok) {
      Object.keys(mcpConfigData.mcp).forEach((k) => delete mcpConfigData.mcp[k])
      Object.assign(mcpConfigData.mcp, (r.data && r.data.mcp) || {})
    }
    return r
  }
  async function searchMcpMarket() {
    if (!mcpMarketQ.value.trim()) return
    mcpSearched.value = true
    const r = await api<{ ok: boolean; data?: any[]; error?: string }>('/api/mcp/search?q=' + encodeURIComponent(mcpMarketQ.value))
    if (r.ok) mcpMarketResults.value = r.data || []
    else ui.toast('搜索失败: ' + r.error, 'err')
  }
  async function getMcpDetail(owner: string, name: string) {
    const r = await api<{ ok: boolean; data?: any; error?: string }>('/api/mcp/detail?owner=' + encodeURIComponent(owner) + '&name=' + encodeURIComponent(name))
    if (r.ok) ui.showModal(owner + '/' + name, JSON.stringify(r.data, null, 2))
    else ui.toast('获取失败: ' + r.error, 'err')
  }
  async function addMarketMcpToTemplate(owner: string, name: string, localName: string) {
    const r = await api<{ ok: boolean; data?: any; error?: string }>('/api/mcp/detail?owner=' + encodeURIComponent(owner) + '&name=' + encodeURIComponent(name))
    if (!r.ok) { ui.toast('获取失败: ' + r.error, 'err'); return }
    const data = r.data || {}
    const servers = data.servers || data.mcp_servers || []
    let cfg: any
    if (servers.length) {
      const s = servers[0]
      cfg = { type: s.type, url: s.url }
      if (data.auth_required) cfg.headers = { Authorization: 'Bearer ${MODELSCOPE_TOKEN}' }
    } else if (data.server_config) {
      cfg = data.server_config
    } else { ui.toast('未找到 server_config', 'warn'); return }
    mcpTemplate.mcpServers[localName] = cfg
    const sr = await api('/api/mcp/save', { method: 'POST', body: JSON.stringify({ data: mcpTemplate }) })
    sr.ok ? ui.toast('已添加 ' + localName) : ui.toast('保存失败: ' + sr.error, 'err')
  }
  async function toggleMcpDisabled(name: string, enabled: boolean) {
    mcpTemplate.mcpServers[name].disabled = !enabled
    await api('/api/mcp/save', { method: 'POST', body: JSON.stringify({ data: mcpTemplate }) })
  }
  async function deleteMcpEntry(name: string) {
    if (!confirm('删除 ' + name + '?')) return
    delete mcpTemplate.mcpServers[name]
    await api('/api/mcp/save', { method: 'POST', body: JSON.stringify({ data: mcpTemplate }) })
  }
  async function saveMcpTemplate() {
    const r = await api<{ ok: boolean; error?: string }>('/api/mcp/save', { method: 'POST', body: JSON.stringify({ data: mcpTemplate }) })
    r.ok ? ui.toast('模板已保存') : ui.toast('保存失败: ' + r.error, 'err')
  }
  async function generateMcpRuntime() {
    const r = await api<{ ok: boolean; stdout?: string; stderr?: string; error?: string }>('/api/init-env', { method: 'POST' })
    if (r.ok) { ui.toast('mcp.json 已生成'); if (r.stdout) ui.showModal('init-env 输出', r.stdout + (r.stderr ? '\n--- stderr ---\n' + r.stderr : '')) }
    else ui.toast('生成失败: ' + r.error, 'err')
  }
  function parsePastedMcp() {
    if (!mcpForm.paste.trim()) { ui.toast('请粘贴配置', 'warn'); return }
    try {
      let p = JSON.parse(mcpForm.paste)
      if (p.mcpServers) p = p.mcpServers
      const k = Object.keys(p)[0]
      if (k) {
        const cfg = p[k]
        mcpForm.name = k
        if (cfg.command) mcpForm.command = cfg.command
        if (cfg.args) mcpForm.args = cfg.args.join(',')
        if (cfg.url) mcpForm.url = cfg.url
        if (cfg.type) mcpForm.type = cfg.type
        if (cfg.headers) mcpForm.headers = JSON.stringify(cfg.headers, null, 2)
        if (cfg.env) mcpForm.env = JSON.stringify(cfg.env, null, 2)
        ui.toast('已解析')
      }
    } catch (e: any) { ui.toast('JSON 解析失败: ' + e.message, 'err') }
  }
  async function addManualMcp() {
    if (!mcpForm.name.trim()) { ui.toast('name 必填', 'warn'); return }
    const cfg: any = {}
    if (mcpForm.type) cfg.type = mcpForm.type
    if (mcpForm.command) cfg.command = mcpForm.command
    if (mcpForm.args.trim()) cfg.args = mcpForm.args.split(',').map((s:string)=>s.trim()).filter(Boolean)
    if (mcpForm.url) cfg.url = mcpForm.url
    try { if (mcpForm.headers.trim()) cfg.headers = JSON.parse(mcpForm.headers) } catch { ui.toast('headers JSON 错误', 'err'); return }
    try { if (mcpForm.env.trim()) cfg.env = JSON.parse(mcpForm.env) } catch { ui.toast('env JSON 错误', 'err'); return }
    mcpTemplate.mcpServers[mcpForm.name.trim()] = cfg
    const r = await api('/api/mcp/save', { method: 'POST', body: JSON.stringify({ data: mcpTemplate }) })
    r.ok ? ui.toast('已添加 ' + mcpForm.name) : ui.toast('保存失败: ' + r.error, 'err')
  }
  async function toggleAllMcp(enabled: boolean) {
    for (const name of Object.keys(mcpTemplate.mcpServers || {})) {
      mcpTemplate.mcpServers[name].disabled = !enabled
    }
    await api('/api/mcp/save', { method: 'POST', body: JSON.stringify({ data: mcpTemplate }) })
    ui.toast(enabled ? '已全部启用' : '已全部禁用')
  }
  async function saveMcpAll(silent = false) {
    const r1 = await api('/api/mcp/save', { method: 'POST', body: JSON.stringify({ data: mcpTemplate }) })
    const r2 = await api('/api/mcp-config', { method: 'POST', body: JSON.stringify({ data: mcpConfigData }) })
    if (!silent) (r1.ok && r2.ok) ? ui.toast('mcp.yaml 已保存') : ui.toast('保存失败', 'err')
    return r1.ok && r2.ok
  }
  async function syncMcpFull() {
    if (sync.syncing) { ui.toast('正在同步中，请稍候', 'warn'); return }
    const r1 = await api('/api/mcp/save', { method: 'POST', body: JSON.stringify({ data: mcpTemplate }) })
    const r2 = await api('/api/mcp-config', { method: 'POST', body: JSON.stringify({ data: mcpConfigData }) })
    if (!r1.ok || !r2.ok) { ui.toast('保存 mcp.yaml 失败', 'err'); return }
    const g = await api('/api/init-env', { method: 'POST' })
    if (!g.ok) { ui.toast('生成 mcp.json 失败', 'err'); return }
    ui.clearLog()
    for (const ideKey of sync.syncTargetIdes) {
      await runSse('/api/init-ide?ide=' + encodeURIComponent(ideKey) + '&scope=mcp', (line) => ui.appendLog(line))
    }
  }
  function startEditMcp(name: string) {
    const cfg = mcpTemplate.mcpServers[name]
    editingMcp.value = name
    editMcpForm.type = cfg.type || ''
    editMcpForm.command = cfg.command || ''
    editMcpForm.args = (cfg.args || []).join(', ')
    editMcpForm.url = cfg.url || ''
    editMcpForm.headers = cfg.headers ? JSON.stringify(cfg.headers, null, 2) : ''
    editMcpForm.env = cfg.env ? JSON.stringify(cfg.env, null, 2) : ''
  }
  function cancelEditMcp() { editingMcp.value = '' }
  async function saveEditMcp() {
    const name = editingMcp.value
    if (!name) return
    const cfg = mcpTemplate.mcpServers[name]
    const disabled = cfg.disabled
    const newCfg: any = {}
    if (editMcpForm.type) newCfg.type = editMcpForm.type
    if (editMcpForm.command) newCfg.command = editMcpForm.command
    if (editMcpForm.args.trim()) newCfg.args = editMcpForm.args.split(',').map((s:string)=>s.trim()).filter(Boolean)
    if (editMcpForm.url) newCfg.url = editMcpForm.url
    try { if (editMcpForm.headers.trim()) newCfg.headers = JSON.parse(editMcpForm.headers) } catch { ui.toast('headers JSON 错误', 'err'); return }
    try { if (editMcpForm.env.trim()) newCfg.env = JSON.parse(editMcpForm.env) } catch { ui.toast('env JSON 错误', 'err'); return }
    if (disabled !== undefined) newCfg.disabled = disabled
    mcpTemplate.mcpServers[name] = newCfg
    editingMcp.value = ''
    const r = await api('/api/mcp/save', { method: 'POST', body: JSON.stringify({ data: mcpTemplate }) })
    r.ok ? ui.toast('已保存 ' + name) : ui.toast('保存失败: ' + r.error, 'err')
  }
  async function saveMcpConfig() {
    const r = await api('/api/mcp-config', { method: 'POST', body: JSON.stringify({ data: mcpConfigData }) })
    r.ok ? ui.toast('mcp.yaml 已保存') : ui.toast('保存失败: ' + r.error, 'err')
  }
  function addMcpConfigKey() {
    const key = prompt('请输入 MCP 密钥名称（如 TAVILY_API_KEY）')
    if (!key || !key.trim()) return
    const t = key.trim()
    if (mcpConfigData.mcp[t]) { ui.toast('Key 已存在', 'warn'); return }
    mcpConfigData.mcp[t] = ''
    ui.toast('已添加: ' + t)
  }
  async function deleteMcpConfigKey(key: string) {
    if (!confirm('删除 key "' + key + '"？')) return
    const r = await api('/api/mcp-config/key/' + encodeURIComponent(key), { method: 'DELETE' })
    if (r.ok) { delete mcpConfigData.mcp[key]; ui.toast('已删除') }
    else ui.toast('删除失败: ' + r.error, 'err')
  }

  return {
    mcpTemplate, mcpConfigData, mcpTab, mcpMarketQ, mcpMarketResults, mcpSearched,
    mcpForm, editingMcp, editMcpForm, mcpEnabledCount,
    loadMcpCatalog, loadMcpConfig, searchMcpMarket, getMcpDetail, addMarketMcpToTemplate,
    toggleMcpDisabled, deleteMcpEntry, saveMcpTemplate, generateMcpRuntime,
    parsePastedMcp, addManualMcp, toggleAllMcp, saveMcpAll, syncMcpFull,
    startEditMcp, cancelEditMcp, saveEditMcp, saveMcpConfig, addMcpConfigKey, deleteMcpConfigKey,
  }
})
