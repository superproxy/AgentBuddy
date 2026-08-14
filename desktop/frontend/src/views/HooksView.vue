<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import {
  useHooksStore,
  HOOK_EVENTS,
  HOOK_EVENT_DESC,
  type HookEvent,
} from '../stores/hooks'

const hooks = useHooksStore()
const { hooksData, dirty, eventCount, totalHooks } = storeToRefs(hooks)
const {
  loadHooks, saveHooks, addHook, deleteHook,
  addCommand, deleteCommand, moveHook, moveCommand,
  syncHooks, exportHooks, importHooks, onContentChange,
} = hooks

const inputRef = ref<HTMLInputElement | null>(null)
const activeEvent = ref<HookEvent>('SessionStart')

const activeGroups = computed(() => hooksData.value.hooks[activeEvent.value] || [])
const armedCount = computed(() =>
  HOOK_EVENTS.filter((ev) => (eventCount.value[ev] || 0) > 0).length,
)
const coverFull = computed(() => armedCount.value === HOOK_EVENTS.length)

/** 组拖拽 */
const dragGroupFrom = ref<number | null>(null)
const dragGroupOver = ref<number | null>(null)
/** 指令拖拽 */
const dragCmd = ref<{ gi: number; ci: number } | null>(null)
const dragCmdOver = ref<{ gi: number; ci: number } | null>(null)

function selectEvent(ev: HookEvent) {
  activeEvent.value = ev
  dragGroupFrom.value = null
  dragGroupOver.value = null
  dragCmd.value = null
  dragCmdOver.value = null
}

function moveActive(delta: number) {
  const i = HOOK_EVENTS.indexOf(activeEvent.value)
  const next = Math.max(0, Math.min(HOOK_EVENTS.length - 1, i + delta))
  if (HOOK_EVENTS[next] !== activeEvent.value) selectEvent(HOOK_EVENTS[next])
}

function onRailKeydown(e: KeyboardEvent) {
  if (e.key === 'ArrowDown') { e.preventDefault(); moveActive(1) }
  else if (e.key === 'ArrowUp') { e.preventDefault(); moveActive(-1) }
  else if (e.key === 'Home') { e.preventDefault(); selectEvent(HOOK_EVENTS[0]) }
  else if (e.key === 'End') { e.preventDefault(); selectEvent(HOOK_EVENTS[HOOK_EVENTS.length - 1]) }
}

function padStep(i: number) {
  return String(i + 1).padStart(2, '0')
}

/* —— 组排序 —— */
function onGroupDragStart(e: DragEvent, gi: number) {
  dragGroupFrom.value = gi
  dragCmd.value = null
  e.dataTransfer!.effectAllowed = 'move'
  e.dataTransfer!.setData('text/plain', `group:${gi}`)
}
function onGroupDragOver(e: DragEvent, gi: number) {
  if (dragGroupFrom.value === null) return
  e.preventDefault()
  e.dataTransfer!.dropEffect = 'move'
  dragGroupOver.value = gi
}
function onGroupDrop(e: DragEvent, gi: number) {
  e.preventDefault()
  const from = dragGroupFrom.value
  if (from === null || from === gi) {
    onGroupDragEnd()
    return
  }
  moveHook(activeEvent.value, from, gi)
  onGroupDragEnd()
}
function onGroupDragEnd() {
  dragGroupFrom.value = null
  dragGroupOver.value = null
}

/* —— 指令排序 —— */
function onCmdDragStart(e: DragEvent, gi: number, ci: number) {
  dragCmd.value = { gi, ci }
  dragGroupFrom.value = null
  e.dataTransfer!.effectAllowed = 'move'
  e.dataTransfer!.setData('text/plain', `cmd:${gi}:${ci}`)
}
function onCmdDragOver(e: DragEvent, gi: number, ci: number) {
  if (!dragCmd.value || dragCmd.value.gi !== gi) return
  e.preventDefault()
  e.dataTransfer!.dropEffect = 'move'
  dragCmdOver.value = { gi, ci }
}
function onCmdDrop(e: DragEvent, gi: number, ci: number) {
  e.preventDefault()
  const from = dragCmd.value
  if (!from || from.gi !== gi || from.ci === ci) {
    onCmdDragEnd()
    return
  }
  moveCommand(activeEvent.value, gi, from.ci, ci)
  onCmdDragEnd()
}
function onCmdDragEnd() {
  dragCmd.value = null
  dragCmdOver.value = null
}

function onGroupDragLeave(gi: number) {
  if (dragGroupOver.value === gi) dragGroupOver.value = null
}
function onCmdDragLeave(gi: number, ci: number) {
  if (dragCmdOver.value?.gi === gi && dragCmdOver.value?.ci === ci) dragCmdOver.value = null
}

