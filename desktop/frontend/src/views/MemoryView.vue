<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useMemoryStore, MEMORY_TYPES, MEMORY_TYPE_DESC, type MemoryType } from '../stores/memory'

const memory = useMemoryStore()
const { memoryData, dirty, saving, totalMemories, enabledCount } = storeToRefs(memory)
const { loadMemory, saveMemory, syncMemory, exportMemory, importMemory, setContent, setEnabled } = memory

const inputRef = ref<HTMLInputElement | null>(null)

/** 当前编辑的两条记忆（用户 / 技能） */
const userMemory = computed(() => memoryData.value.memories.find((m) => m.type === 'user'))
const skillMemory = computed(() => memoryData.value.memories.find((m) => m.type === 'skill'))

function contentOf(type: MemoryType): string {
  return (type === 'user' ? userMemory.value : skillMemory.value)?.content ?? ''
}
function enabledOf(type: MemoryType): boolean {
  return (type === 'user' ? userMemory.value : skillMemory.value)?.enabled ?? true
}
function onInput(type: MemoryType, e: Event) {
  setContent(type, (e.target as HTMLTextAreaElement).value)
}
function onToggle(type: MemoryType) {
  setEnabled(type, !enabledOf(type))
}

async function onImport(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files && input.files[0]
  if (!f) return
  const content = await f.text()
  input.value = ''
  await importMemory(content)
}

onMounted(() => { loadMemory() })
</script>

