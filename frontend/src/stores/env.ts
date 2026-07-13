import { defineStore } from 'pinia'
import { reactive, computed, ref } from 'vue'
import { api } from '../api/client'
import { runSse } from '../api/sse'
import { useUiStore } from './ui'

export interface ProviderCandidate {
  provider: string
  label?: string
  family?: string
  score?: number
  reason?: string
  protocols?: Record<string, { base_url?: string; models?: Record<string, { name?: string }> }>
  detected_protocol?: string
  protocol_reason?: string
  suggested_protocol?: string
  active_protocol?: string
}

export type SmartFlowStep =
  | 'idle'
  | 'key'
  | 'detecting'
  | 'choose'
  | 'custom_url'
  | 'applying'
  | 'done'
  | 'error'

export interface SmartFlowLog {
  cls: 'run' | 'ok' | 'err' | ''
  text: string
}

export interface SmartFlowResult {
  provider: string
  label?: string
  protocol: string
  models: number
  url: string
}

export const useEnvStore = defineStore('env', () => {
  const ui = useUiStore()
  const envData = reactive<any>({ llm: {}, proxy: {} })
  const envDataText = reactive<Record<string, string>>({})
  const selectedProvider = ref('')
  const smartFlow = reactive({
    visible: false,
    step: 'idle' as SmartFlowStep,
    apiKey: '',
    baseUrl: '',
    candidates: [] as ProviderCandidate[],
    selected: '',
    logs: [] as SmartFlowLog[],
    error: '',
    result: null as SmartFlowResult | null,
    busy: false,
  })
  const smartBusy = computed(() =>
    smartFlow.busy || (smartFlow.visible && ['detecting', 'applying'].includes(smartFlow.step)),
  )

  const providerNames = computed(() =>
    Object.keys(envData.llm || {}).filter(
      (k) => !k.startsWith('_') && envData.llm[k] && typeof envData.llm[k] === 'object',
    ),
  )
  const proxyEnabled = computed(() => envData.proxy && envData.proxy.enable)

  function ensureSelectedProvider(prefer?: string) {
    const names = providerNames.value
    if (prefer && names.includes(prefer)) {
      selectedProvider.value = prefer
      return
    }
    if (selectedProvider.value && names.includes(selectedProvider.value)) return
    const active = envData.llm?._active_provider
    selectedProvider.value = (active && names.includes(active) ? active : names[0]) || ''
  }

  function replaceEnvData(data: any) {
    Object.keys(envData).forEach((k) => delete (envData as any)[k])
    Object.assign(envData, data || { llm: {}, proxy: {} })
    if (!envData.llm) envData.llm = {}
    if (!envData.proxy) envData.proxy = {}
    ;['embedding', 'tts', 'asr', 'vision', 'misc'].forEach((sec) => {
      envDataText[sec] = JSON.stringify((envData as any)[sec] || {}, null, 2)
    })
    ensureSelectedProvider()
  }

  async function loadEnv() {
    const r = await api<{ ok: boolean; data?: any; error?: string }>('/api/llm')
    if (!r.ok) { ui.toast('加载 llm.yaml 失败: ' + r.error, 'err'); return }
    replaceEnvData(r.data)
  }
  function selectProvider(name: string) {
    selectedProvider.value = name
  }
  function updateEnvDataSection(sec: string) {
    try { (envData as any)[sec] = JSON.parse(envDataText[sec] || '{}') } catch { /* ignore */ }
  }
  async function addProvider() {
    const name = await ui.askPrompt({
      title: '添加 Provider',
      message: '写入 llm.yaml 的厂商标识，建议使用小写英文。',
      label: 'Provider 名称',
      placeholder: '例如 deepseek / openai / moonshot',
      confirmText: '添加',
      mono: true,
      validate: (v) => {
        if (!v) return '请输入 Provider 名称'
        if (envData.llm[v]) return 'Provider 已存在'
        if (!/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$/.test(v)) return '仅支持字母、数字、点、下划线、连字符'
        return null
      },
    })
    if (!name) return
    const t = name.trim()
    envData.llm[t] = { openai: { base_url: '', api_key: '', models: {} } }
    if (!envData.llm._active_provider) envData.llm._active_provider = t
    selectProvider(t)
    ui.toast('已添加 Provider: ' + t)
  }
  async function deleteProvider(name: string) {
    const ok = await ui.askConfirm({
      title: '删除 Provider',
      message: '删除后不可恢复，相关协议与模型配置会一并移除。',
      detail: name,
      confirmText: '删除',
      tone: 'danger',
    })
    if (!ok) return
    delete envData.llm[name]
    if (envData.llm._active_provider === name) envData.llm._active_provider = providerNames.value[0] || ''
    ensureSelectedProvider()
    ui.toast('已删除')
  }
  function setActiveProvider(name: string) {
    envData.llm._active_provider = name
    ui.toast('Active 设为: ' + name)
  }
  async function addProtocol(pn: string) {
    const proto = await ui.askPrompt({
      title: '添加协议',
      message: `为 ${pn} 新增协议配置块。`,
      label: '协议名称',
      placeholder: 'openai 或 anthropic',
      defaultValue: 'openai',
      confirmText: '添加',
      mono: true,
      validate: (v) => {
        const t = v.toLowerCase()
        if (!t) return '请输入协议名称'
        if (envData.llm[pn]?.[t]) return '协议已存在'
        if (!/^[a-z][a-z0-9_-]{0,31}$/.test(t)) return '建议使用小写协议名，如 openai / anthropic'
        return null
      },
    })
    if (!proto) return
    const t = proto.trim().toLowerCase()
    envData.llm[pn][t] = { base_url: '', api_key: '', models: {} }
  }
  async function deleteProtocol(pn: string, proto: string) {
    const ok = await ui.askConfirm({
      title: '删除协议',
      message: `将从 ${pn} 中移除该协议及其模型列表。`,
      detail: proto,
      confirmText: '删除',
      tone: 'danger',
    })
    if (!ok) return
    delete envData.llm[pn][proto]
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

  async function verifyLlm(pn: string, proto: string, silent = false) {
    const cfg = envData.llm[pn]?.[proto]
    if (!cfg || !cfg.base_url || !cfg.api_key) {
      if (!silent) ui.toast('请先填 base_url 和 api_key', 'warn')
      return false
    }
    if (!silent) ui.toast('验证中...', 'ok')
    const r = await api<{ ok: boolean; models?: string[]; error?: string }>('/api/llm/verify', {
      method: 'POST', body: JSON.stringify({ base_url: cfg.base_url, api_key: cfg.api_key, protocol: proto }),
    })
    if (r.ok) {
      if (!silent) ui.toast(`验证成功，${r.models?.length || 0} 个模型可用`)
      if (r.models && r.models.length) {
        const newModels: any = {}
        for (const m of r.models) newModels[m] = { name: m }
        cfg.models = newModels
      }
      return true
    }
    if (!silent) ui.toast('验证失败: ' + r.error, 'err')
    return false
  }

  function pushSmartLog(cls: SmartFlowLog['cls'], text: string) {
    smartFlow.logs.push({ cls, text })
  }

  function resetSmartFlow() {
    smartFlow.visible = false
    smartFlow.step = 'idle'
    smartFlow.apiKey = ''
    smartFlow.baseUrl = ''
    smartFlow.candidates = []
    smartFlow.selected = ''
    smartFlow.logs = []
    smartFlow.error = ''
    smartFlow.result = null
    smartFlow.busy = false
  }

  function cancelSmartPicker() {
    if (smartFlow.busy && smartFlow.step === 'applying') return
    resetSmartFlow()
  }

  function openSmartFlow() {
    if (smartFlow.busy) return
    smartFlow.visible = true
    smartFlow.step = 'key'
    smartFlow.apiKey = ''
    smartFlow.baseUrl = ''
    smartFlow.candidates = []
    smartFlow.selected = ''
    smartFlow.logs = []
    smartFlow.error = ''
    smartFlow.result = null
  }

  /** 智能添加入口：打开多步弹窗（替代 prompt） */
  function addSmartProvider() {
    openSmartFlow()
  }

  function protocolOf(c: ProviderCandidate) {
    return c.detected_protocol || c.suggested_protocol || c.active_protocol || 'openai'
  }

  function catalogUrlOf(c: ProviderCandidate) {
    const proto = protocolOf(c)
    return (
      c.protocols?.[proto]?.base_url
      || c.protocols?.openai?.base_url
      || c.protocols?.anthropic?.base_url
      || Object.values(c.protocols || {})[0]?.base_url
      || ''
    )
  }

  async function applyAndVerify(candidate: ProviderCandidate, apiKey: string, baseUrl = '') {
    const detectedProto = protocolOf(candidate)
    const catalogUrl = catalogUrlOf(candidate)
    const effectiveUrl = (baseUrl || catalogUrl || '').trim()

    pushSmartLog('run', `→ POST /api/llm/apply  ${candidate.provider} / ${detectedProto || '?'}`)
    const r = await api<{
      ok: boolean
      applied?: {
        provider: string
        protocols: string[]
        detected_protocol?: string
        suggested_protocol?: string
        active_protocol?: string
        protocol_reason?: string
        existed?: boolean
      }
      data?: any
      error?: string
    }>('/api/llm/apply', {
      method: 'POST',
      body: JSON.stringify({
        api_key: apiKey,
        provider: candidate.provider,
        protocol: detectedProto || undefined,
        base_url: baseUrl.trim() || undefined,
        set_active: true,
        candidate,
      }),
    })
    if (!r.ok || !r.data) {
      pushSmartLog('err', `✗ 写入失败: ${r.error || 'unknown'}`)
      return { ok: false as const, error: r.error || '写入失败' }
    }
    replaceEnvData(r.data)
    const pn = r.applied?.provider || candidate.provider
    const activeProto = r.applied?.detected_protocol || r.applied?.active_protocol || detectedProto
    const appliedUrl = envData.llm?.[pn]?.[activeProto]?.base_url || effectiveUrl
    selectProvider(pn)
    pushSmartLog('ok', `✓ 已写入 base_url + api_key`)
    pushSmartLog('run', `→ POST /api/llm/verify  拉取模型列表…`)

    const allProtos = r.applied?.protocols?.length
      ? r.applied.protocols
      : Object.keys(envData.llm[pn] || {}).filter((k) => typeof envData.llm[pn][k] === 'object')
    const ordered = activeProto
      ? [activeProto, ...allProtos.filter((p) => p !== activeProto)]
      : allProtos

    let okCount = 0
    let verifiedProto = ''
    for (const proto of ordered) {
      const ok = await verifyLlm(pn, proto, true)
      if (ok) {
        okCount++
        if (!verifiedProto) verifiedProto = proto
        if (activeProto && proto === activeProto) break
      }
    }

    const finalProto = verifiedProto || activeProto || detectedProto
    const modelCount = Object.keys(envData.llm[pn]?.[finalProto]?.models || {}).length

    if (okCount > 0) {
      if (verifiedProto) {
        envData.llm._active_provider = pn
        envData.llm._active_protocol = verifiedProto
      }
      await saveEnv(true)
      pushSmartLog('ok', `✓ 验证成功 · ${modelCount} 个模型可用`)
      pushSmartLog('ok', `✓ 设为 Active · 已保存 llm.yaml`)
      return {
        ok: true as const,
        result: {
          provider: pn,
          label: candidate.label,
          protocol: finalProto,
          models: modelCount,
          url: appliedUrl,
        } satisfies SmartFlowResult,
        verified: true,
      }
    }

    pushSmartLog('err', '✗ 验证未通过（请检查 Key 是否有效）')
    return {
      ok: true as const,
      result: {
        provider: pn,
        label: candidate.label,
        protocol: finalProto,
        models: modelCount,
        url: appliedUrl,
      } satisfies SmartFlowResult,
      verified: false,
    }
  }

  async function runSmartDetect() {
    const apiKey = smartFlow.apiKey.trim()
    if (!apiKey) {
      ui.toast('请先粘贴 API Key', 'warn')
      return
    }
    smartFlow.busy = true
    smartFlow.step = 'detecting'
    smartFlow.error = ''
    smartFlow.logs = [{ cls: 'run', text: '→ POST /api/llm/detect' }, { cls: '', text: '… scanning provider catalog' }]
    try {
      const r = await api<{
        ok: boolean
        candidates?: ProviderCandidate[]
        needs_choice?: boolean
        error?: string
      }>('/api/llm/detect', {
        method: 'POST',
        body: JSON.stringify({ api_key: apiKey }),
      })
      if (!r.ok || !r.candidates?.length) {
        smartFlow.step = 'error'
        smartFlow.error = '未能识别厂商：' + (r.error || '无候选')
        return
      }

      smartFlow.candidates = r.candidates
      smartFlow.selected = r.candidates[0].provider
      const top = r.candidates[0]
      const isCustom = top.provider === 'custom' || top.provider === 'openai-compatible'
      const hasCatalogUrl = Object.values(top.protocols || {}).some((p) => !!(p?.base_url))

      if (isCustom && !hasCatalogUrl) {
        smartFlow.step = 'custom_url'
        smartFlow.baseUrl = ''
        return
      }

      // 只信后端 needs_choice（高置信唯一锁定时允许自动 Apply）
      if (r.needs_choice) {
        smartFlow.step = 'choose'
        return
      }

      await runSmartApply(top, '')
    } catch (e: any) {
      smartFlow.step = 'error'
      smartFlow.error = '识别失败：' + (e?.message || String(e))
    } finally {
      // apply 路径已 await 结束；选择/错误路径在此释放 busy
      smartFlow.busy = false
    }
  }

  async function confirmSmartCustomUrl() {
    const url = smartFlow.baseUrl.trim()
    if (!url) {
      ui.toast('自定义端点需要 Base URL', 'warn')
      return
    }
    const top = smartFlow.candidates[0]
    if (!top) return
    const proto = protocolOf(top)
    top.protocols = { [proto]: { base_url: url, models: {} } }
    await runSmartApply(top, url)
  }

  async function confirmSmartPicker() {
    const selected = smartFlow.candidates.find((c) => c.provider === smartFlow.selected)
    if (!selected) {
      ui.toast('请选择一个 Provider', 'warn')
      return
    }
    await runSmartApply(selected, '')
  }

  async function runSmartApply(candidate: ProviderCandidate, baseUrl: string) {
    smartFlow.busy = true
    smartFlow.step = 'applying'
    smartFlow.logs = []
    smartFlow.error = ''
    try {
      const outcome = await applyAndVerify(candidate, smartFlow.apiKey.trim(), baseUrl)
      if (!outcome.ok) {
        smartFlow.step = 'error'
        smartFlow.error = outcome.error
        return
      }
      smartFlow.result = outcome.result
      smartFlow.step = 'done'
      if (outcome.verified) {
        ui.toast(`完成：${outcome.result.provider} / ${outcome.result.protocol} 已激活，${outcome.result.models} 个模型`)
      } else {
        ui.toast('已写入厂商与 Base URL，但验证未通过（请检查 Key 是否有效）', 'warn')
      }
    } catch (e: any) {
      smartFlow.step = 'error'
      smartFlow.error = '管道失败：' + (e?.message || String(e))
    } finally {
      smartFlow.busy = false
    }
  }

  function smartFlowAgain() {
    smartFlow.step = 'key'
    smartFlow.apiKey = ''
    smartFlow.baseUrl = ''
    smartFlow.candidates = []
    smartFlow.selected = ''
    smartFlow.logs = []
    smartFlow.error = ''
    smartFlow.result = null
    smartFlow.busy = false
  }

  /** 兼容旧名 */
  const smartPicker = smartFlow

  return {
    envData, envDataText, selectedProvider, providerNames, proxyEnabled,
    smartFlow, smartPicker, smartBusy,
    loadEnv, selectProvider, updateEnvDataSection, addProvider, deleteProvider, setActiveProvider,
    addProtocol, deleteProtocol, addModel, deleteModel, renameModel, saveEnv,
    generateProxyConfig, startProxyServer, verifyLlm, addSmartProvider,
    cancelSmartPicker, confirmSmartPicker, confirmSmartCustomUrl,
    runSmartDetect, smartFlowAgain, protocolOf, catalogUrlOf,
  }
})
