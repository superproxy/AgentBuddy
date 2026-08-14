<script setup lang="ts">
import { computed, ref, reactive, watch } from 'vue'
import { storeToRefs } from 'pinia'
import * as yaml from 'js-yaml'
import { useEnvStore } from '../stores/env'
import { useUiStore } from '../stores/ui'
import { api } from '../api/client'
import SmartProviderPicker from '../components/SmartProviderPicker.vue'

const env = useEnvStore()
const ui = useUiStore()
const { envData, envDataText, selectedProvider, providerNames, enabledProviderNames, proxyEnabled, smartBusy, envVars, envVarsBusy } = storeToRefs(env)
const { isProviderEnabled, toggleProviderEnabled } = env
const {
  selectProvider, updateEnvDataSection, addProvider, deleteProvider, setActiveProvider,
  addProtocol, deleteProtocol, addModel, deleteModel, renameModel, saveEnv,
  isModelEnabled, toggleModelEnabled, setAllModelsEnabled, syncModelsToAllProtocols,
  generateProxyConfig, startProxyServer, stopProxyServer, verifyLlm, addSmartProvider,
  fetchEnvVars, setApiKeyFromEnv,
} = env

const providerFilter = ref('')
const proxyRunning = ref(false)

/* ============ 协议排序：openaiv1 最靠前，anthropic 靠后 ============ */
const PROTOCOL_ORDER = ['openaiv1', 'responses', 'anthropic']
function protocolSortKey(proto: string): number {
  const idx = PROTOCOL_ORDER.indexOf(proto)
  return idx >= 0 ? idx : PROTOCOL_ORDER.length
}

/* ============ 协议折叠状态 ============ */
const collapsedProtocols = ref<Record<string, boolean>>({})
function isProtocolCollapsed(proto: string): boolean {
  return !!collapsedProtocols.value[proto]
}
function toggleProtocolCollapse(proto: string) {
  collapsedProtocols.value[proto] = !collapsedProtocols.value[proto]
}

/* ============ LLM 网关 ============ */
const gateway = computed(() => envData.value.proxy?.gateway || {})
const gatewayRoutes = computed(() => envData.value.proxy?.gateway?.routes || [])
const gatewaySummary = computed(() => {
  const routes = gatewayRoutes.value
  if (!routes.length) return '无路由'
  const enabled = routes.filter((r: any) => r.enabled !== false)
  return `${enabled.length}/${routes.length} 路由`
})

function addGatewayRoute() {
  if (!envData.value.proxy?.gateway?.routes) {
    envData.value.proxy.gateway.routes = []
  }
  envData.value.proxy.gateway.routes.push({
    enabled: true,
    provider: '',
    protocol: 'openaiv1',
    upstream_model: '',
    gateway_model: '',
  })
}
function removeGatewayRoute(index: number) {
  if (!envData.value.proxy?.gateway?.routes) return
  envData.value.proxy.gateway.routes.splice(index, 1)
}
function availableProtocolsFor(pn: string): string[] {
  const provider = envData.value.llm?.[pn]
  if (!provider || typeof provider !== 'object') return []
  return Object.keys(provider)
    .filter((k) => !k.startsWith('_') && typeof provider[k] === 'object' && provider[k] !== null)
    .sort((a, b) => protocolSortKey(a) - protocolSortKey(b))
}
function availableModelsFor(pn: string, proto: string): string[] {
  const models = envData.value.llm?.[pn]?.[proto]?.models
  if (!models || typeof models !== 'object') return []
  return Object.keys(models)
}

async function syncToIde() {
  ui.clearLog()
  ui.toast('正在同步到 IDE...')
  try {
    const resp = await fetch('/api/sync?ide=All&scope=llm,mcp', { method: 'GET', headers: { Accept: 'text/event-stream' } })
    if (!resp.ok) { ui.toast('同步失败', 'err'); return }
    const reader = resp.body!.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() || ''
      for (const line of lines) {
        if (line.startsWith('data: ')) ui.appendLog(line.slice(6))
      }
    }
    ui.toast('LLM 配置已同步到所有 IDE')
  } catch (e) {
    ui.toast('同步失败: ' + String(e), 'err')
  }
}

async function toggleProxyRun() {
  if (proxyRunning.value) {
    await stopProxyServer()
    proxyRunning.value = false
    return
  }
  envData.value.proxy.gateway.enabled = true
  const sr = await saveEnv(true)
  if (!sr) { ui.toast('保存失败', 'err'); return }
  const r = await api<{ ok: boolean; stdout?: string; stderr?: string }>('/api/sync', { method: 'POST' })
  if (!r.ok) { ui.toast('生成配置失败', 'err'); return }
  proxyRunning.value = true
  ui.toast('LLM 网关已启动，配置已生成')
  await startProxyServer()
}

