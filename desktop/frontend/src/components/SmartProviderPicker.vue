<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useEnvStore, type ProviderCandidate } from '../stores/env'

const env = useEnvStore()
const { smartFlow } = storeToRefs(env)

const keyInput = ref<HTMLInputElement | null>(null)
const urlInput = ref<HTMLInputElement | null>(null)

const progressIndex = computed(() => {
  switch (smartFlow.value.step) {
    case 'key':
    case 'detecting':
    case 'error':
      return 0
    case 'choose':
    case 'custom_url':
      return 1
    case 'applying':
      return 2
    case 'done':
      return 3
    default:
      return -1
  }
})

const subtitle = computed(() => {
  switch (smartFlow.value.step) {
    case 'key':
      return '只需粘贴 Key · Base URL / 协议 / 模型由管道自动配置'
    case 'detecting':
      return '正在识别厂商、协议与 Base URL…'
    case 'choose':
      return '匹配到多个厂商，选择后将写入并验证'
    case 'custom_url':
      return '未能匹配已知厂商，请补充 Base URL'
    case 'applying':
      return '正在写入配置并验证密钥…'
    case 'done':
      return '管道完成'
    case 'error':
      return '未能识别'
    default:
      return ''
  }
})

const canDismiss = computed(() =>
  ['key', 'choose', 'custom_url', 'done', 'error'].includes(smartFlow.value.step),
)

function protocolBadge(c: ProviderCandidate) {
  return env.protocolOf(c)
}

function scoreText(c: ProviderCandidate) {
  if (typeof c.score !== 'number') return ''
  return ` · score ${Math.round(c.score * 100)}%`
}

watch(
  () => [smartFlow.value.visible, smartFlow.value.step] as const,
  async ([visible, step]) => {
    if (!visible) return
    await nextTick()
    if (step === 'key') keyInput.value?.focus()
    if (step === 'custom_url') urlInput.value?.focus()
  },
)

function onOverlayClick() {
  if (canDismiss.value) env.cancelSmartPicker()
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && canDismiss.value) env.cancelSmartPicker()
}

function onKeyEnter(e: KeyboardEvent) {
  if (e.key === 'Enter') {
    e.preventDefault()
    env.runSmartDetect()
  }
}

function onUrlEnter(e: KeyboardEvent) {
  if (e.key === 'Enter') {
    e.preventDefault()
    env.confirmSmartCustomUrl()
  }
}
</script>

