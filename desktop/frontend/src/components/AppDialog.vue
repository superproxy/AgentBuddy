<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useUiStore } from '../stores/ui'

const ui = useUiStore()
const inputRef = ref<HTMLInputElement | null>(null)
const confirmBtnRef = ref<HTMLButtonElement | null>(null)

const isPrompt = computed(() => ui.dialog.kind === 'prompt')
const isDanger = computed(() => ui.dialog.tone === 'danger')

const detailInitials = computed(() => {
  const name = (ui.dialog.detail || '').trim()
  if (!name) return '?'
  const parts = name.replace(/[^a-zA-Z0-9\u4e00-\u9fff]+/g, ' ').trim().split(/\s+/)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return name.slice(0, 2).toUpperCase()
})

const detailLabel = computed(() => {
  if (ui.dialog.title.includes('协议')) return '协议'
  if (ui.dialog.title.includes('Provider')) return 'Provider'
  return '目标'
})

watch(
  () => ui.dialog.visible,
  async (visible) => {
    if (!visible) return
    await nextTick()
    if (isPrompt.value) inputRef.value?.focus()
    else confirmBtnRef.value?.focus()
  },
)

function onKeydown(e: KeyboardEvent) {
  if (!ui.dialog.visible) return
  if (e.key === 'Escape') {
    e.preventDefault()
    ui.cancelDialog()
  } else if (e.key === 'Enter' && !e.isComposing) {
    if (isPrompt.value || e.target === confirmBtnRef.value) {
      e.preventDefault()
      ui.submitDialog()
    }
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="app-dialog">
      <div
        v-if="ui.dialog.visible"
        class="fixed inset-0 z-[110] flex items-center justify-center p-5 bg-[rgba(15,20,30,0.48)]"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="'app-dialog-title'"
        :aria-describedby="ui.dialog.message ? 'app-dialog-desc' : undefined"
        @click.self="ui.cancelDialog()"
        @keydown="onKeydown"
      >
        <div class="w-full max-w-[420px] bg-white rounded-2xl shadow-[0_24px_64px_rgba(15,20,30,0.22)] overflow-hidden flex flex-col">
          <!-- Head -->
          <div class="px-5 pt-5 pb-3 flex items-start gap-3">
            <div
              class="w-10 h-10 rounded-xl grid place-items-center shrink-0"
              :class="isDanger ? 'bg-red-50 text-red-600' : 'bg-brand-50 text-brand-600'"
              aria-hidden="true"
            >
              <!-- trash / plus / pencil icons -->
              <svg v-if="isDanger" class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                <path d="M10 11v6M14 11v6" />
              </svg>
              <svg v-else class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 5v14M5 12h14" />
              </svg>
            </div>
            <div class="min-w-0 flex-1 pt-0.5">
              <h3 id="app-dialog-title" class="m-0 text-[15px] font-bold text-ink-900 leading-snug">
                {{ ui.dialog.title }}
              </h3>
              <p
                v-if="ui.dialog.message"
                id="app-dialog-desc"
                class="m-0 mt-1 text-xs text-ink-500 leading-relaxed whitespace-pre-line"
              >
                {{ ui.dialog.message }}
              </p>
            </div>
          </div>

          <!-- Body -->
          <div class="px-5 pb-2">
            <!-- Confirm target: identity chip, not an input-like bar -->
            <div
              v-if="ui.dialog.detail && !isPrompt"
              class="mb-3 flex items-center gap-3 rounded-xl border px-3 py-2.5"
              :class="isDanger ? 'border-red-100 bg-red-50/60' : 'border-brand-100 bg-brand-50/50'"
            >
              <div
                class="w-8 h-8 rounded-lg grid place-items-center text-[11px] font-bold text-white shrink-0"
                :class="isDanger
                  ? 'bg-gradient-to-br from-red-500 to-red-700'
                  : 'bg-gradient-to-br from-brand-500 to-brand-700'"
                aria-hidden="true"
              >{{ detailInitials }}</div>
              <div class="min-w-0 flex-1">
                <div class="text-[10px] font-semibold uppercase tracking-wide text-ink-500">
                  将{{ isDanger ? '删除' : '操作' }}的{{ detailLabel }}
                </div>
                <div
                  class="mt-0.5 text-[13px] font-semibold font-mono text-ink-900 truncate"
                  :title="ui.dialog.detail"
                >{{ ui.dialog.detail }}</div>
              </div>
            </div>

            <div
              v-if="!isPrompt && ui.dialog.links?.length"
              class="mb-3 flex flex-wrap gap-2"
            >
              <a
                v-for="link in ui.dialog.links"
                :key="link.href"
                :href="link.href"
                target="_blank"
                rel="noopener noreferrer"
                class="inline-flex items-center gap-1 h-7 px-2.5 text-[11px] font-medium rounded-lg border border-ink-300 text-brand-600 bg-white hover:bg-brand-50 hover:border-brand-300 transition"
              >
                <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                  <path d="M15 3h6v6" />
                  <path d="M10 14L21 3" />
                </svg>
                {{ link.label }}
              </a>
            </div>

            <template v-if="isPrompt">
              <label
                v-if="ui.dialog.label"
                for="app-dialog-input"
                class="block text-[11px] font-medium text-ink-700 mb-1.5"
              >{{ ui.dialog.label }}</label>
              <input
                id="app-dialog-input"
                ref="inputRef"
                v-model="ui.dialog.value"
                type="text"
                :placeholder="ui.dialog.placeholder"
                :class="[
                  'w-full px-3 py-2.5 text-[13px] border rounded-[10px] transition',
                  ui.dialog.mono ? 'font-mono' : '',
                  ui.dialog.error
                    ? 'border-red-400 focus:border-red-500'
                    : 'border-ink-300',
                ]"
                @input="ui.dialog.error = ''"
              />
              <p
                v-if="ui.dialog.error"
                role="alert"
                class="m-0 mt-1.5 text-[11px] text-red-600"
              >{{ ui.dialog.error }}</p>
            </template>
          </div>

          <!-- Foot -->
          <div class="px-5 py-4 flex justify-end gap-2">
            <button
              type="button"
              class="cursor-pointer inline-flex items-center h-[34px] px-3.5 text-[12.5px] font-semibold rounded-[10px] bg-white text-ink-700 border border-ink-300 hover:bg-ink-100 transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40"
              @click="ui.cancelDialog()"
            >{{ ui.dialog.cancelText }}</button>
            <button
              ref="confirmBtnRef"
              type="button"
              class="cursor-pointer inline-flex items-center h-[34px] px-3.5 text-[12.5px] font-semibold rounded-[10px] text-white border transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 disabled:opacity-45"
              :class="isDanger
                ? 'bg-red-600 border-red-700/20 hover:bg-red-700 focus-visible:ring-red-500/40'
                : 'bg-gradient-to-b from-[#2f72ff] via-brand-500 to-[#1454e8] border-brand-700/20 hover:from-brand-500 hover:to-brand-600 focus-visible:ring-brand-500/40'"
              @click="ui.submitDialog()"
            >{{ ui.dialog.confirmText }}</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.app-dialog-enter-active,
.app-dialog-leave-active {
  transition: opacity 0.18s ease;
}
.app-dialog-enter-active > div,
.app-dialog-leave-active > div {
  transition: transform 0.18s ease;
}
.app-dialog-enter-from,
.app-dialog-leave-to {
  opacity: 0;
}
.app-dialog-enter-from > div,
.app-dialog-leave-to > div {
  transform: translateY(8px) scale(0.98);
}
@media (prefers-reduced-motion: reduce) {
  .app-dialog-enter-active,
  .app-dialog-leave-active,
  .app-dialog-enter-active > div,
  .app-dialog-leave-active > div {
    transition: none;
  }
}
</style>
