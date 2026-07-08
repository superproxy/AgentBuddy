import { defineStore } from 'pinia'
import { reactive, computed } from 'vue'
import { api } from '../api/client'
import { runSse } from '../api/sse'
import { useUiStore } from './ui'

export const useEnvStore = defineStore('env', () => {
  const ui = useUiStore()
  const envData = reactive<any>({ llm: {}, proxy: {} })
  const envDataText = reactive<Record<string, string>>({})
  const openedProviders = reactive(new Set<string>())

  const providerNames = computed(() =>
    Object.keys(envData.llm || {}).filter(
      (k) => !k.startsWith('_') && envData.llm[k] && typeof envData.llm[k] === 'object',
    ),
  )
  const proxyEnabled = computed(() => envData.proxy && envData.proxy.enable)

  async function loadEnv() {
    const r = await api<{ ok: boolean; data?: any; error?: string }>('/api/llm')
    if (!r.ok) { ui.toast('加载 llm.yaml 失败: ' + r.error, 'err'); return }
    Object.assign(envData, r.data)
    ;['embedding', 'tts', 'asr', 'vision', 'misc'].forEach((sec) => {
      envDataText[sec] = JSON.stringify((envData as any)[sec] || {}, null, 2)
    })
  }
  function toggleProvider(name: string) {
    if (openedProviders.has(name)) openedProviders.delete(name)
    else openedProviders.add(name)
  }
  function updateEnvDataSection(sec: string) {
    try { (envData as any)[sec] = JSON.parse(envDataText[sec] || '{}') } catch { /* ignore */ }
  }
  function addProvider() {
    const name = prompt('请输入 Provider 名称')
    if (!name || !name.trim()) return
    const t = name.trim()
    if (envData.llm[t]) { ui.toast('Provider 已存在', 'warn'); return }
    envData.llm[t] = { openai: { base_url: '', api_key: '', models: {} } }
    if (!envData.llm._active_provider) envData.llm._active_provider = t
    ui.toast('已添加 Provider: ' + t)
  }
  function deleteProvider(name: string) {
    if (!confirm('删除 Provider "' + name + '"？')) return
    delete envData.llm[name]
    if (envData.llm._active_provider === name) envData.llm._active_provider = providerNames.value[0] || ''
    ui.toast('已删除')
  }
  function setActiveProvider(name: string) {
    envData.llm._active_provider = name
    ui.toast('Active 设为: ' + name)
  }
  function addProtocol(pn: string) {
    const proto = prompt('协议名称（如 openai/anthropic）')
    if (!proto || !proto.trim()) return
    const t = proto.trim().toLowerCase()
    if (envData.llm[pn][t]) { ui.toast('协议已存在', 'warn'); return }
    envData.llm[pn][t] = { base_url: '', api_key: '', models: {} }
  }
  function deleteProtocol(pn: string, proto: string) {
    if (confirm('删除协议 "' + proto + '"？')) delete envData.llm[pn][proto]
  }
  function addModel(pn: string, proto: string) {
    envData.llm[pn][proto].models = envData.llm[pn][proto].models || {}
    const k = 'new-model-' + Date.now()
    envData.llm[pn][proto].models[k] = { name: k }
  }
  function deleteModel(pn: string, proto: string, mk: string) {
    delete envData.llm[pn][proto].models[mk]
  }
  function renameModel(pn: string, proto: string, oldKey: string, newKey: string) {
    if (oldKey === newKey) return
    const m = envData.llm[pn][proto].models
    m[newKey] = m[oldKey]
    delete m[oldKey]
  }
  async function saveEnv(silent = false) {
    const r = await api<{ ok: boolean; error?: string }>('/api/llm', {
      method: 'POST', body: JSON.stringify({ data: envData }),
    })
    if (!silent) r.ok ? ui.toast('llm.yaml 已保存') : ui.toast('保存失败: ' + r.error, 'err')
    return r.ok
  }
  async function generateProxyConfig() {
    const sr = await api<{ ok: boolean }>('/api/llm', { method: 'POST', body: JSON.stringify({ data: envData }) })
    if (!sr.ok) { ui.toast('llm.yaml 保存失败', 'err'); return }
    const r = await api<{ ok: boolean; stdout?: string; stderr?: string }>('/api/init-env', { method: 'POST' })
    if (r.ok) {
      ui.toast('proxy/config.yaml 已生成')
      if (r.stdout) ui.showModal('init-env 输出', r.stdout + (r.stderr ? '\n--- stderr ---\n' + r.stderr : ''))
    } else { ui.toast('生成失败', 'err') }
  }
  async function startProxyServer() {
    if (!proxyEnabled.value) { ui.toast('请先开启 proxy', 'warn'); return }
    const cmd = envData.proxy.start_cmd || 'litellm --config proxy/config.yaml --port 4000'
    ui.clearLog()
    await runSse('/api/proxy/start?cmd=' + encodeURIComponent(cmd), (line) => ui.appendLog(line))
  }

  async function verifyLlm(pn: string, proto: string) {
    const cfg = envData.llm[pn][proto]
    if (!cfg || !cfg.base_url || !cfg.api_key) { ui.toast('请先填 base_url 和 api_key', 'warn'); return }
    ui.toast('验证中...', 'ok')
    const r = await api<{ ok: boolean; models?: string[]; error?: string }>('/api/llm/verify', {
      method: 'POST', body: JSON.stringify({ base_url: cfg.base_url, api_key: cfg.api_key, protocol: proto }),
    })
    if (r.ok) {
      ui.toast(`验证成功，${r.models?.length || 0} 个模型可用`)
      if (r.models && r.models.length) {
        const newModels: any = {}
        for (const m of r.models) newModels[m] = { name: m }
        cfg.models = newModels
      }
    } else {
      ui.toast('验证失败: ' + r.error, 'err')
    }
  }

  return {
    envData, envDataText, openedProviders, providerNames, proxyEnabled,
    loadEnv, toggleProvider, updateEnvDataSection, addProvider, deleteProvider, setActiveProvider,
    addProtocol, deleteProtocol, addModel, deleteModel, renameModel, saveEnv,
    generateProxyConfig, startProxyServer, verifyLlm,
  }
})