<template>
  <div
    v-if="smartFlow.visible"
    class="fixed inset-0 z-[80] flex items-center justify-center p-5 bg-[rgba(15,20,30,0.48)]"
    role="dialog"
    aria-modal="true"
    aria-labelledby="sf-title"
    tabindex="-1"
    @click.self="onOverlayClick"
    @keydown="onKeydown"
  >
    <div class="w-full max-w-[560px] max-h-[min(84vh,720px)] bg-white rounded-2xl shadow-[0_24px_64px_rgba(15,20,30,0.22)] flex flex-col overflow-hidden">
      <!-- Head -->
      <div class="px-[18px] pt-4 pb-3 border-b border-ink-100">
        <h3 id="sf-title" class="m-0 text-[15px] font-bold text-ink-900">智能添加 Provider</h3>
        <p class="m-0 mt-1 text-xs text-ink-500 leading-snug">{{ subtitle }}</p>
      </div>

      <!-- Progress -->
      <div class="flex gap-1.5 px-[18px] pb-3" aria-hidden="true">
        <i
          v-for="i in 4"
          :key="i"
          class="flex-1 h-[3px] rounded-full transition-colors"
          :class="
            progressIndex === i - 1
              ? 'bg-brand-500'
              : progressIndex > i - 1
                ? 'bg-brand-100'
                : 'bg-ink-200'
          "
        />
      </div>

      <!-- Body -->
      <div class="px-[18px] py-3.5 overflow-auto flex-1">
        <!-- Key entry -->
        <template v-if="smartFlow.step === 'key'">
          <div class="flex flex-col gap-1.5 mt-1">
            <label for="sf-key-input" class="text-[11px] font-medium text-ink-700">API Key</label>
            <input
              id="sf-key-input"
              ref="keyInput"
              v-model="smartFlow.apiKey"
              type="password"
              placeholder="sk-... 或厂商密钥"
              autocomplete="off"
              class="w-full px-3 py-3 text-[13px] font-mono border border-ink-300 rounded-[10px]"
              @keydown="onKeyEnter"
            />
          </div>
          <p class="m-0 mt-2.5 text-[11px] text-ink-500 leading-relaxed">
            粘贴 Key 后开始识别；多候选时会让你选择厂商，自定义端点才会追问 Base URL。
          </p>
        </template>

        <!-- Detecting -->
        <template v-else-if="smartFlow.step === 'detecting'">
          <div class="grid place-items-center text-center py-9 px-3">
            <div
              class="w-9 h-9 rounded-full border-[3px] border-brand-100 border-t-brand-500 animate-spin mb-3.5"
              aria-hidden="true"
            />
            <h4 class="m-0 mb-1.5 text-sm font-semibold">识别中</h4>
            <p class="m-0 text-xs text-ink-500 leading-relaxed">解析 Key 指纹 · 匹配厂商目录 · 推断协议</p>
            <div class="mt-4 w-full max-w-[360px] text-left bg-ink-100 rounded-[10px] px-3 py-2.5 text-[11px] font-mono text-ink-700 leading-relaxed">
              <div
                v-for="(line, idx) in smartFlow.logs"
                :key="idx"
                :class="{
                  'text-brand-600': line.cls === 'run',
                  'text-emerald-600': line.cls === 'ok',
                  'text-red-600': line.cls === 'err',
                }"
              >{{ line.text }}</div>
            </div>
          </div>
        </template>

        <!-- Choose provider -->
        <template v-else-if="smartFlow.step === 'choose'">
          <button
            v-for="c in smartFlow.candidates"
            :key="c.provider"
            type="button"
            class="w-full text-left border rounded-xl px-3 py-3 mb-2 bg-white transition hover:border-brand-500 hover:bg-brand-50"
            :class="smartFlow.selected === c.provider
              ? 'border-brand-500 bg-brand-50 shadow-[0_0_0_1px_#165dff]'
              : 'border-ink-300'"
            @click="smartFlow.selected = c.provider"
          >
            <div class="flex items-start justify-between gap-2.5">
              <div class="min-w-0">
                <div class="text-[13px] font-bold text-ink-900">{{ c.label || c.provider }}</div>
                <div class="text-[11px] text-ink-500 mt-0.5 font-mono">
                  {{ c.provider }}{{ scoreText(c) }}
                </div>
              </div>
              <span
                class="px-1.5 py-0.5 text-[10px] font-bold rounded-full shrink-0"
                :class="protocolBadge(c) === 'anthropic' ? 'bg-orange-50 text-orange-700' : 'bg-emerald-50 text-emerald-700'"
              >{{ protocolBadge(c) }}</span>
            </div>
            <div class="mt-2 space-y-0.5 text-[10px] font-mono text-ink-500">
              <div
                v-for="(pc, proto) in (c.protocols || {})"
                :key="proto"
                :class="proto === protocolBadge(c) ? 'text-brand-600 font-semibold' : ''"
              >
                {{ proto === protocolBadge(c) ? '▸ ' : '  ' }}{{ proto }}: {{ pc.base_url || '(空)' }}
              </div>
            </div>
            <div v-if="c.protocol_reason" class="text-[11px] text-brand-600 mt-1.5">{{ c.protocol_reason }}</div>
            <div v-else-if="c.reason" class="text-[11px] text-ink-500 mt-1.5">{{ c.reason }}</div>
          </button>
        </template>

        <!-- Custom URL -->
        <template v-else-if="smartFlow.step === 'custom_url'">
          <div class="flex flex-col gap-1.5">
            <label for="sf-url-input" class="text-[11px] font-medium text-ink-700">Base URL</label>
            <input
              id="sf-url-input"
              ref="urlInput"
              v-model="smartFlow.baseUrl"
              type="url"
              placeholder="https://api.example.com/v1"
              class="w-full px-3 py-3 text-[13px] font-mono border border-ink-300 rounded-[10px]"
              @keydown="onUrlEnter"
            />
          </div>
          <p class="m-0 mt-2.5 text-[11px] text-ink-500 leading-relaxed">
            将按 OpenAI 兼容协议写入，并自动验证模型列表。
          </p>
        </template>

        <!-- Applying -->
        <template v-else-if="smartFlow.step === 'applying'">
          <div class="grid place-items-center text-center py-9 px-3">
            <div
              class="w-9 h-9 rounded-full border-[3px] border-brand-100 border-t-brand-500 animate-spin mb-3.5"
              aria-hidden="true"
            />
            <h4 class="m-0 mb-1.5 text-sm font-semibold">写入并验证</h4>
            <p class="m-0 text-xs text-ink-500 leading-relaxed">
              {{ smartFlow.candidates.find(c => c.provider === smartFlow.selected)?.label || smartFlow.selected || 'Provider' }}
              · 自动填充 Base URL
            </p>
            <div class="mt-4 w-full max-w-[360px] text-left bg-ink-100 rounded-[10px] px-3 py-2.5 text-[11px] font-mono text-ink-700 leading-relaxed max-h-40 overflow-auto">
              <div
                v-for="(line, idx) in smartFlow.logs"
                :key="idx"
                :class="{
                  'text-brand-600': line.cls === 'run',
                  'text-emerald-600': line.cls === 'ok',
                  'text-red-600': line.cls === 'err',
                }"
              >{{ line.text }}</div>
            </div>
          </div>
        </template>

        <!-- Done -->
        <template v-else-if="smartFlow.step === 'done' && smartFlow.result">
          <div class="text-center pt-7 pb-3 px-3">
            <div class="w-12 h-12 rounded-full bg-emerald-50 text-emerald-600 grid place-items-center mx-auto mb-3.5 text-[22px] font-bold" aria-hidden="true">✓</div>
            <h4 class="m-0 mb-1.5 text-base font-semibold">已接入并设为 Active</h4>
            <p class="m-0 text-xs text-ink-500 leading-relaxed">
              {{ smartFlow.result.label || smartFlow.result.provider }} 已写入 llm.yaml，并设为当前 Active。
            </p>
            <div class="grid grid-cols-3 gap-2 mt-[18px] mb-1 text-left">
              <div class="bg-ink-100 rounded-[10px] p-2.5">
                <span class="text-[10px] text-ink-500 font-semibold uppercase tracking-wide">Provider</span>
                <b class="block text-[13px] mt-0.5 font-semibold truncate">{{ smartFlow.result.provider }}</b>
              </div>
              <div class="bg-ink-100 rounded-[10px] p-2.5">
                <span class="text-[10px] text-ink-500 font-semibold uppercase tracking-wide">Protocol</span>
                <b class="block text-[13px] mt-0.5 font-semibold truncate">{{ smartFlow.result.protocol }}</b>
              </div>
              <div class="bg-ink-100 rounded-[10px] p-2.5">
                <span class="text-[10px] text-ink-500 font-semibold uppercase tracking-wide">Models</span>
                <b class="block text-[13px] mt-0.5 font-semibold">{{ smartFlow.result.models }}</b>
              </div>
            </div>
            <p v-if="smartFlow.result.url" class="mt-3 font-mono text-[11px] text-ink-500 truncate">{{ smartFlow.result.url }}</p>
          </div>
        </template>

        <!-- Error -->
        <template v-else-if="smartFlow.step === 'error'">
          <div class="text-center py-7 px-3">
            <div class="w-12 h-12 rounded-full bg-red-50 text-red-600 grid place-items-center mx-auto mb-3.5 font-bold text-xl" aria-hidden="true">!</div>
            <h4 class="m-0 mb-1.5 text-[15px] font-semibold">识别失败</h4>
            <p class="m-0 text-xs text-ink-500 leading-relaxed">{{ smartFlow.error || '未知错误' }}</p>
          </div>
        </template>
      </div>

      <!-- Foot -->
      <div class="px-[18px] py-3 border-t border-ink-100 flex justify-end gap-2 bg-white">
        <template v-if="smartFlow.step === 'key'">
          <button
            type="button"
            class="inline-flex items-center h-[34px] px-3.5 text-[12.5px] font-semibold rounded-[10px] bg-white text-ink-700 border border-ink-300 hover:bg-ink-100 transition"
            @click="env.cancelSmartPicker()"
          >取消</button>
          <button
            type="button"
            class="inline-flex items-center h-[34px] px-3.5 text-[12.5px] font-semibold rounded-[10px] text-white bg-gradient-to-b from-[#2f72ff] via-brand-500 to-[#1454e8] border border-brand-700/20 hover:from-brand-500 hover:to-brand-600 transition disabled:opacity-45"
            :disabled="!smartFlow.apiKey.trim()"
            @click="env.runSmartDetect()"
          >开始识别</button>
        </template>

        <template v-else-if="smartFlow.step === 'detecting'">
          <button
            type="button"
            class="inline-flex items-center h-[34px] px-3.5 text-[12.5px] font-semibold rounded-[10px] bg-white text-ink-700 border border-ink-300 hover:bg-ink-100 transition"
            @click="env.cancelSmartPicker()"
          >取消</button>
        </template>

        <template v-else-if="smartFlow.step === 'choose'">
          <button
            type="button"
            class="inline-flex items-center h-[34px] px-3.5 text-[12.5px] font-semibold rounded-[10px] bg-white text-ink-700 border border-ink-300 hover:bg-ink-100 transition"
            @click="env.cancelSmartPicker()"
          >取消</button>
          <button
            type="button"
            class="inline-flex items-center h-[34px] px-3.5 text-[12.5px] font-semibold rounded-[10px] text-white bg-gradient-to-b from-[#2f72ff] via-brand-500 to-[#1454e8] border border-brand-700/20 hover:from-brand-500 hover:to-brand-600 transition disabled:opacity-45"
            :disabled="!smartFlow.selected || smartFlow.busy"
            @click="env.confirmSmartPicker()"
          >确认并验证</button>
        </template>

        <template v-else-if="smartFlow.step === 'custom_url'">
          <button
            type="button"
            class="inline-flex items-center h-[34px] px-3.5 text-[12.5px] font-semibold rounded-[10px] bg-white text-ink-700 border border-ink-300 hover:bg-ink-100 transition"
            @click="env.cancelSmartPicker()"
          >取消</button>
          <button
            type="button"
            class="inline-flex items-center h-[34px] px-3.5 text-[12.5px] font-semibold rounded-[10px] text-white bg-gradient-to-b from-[#2f72ff] via-brand-500 to-[#1454e8] border border-brand-700/20 hover:from-brand-500 hover:to-brand-600 transition disabled:opacity-45"
            :disabled="!smartFlow.baseUrl.trim() || smartFlow.busy"
            @click="env.confirmSmartCustomUrl()"
          >继续并验证</button>
        </template>

        <template v-else-if="smartFlow.step === 'applying'">
          <button
            type="button"
            disabled
            class="inline-flex items-center h-[34px] px-3.5 text-[12.5px] font-semibold rounded-[10px] bg-white text-ink-500 border border-ink-300 opacity-45"
          >管道运行中…</button>
        </template>

        <template v-else-if="smartFlow.step === 'done'">
          <button
            type="button"
            class="inline-flex items-center h-[34px] px-3.5 text-[12.5px] font-semibold rounded-[10px] bg-white text-ink-700 border border-ink-300 hover:bg-ink-100 transition"
            @click="env.smartFlowAgain()"
          >再添加一个</button>
          <button
            type="button"
            class="inline-flex items-center h-[34px] px-3.5 text-[12.5px] font-semibold rounded-[10px] text-white bg-gradient-to-b from-[#2f72ff] via-brand-500 to-[#1454e8] border border-brand-700/20 hover:from-brand-500 hover:to-brand-600 transition"
            @click="env.cancelSmartPicker()"
          >完成</button>
        </template>

        <template v-else-if="smartFlow.step === 'error'">
          <button
            type="button"
            class="inline-flex items-center h-[34px] px-3.5 text-[12.5px] font-semibold rounded-[10px] bg-white text-ink-700 border border-ink-300 hover:bg-ink-100 transition"
            @click="env.cancelSmartPicker()"
          >关闭</button>
          <button
            type="button"
            class="inline-flex items-center h-[34px] px-3.5 text-[12.5px] font-semibold rounded-[10px] text-white bg-gradient-to-b from-[#2f72ff] via-brand-500 to-[#1454e8] border border-brand-700/20 hover:from-brand-500 hover:to-brand-600 transition"
            @click="env.smartFlowAgain()"
          >重试</button>
        </template>
      </div>
    </div>
  </div>
</template>
