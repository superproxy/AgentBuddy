<script setup lang="ts">
import { ref, onMounted } from 'vue'
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
  addCommand, deleteCommand, syncHooks, exportHooks, importHooks,
} = hooks

const inputRef = ref<HTMLInputElement | null>(null)
const expandedEvents = ref<Set<HookEvent>>(new Set())

function toggleEvent(ev: HookEvent) {
  if (expandedEvents.value.has(ev)) {
    expandedEvents.value.delete(ev)
  } else {
    expandedEvents.value.add(ev)
  }
}

function isExpanded(ev: HookEvent) {
  return expandedEvents.value.has(ev) || (eventCount.value[ev] || 0) > 0
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
  <div class="space-y-3">
    <div class="bg-white rounded-xl shadow-card p-4">
      <!-- 工具栏 -->
      <div class="flex items-center justify-between mb-3 pb-2 border-b border-gray-100">
        <h3 class="text-sm font-semibold flex items-center gap-2">
          <span class="w-1 h-4 bg-brand-500 rounded"></span>Hooks 配置
          <span class="text-[10px] text-ink-500 font-normal">{{ totalHooks }} 个 hook 组</span>
          <span v-if="dirty" class="text-[10px] text-orange-500 font-normal">● 未保存</span>
        </h3>
        <div class="flex items-center gap-2">
          <button @click="saveHooks" :disabled="!dirty" class="text-[11px] text-brand-600 hover:underline disabled:text-ink-300">保存</button>
          <button @click="syncHooks" class="text-[11px] text-brand-600 hover:underline">同步到 IDE</button>
          <button @click="exportHooks" class="text-[11px] text-ink-600 hover:text-brand-600">导出</button>
          <button @click="inputRef?.click()" class="text-[11px] text-brand-600 hover:underline">导入</button>
          <input ref="inputRef" type="file" accept=".json" @change="onImport" class="hidden">
        </div>
      </div>

      <!-- description -->
      <div class="mb-3">
        <label class="text-[10px] text-ink-500 block mb-0.5">描述</label>
        <input
          v-model="hooksData.description"
          @input="hooks.onContentChange?.()"
          class="w-full text-xs border border-gray-200 rounded px-2 py-1 focus:border-brand-400 focus:outline-none"
          placeholder="Hooks 配置描述"
        >
      </div>

      <!-- 事件列表 -->
      <div class="space-y-2">
        <div
          v-for="ev in HOOK_EVENTS"
          :key="ev"
          class="border border-gray-200 rounded-lg overflow-hidden"
        >
          <!-- 事件头 -->
          <div
            class="flex items-center justify-between px-3 py-2 cursor-pointer hover:bg-gray-50"
            @click="toggleEvent(ev)"
          >
            <div class="flex items-center gap-2">
              <span class="text-xs font-medium text-ink-800">{{ ev }}</span>
              <span
                v-if="eventCount[ev]"
                class="text-[9px] bg-brand-50 text-brand-600 px-1.5 py-0.5 rounded"
              >{{ eventCount[ev] }} 组</span>
            </div>
            <div class="flex items-center gap-2">
              <span class="text-[10px] text-ink-400 hidden md:inline">{{ HOOK_EVENT_DESC[ev] }}</span>
              <button
                @click.stop="addHook(ev)"
                class="text-[10px] text-brand-600 hover:underline"
              >+ 添加</button>
              <span class="text-[10px] text-ink-300">{{ isExpanded(ev) ? '▾' : '▸' }}</span>
            </div>
          </div>

          <!-- hook 组列表 -->
          <div v-if="isExpanded(ev)" class="px-3 pb-2 space-y-2 bg-gray-50/50">
            <div
              v-for="(group, gi) in hooksData.hooks[ev] || []"
              :key="gi"
              class="border border-gray-200 rounded-lg p-2 bg-white"
            >
              <!-- matcher -->
              <div class="flex items-center gap-2 mb-2">
                <input
                  v-model="group.matcher"
                  @input="hooks.onContentChange?.()"
                  class="flex-1 text-[11px] border border-gray-200 rounded px-2 py-0.5 focus:border-brand-400 focus:outline-none"
                  placeholder="matcher（如 Edit|Write，可选）"
                >
                <button
                  @click="addCommand(ev, gi)"
                  class="text-[10px] text-brand-600 hover:underline whitespace-nowrap"
                >+ 命令</button>
                <button
                  @click="deleteHook(ev, gi)"
                  class="text-[10px] text-red-500 hover:underline"
                >删除组</button>
              </div>
              <!-- commands -->
              <div v-for="(cmd, ci) in group.hooks" :key="ci" class="flex items-start gap-2 mb-1">
                <span class="text-[10px] text-ink-400 mt-1 w-6 flex-shrink-0">└</span>
                <input
                  v-model="cmd.command"
                  @input="hooks.onContentChange?.()"
                  class="flex-1 text-[11px] font-mono border border-gray-200 rounded px-2 py-0.5 focus:border-brand-400 focus:outline-none"
                  placeholder="echo 'hello'"
                >
                <input
                  v-model.number="cmd.timeout"
                  type="number"
                  @input="hooks.onContentChange?.()"
                  class="w-16 text-[11px] border border-gray-200 rounded px-2 py-0.5 focus:border-brand-400 focus:outline-none"
                  placeholder="超时(s)"
                >
                <button
                  @click="deleteCommand(ev, gi, ci)"
                  class="text-[10px] text-red-500 hover:underline mt-0.5"
                >✕</button>
              </div>
              <div v-if="!group.hooks.length" class="text-[10px] text-ink-400 py-1">
                无命令，点击「+ 命令」添加
              </div>
            </div>
            <div v-if="!(hooksData.hooks[ev] || []).length" class="text-[10px] text-ink-400 py-2 text-center">
              暂无 {{ ev }} hook，点击上方「+ 添加」创建
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