<template>
  <div class="memory-page flex flex-col gap-3">
    <!-- 顶栏 -->
    <div class="bg-white border border-ink-300/80 rounded-[14px] shadow-card px-4 py-3.5 flex items-start justify-between gap-3 flex-wrap shrink-0">
      <div>
        <h2 class="m-0 text-[15px] font-semibold flex items-center gap-2">
          <span class="w-1 h-4 bg-brand-500 rounded shrink-0" aria-hidden="true" />
          记忆配置
        </h2>
        <p class="m-0 mt-1 text-xs text-ink-500 max-w-[52ch]">
          持久记忆注入 AI 对话上下文 · 用户记忆与技能记忆各一条，可单独禁用
        </p>
        <div class="flex items-center gap-2 mt-2.5 flex-wrap">
          <span class="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-brand-50 text-brand-600">
            {{ totalMemories }} 条记忆
          </span>
          <span class="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-green-50 text-green-600">
            启用 {{ enabledCount }} 条
          </span>
          <span
            v-if="dirty"
            class="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-orange-50 text-orange-600"
          >● 未保存</span>
        </div>
      </div>
      <div class="flex items-center gap-2 flex-wrap">
        <button type="button" class="btn btn-ghost" @click="inputRef?.click()">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 3v12M8 11l4 4 4-4M4 19h16"/></svg>
          导入
        </button>
        <button type="button" class="btn btn-ghost" @click="exportMemory">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 21V9M8 13l4-4 4 4M4 5h16"/></svg>
          导出
        </button>
        <button type="button" class="btn btn-soft" @click="syncMemory">同步到 IDE</button>
        <button type="button" class="btn btn-primary" :disabled="!dirty || saving" @click="saveMemory()">
          {{ saving ? '保存中…' : '保存' }}
        </button>
        <input ref="inputRef" type="file" accept=".json" class="hidden" @change="onImport">
      </div>
    </div>

    <!-- 两块大编辑卡片：用户记忆 / 技能记忆 -->
    <div class="memory-cards grid grid-rows-2 gap-3 min-h-0 flex-1">
      <section
        v-for="t in MEMORY_TYPES"
        :key="t.value"
        class="memory-card flex flex-col min-h-0 bg-white border border-ink-300/80 rounded-[14px] shadow-card overflow-hidden"
        :class="{ disabled: !enabledOf(t.value) }"
      >
        <header class="shrink-0 px-4 py-2.5 border-b border-ink-100 flex items-center gap-2.5">
          <span
            class="shrink-0 text-[10px] font-semibold px-2 py-0.5 rounded-full"
            :class="t.value === 'user' ? 'bg-brand-50 text-brand-600' : 'bg-violet-50 text-violet-600'"
          >{{ t.label }}</span>
          <div class="flex-1 min-w-0">
            <h3 class="m-0 text-[13px] font-semibold leading-tight">{{ t.label }}</h3>
            <p class="m-0 text-[11px] text-ink-500 leading-snug truncate">{{ MEMORY_TYPE_DESC[t.value] }}</p>
          </div>
          <label class="shrink-0 inline-flex items-center gap-1.5 cursor-pointer select-none" :title="enabledOf(t.value) ? '点击禁用' : '点击启用'">
            <button
              type="button"
              role="switch"
              :aria-checked="enabledOf(t.value)"
              class="toggle"
              :class="{ on: enabledOf(t.value) }"
              @click="onToggle(t.value)"
            >
              <span class="knob" />
            </button>
            <span class="text-[10px] font-semibold" :class="enabledOf(t.value) ? 'text-green-600' : 'text-ink-500'">
              {{ enabledOf(t.value) ? '启用' : '禁用' }}
            </span>
          </label>
        </header>

        <div class="flex-1 min-h-0 px-4 py-3 flex flex-col">
          <textarea
            :value="contentOf(t.value)"
            :rows="t.value === 'user' ? 7 : 8"
            class="editor-textarea w-full flex-1 min-h-0 resize-y text-xs leading-relaxed border border-ink-200 rounded-lg px-3 py-2.5 bg-white font-mono focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-500/15"
            :placeholder="t.value === 'user' ? '例如：我是全栈开发者，擅长 Python / Vue 3 / TypeScript，使用中文回复…' : '例如：代码风格偏好、项目技术栈约定、工作流程规范…'"
            :aria-label="t.label + '内容'"
            @input="onInput(t.value, $event)"
          />
          <p class="m-0 mt-2 text-[10px] text-ink-400">内容将注入 AI 对话上下文，换行可用空行分段</p>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.memory-page {
  height: calc(100vh - 12rem);
  min-height: 520px;
}
.memory-cards {
  min-height: 0;
}
.memory-card.disabled .editor-textarea {
  opacity: .6;
}
.editor-textarea::-webkit-scrollbar {
  width: 8px;
}
.editor-textarea::-webkit-scrollbar-thumb {
  background: var(--border-strong);
  border-radius: 4px;
}
.editor-textarea::-webkit-scrollbar-thumb:hover {
  background: var(--text-tertiary);
}
.editor-textarea::-webkit-scrollbar-track {
  background: transparent;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 12px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  border: none;
  cursor: pointer;
  transition: background .18s ease, color .18s ease, border-color .18s ease, opacity .18s ease;
}
.btn:disabled {
  opacity: .45;
  cursor: not-allowed;
}
.btn-primary {
  background: var(--primary);
  color: #fff;
  box-shadow: 0 1px 2px rgba(22, 93, 255, .22);
}
.btn-primary:hover:not(:disabled) { background: var(--primary-hover); }
.btn-ghost {
  background: var(--bg-elevated);
  color: var(--text-secondary);
  border: 1px solid var(--border-base);
}
.btn-ghost:hover {
  border-color: var(--primary);
  color: var(--primary-hover);
  background: var(--primary-container);
}
.btn-soft {
  background: var(--primary-container);
  color: var(--primary-hover);
  border: 1px solid transparent;
}
.btn-soft:hover {
  background: #d9e6ff;
  border-color: var(--primary-container-strong);
}

/* 启用开关 */
.toggle {
  position: relative;
  width: 34px;
  height: 19px;
  border-radius: 999px;
  border: 1px solid var(--border-strong);
  background: var(--bg-muted, #e5e6eb);
  cursor: pointer;
  padding: 0;
  transition: background .18s ease, border-color .18s ease;
}
.toggle .knob {
  position: absolute;
  top: 1.5px;
  left: 2px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 1px 2px rgba(0, 0, 0, .18);
  transition: transform .18s ease;
}
.toggle.on {
  background: var(--primary);
  border-color: var(--primary);
}
.toggle.on .knob {
  transform: translateX(15px);
}

@media (prefers-reduced-motion: reduce) {
  .btn, .memory-card, .toggle, .toggle .knob {
    transition: none !important;
  }
}
</style>