async function exportLlmConfig() {
  const llmConfig = { llm: envData.value.llm, proxy: envData.value.proxy }
  const text = yaml.dump(llmConfig, { indent: 2, lineWidth: 120 })
  const filename = 'llm-config.yaml'
  const pw = (window as any).pywebview
  if (pw?.api?.save_file) {
    // pywebview 桌面模式：走 JS-Python 桥接弹原生保存对话框（pywebview 不处理附件下载）
    try {
      const blob = new Blob([text], { type: 'text/yaml' })
      const b64 = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => resolve(String(reader.result).split(',')[1])
        reader.onerror = reject
        reader.readAsDataURL(blob)
      })
      const raw = await pw.api.save_file(filename, b64)
      const res = raw?.result ?? raw
      if (res?.ok) ui.toast(`LLM 配置已保存到: ${res.path}`)
      else if (res?.error !== 'cancelled') ui.toast('导出失败: ' + (res?.error || JSON.stringify(raw)), 'err')
    } catch (e: any) {
      ui.toast('导出失败: ' + (e?.message || e), 'err')
    }
    return
  }
  // 浏览器模式：用 a 标签触发下载
  const blob = new Blob([text], { type: 'text/yaml' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  ui.toast('LLM 配置已导出')
}

const importFileInput = ref<HTMLInputElement | null>(null)
function triggerImport() {
  importFileInput.value?.click()
}
async function handleImportFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    const text = await file.text()
    // 自动识别 YAML / JSON
    const data = text.trim().startsWith('{') || text.trim().startsWith('[')
      ? JSON.parse(text)
      : yaml.load(text) as any
    if (data.llm && typeof data.llm === 'object') {
      envData.value.llm = data.llm
    }
    if (data.proxy && typeof data.proxy === 'object') {
      envData.value.proxy = data.proxy
    }
    await saveEnv(true)
    ui.toast('LLM 配置已导入并保存')
  } catch (err: any) {
    ui.toast(`导入失败: ${err?.message || err}`, 'err')
  }
  input.value = ''
}

const filteredProviders = computed(() => {
  const q = providerFilter.value.trim().toLowerCase()
  if (!q) return providerNames.value
  return providerNames.value.filter((n) => n.toLowerCase().includes(q))
})

const selectedProtocols = computed(() => {
  const pn = selectedProvider.value
  if (!pn || !envData.value.llm?.[pn]) return [] as string[]
  return Object.keys(envData.value.llm[pn])
    .filter((k) => !k.startsWith('_') && typeof envData.value.llm[pn][k] === 'object' && envData.value.llm[pn][k] !== null)
    .sort((a, b) => protocolSortKey(a) - protocolSortKey(b))
})

function providerInitials(name: string) {
  const parts = name.replace(/[^a-zA-Z0-9]+/g, ' ').trim().split(/\s+/)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return name.slice(0, 2).toUpperCase()
}

function protocolSummary(pn: string) {
  const block = envData.value.llm?.[pn]
  if (!block || typeof block !== 'object') return '—'
  const protos = Object.keys(block).filter((k) => typeof block[k] === 'object' && block[k] !== null)
  const primary = protos[0] || '?'
  let models = 0
  for (const p of protos) models += Object.keys(block[p]?.models || {}).length
  return `${primary} · ${models} models`
}

/* ============ 默认 LLM 源（Provider 或 网关）+ 默认模型 ============ */
const GATEWAY_SOURCE = '__gateway__'

const activeSource = computed<string>({
  get: () => proxyEnabled.value ? GATEWAY_SOURCE : (envData.value.llm?._active_provider || ''),
  set: (v: string) => {
    if (v === GATEWAY_SOURCE) {
      envData.value.proxy.gateway.enabled = true
      envData.value.llm._active_provider = ''
    } else {
      envData.value.proxy.gateway.enabled = false
      envData.value.llm._active_provider = v
    }
  },
})

const activeModel = computed<string>({
  get: () => {
    if (proxyEnabled.value) {
      const routes = gatewayRoutes.value
      for (const r of routes) {
        if (r.enabled !== false && r.gateway_model) return r.gateway_model
      }
      return ''
    }
    return envData.value.llm?._active_model || ''
  },
  set: (v: string) => {
    if (proxyEnabled.value) {
      // 网关模式：标记选中的 gateway_model（通过 _active_model 存储）
      envData.value.llm._active_model = v
    } else {
      envData.value.llm._active_model = v
    }
  },
})

const availableModels = computed<string[]>(() => {
  if (proxyEnabled.value) {
    return gatewayRoutes.value
      .filter((r: any) => r.enabled !== false && r.gateway_model)
      .map((r: any) => r.gateway_model)
  }
  const pn = envData.value.llm?._active_provider
  if (!pn) return []
  const provider = envData.value.llm?.[pn]
  if (!provider) return []
  // 取所有协议下的模型并集
  const models: string[] = []
  for (const proto of Object.keys(provider)) {
    if (proto.startsWith('_')) continue
    const protoCfg = provider[proto]
    if (protoCfg?.models && typeof protoCfg.models === 'object') {
      models.push(...Object.keys(protoCfg.models))
    }
  }
  return [...new Set(models)]
})

const hasProviders = computed(() => enabledProviderNames.value.length > 0)

/* ============ 自动保存 ============ */
let autoSaveTimer: ReturnType<typeof setTimeout> | null = null
function autoSave() {
  if (autoSaveTimer) clearTimeout(autoSaveTimer)
  autoSaveTimer = setTimeout(async () => {
    const ok = await saveEnv(true)
    if (ok) {
      // 保存后自动重新生成 IDE 配置（codex config.toml / auth.json 等）
      try {
        await api('/api/sync', { method: 'POST' })
      } catch { /* 静默失败，不影响保存 */ }
    }
  }, 500)
}
watch(activeSource, () => autoSave())
watch(activeModel, () => autoSave())

function avatarStyle(name: string) {
  const hues: Record<string, string> = {
    openaiv1: 'linear-gradient(145deg,#0e42d2,#1f2329)',
    responses: 'linear-gradient(145deg,#0e42d2,#1f2329)',
    anthropic: 'linear-gradient(145deg,#4e5969,#1f2329)',
    deepseek: 'linear-gradient(145deg,#165dff,#0a2e9c)',
  }
  return hues[name.toLowerCase()] || 'linear-gradient(145deg,#165dff,#0a2e9c)'
}

