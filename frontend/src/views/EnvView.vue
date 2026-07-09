<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useEnvStore } from '../stores/env'
import SmartProviderPicker from '../components/SmartProviderPicker.vue'

const env = useEnvStore()
const { envData, envDataText, selectedProvider, providerNames, proxyEnabled, smartBusy } = storeToRefs(env)
const {
  selectProvider, updateEnvDataSection, addProvider, deleteProvider, setActiveProvider,
  addProtocol, deleteProtocol, addModel, deleteModel, renameModel, saveEnv,
  generateProxyConfig, startProxyServer, verifyLlm, addSmartProvider,
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
  const primary = envData.value.llm._active_provider === pn
    ? (envData.value.llm._active_protocol || protos[0] || '?')
    : (protos[0] || '?')
  let models = 0
  for (const p of protos) models += Object.keys(block[p]?.models || {}).length
  return `${primary} · ${models} models`
}

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
                >active</span>
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
                  当前 Active Provider · 协议 {{ envData.llm._active_protocol || '—' }}
                </template>
                <template v-else>未设为 Active</template>
              </div>
            </div>
            <div class="flex gap-2 flex-wrap">
              <button
                type="button"
                @click="setActiveProvider(selectedProvider)"
                class="inline-flex items-center gap-1.5 h-7 px-2.5 text-[11.5px] font-semibold rounded-lg bg-brand-50 text-brand-600 border border-brand-100 hover:bg-brand-100 transition"
              >
                <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6L9 17l-5-5"/></svg>
                设为 Active
              </button>
              <button
                type="button"
                @click="deleteProvider(selectedProvider)"
                class="inline-flex items-center h-7 px-2.5 text-[11.5px] font-semibold rounded-lg text-ink-500 hover:bg-red-50 hover:text-red-600 hover:border-red-200 border border-transparent transition"
              >删除</button>
            </div>
          </div>

          <div class="px-[18px] py-4 pb-5 grid gap-3.5 overflow-auto">
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              <div class="flex flex-col gap-1">
                <label class="text-[11px] font-medium text-ink-700">Active Provider</label>
                <select v-model="envData.llm._active_provider" class="w-full px-2.5 py-2 text-xs border border-ink-300 rounded-lg">
                  <option v-for="p in providerNames" :key="p" :value="p">{{ p }}</option>
                </select>
              </div>
              <div class="flex flex-col gap-1">
                <label class="text-[11px] font-medium text-ink-700">Active Protocol</label>
                <input
                  v-model="envData.llm._active_protocol"
                  placeholder="openai|anthropic"
                  class="w-full px-2.5 py-2 text-xs border border-ink-300 rounded-lg font-mono"
                />
              </div>
            </div>

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
                  <label class="text-[11px] font-medium text-ink-700">api_key</label>
                  <input type="password" v-model="envData.llm[selectedProvider][proto].api_key" class="w-full px-2.5 py-2 text-xs border border-ink-300 rounded-lg" />
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
                  <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="M22 4L12 14.01l-3-3"/></svg>
                  验证 key
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
  </div>
</template>
