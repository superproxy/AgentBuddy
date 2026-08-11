<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useMemoryStore, MEMORY_TYPES, MEMORY_TYPE_DESC, type MemoryType } from '../stores/memory'

const memory = useMemoryStore()
const { memoryData, dirty, saving, totalMemories, enabledCount } = storeToRefs(memory)
const {
  loadMemory, saveMemory, addMemory, deleteMemory,
  toggleMemory, moveMemory, syncMemory, exportMemory,
  importMemory, onContentChange,
} = memory

const inputRef = ref<HTMLInputElement | null>(null)
const filterType = ref<MemoryType | 'all'>('all')
const searchText = ref('')

const filteredMemories = computed(() => {
  let list = memoryData.value.memories
  if (filterType.value !== 'all') {
    list = list.filter((m) => m.type === filterType.value)
  }
  const kw = searchText.value.trim().toLowerCase()
  if (kw) {
    list = list.filter(
      (m) => m.name.toLowerCase().includes(kw) || m.content.toLowerCase().includes(kw),
    )
  }
  return list
})

/** 记忆拖拽排序 */
const dragFrom = ref<number | null>(null)
const dragOver = ref<number | null>(null)

function onDragStart(e: DragEvent, idx: number) {
  dragFrom.value = idx
  e.dataTransfer!.effectAllowed = 'move'
  e.dataTransfer!.setData('text/plain', `memory:${idx}`)
}
function onDragOver(e: DragEvent, idx: number) {
  if (dragFrom.value === null) return
  e.preventDefault()
  e.dataTransfer!.dropEffect = 'move'
  dragOver.value = idx
}
function onDrop(e: DragEvent, idx: number) {
  e.preventDefault()
  const from = dragFrom.value
  if (from === null || from === idx) {
    onDragEnd()
    return
  }
  moveMemory(from, idx)
  onDragEnd()
}
function onDragEnd() {
  dragFrom.value = null
  dragOver.value = null
}
function onDragLeave(idx: number) {
  if (dragOver.value === idx) dragOver.value = null
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
  <div class="memory-page space-y-3.5">
    <!-- 顶栏 -->
    <div class="bg-white border border-ink-300/80 rounded-[14px] shadow-card px-4 py-3.5 flex items-start justify-between gap-3 flex-wrap">
      <div>
        <h2 class="m-0 text-[15px] font-semibold flex items-center gap-2">
          <span class="w-1 h-4 bg-brand-500 rounded shrink-0" aria-hidden="true" />
          记忆配置
        </h2>
        <p class="m-0 mt-1 text-xs text-ink-500 max-w-[48ch]">
          持久记忆注入 AI 对话上下文 · 支持用户记忆 / 项目记忆 / 全局记忆，可多条、可单独禁用
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

    <!-- 工具栏：筛选 -->
    <div class="bg-white border border-ink-300/80 rounded-[14px] shadow-card px-4 py-3 flex items-center justify-between gap-3 flex-wrap">
      <div class="flex items-center gap-1.5 flex-wrap" role="group" aria-label="记忆类型筛选">
        <button
          type="button"
          class="filter-chip"
          :class="{ active: filterType === 'all' }"
          @click="filterType = 'all'"
        >全部</button>
        <button
          v-for="t in MEMORY_TYPES"
          :key="t.value"
          type="button"
          class="filter-chip"
          :class="{ active: filterType === t.value }"
          @click="filterType = t.value"
        >{{ t.label }}</button>
      </div>
      <input
        v-model="searchText"
        type="search"
        class="w-52 max-w-full text-xs border border-ink-200 rounded-lg px-2.5 py-1.5"
        placeholder="搜索记忆名称 / 内容…"
        aria-label="搜索记忆"
      >
    </div>

    <!-- 记忆列表 -->
    <section class="bg-white border border-ink-300/80 rounded-[14px] shadow-card overflow-hidden" aria-live="polite">
      <div class="shrink-0 px-[18px] py-3.5 border-b border-ink-100 flex items-center justify-between gap-3 flex-wrap bg-gradient-to-r from-brand-50 to-transparent">
        <div>
          <h2 class="m-0 text-base font-semibold tracking-tight">记忆列表</h2>
          <p class="m-0 mt-0.5 text-xs text-ink-500">拖拽左侧把手调整顺序 · 点击开关禁用单条记忆</p>
        </div>
        <div class="flex items-center gap-2">
          <button type="button" class="btn btn-primary" @click="addMemory('user')">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>
            添加记忆
          </button>
        </div>
      </div>

      <div class="editor-scroll flex-1 min-h-0 overflow-y-auto overscroll-contain px-[18px] py-4 flex flex-col gap-3">
        <template v-if="filteredMemories.length">
          <article
            v-for="(mem, idx) in filteredMemories"
            :key="mem.id"
            class="memory-card border border-ink-200 rounded-[10px] overflow-hidden bg-ink-100 transition"
            :class="{
              'opacity-40 border-dashed border-brand-500': dragFrom === idx,
              'border-brand-500 shadow-[0_0_0_2px_rgba(22,93,255,0.18)]': dragOver === idx && dragFrom !== idx,
              'disabled': !mem.enabled,
            }"
            :style="mem.enabled ? '' : 'opacity:.75'"
            @dragover="onDragOver($event, idx)"
            @drop="onDrop($event, idx)"
            @dragleave="onDragLeave(idx)"
          >
            <div class="flex items-center gap-2.5 px-3 py-2.5 bg-white border-b border-ink-200">
              <button
                type="button"
                class="drag-handle"
                title="拖拽调整记忆顺序"
                aria-label="拖拽调整记忆顺序"
                draggable="true"
                @dragstart="onDragStart($event, idx)"
                @dragend="onDragEnd"
              >
                <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="9" cy="7" r="1.5"/><circle cx="15" cy="7" r="1.5"/><circle cx="9" cy="12" r="1.5"/><circle cx="15" cy="12" r="1.5"/><circle cx="9" cy="17" r="1.5"/><circle cx="15" cy="17" r="1.5"/></svg>
              </button>

              <span
                class="shrink-0 text-[10px] font-semibold px-2 py-0.5 rounded-full"
                :class="{
                  'bg-brand-50 text-brand-600': mem.type === 'user',
                  'bg-violet-50 text-violet-600': mem.type === 'project',
                  'bg-ink-100 text-ink-700': mem.type === 'global',
                }"
                :title="MEMORY_TYPE_DESC[mem.type]"
              >{{ MEMORY_TYPES.find((t) => t.value === mem.type)?.label || mem.type }}</span>

              <input
                v-model="mem.name"
                class="flex-1 min-w-0 text-[13px] font-semibold bg-transparent border-b border-transparent focus:border-brand-400 outline-none px-0.5 py-0.5"
                placeholder="记忆名称（如：编码风格）"
                aria-label="记忆名称"
                @input="onContentChange()"
              >

              <!-- 启用开关 -->
              <label
                class="shrink-0 inline-flex items-center gap-1.5 cursor-pointer select-none"
                :title="mem.enabled ? '点击禁用' : '点击启用'"
              >
                <button
                  type="button"
                  role="switch"
                  :aria-checked="mem.enabled"
                  class="toggle"
                  :class="{ on: mem.enabled }"
                  @click="toggleMemory(mem.id)"
                >
                  <span class="knob" />
                </button>
                <span class="text-[10px] font-semibold" :class="mem.enabled ? 'text-green-600' : 'text-ink-500'">
                  {{ mem.enabled ? '启用' : '禁用' }}
                </span>
              </label>

              <button
                type="button"
                class="icon-btn"
                title="删除记忆"
                aria-label="删除记忆"
                @click="deleteMemory(mem.id)"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
              </button>
            </div>

            <div class="px-3 py-2.5">
              <textarea
                v-model="mem.content"
                rows="3"
                class="w-full text-xs leading-relaxed border border-ink-200 rounded-lg px-2.5 py-2 bg-white resize-y font-mono"
                placeholder="记忆内容，将注入 AI 对话上下文…"
                aria-label="记忆内容"
                @input="onContentChange()"
              />
            </div>
          </article>
        </template>

        <div
          v-else
          class="flex-1 flex flex-col items-center justify-center gap-2 text-center py-10 px-4 border border-dashed border-ink-300 rounded-[10px] bg-gradient-to-b from-white to-ink-100 text-ink-500 text-xs"
        >
          <strong class="text-[13px] text-ink-700 font-semibold">暂无记忆</strong>
          <span>{{ filterType !== 'all' ? '当前筛选条件下没有记忆' : '点击右上角「添加记忆」开始配置' }}</span>
          <button type="button" class="btn btn-primary mt-2" @click="addMemory('user')">添加第一条记忆</button>
        </div>
      </div>
    </section>

    <!-- 类型说明 -->
    <div class="bg-white border border-ink-300/80 rounded-[14px] shadow-card px-4 py-3 grid grid-cols-1 sm:grid-cols-3 gap-3">
      <div v-for="t in MEMORY_TYPES" :key="t.value" class="flex items-start gap-2.5">
        <span
          class="shrink-0 mt-0.5 text-[10px] font-semibold px-2 py-0.5 rounded-full"
          :class="{
            'bg-brand-50 text-brand-600': t.value === 'user',
            'bg-violet-50 text-violet-600': t.value === 'project',
            'bg-ink-100 text-ink-700': t.value === 'global',
          }"
        >{{ t.label }}</span>
        <p class="m-0 text-[11px] text-ink-500 leading-relaxed">{{ MEMORY_TYPE_DESC[t.value] }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.memory-page {
  display: flex;
  flex-direction: column;
}
.editor-scroll {
  scrollbar-gutter: stable;
  max-height: min(60vh, 520px);
}
@media (min-width: 1024px) {
  .editor-scroll {
    max-height: none;
    height: calc(100vh - 19rem);
  }
}
.editor-scroll::-webkit-scrollbar {
  width: 8px;
}
.editor-scroll::-webkit-scrollbar-thumb {
  background: var(--border-strong);
  border-radius: 4px;
}
.editor-scroll::-webkit-scrollbar-thumb:hover {
  background: var(--text-tertiary);
}
.editor-scroll::-webkit-scrollbar-track {
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

.filter-chip {
  height: 28px;
  padding: 0 12px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  border: 1px solid var(--border-base);
  background: var(--bg-elevated);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all .15s ease;
}
.filter-chip:hover {
  border-color: var(--primary);
  color: var(--primary-hover);
}
.filter-chip.active {
  background: var(--primary);
  border-color: var(--primary);
  color: #fff;
}

.drag-handle {
  width: 28px;
  height: 32px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  cursor: grab;
  flex-shrink: 0;
  border: none;
  background: transparent;
  transition: color .15s ease, background .15s ease;
  touch-action: none;
}
.drag-handle:hover {
  color: var(--primary-hover);
  background: var(--primary-container);
}
.drag-handle:active { cursor: grabbing; }
.drag-handle svg {
  width: 14px;
  height: 14px;
  pointer-events: none;
}

.icon-btn {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--text-tertiary);
  background: var(--bg-elevated);
  border: 1px solid var(--border-base);
  cursor: pointer;
  flex-shrink: 0;
  transition: color .15s ease, background .15s ease, border-color .15s ease;
}
.icon-btn:hover {
  color: #f53f3f;
  border-color: #ffccc7;
  background: #fff1f0;
}
.icon-btn svg {
  width: 14px;
  height: 14px;
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
  .btn, .drag-handle, .icon-btn, .memory-card, .toggle, .toggle .knob {
    transition: none !important;
  }
}
</style>