function onRenameModel(proto: string, oldKey: string, event: Event) {
  const next = (event.target as HTMLInputElement).value
  renameModel(selectedProvider.value, proto, oldKey, next)
}

/* ============ api_key 增强：显示/隐藏 + 环境变量选择 ============ */
const apiKeyVisible = reactive<Record<string, boolean>>({})
const envVarPicker = reactive<{ open: boolean; pn: string; proto: string; q: string }>({
  open: false, pn: '', proto: '', q: '',
})
const envVarFilter = ref('')

const filteredEnvVars = computed(() => {
  const q = envVarFilter.value.trim().toLowerCase()
  if (!q) return envVars.value
  return envVars.value.filter((n) => n.toLowerCase().includes(q))
})

function keyVisibleKey(pn: string, proto: string) { return pn + '::' + proto }

function isKeyVisible(pn: string, proto: string) {
  return !!apiKeyVisible[keyVisibleKey(pn, proto)]
}
function toggleKeyVisible(pn: string, proto: string) {
  const k = keyVisibleKey(pn, proto)
  apiKeyVisible[k] = !apiKeyVisible[k]
}

function isEnvRef(val: string) {
  // 兼容 ${VAR} 新语法与 env:VAR 旧语法（旧导出迁移期间可能残留）
  return typeof val === 'string' && /^\$\{[\w]+\}$/.test(val)
}

async function openEnvVarPicker(pn: string, proto: string) {
  envVarPicker.open = true
  envVarPicker.pn = pn
  envVarPicker.proto = proto
  envVarFilter.value = ''
  await fetchEnvVars()
}
function closeEnvVarPicker() {
  envVarPicker.open = false
}
function confirmEnvVar(varName: string) {
  setApiKeyFromEnv(envVarPicker.pn, envVarPicker.proto, varName)
  closeEnvVarPicker()
}
function clearEnvRef() {
  if (!envVarPicker.pn || !envVarPicker.proto) return
  if (envData.value.llm?.[envVarPicker.pn]?.[envVarPicker.proto]) {
    envData.value.llm[envVarPicker.pn][envVarPicker.proto].api_key = ''
    ui.toast('已清除环境变量引用')
  }
  closeEnvVarPicker()
}
</script>