async function onImport(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files && input.files[0]
  if (!f) return
  const content = await f.text()
  input.value = ''
  await importHooks(content)
}

onMounted(() => { loadHooks() })
</script>

<template>
  <div class="hooks-page space-y-3.5">
    <!-- 顶栏 -->
    <div class="bg-white border border-ink-300/80 rounded-[14px] shadow-card px-4 py-3.5 flex items-start justify-between gap-3 flex-wrap">
      <div>
        <h2 class="m-0 text-[15px] font-semibold flex items-center gap-2">
          <span class="w-1 h-4 bg-brand-500 rounded shrink-0" aria-hidden="true" />
          Hooks 配置
        </h2>
        <p class="m-0 mt-1 text-xs text-ink-500 max-w-[42ch]">
          按会话生命周期挂载脚本（PreToolUse / PostToolUse / UserPromptSubmit 等）· 左侧选节点，右侧编辑规则与命令
        </p>
        <div class="flex items-center gap-2 mt-2.5 flex-wrap">
          <span class="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-brand-50 text-brand-600">
            {{ totalHooks }} 个 hook 组
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
        <button type="button" class="btn btn-ghost" @click="exportHooks">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 21V9M8 13l4-4 4 4M4 5h16"/></svg>
          导出
        </button>
        <button type="button" class="btn btn-soft" @click="syncHooks">同步到 IDE</button>
        <button type="button" class="btn btn-primary" :disabled="!dirty" @click="saveHooks()">保存</button>
        <input ref="inputRef" type="file" accept=".json" class="hidden" @change="onImport">
      </div>
    </div>

    <!-- 时间线 + 编辑器 -->
    <div class="hooks-workspace grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-3.5 min-h-[560px]">
      <!-- 左侧生命周期 -->
      <nav
        class="bg-white border border-ink-300/80 rounded-[14px] shadow-card flex flex-col overflow-hidden min-h-0"
        aria-label="Hook 事件时间线"
      >
        <div class="px-3.5 pt-3.5 pb-2.5 flex items-start justify-between gap-2">
          <div>
            <div class="text-[10px] font-bold tracking-wider uppercase text-ink-500">会话生命周期</div>
            <p class="m-0 mt-1 text-[10px] text-ink-500 leading-snug">按执行顺序选择节点</p>
          </div>
          <span
            class="shrink-0 text-[10px] font-bold px-2 py-1 rounded-full whitespace-nowrap"
            :class="coverFull ? 'bg-brand-50 text-brand-600' : 'bg-ink-100 text-ink-700'"
            title="已配置事件数"
          >{{ armedCount }} / {{ HOOK_EVENTS.length }}</span>
        </div>

        <div
          class="rail-list relative flex-1 overflow-auto px-2 pb-2 flex flex-col gap-1.5"
          role="listbox"
          :aria-activedescendant="'hook-ev-' + activeEvent"
          @keydown="onRailKeydown"
        >
          <button
            v-for="(ev, i) in HOOK_EVENTS"
            :id="'hook-ev-' + ev"
            :key="ev"
            type="button"
            role="option"
            class="event relative z-[1] grid grid-cols-[42px_1fr] gap-x-2.5 w-full text-left min-h-[52px] py-2.5 pr-2.5 pl-1 rounded-xl border border-transparent transition cursor-pointer"
            :class="[
              activeEvent === ev
                ? 'bg-white border-brand-100 shadow-[0_1px_2px_rgba(22,93,255,0.06),0_6px_16px_var(--primary-container)]'
                : 'hover:bg-ink-100',
              (eventCount[ev] || 0) > 0 ? 'has-hooks' : '',
            ]"
            :aria-selected="activeEvent === ev"
            :aria-label="`${ev}，${eventCount[ev] ? '已配置 ' + eventCount[ev] + ' 组' : '未配置'}。${HOOK_EVENT_DESC[ev]}`"
            @click="selectEvent(ev)"
          >
            <span
              v-if="activeEvent === ev"
              class="absolute left-0 top-2.5 bottom-2.5 w-[3px] rounded-r bg-brand-500"
              aria-hidden="true"
            />
            <span
              class="node w-[34px] h-[34px] ml-2 mt-0.5 rounded-full inline-flex items-center justify-center text-[11px] font-medium font-mono border-2 shadow-sm transition"
              :class="activeEvent === ev
                ? 'border-brand-500 bg-brand-500 text-white shadow-[0_0_0_4px_var(--primary-container-strong)]'
                : (eventCount[ev] || 0) > 0
                  ? 'border-brand-500 text-brand-600 bg-brand-50'
                  : 'border-ink-300 text-ink-500 bg-white'"
              aria-hidden="true"
            >{{ padStep(i) }}</span>
            <span class="min-w-0 flex flex-col gap-0.5 pr-0.5">
              <span class="flex items-center justify-between gap-1.5">
                <span
                  class="text-[13px] font-semibold truncate tracking-tight"
                  :class="activeEvent === ev ? 'text-brand-700' : 'text-ink-900'"
                >{{ ev }}</span>
                <span
                  class="shrink-0 text-[10px] font-bold px-1.5 py-0.5 rounded-full leading-snug"
                  :class="(eventCount[ev] || 0) > 0
                    ? 'bg-brand-50 text-brand-600'
                    : 'bg-ink-100 text-ink-500'"
                >{{ (eventCount[ev] || 0) > 0 ? eventCount[ev] + ' 组' : '未配置' }}</span>
              </span>
              <span class="text-[11px] text-ink-700 leading-snug line-clamp-2">{{ HOOK_EVENT_DESC[ev] }}</span>
            </span>
          </button>
        </div>

        <p class="m-0 px-3.5 py-2.5 border-t border-ink-200 text-[10px] text-ink-500 leading-relaxed">
          <kbd class="inline-block font-mono text-[9px] px-1 py-px rounded border border-ink-200 bg-ink-100 text-ink-700">↑</kbd>
          <kbd class="inline-block font-mono text-[9px] px-1 py-px rounded border border-ink-200 bg-ink-100 text-ink-700">↓</kbd>
          切换节点 · 拖拽把手调整顺序
        </p>
      </nav>

      <!-- 右侧编辑 -->
      <section class="bg-white border border-ink-300/80 rounded-[14px] shadow-card flex flex-col overflow-hidden min-h-0" aria-live="polite">
        <div class="shrink-0 px-[18px] py-4 border-b border-ink-100 flex items-start justify-between gap-3 flex-wrap bg-gradient-to-r from-brand-50 to-transparent">
          <div>
            <h2 class="m-0 text-base font-semibold tracking-tight">{{ activeEvent }}</h2>
            <p class="m-0 mt-1 text-xs text-ink-500">{{ HOOK_EVENT_DESC[activeEvent] }}</p>
          </div>
          <button type="button" class="btn btn-primary" @click="addHook(activeEvent)">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>
            添加组
          </button>
        </div>

        <div class="editor-scroll flex-1 min-h-0 overflow-y-auto overscroll-contain px-[18px] py-4 flex flex-col gap-3">
          <template v-if="activeGroups.length">
            <p class="m-0 text-[11px] text-ink-500">拖拽左侧把手可调整组 / 指令顺序</p>

            <article
              v-for="(group, gi) in activeGroups"
              :key="activeEvent + '-g-' + gi"
              class="group-card border border-ink-200 rounded-[10px] overflow-hidden bg-ink-100 transition"
              :class="{
                'opacity-40 border-dashed border-brand-500': dragGroupFrom === gi,
                'border-brand-500 shadow-[0_0_0_2px_rgba(22,93,255,0.18)]': dragGroupOver === gi && dragGroupFrom !== gi,
              }"
              @dragover="onGroupDragOver($event, gi)"
              @drop="onGroupDrop($event, gi)"
              @dragleave="onGroupDragLeave(gi)"
            >
              <div class="flex items-end gap-2 px-3 py-2.5 bg-white border-b border-ink-200">
                <button
                  type="button"
                  class="drag-handle"
                  title="拖拽调整组顺序"
                  aria-label="拖拽调整组顺序"
                  draggable="true"
                  @dragstart="onGroupDragStart($event, gi)"
                  @dragend="onGroupDragEnd"
                >
                  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="9" cy="7" r="1.5"/><circle cx="15" cy="7" r="1.5"/><circle cx="9" cy="12" r="1.5"/><circle cx="15" cy="12" r="1.5"/><circle cx="9" cy="17" r="1.5"/><circle cx="15" cy="17" r="1.5"/></svg>
                </button>
                <div class="flex-1 min-w-0">
                  <label class="block text-[10px] font-semibold text-ink-500 mb-1">Matcher（可选）</label>
                  <input
                    v-model="group.matcher"
                    class="w-full text-xs border border-ink-200 rounded-lg px-2.5 py-1.5"
                    placeholder="如 Edit|Write，留空 = 匹配全部"
                    @input="onContentChange()"
                  >
                </div>
                <button
                  type="button"
                  class="icon-btn add"
                  title="添加命令"
                  aria-label="添加命令"
                  @click="addCommand(activeEvent, gi)"
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>
                </button>
                <button
                  type="button"
                  class="icon-btn"
                  title="删除组"
                  aria-label="删除组"
                  @click="deleteHook(activeEvent, gi)"
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
                </button>
              </div>

              <div class="px-3 py-2.5 flex flex-col gap-2">
                <div
                  v-for="(cmd, ci) in group.hooks"
                  :key="activeEvent + '-g-' + gi + '-c-' + ci"
                  class="cmd-row grid grid-cols-[28px_1fr_72px_32px] gap-2 items-center p-1 -m-1 rounded-lg border border-transparent transition"
                  :class="{
                    'opacity-40 border-dashed border-brand-500 bg-brand-50': dragCmd?.gi === gi && dragCmd?.ci === ci,
                    'border-brand-500 bg-white shadow-[0_0_0_2px_rgba(22,93,255,0.12)]': dragCmdOver?.gi === gi && dragCmdOver?.ci === ci && !(dragCmd?.gi === gi && dragCmd?.ci === ci),
                  }"
                  @dragover="onCmdDragOver($event, gi, ci)"
                  @drop="onCmdDrop($event, gi, ci)"
                  @dragleave="onCmdDragLeave(gi, ci)"
                >
                  <button
                    type="button"
                    class="drag-handle"
                    title="拖拽调整指令顺序"
                    aria-label="拖拽调整指令顺序"
                    draggable="true"
                    @dragstart="onCmdDragStart($event, gi, ci)"
                    @dragend="onCmdDragEnd"
                  >
                    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="9" cy="7" r="1.5"/><circle cx="15" cy="7" r="1.5"/><circle cx="9" cy="12" r="1.5"/><circle cx="15" cy="12" r="1.5"/><circle cx="9" cy="17" r="1.5"/><circle cx="15" cy="17" r="1.5"/></svg>
                  </button>
                  <input
                    v-model="cmd.command"
                    class="w-full text-[11px] font-mono border border-ink-200 rounded-lg px-2.5 py-1.5 bg-white"
                    placeholder="echo 'hello'"
                    aria-label="命令"
                    @input="onContentChange()"
                  >
                  <input
                    v-model.number="cmd.timeout"
                    type="number"
                    min="1"
                    class="w-full text-[11px] border border-ink-200 rounded-lg px-2 py-1.5 bg-white"
                    title="超时 (秒)"
                    aria-label="超时秒"
                    @input="onContentChange()"
                  >
                  <button
                    type="button"
                    class="icon-btn"
                    aria-label="删除命令"
                    @click="deleteCommand(activeEvent, gi, ci)"
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>
                  </button>
                </div>
                <div v-if="!group.hooks.length" class="text-[11px] text-ink-500 py-1">
                  无命令，点击「+」添加
                </div>
              </div>
            </article>
          </template>

          <div
            v-else
            class="flex-1 flex flex-col items-center justify-center gap-2 text-center py-10 px-4 border border-dashed border-ink-300 rounded-[10px] bg-gradient-to-b from-white to-ink-100 text-ink-500 text-xs"
          >
            <strong class="text-[13px] text-ink-700 font-semibold">此节点暂无 hook</strong>
            <span>点击右上角「添加组」开始配置命令</span>
            <button type="button" class="btn btn-primary mt-2" @click="addHook(activeEvent)">添加第一组</button>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.hooks-page {
  display: flex;
  flex-direction: column;
}
.hooks-workspace {
  height: auto;
  max-height: none;
  min-height: 560px;
}
@media (min-width: 1024px) {
  .hooks-workspace {
    height: calc(100vh - 11.5rem);
    max-height: calc(100vh - 11.5rem);
  }
}
.editor-scroll {
  scrollbar-gutter: stable;
  max-height: min(60vh, 520px);
}
@media (min-width: 1024px) {
  .editor-scroll {
    max-height: none;
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

.rail-list::before {
  content: "";
  position: absolute;
  left: 29px;
  top: 28px;
  bottom: 28px;
  width: 2px;
  background: linear-gradient(180deg, #d9e6ff, var(--border-base) 40%, #e5e6eb);
  border-radius: 1px;
  pointer-events: none;
  z-index: 0;
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
.icon-btn.add:hover {
  color: var(--primary-hover);
  border-color: var(--primary-container-strong);
  background: var(--primary-container);
}
.icon-btn svg {
  width: 14px;
  height: 14px;
}

@media (prefers-reduced-motion: reduce) {
  .btn, .drag-handle, .icon-btn, .event, .group-card, .cmd-row {
    transition: none !important;
  }
}
</style>
