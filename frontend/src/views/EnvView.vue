<script setup lang="ts">
import { computed, ref, reactive } from 'vue'
import { storeToRefs } from 'pinia'
import { useEnvStore } from '../stores/env'
import { useUiStore } from '../stores/ui'
import SmartProviderPicker from '../components/SmartProviderPicker.vue'

const env = useEnvStore()
const ui = useUiStore()
const { envData, envDataText, selectedProvider, providerNames, proxyEnabled, smartBusy, envVars, envVarsBusy } = storeToRefs(env)
const {
  selectProvider, updateEnvDataSection, addProvider, deleteProvider, setActiveProvider,
  addProtocol, deleteProtocol, addModel, deleteModel, renameModel, saveEnv,
  generateProxyConfig, startProxyServer, verifyLlm, addSmartProvider,
  fetchEnvVars, setApiKeyFromEnv,
} = env

const providerFilter = ref('')

const filteredProviders = computed(() => {
  const q = providerFilter.value.trim().toLowerCase()
  if (!q) return providerNames.value
  return providerNames.value.filter((n) => n.toLowerCase().includes(q))
})

const selectedProtocols = computed(() => {
  const pn = selectedProvider.value
  if (!pn || !envData.value.llm?.[pn]) return [] as string[]
  return Object.keys(envData.value.llm[pn]).filter(
    (k) => typeof envData.value.llm[pn][k] === 'object' && envData.value.llm[pn][k] !== null,
  )
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

const defaultProvider = computed<string>({
  get: () => envData.value.llm?._active_provider || '',
  set: (v: string) => { if (envData.value.llm) envData.value.llm._active_provider = v },
})
const hasProviders = computed(() => providerNames.value.length > 0)

function avatarStyle(name: string) {
  const hues: Record<string, string> = {
    openai: 'linear-gradient(145deg,#0e42d2,#1f2329)',
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
          Master–Detail · 左侧选厂商，右侧编辑协议与模型 ·
          <span class="font-mono text-[12px]">llm.yaml</span>
        </p>
      </div>
      <div class="flex gap-2 flex-wrap">
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
          @click="saveEnv()"
          class="inline-flex items-center gap-1.5 h-9 px-3.5 text-[12.5px] font-semibold rounded-[10px] text-white border border-brand-700/20 bg-gradient-to-b from-[#2f72ff] via-brand-500 to-[#1454e8] hover:from-brand-500 hover:to-brand-600 shadow-sm transition"
        >
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><path d="M17 21v-8H7v8M7 3v5h8"/></svg>
          保存
        </button>
      </div>
    </div>

    <!-- 默认启用的 LLM Provider -->
    <section class="bg-white border border-ink-300/80 rounded-[14px] shadow-card p-[18px]">
      <div class="flex items-center gap-2.5 mb-2">
        <span class="inline-flex items-center justify-center w-5 h-5 rounded-md bg-brand-50 text-brand-600">
          <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
        </span>
        <h3 class="m-0 text-[13px] font-semibold text-ink-900">默认启用的 LLM Provider</h3>
        <span v-if="defaultProvider" class="px-1.5 py-0.5 text-[10px] font-semibold rounded bg-brand-50 text-brand-600">{{ defaultProvider }}</span>
      </div>
      <p class="m-0 mb-3 text-xs text-ink-500 leading-relaxed">
        选择的 Provider 将作为同步到 IDE 时的默认 LLM。可随时切换，保存后生效。
      </p>
      <div class="flex items-center gap-2.5 flex-wrap">
        <select
          v-model="defaultProvider"
          :disabled="!hasProviders"
          class="px-3 py-2 text-xs border border-ink-300 rounded-lg bg-white min-w-[220px] disabled:bg-ink-100 disabled:text-ink-500"
        >
          <option value="" disabled>{{ hasProviders ? '请选择…' : '暂无 Provider' }}</option>
          <option v-for="p in providerNames" :key="p" :value="p">{{ p }}</option>
        </select>
        <button
          v-if="selectedProvider && selectedProvider !== defaultProvider"
          type="button"
          @click="defaultProvider = selectedProvider"
          class="inline-flex items-center gap-1.5 h-9 px-3 text-[12px] font-semibold rounded-lg bg-brand-50 text-brand-600 border border-brand-100 hover:bg-brand-100 transition"
        >
          <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6L9 17l-5-5"/></svg>
          设当前为默认
        </button>
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
              <div class="text-[13px] font-semibold truncate">
                {{ pn }}
                <span
                  v-if="envData.llm._active_provider === pn"
                  class="ml-1 px-1.5 py-0.5 text-[10px] font-semibold rounded bg-brand-50 text-brand-600 align-middle"
                >默认</span>
              </div>
              <div class="text-[11px] text-ink-500 font-mono mt-0.5 truncate">{{ protocolSummary(pn) }}</div>
            </div>
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
                <template v-if="envData.llm._active_provider === selectedProvider">
                  当前默认 Provider
                </template>
                <template v-else>非默认 · 点击右侧按钮设为默认</template>
              </div>
            </div>
            <div class="flex gap-2 flex-wrap">
              <button
                v-if="envData.llm._active_provider !== selectedProvider"
                type="button"
                @click="setActiveProvider(selectedProvider)"
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
              class="border border-ink-300/80 rounded-xl p-3.5 bg-gradient-to-b from-white to-ink-100/80"
            >
              <div class="flex items-center justify-between mb-3">
                <h3 class="m-0 text-[12px] font-semibold tracking-wider uppercase text-ink-700">{{ proto }}</h3>
                <button
                  type="button"
                  @click="deleteProtocol(selectedProvider, proto)"
                  class="inline-flex items-center h-7 px-2.5 text-[11.5px] font-semibold rounded-lg text-ink-500 hover:bg-red-50 hover:text-red-600 border border-transparent transition"
                >删除协议</button>
              </div>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5 mb-2.5">
                <div class="flex flex-col gap-1">
                  <label class="text-[11px] font-medium text-ink-700">base_url</label>
                  <input v-model="envData.llm[selectedProvider][proto].base_url" class="w-full px-2.5 py-2 text-xs border border-ink-300 rounded-lg font-mono" />
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
                      class="w-full px-2.5 py-2 pr-20 text-xs border border-ink-300 rounded-lg font-mono"
                      :class="{ 'border-emerald-300 bg-emerald-50/40': isEnvRef(envData.llm[selectedProvider][proto].api_key) }"
                    />
                    <div class="absolute right-1 top-1/2 -translate-y-1/2 flex items-center gap-0.5">
                      <button
                        type="button"
                        :aria-label="isKeyVisible(selectedProvider, proto) ? '隐藏' : '显示'"
                        :title="isKeyVisible(selectedProvider, proto) ? '隐藏密钥' : '查看密钥'"
                        @click="toggleKeyVisible(selectedProvider, proto)"
                        class="inline-flex items-center justify-center w-7 h-7 rounded-md text-ink-500 hover:bg-ink-100 hover:text-ink-700 transition"
                      >
                        <svg v-if="isKeyVisible(selectedProvider, proto)" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
                        <svg v-else class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                      </button>
                      <button
                        type="button"
                        aria-label="从环境变量选择"
                        title="从环境变量选择"
                        @click="openEnvVarPicker(selectedProvider, proto)"
                        class="inline-flex items-center justify-center w-7 h-7 rounded-md text-ink-500 hover:bg-brand-50 hover:text-brand-600 transition"
                      >
                        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>
                      </button>
                    </div>
                  </div>
                </div>
              </div>
              <table class="w-full text-xs border-collapse mt-2.5 bg-white rounded-lg overflow-hidden border border-ink-300/80">
                <thead>
                  <tr>
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
                  >
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

    <!-- Side strip: Proxy + extras -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-3.5">
      <section class="bg-white border border-ink-300/80 rounded-[14px] shadow-card p-[18px]">
        <h3 class="m-0 mb-1.5 text-[13px] font-semibold flex items-center gap-2 before:content-[''] before:w-[3px] before:h-3.5 before:rounded-sm before:bg-brand-500">
          Proxy
        </h3>
        <p class="m-0 mb-3 text-xs text-ink-500 leading-relaxed">
          IDE → proxy(127.0.0.1:4000) → 真实 provider。开启后 init-env 会覆盖 ACTIVE_BASE_URL。
        </p>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
          <div class="flex items-center gap-2.5">
            <label class="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" v-model="envData.proxy.enable" class="sr-only peer">
              <div class="w-9 h-5 bg-ink-300 rounded-full peer-checked:bg-emerald-500 transition relative">
                <div
                  class="absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition"
                  :class="{ 'translate-x-4': envData.proxy && envData.proxy.enable }"
                />
              </div>
            </label>
            <span
              :class="['text-xs font-semibold', envData.proxy && envData.proxy.enable ? 'text-emerald-600' : 'text-ink-500']"
            >{{ envData.proxy && envData.proxy.enable ? '已开启' : '已关闭' }}</span>
          </div>
          <div class="hidden sm:block" />
          <div class="flex flex-col gap-1">
            <label class="text-[11px] font-medium text-ink-700">base_url</label>
            <input
              v-model="envData.proxy.base_url"
              :disabled="!envData.proxy || !envData.proxy.enable"
              placeholder="http://127.0.0.1:4000/v1"
              class="w-full px-2.5 py-2 text-xs border border-ink-300 rounded-lg font-mono disabled:bg-ink-100 disabled:text-ink-500"
            />
          </div>
          <div class="flex flex-col gap-1">
            <label class="text-[11px] font-medium text-ink-700">api_key</label>
            <input
              type="password"
              v-model="envData.proxy.api_key"
              :disabled="!envData.proxy || !envData.proxy.enable"
              class="w-full px-2.5 py-2 text-xs border border-ink-300 rounded-lg disabled:bg-ink-100 disabled:text-ink-500"
            />
          </div>
        </div>
        <div class="flex flex-col gap-1 mb-3">
          <label class="text-[11px] font-medium text-ink-700">启动命令</label>
          <input
            v-model="envData.proxy.start_cmd"
            placeholder="litellm --config proxy/config.yaml --port 4000"
            class="w-full px-2.5 py-2 text-xs border border-ink-300 rounded-lg font-mono"
          />
        </div>
        <div class="flex gap-2 flex-wrap">
          <button
            type="button"
            @click="generateProxyConfig"
            class="inline-flex items-center h-[34px] px-3.5 text-[12.5px] font-semibold rounded-[10px] bg-white text-ink-700 border border-ink-300 hover:bg-ink-100 transition"
          >生成 config</button>
          <button
            type="button"
            @click="startProxyServer"
            :disabled="!proxyEnabled"
            class="inline-flex items-center gap-1.5 h-[34px] px-3.5 text-[12.5px] font-semibold rounded-[10px] text-white border border-brand-700/20 bg-gradient-to-b from-[#2f72ff] via-brand-500 to-[#1454e8] hover:from-brand-500 hover:to-brand-600 disabled:opacity-45 transition"
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            启动代理
          </button>
        </div>
      </section>

      <section class="bg-white border border-ink-300/80 rounded-[14px] shadow-card p-[18px]">
        <h3 class="m-0 mb-1.5 text-[13px] font-semibold flex items-center gap-2 before:content-[''] before:w-[3px] before:h-3.5 before:rounded-sm before:bg-brand-500">
          Embedding / TTS / ASR / Vision / Misc
        </h3>
        <p class="m-0 mb-3 text-xs text-ink-500 leading-relaxed">附属段以 JSON 编辑，保存时写回 llm.yaml。</p>
        <div class="space-y-3">
          <div v-for="sec in ['embedding','tts','asr','vision','misc']" :key="sec" class="flex flex-col gap-1">
            <label class="text-[11px] font-medium text-ink-700">{{ sec }}</label>
            <textarea
              v-model="envDataText[sec]"
              @input="updateEnvDataSection(sec)"
              rows="4"
              class="w-full px-2.5 py-2 text-[11px] border border-ink-300 rounded-lg font-mono bg-ink-100"
            />
          </div>
        </div>
      </section>
    </div>

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