<template>
  <div class="space-y-3.5">
    <SmartProviderPicker />

    <!-- Top bar -->
    <div class="flex items-end justify-between gap-4 flex-wrap">
      <div>
        <h1 class="text-[22px] font-bold tracking-tight text-ink-900 m-0 mb-1">LLM Providers</h1>
        <p class="m-0 text-[13px] text-ink-500">
          管理 LLM 厂商与模型清单 · 支持 OpenAI / Anthropic / Gemini 等多协议 · 自动保存
        </p>
      </div>
      <div class="flex gap-2 flex-wrap ml-auto">
        <button
          type="button"
          @click="addSmartProvider"
          :disabled="smartBusy"
          class="inline-flex items-center gap-1.5 h-9 px-3.5 text-[12.5px] font-semibold rounded-[10px] bg-white text-emerald-700 border border-emerald-200 hover:bg-emerald-50 hover:border-emerald-300 disabled:opacity-45 transition"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
          {{ smartBusy ? '管道运行中…' : '智能添加' }}
        </button>
        <button
          type="button"
          @click="addProvider"
          class="inline-flex items-center gap-1.5 h-9 px-3.5 text-[12.5px] font-semibold rounded-[10px] bg-brand-50 text-brand-600 border border-brand-100 hover:bg-brand-100 transition"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>
          添加 Provider
        </button>
        <button
          type="button"
          @click="exportLlmConfig"
          class="inline-flex items-center gap-1.5 h-9 px-3.5 text-[12.5px] font-semibold rounded-[10px] bg-white text-ink-700 border border-ink-300 hover:bg-ink-100 transition"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          导出
        </button>
        <button
          type="button"
          @click="triggerImport"
          class="inline-flex items-center gap-1.5 h-9 px-3.5 text-[12.5px] font-semibold rounded-[10px] bg-white text-ink-700 border border-ink-300 hover:bg-ink-100 transition"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
          导入
        </button>
        <input
          ref="importFileInput"
          type="file"
          accept=".yaml,.yml,.json"
          class="hidden"
          @change="handleImportFile"
        />
      </div>
    </div>

    <!-- 默认 LLM 源（Provider 或 网关） -->
    <section class="bg-white border border-ink-300/80 rounded-[14px] shadow-card p-[18px]">
      <div class="flex items-center gap-2.5 mb-2">
        <span class="inline-flex items-center justify-center w-5 h-5 rounded-md bg-brand-50 text-brand-600">
          <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
        </span>
        <h3 class="m-0 text-[13px] font-semibold text-ink-900">默认 LLM 源</h3>
        <span v-if="activeSource" class="px-1.5 py-0.5 text-[10px] font-semibold rounded bg-brand-50 text-brand-600">{{ activeSource === GATEWAY_SOURCE ? '网关' : activeSource }}</span>
      </div>
      <p class="m-0 mb-3 text-xs text-ink-500 leading-relaxed">
        选择 Provider 或 LLM 网关作为默认 LLM 源，同步到 IDE 时生效。切换后自动保存。
      </p>
      <div class="flex items-center gap-2.5 flex-wrap">
        <div class="flex flex-col gap-1">
          <label class="text-[10px] font-medium text-ink-700">来源</label>
          <select
            v-model="activeSource"
            :disabled="!hasProviders && !proxyEnabled"
            class="px-3 py-2 text-xs border border-ink-300 rounded-lg bg-white min-w-[220px] disabled:bg-ink-100 disabled:text-ink-500"
          >
            <option value="" disabled>{{ hasProviders ? '请选择…' : '暂无启用的 Provider' }}</option>
            <option v-for="p in enabledProviderNames" :key="p" :value="p">{{ p }}</option>
            <option :value="GATEWAY_SOURCE">LLM 网关</option>
          </select>
        </div>
        <div class="flex flex-col gap-1">
          <label class="text-[10px] font-medium text-ink-700">默认模型</label>
          <select
            v-model="activeModel"
            :disabled="!availableModels.length"
            class="px-3 py-2 text-xs border border-ink-300 rounded-lg bg-white min-w-[200px] disabled:bg-ink-100 disabled:text-ink-500"
          >
            <option value="" disabled>{{ availableModels.length ? '请选择…' : '无可用模型' }}</option>
            <option v-for="m in availableModels" :key="m" :value="m">{{ m }}</option>
          </select>
        </div>
      </div>
    </section>

    <!-- Deck: rail + pane -->
    <div class="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-3.5 min-h-[620px]">
      <!-- Left rail -->
      <aside class="bg-white border border-ink-300/80 rounded-[14px] shadow-card flex flex-col overflow-hidden min-h-[320px]">
        <div class="px-3.5 pt-3.5 pb-2.5 border-b border-ink-100">
          <div class="flex items-center justify-between mb-2.5">
            <h2 class="text-[13px] font-semibold m-0">Providers</h2>
            <span class="px-1.5 py-0.5 text-[10px] font-semibold rounded bg-ink-100 text-ink-700">{{ providerNames.length }}</span>
          </div>
          <input
            v-model="providerFilter"
            type="search"
            placeholder="筛选厂商…"
            aria-label="筛选厂商"
            class="w-full px-2.5 py-2 text-xs border border-ink-300 rounded-lg"
          />
        </div>
        <div class="flex-1 overflow-auto p-2">
          <button
            v-for="pn in filteredProviders"
            :key="pn"
            type="button"
            class="relative flex items-center gap-2.5 w-full text-left px-2.5 py-2.5 rounded-[10px] border border-transparent mb-1 transition hover:bg-ink-100"
            :class="selectedProvider === pn ? 'bg-brand-50 border-brand-100' : ''"
            @click="selectProvider(pn)"
          >
            <span
              v-if="selectedProvider === pn"
              class="absolute left-0 top-2.5 bottom-2.5 w-[3px] rounded-r bg-brand-500"
            />
            <div
              class="w-8 h-8 rounded-lg text-white text-[11px] font-bold grid place-items-center shrink-0"
              :style="{ background: avatarStyle(pn) }"
            >{{ providerInitials(pn) }}</div>
            <div class="min-w-0 flex-1">
              <div class="text-[13px] font-semibold truncate flex items-center gap-1">
                {{ pn }}
                <span
                  v-if="activeSource === pn"
                  class="px-1.5 py-0.5 text-[10px] font-semibold rounded bg-brand-50 text-brand-600 align-middle"
                >默认</span>
                <span
                  v-if="!isProviderEnabled(pn)"
                  class="px-1.5 py-0.5 text-[10px] font-semibold rounded bg-ink-100 text-ink-500 align-middle"
                >未启用</span>
              </div>
              <div class="text-[11px] text-ink-500 font-mono mt-0.5 truncate">{{ protocolSummary(pn) }}</div>
            </div>
            <!-- 启用/禁用开关 -->
            <button
              type="button"
              class="relative w-8 h-[18px] rounded-full transition shrink-0"
              :class="isProviderEnabled(pn) ? 'bg-brand-500' : 'bg-ink-300'"
              @click.stop="toggleProviderEnabled(pn); autoSave()"
              :title="isProviderEnabled(pn) ? '点击禁用' : '点击启用'"
            >
              <span
                class="absolute top-0.5 w-[14px] h-[14px] rounded-full bg-white shadow transition-all"
                :class="isProviderEnabled(pn) ? 'left-[16px]' : 'left-[2px]'"
              />
            </button>
          </button>
          <p v-if="!filteredProviders.length" class="text-xs text-ink-500 text-center py-8 px-3">
            {{ providerNames.length ? '无匹配厂商' : '暂无 Provider，请添加' }}
          </p>
        </div>
      </aside>

      <!-- Right pane -->
      <section class="bg-white border border-ink-300/80 rounded-[14px] shadow-card flex flex-col overflow-hidden min-h-[320px]">
        <template v-if="selectedProvider && envData.llm[selectedProvider]">
          <div class="px-[18px] py-4 border-b border-ink-100 flex items-center justify-between gap-3 flex-wrap">
            <div>
              <h2 class="m-0 text-base font-semibold">{{ selectedProvider }}</h2>
              <div class="text-xs text-ink-500 mt-0.5">
                <template v-if="activeSource === selectedProvider">
                  当前默认 LLM 源
                </template>
                <template v-else>非默认 · 点击右侧按钮设为默认</template>
              </div>
            </div>
            <div class="flex gap-2 flex-wrap">
              <button
                v-if="activeSource !== selectedProvider"
                type="button"
                @click="activeSource = selectedProvider"
                class="inline-flex items-center gap-1.5 h-7 px-2.5 text-[11.5px] font-semibold rounded-lg bg-brand-50 text-brand-600 border border-brand-100 hover:bg-brand-100 transition"
              >
                <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6L9 17l-5-5"/></svg>
                设为默认
              </button>
              <button
                type="button"
                @click="deleteProvider(selectedProvider)"
                class="inline-flex items-center h-7 px-2.5 text-[11.5px] font-semibold rounded-lg text-ink-500 hover:bg-red-50 hover:text-red-600 hover:border-red-200 border border-transparent transition"
              >删除</button>
            </div>
          </div>

          <div class="px-[18px] py-4 pb-5 grid gap-3.5 overflow-auto">
            <div
              v-for="proto in selectedProtocols"
              :key="proto"
              class="border border-ink-300/80 rounded-xl bg-gradient-to-b from-white to-ink-100/80 overflow-hidden"
            >
              <div
                class="flex items-center justify-between px-3.5 py-2.5 cursor-pointer select-none"
                @click="toggleProtocolCollapse(proto)"
              >
                <div class="flex items-center gap-2">
                  <svg class="w-3 h-3 transition-transform text-ink-500" :class="{ 'rotate-90': !isProtocolCollapsed(proto) }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18l6-6-6-6"/></svg>
                  <h3 class="m-0 text-[12px] font-semibold tracking-wider uppercase text-ink-700">{{ proto }}</h3>
                </div>
                <button
                  type="button"
                  @click.stop="deleteProtocol(selectedProvider, proto)"
                  class="inline-flex items-center h-7 px-2.5 text-[11.5px] font-semibold rounded-lg text-ink-500 hover:bg-red-50 hover:text-red-600 border border-transparent transition"
                >删除协议</button>
              </div>
              <div v-show="!isProtocolCollapsed(proto)" class="px-3.5 pb-3.5">
              <!-- 协议级 base_url / api_key -->
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5 mb-2.5">
                <div class="flex flex-col gap-1">
                  <label class="text-[11px] font-medium text-ink-700">base_url</label>
                  <input
                    v-model="envData.llm[selectedProvider][proto].base_url"
                    placeholder="https://api.example.com/v1"
                    class="w-full px-2.5 py-2 text-xs border border-ink-300 rounded-lg font-mono"
                  />
                </div>
                <div class="flex flex-col gap-1">
                  <label class="text-[11px] font-medium text-ink-700 flex items-center justify-between">
                    <span>api_key</span>
                    <span
                      v-if="isEnvRef(envData.llm[selectedProvider][proto].api_key)"
                      class="text-[10px] font-semibold text-emerald-600"
                    >环境变量引用</span>
                  </label>
                  <div class="relative flex items-center">
                    <input
                      :type="isKeyVisible(selectedProvider, proto) ? 'text' : 'password'"
                      v-model="envData.llm[selectedProvider][proto].api_key"
                      :placeholder="isEnvRef(envData.llm[selectedProvider][proto].api_key) ? '${VAR_NAME}' : 'sk-...'"
                      class="w-full px-2.5 py-2 pr-10 text-xs border border-ink-300 rounded-lg font-mono"
                      :class="{ 'border-emerald-300 bg-emerald-50/40': isEnvRef(envData.llm[selectedProvider][proto].api_key) }"
                    />
                    <button
                      type="button"
                      :aria-label="isKeyVisible(selectedProvider, proto) ? '隐藏' : '显示'"
                      :title="isKeyVisible(selectedProvider, proto) ? '隐藏密钥' : '查看密钥'"
                      @click="toggleKeyVisible(selectedProvider, proto)"
                      class="absolute right-1 top-1/2 -translate-y-1/2 inline-flex items-center justify-center w-7 h-7 rounded-md text-ink-500 hover:bg-ink-100 hover:text-ink-700 transition"
                    >
                      <svg v-if="isKeyVisible(selectedProvider, proto)" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
                      <svg v-else class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                    </button>
                  </div>
                </div>
              </div>
              <table class="w-full text-xs border-collapse bg-white rounded-lg overflow-hidden border border-ink-300/80">
                <thead>
                  <tr>
                    <th class="px-2.5 py-2 w-8 bg-ink-100">
                      <input
                        type="checkbox"
                        :checked="Object.keys(envData.llm[selectedProvider][proto].models || {}).length > 0 && Object.keys(envData.llm[selectedProvider][proto].models || {}).every((mk) => isModelEnabled(selectedProvider, proto, mk))"
                        @change="setAllModelsEnabled(selectedProvider, proto, !Object.keys(envData.llm[selectedProvider][proto].models || {}).every((mk) => isModelEnabled(selectedProvider, proto, mk)))"
                        class="w-3.5 h-3.5 rounded border-ink-300 text-brand-600 focus:ring-brand-500"
                        title="全选启用/禁用"
                      />
                    </th>
                    <th class="px-2.5 py-2 text-left bg-ink-100 text-ink-700 font-semibold text-[11px]">key</th>
                    <th class="px-2.5 py-2 text-left bg-ink-100 text-ink-700 font-semibold text-[11px]">name</th>
                    <th class="px-2.5 py-2 w-10 bg-ink-100"></th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(mv, mk) in (envData.llm[selectedProvider][proto].models || {})"
                    :key="mk"
                    class="border-t border-ink-100"
                    :class="{ 'opacity-40': !isModelEnabled(selectedProvider, proto, String(mk)) }"
                  >
                    <td class="px-2.5 py-1.5 text-center">
                      <input
                        type="checkbox"
                        :checked="isModelEnabled(selectedProvider, proto, String(mk))"
                        @change="toggleModelEnabled(selectedProvider, proto, String(mk))"
                        class="w-3.5 h-3.5 rounded border-ink-300 text-brand-600 focus:ring-brand-500"
                        title="启用/禁用"
                      />
                    </td>
                    <td class="px-2.5 py-1.5">
                      <input
                        :value="mk"
                        @change="onRenameModel(proto, String(mk), $event)"
                        class="w-full px-0 py-1 text-xs border-0 shadow-none font-mono focus:ring-0 focus:shadow-none"
                      />
                    </td>
                    <td class="px-2.5 py-1.5">
                      <input v-model="mv.name" class="w-full px-0 py-1 text-xs border-0 shadow-none focus:ring-0 focus:shadow-none" />
                    </td>
                    <td class="px-1.5 py-1.5 text-center">
                      <button
                        type="button"
                        aria-label="删除模型"
                        @click="deleteModel(selectedProvider, proto, String(mk))"
                        class="inline-flex items-center justify-center w-[26px] h-[26px] rounded-md text-ink-500 hover:bg-red-50 hover:text-red-600 transition"
                      >
                        <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12"/></svg>
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
              <div class="flex gap-2 mt-2.5 flex-wrap">
                <button
                  type="button"
                  @click="addModel(selectedProvider, proto)"
                  class="inline-flex items-center gap-1.5 h-7 px-2.5 text-[11.5px] font-semibold rounded-lg bg-brand-50 text-brand-600 border border-brand-100 hover:bg-brand-100 transition"
                >
                  <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>
                  添加 model
                </button>
                <button
                  type="button"
                  @click="verifyLlm(selectedProvider, proto)"
                  class="inline-flex items-center gap-1.5 h-7 px-2.5 text-[11.5px] font-semibold rounded-lg bg-white text-emerald-700 border border-emerald-200 hover:bg-emerald-50 transition"
                >
                  <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                  获取模型
                </button>
                <button
                  v-if="selectedProtocols.length > 1"
                  type="button"
                  @click="syncModelsToAllProtocols(selectedProvider, proto); ui.toast('模型已同步到所有协议')"
                  class="inline-flex items-center gap-1.5 h-7 px-2.5 text-[11.5px] font-semibold rounded-lg bg-white text-indigo-700 border border-indigo-200 hover:bg-indigo-50 transition"
                  title="将当前协议的模型列表复制到同 Provider 的所有其他协议"
                >
                  <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17 1l4 4-4 4"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><path d="M7 23l-4-4 4-4"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/></svg>
                  同步到所有协议
                </button>
              </div>
              </div>
            </div>

            <button
              type="button"
              @click="addProtocol(selectedProvider)"
              class="inline-flex items-center gap-1.5 h-7 px-2.5 text-[11.5px] font-semibold rounded-lg bg-white text-ink-700 border border-ink-300 hover:bg-ink-100 justify-self-start transition"
            >
              <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>
              添加协议
            </button>
          </div>
        </template>

        <div v-else class="flex-1 grid place-items-center text-sm text-ink-500 px-6 py-16">
          请选择或添加一个 Provider
        </div>
      </section>
    </div>

    <!-- LLM 网关（多协议路由） -->
    <section class="bg-white border border-ink-300/80 rounded-[14px] shadow-card overflow-hidden">
      <div class="flex items-center justify-between gap-3.5 px-[18px] py-3.5 flex-wrap">
        <div class="flex items-center gap-2.5 min-w-0">
          <div class="min-w-0">
            <h3 class="m-0 text-[13px] font-semibold flex items-center gap-2 before:content-[''] before:w-[3px] before:h-3.5 before:rounded-sm before:bg-brand-500">
              LLM 网关
            </h3>
            <p class="m-0 mt-0.5 text-[11px] text-ink-500 font-mono truncate">{{ gatewaySummary }}</p>
          </div>
        </div>
        <div class="flex items-center gap-2 flex-wrap">
          <span
            :class="['inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-semibold rounded-full', proxyRunning ? 'bg-emerald-50 text-emerald-600' : 'bg-ink-100 text-ink-500']"
          >
            <span class="w-1.5 h-1.5 rounded-full" :class="proxyRunning ? 'bg-emerald-500' : 'bg-ink-400'" />
            {{ proxyRunning ? '运行中' : '已停止' }}
          </span>
          <button
            type="button"
            @click="addGatewayRoute"
            class="inline-flex items-center gap-1.5 h-[34px] px-3.5 text-[12.5px] font-semibold rounded-[10px] bg-white text-ink-700 border border-ink-300 hover:bg-ink-100 transition"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>
            添加路由
          </button>
          <button
            type="button"
            @click="toggleProxyRun"
            :class="['inline-flex items-center gap-1.5 h-[34px] px-3.5 text-[12.5px] font-semibold rounded-[10px] text-white border transition', proxyRunning ? 'bg-red-500 border-red-600 hover:bg-red-600' : 'bg-gradient-to-b from-[#2f72ff] via-brand-500 to-[#1454e8] border-brand-700/20 hover:from-brand-500 hover:to-brand-600']"
          >
            <svg v-if="!proxyRunning" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            <svg v-else class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
            {{ proxyRunning ? '停止' : '启动' }}
          </button>
        </div>
      </div>

      <div class="border-t border-ink-100 px-[18px] py-4 bg-ink-100/30">
        <!-- 路由列表 -->
        <div v-if="gatewayRoutes.length" class="space-y-2.5 mb-3">
          <div
            v-for="(route, idx) in gatewayRoutes"
            :key="idx"
            class="border border-ink-300/80 rounded-[10px] bg-white p-3"
          >
            <div class="flex items-center justify-between mb-2.5">
              <label class="inline-flex items-center gap-2 cursor-pointer">
                <input type="checkbox" v-model="route.enabled" class="sr-only peer" />
                <div class="w-7 h-4 bg-ink-300 rounded-full peer-checked:bg-emerald-500 transition relative">
                  <div class="absolute top-0.5 left-0.5 w-3 h-3 bg-white rounded-full transition" :class="{ 'translate-x-3': route.enabled }" />
                </div>
                <span class="text-[11px] font-semibold" :class="route.enabled ? 'text-emerald-600' : 'text-ink-500'">{{ route.enabled ? '启用' : '禁用' }}</span>
              </label>
              <button
                type="button"
                @click="removeGatewayRoute(idx)"
                class="inline-flex items-center h-6 px-2 text-[11px] font-semibold rounded-lg text-ink-500 hover:bg-red-50 hover:text-red-600 border border-transparent transition"
              >删除</button>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
              <div class="flex flex-col gap-1">
                <label class="text-[10px] font-medium text-ink-700">Provider</label>
                <select v-model="route.provider" class="w-full px-2 py-1.5 text-xs border border-ink-300 rounded-lg bg-white">
                  <option value="">未选择</option>
                  <option v-for="pn in providerNames" :key="pn" :value="pn">{{ pn }}</option>
                </select>
              </div>
              <div class="flex flex-col gap-1">
                <label class="text-[10px] font-medium text-ink-700">协议</label>
                <select v-model="route.protocol" class="w-full px-2 py-1.5 text-xs border border-ink-300 rounded-lg bg-white">
                  <option value="openaiv1">openaiv1</option>
                  <option value="responses">responses</option>
                  <option value="anthropic">anthropic</option>
                </select>
              </div>
              <div class="flex flex-col gap-1">
                <label class="text-[10px] font-medium text-ink-700">上游模型</label>
                <input
                  v-model="route.upstream_model"
                  list="upstream-models-list"
                  placeholder="gpt-5.5"
                  class="w-full px-2 py-1.5 text-xs border border-ink-300 rounded-lg font-mono"
                />
              </div>
              <div class="flex flex-col gap-1">
                <label class="text-[10px] font-medium text-ink-700">网关模型名</label>
                <input
                  v-model="route.gateway_model"
                  placeholder="gpt-5.4"
                  class="w-full px-2 py-1.5 text-xs border border-ink-300 rounded-lg font-mono"
                />
              </div>
            </div>
            <!-- 自定义 base_url（可选，留空则从 Provider 配置自动获取） -->
            <details class="mt-2">
              <summary class="cursor-pointer text-[10px] text-ink-500 font-semibold">自定义地址（留空则从 Provider 自动获取）</summary>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5 mt-2">
                <div class="flex flex-col gap-1">
                  <label class="text-[10px] font-medium text-ink-700">base_url</label>
                  <input v-model="route.base_url" placeholder="https://..." class="w-full px-2 py-1.5 text-xs border border-ink-300 rounded-lg font-mono" />
                </div>
                <div class="flex flex-col gap-1">
                  <label class="text-[10px] font-medium text-ink-700">api_key</label>
                  <input v-model="route.api_key" placeholder="sk-..." class="w-full px-2 py-1.5 text-xs border border-ink-300 rounded-lg font-mono" />
                </div>
              </div>
            </details>
          </div>
        </div>

        <!-- 高级设置 -->
        <details>
          <summary class="cursor-pointer text-ink-500 text-xs font-semibold">高级网关设置</summary>
          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mt-2.5">
            <div class="flex flex-col gap-1">
              <label class="text-[11px] font-medium text-ink-700">监听地址</label>
              <input v-model="envData.proxy.gateway.listen_host" placeholder="127.0.0.1" class="w-full px-2.5 py-2 text-xs border border-ink-300 rounded-lg font-mono" />
            </div>
            <div class="flex flex-col gap-1">
              <label class="text-[11px] font-medium text-ink-700">端口</label>
              <input v-model.number="envData.proxy.gateway.listen_port" type="number" placeholder="4000" class="w-full px-2.5 py-2 text-xs border border-ink-300 rounded-lg font-mono" />
            </div>
            <div class="flex flex-col gap-1">
              <label class="text-[11px] font-medium text-ink-700">网关密钥</label>
              <input v-model="envData.proxy.gateway.api_key" placeholder="sk-..." class="w-full px-2.5 py-2 text-xs border border-ink-300 rounded-lg font-mono" />
            </div>
            <div class="flex flex-col gap-1">
              <label class="text-[11px] font-medium text-ink-700">适配器</label>
              <input value="LiteLLM" disabled class="w-full px-2.5 py-2 text-xs border border-ink-300 rounded-lg font-mono bg-ink-100 text-ink-500" />
            </div>
          </div>
        </details>
      </div>
    </section>

    <!-- 环境变量选择弹层 -->
    <Teleport to="body">
      <Transition name="envvar-pop">
        <div v-if="envVarPicker.open" class="envvar-root" @click.self="closeEnvVarPicker">
          <div class="envvar-panel" role="dialog" aria-modal="true" aria-labelledby="envvar-title">
            <header class="envvar-head">
              <h3 id="envvar-title">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>
                选择环境变量
              </h3>
              <button type="button" class="btn-icon-close" aria-label="关闭" @click="closeEnvVarPicker">
                <svg viewBox="0 0 24 24"><path d="M18 6 6 18M6 6l12 12"/></svg>
              </button>
            </header>
            <div class="envvar-body">
              <p class="envvar-target">
                将为 <code>{{ envVarPicker.pn }}</code> / <code>{{ envVarPicker.proto }}</code> 的 api_key 设置 <code>${VAR_NAME}</code> 引用。
              </p>
              <input
                v-model="envVarFilter"
                type="search"
                placeholder="筛选变量名…"
                aria-label="筛选环境变量"
                class="envvar-filter"
              />
              <div class="envvar-list">
                <button
                  v-for="name in filteredEnvVars"
                  :key="name"
                  type="button"
                  class="envvar-item"
                  @click="confirmEnvVar(name)"
                >
                  <span class="envvar-name">{{ name }}</span>
                  <svg class="envvar-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>
                </button>
                <p v-if="!filteredEnvVars.length && !envVarsBusy" class="envvar-empty">
                  {{ envVars.length ? '无匹配变量' : '未检测到含 KEY/TOKEN/SECRET 的环境变量' }}
                </p>
                <p v-if="envVarsBusy" class="envvar-empty">加载中…</p>
              </div>
              <p class="envvar-tip">
                仅显示名称中包含 KEY / TOKEN / SECRET 的环境变量。选中后 api_key 字段会被设为 <code>env:VAR_NAME</code>，验证时由后端从环境变量解析实际值。
              </p>
            </div>
            <footer class="envvar-foot">
              <button type="button" class="btn btn-ghost" @click="clearEnvRef">清除引用</button>
              <button type="button" class="btn btn-primary" @click="closeEnvVarPicker">关闭</button>
            </footer>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.envvar-root {
  position: fixed; inset: 0; z-index: 1000;
  display: flex; align-items: center; justify-content: center;
  background: rgba(0, 0, 0, 0.45);
  padding: 24px;
}
.envvar-panel {
  width: min(480px, 100%); max-height: 80vh;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.25);
  display: flex; flex-direction: column;
  overflow: hidden;
}
.envvar-head {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 18px; border-bottom: 1px solid #e5e7eb;
}
.envvar-head h3 {
  display: flex; align-items: center; gap: 8px;
  margin: 0; font-size: 14px; font-weight: 600; color: #111827;
}
.envvar-head h3 svg { width: 18px; height: 18px; color: #165dff; }
.btn-icon-close {
  display: inline-flex; align-items: center; justify-content: center;
  width: 28px; height: 28px; border-radius: 6px;
  color: #6b7280; background: transparent; border: none; cursor: pointer;
  transition: all 0.15s;
}
.btn-icon-close:hover { background: #f3f4f6; color: #111827; }
.btn-icon-close svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; }
.envvar-body {
  padding: 14px 18px; overflow: auto; flex: 1;
  display: flex; flex-direction: column; gap: 10px;
}
.envvar-target {
  margin: 0; font-size: 12px; color: #6b7280; line-height: 1.6;
}
.envvar-target code {
  padding: 1px 5px; background: #f3f4f6; border-radius: 3px;
  font-family: 'SF Mono', Menlo, Consolas, monospace; font-size: 11px; color: #165dff;
}
.envvar-filter {
  width: 100%; padding: 8px 12px;
  font-size: 12px; border: 1px solid #d1d5db; border-radius: 8px;
  outline: none;
}
.envvar-filter:focus { border-color: #165dff; box-shadow: 0 0 0 3px rgba(22, 93, 255, 0.12); }
.envvar-list {
  flex: 1; overflow: auto; max-height: 320px;
  border: 1px solid #e5e7eb; border-radius: 8px;
  display: flex; flex-direction: column;
}
.envvar-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 9px 12px;
  background: #fff; border: none; border-bottom: 1px solid #f3f4f6;
  cursor: pointer; text-align: left;
  transition: background 0.12s;
}
.envvar-item:last-child { border-bottom: none; }
.envvar-item:hover { background: #eff6ff; }
.envvar-name {
  font-family: 'SF Mono', Menlo, Consolas, monospace;
  font-size: 12px; color: #111827;
}
.envvar-check { width: 14px; height: 14px; color: #165dff; opacity: 0; transition: opacity 0.12s; }
.envvar-item:hover .envvar-check { opacity: 1; }
.envvar-empty {
  margin: 0; padding: 24px 12px; text-align: center;
  font-size: 12px; color: #9ca3af;
}
.envvar-tip {
  margin: 0; font-size: 11px; color: #9ca3af; line-height: 1.5;
}
.envvar-tip code {
  padding: 1px 4px; background: #f3f4f6; border-radius: 3px;
  font-family: 'SF Mono', Menlo, Consolas, monospace; font-size: 10px;
}
.envvar-foot {
  display: flex; justify-content: flex-end; gap: 8px;
  padding: 12px 18px; border-top: 1px solid #e5e7eb;
}
.envvar-foot .btn {
  height: 32px; padding: 0 14px; font-size: 12px; font-weight: 600;
  border-radius: 8px; cursor: pointer; border: 1px solid transparent;
}
.envvar-foot .btn-ghost { background: transparent; color: #6b7280; border-color: #d1d5db; }
.envvar-foot .btn-ghost:hover { background: #f3f4f6; }
.envvar-foot .btn-primary { background: #165dff; color: #fff; }
.envvar-foot .btn-primary:hover { background: #1454e8; }
.envvar-pop-enter-active, .envvar-pop-leave-active { transition: opacity 0.18s ease; }
.envvar-pop-enter-from, .envvar-pop-leave-to { opacity: 0; }
</style>
