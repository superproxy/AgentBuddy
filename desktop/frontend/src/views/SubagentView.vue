<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useSubagentStore, type SubagentItem } from '../stores/subagent'
import { useUiStore } from '../stores/ui'

const sa = useSubagentStore()
const ui = useUiStore()
const { subagentData } = storeToRefs(sa)
const {
  loadSubagent,
  saveSubagent,
  addSubagent,
  deleteSubagent,
  updateSubagent,
  exportSubagent,
  importSubagent,
  syncToOpencode,
} = sa

const inputRef = ref<HTMLInputElement | null>(null)
const nameInputRef = ref<HTMLInputElement | null>(null)
const searchQ = ref('')
const filterCat = ref('全部')

const workbenchOpen = ref(false)
/** null = 新建未落库；number = 编辑已有项 */
const editIndex = ref<number | null>(null)
const draft = reactive<SubagentItem>({
  name: '',
  role: '',
  desc: '',
  category: '开发',
  prompt: '',
})

const categories = computed(() => {
  const set = new Set<string>()
  for (const s of subagentData.value.subagents) {
    set.add((s.category || '').trim() || '未分类')
  }
  return ['全部', ...set]
})

const filteredAgents = computed(() => {
  const q = searchQ.value.trim().toLowerCase()
  return subagentData.value.subagents
    .map((item, index) => ({ item, index }))
    .filter(({ item }) => {
      const cat = (item.category || '').trim() || '未分类'
      if (filterCat.value !== '全部' && cat !== filterCat.value) return false
      if (!q) return true
      return [item.name, item.role, item.desc, item.category]
        .map((x) => String(x || '').toLowerCase())
        .join(' ')
        .includes(q)
    })
})

const workbenchTitle = computed(() =>
  draft.name?.trim() ? `编辑 · ${draft.name.trim()}` : '新建角色',
)

const workbenchAvatar = computed(() => initials(draft.name || draft.role || '?'))

function initials(name: string) {
  const parts = (name || '?').split(/[-_\s]/).filter(Boolean)
  return ((parts[0]?.[0] || '?') + (parts[1]?.[0] || '')).toUpperCase()
}

function catKey(cat?: string) {
  const c = (cat || '').trim() || '未分类'
  if (c === '产品') return 'product'
  if (c === '通用') return 'common'
  if (c === '开发') return 'dev'
  return 'default'
}

function resetDraft(src?: Partial<SubagentItem>) {
  draft.name = src?.name || ''
  draft.role = src?.role || ''
  draft.desc = src?.desc || ''
  draft.category = src?.category || '开发'
  draft.prompt = src?.prompt || ''
}

async function showWorkbench() {
  workbenchOpen.value = true
  document.body.style.overflow = 'hidden'
  await nextTick()
  nameInputRef.value?.focus()
}

async function openWorkbench(index: number) {
  const item = subagentData.value.subagents[index]
  if (!item) return
  editIndex.value = index
  resetDraft(item)
  await showWorkbench()
}

async function openNewWorkbench() {
  editIndex.value = null
  resetDraft({ category: '开发' })
  await showWorkbench()
}

function closeWorkbench() {
  workbenchOpen.value = false
  editIndex.value = null
  document.body.style.overflow = ''
}

function applyWorkbench() {
  const name = draft.name.trim()
  if (!name) {
    ui.toast('请填写 name', 'err')
    nameInputRef.value?.focus()
    return
  }
  const payload: SubagentItem = {
    name,
    role: draft.role.trim(),
    desc: draft.desc?.trim() || '',
    category: draft.category?.trim() || '',
    prompt: draft.prompt || '',
  }
  if (editIndex.value == null) {
    addSubagent(payload)
    ui.toast('已添加角色')
  } else {
    updateSubagent(editIndex.value, payload)
    ui.toast('已更新角色')
  }
  closeWorkbench()
}

async function deleteFromWorkbench() {
  if (editIndex.value == null) {
    closeWorkbench()
    return
  }
  const ok = await ui.askConfirm({
    title: '删除角色',
    message: `确定删除「${draft.name || draft.role || '未命名'}」？`,
    confirmText: '删除',
    tone: 'danger',
  })
  if (!ok) return
  deleteSubagent(editIndex.value)
  closeWorkbench()
  ui.toast('已删除')
}

async function onImport(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (!f) return
  const content = await f.text()
  ;(e.target as HTMLInputElement).value = ''
  await importSubagent(content)
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && workbenchOpen.value) closeWorkbench()
}

onMounted(() => {
  loadSubagent()
  window.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  document.body.style.overflow = ''
})
</script>

<template>
  <div class="space-y-4">
    <div class="bg-white rounded-xl shadow-card overflow-hidden">
      <!-- 工具栏 -->
      <div class="flex items-center justify-between gap-3 px-[18px] py-3.5 border-b border-ink-200 flex-wrap">
        <h2 class="text-sm font-semibold flex items-center gap-2">
          <span class="w-[3px] h-4 bg-brand-500 rounded-sm"></span>
          Subagent 角色
          <span class="text-[10px] text-ink-500 font-normal">
            定义角色与工具权限 · {{ subagentData.subagents.length }} 个
          </span>
        </h2>
        <div class="flex gap-2 flex-wrap">
          <button
            type="button"
            class="px-3 py-1.5 text-xs bg-brand-500 text-white rounded-md hover:bg-brand-600 font-medium cursor-pointer"
            @click="saveSubagent()"
          >
            保存
          </button>
          <button
            type="button"
            class="px-3 py-1.5 text-xs text-green-600 bg-green-50 rounded-md hover:bg-green-100 font-medium cursor-pointer"
            @click="syncToOpencode"
          >
            同步到 IDE
          </button>
          <button
            type="button"
            class="px-3 py-1.5 text-xs text-ink-700 hover:text-brand-600 hover:bg-ink-100 rounded-md cursor-pointer"
            @click="exportSubagent"
          >
            导出
          </button>
          <button
            type="button"
            class="px-3 py-1.5 text-xs text-ink-700 hover:text-brand-600 hover:bg-ink-100 rounded-md cursor-pointer"
            @click="inputRef?.click()"
          >
            导入
          </button>
          <input ref="inputRef" type="file" accept=".yaml,.yml" class="hidden" @change="onImport">
        </div>
      </div>

      <!-- 筛选 -->
      <div class="flex items-center gap-3 px-[18px] py-3 border-b border-ink-200 bg-[#fafbfc] flex-wrap">
        <div class="sa-search flex items-center gap-2 bg-white border border-ink-300 rounded-lg px-2.5 min-w-[220px] flex-1 max-w-xs">
          <svg class="w-3.5 h-3.5 text-ink-500 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="11" cy="11" r="7" />
            <path d="M20 20l-3-3" />
          </svg>
          <input
            v-model="searchQ"
            type="search"
            placeholder="筛选角色…"
            autocomplete="off"
            class="border-0 outline-none flex-1 text-xs py-2 bg-transparent"
          >
        </div>
        <div class="flex flex-wrap gap-1.5">
          <button
            v-for="c in categories"
            :key="c"
            type="button"
            class="sa-chip cursor-pointer"
            :class="{ active: filterCat === c }"
            @click="filterCat = c"
          >
            {{ c }}
          </button>
        </div>
        <div class="ml-auto text-[11px] text-ink-500">
          展示 <strong class="text-brand-600 font-semibold">{{ filteredAgents.length }}</strong>
          / {{ subagentData.subagents.length }}
        </div>
      </div>

      <!-- 卡片墙 -->
      <div class="sa-gallery p-[18px] grid gap-3.5">
        <button
          v-for="{ item, index } in filteredAgents"
          :key="`${index}-${item.name}`"
          type="button"
          class="sa-card cursor-pointer text-left"
          :data-cat="catKey(item.category)"
          @click="openWorkbench(index)"
        >
          <div class="sa-card-stripe"></div>
          <div class="sa-card-body">
            <div class="flex items-start justify-between gap-2">
              <div class="sa-avatar">{{ initials(item.name || item.role || '?') }}</div>
              <span class="text-[10px] text-ink-500 bg-ink-100 px-1.5 py-0.5 rounded">
                {{ (item.category || '').trim() || '未分类' }}
              </span>
            </div>
            <div>
              <div class="font-mono text-[13px] font-semibold text-ink-900 truncate">
                {{ item.name || '未命名' }}
              </div>
              <div class="text-xs text-ink-700 font-medium truncate">{{ item.role || '—' }}</div>
            </div>
            <p class="sa-card-desc">{{ item.desc || '暂无描述' }}</p>
          </div>
          <div class="sa-card-foot">
            <span>编辑配置</span>
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M9 18l6-6-6-6" />
            </svg>
          </div>
        </button>

        <button
          type="button"
          class="sa-card sa-card-add cursor-pointer"
          @click="openNewWorkbench"
        >
          <svg class="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 5v14M5 12h14" />
          </svg>
          添加角色
        </button>
      </div>
    </div>

    <!-- 居中工作台 -->
    <Teleport to="body">
      <div
        v-if="workbenchOpen"
        class="sa-overlay"
        role="presentation"
        @click.self="closeWorkbench"
      >
        <div
          class="sa-workbench"
          role="dialog"
          aria-modal="true"
          aria-labelledby="sa-wb-title"
          @click.stop
        >
          <div class="sa-wb-head">
            <div class="flex items-start gap-3 min-w-0">
              <div class="sa-wb-avatar shrink-0">{{ workbenchAvatar }}</div>
              <div class="min-w-0">
                <h3 id="sa-wb-title" class="text-[15px] font-semibold text-ink-900 truncate">
                  {{ workbenchTitle }}
                </h3>
                <p class="text-[11px] text-ink-500 mt-0.5">居中工作台编辑 · 完成后写回卡片墙</p>
              </div>
            </div>
            <button
              type="button"
              class="sa-icon-btn cursor-pointer"
              aria-label="关闭"
              @click="closeWorkbench"
            >
              <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>

          <div class="sa-wb-body">
            <div class="sa-row2">
              <div class="sa-field">
                <label>标识 name <span class="text-red-500">*</span></label>
                <input
                  ref="nameInputRef"
                  v-model="draft.name"
                  class="font-mono"
                  placeholder="java-dev"
                >
                <span class="help">IDE 同步用的角色 ID</span>
              </div>
              <div class="sa-field">
                <label>显示角色 <span class="text-red-500">*</span></label>
                <input v-model="draft.role" placeholder="Java 开发">
              </div>
            </div>
            <div class="sa-row2">
              <div class="sa-field">
                <label>分类</label>
                <input v-model="draft.category" placeholder="开发" list="sa-cat-list">
                <datalist id="sa-cat-list">
                  <option value="开发"></option>
                  <option value="产品"></option>
                  <option value="通用"></option>
                </datalist>
              </div>
              <div class="sa-field">
                <label>一句话描述</label>
                <input v-model="draft.desc" placeholder="擅长什么">
              </div>
            </div>
            <div class="sa-field">
              <label>系统 Prompt</label>
              <textarea
                v-model="draft.prompt"
                class="font-mono"
                rows="10"
                placeholder="角色系统提示词…"
              ></textarea>
            </div>
          </div>

          <div class="sa-wb-foot">
            <button
              type="button"
              class="px-3 py-1.5 text-xs text-red-500 bg-red-50 rounded-md hover:bg-red-100 font-medium cursor-pointer min-w-[88px]"
              @click="deleteFromWorkbench"
            >
              删除
            </button>
            <div class="flex gap-2">
              <button
                type="button"
                class="px-3 py-1.5 text-xs text-ink-700 hover:text-brand-600 hover:bg-white rounded-md cursor-pointer min-w-[88px]"
                @click="closeWorkbench"
              >
                取消
              </button>
              <button
                type="button"
                class="px-3 py-1.5 text-xs bg-brand-500 text-white rounded-md hover:bg-brand-600 font-medium cursor-pointer min-w-[88px]"
                @click="applyWorkbench"
              >
                完成
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.sa-search:focus-within {
  border-color: var(--color-brand-500);
  box-shadow: var(--shadow-glow);
}

.sa-chip {
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid var(--color-ink-200);
  background: var(--bg-elevated);
  color: var(--color-ink-700);
  font-family: inherit;
  transition: all 0.15s;
}
.sa-chip:hover {
  border-color: var(--color-brand-100);
  color: var(--color-brand-600);
}
.sa-chip.active {
  background: var(--color-brand-500);
  border-color: var(--color-brand-500);
  color: #fff;
  font-weight: 600;
}

.sa-gallery {
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  align-content: start;
}

.sa-card {
  background: var(--bg-elevated);
  border: 1px solid var(--color-ink-200);
  border-radius: 10px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding: 0;
  font-family: inherit;
  color: inherit;
  transition: border-color 0.2s, box-shadow 0.2s, transform 0.2s;
}
.sa-card:hover {
  border-color: var(--color-brand-100);
  box-shadow: 0 4px 16px var(--primary-container);
  transform: translateY(-1px);
}
.sa-card:focus-visible {
  outline: none;
  box-shadow: var(--shadow-glow);
  border-color: var(--color-brand-500);
}

.sa-card-stripe {
  height: 3px;
  background: var(--color-brand-500);
}
.sa-card[data-cat='product'] .sa-card-stripe { background: #722ed1; }
.sa-card[data-cat='common'] .sa-card-stripe { background: #0fc6c2; }
.sa-card[data-cat='dev'] .sa-card-stripe { background: var(--color-brand-500); }

.sa-card-body {
  padding: 14px 14px 12px;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sa-avatar {
  width: 36px;
  height: 36px;
  border-radius: 9px;
  background: var(--color-brand-50);
  color: var(--color-brand-600);
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}
.sa-card[data-cat='product'] .sa-avatar {
  background: #f5e8ff;
  color: #722ed1;
}
.sa-card[data-cat='common'] .sa-avatar {
  background: #e8fffb;
  color: #0fc6c2;
}

.sa-card-desc {
  font-size: 11px;
  color: var(--color-ink-500);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  flex: 1;
}

.sa-card-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  border-top: 1px solid var(--color-ink-100);
  font-size: 11px;
  color: var(--color-brand-600);
  font-weight: 500;
}

.sa-card-add {
  border: 1.5px dashed var(--color-ink-300);
  background: var(--color-ink-100);
  min-height: 168px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--color-ink-500);
  font-size: 12px;
}
.sa-card-add:hover {
  border-color: var(--color-brand-500);
  color: var(--color-brand-600);
  background: var(--color-brand-50);
  box-shadow: none;
  transform: none;
}

.sa-overlay {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
  background: rgba(31, 35, 41, 0.45);
  backdrop-filter: blur(2px);
  animation: sa-fade-in 0.2s ease;
}

.sa-workbench {
  width: min(720px, 100%);
  max-height: min(88vh, 760px);
  background: var(--bg-elevated);
  border-radius: 14px;
  box-shadow: 0 16px 48px rgba(31, 35, 41, 0.18), 0 0 0 1px rgba(22, 93, 255, 0.06);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: sa-pop-in 0.22s ease;
}

.sa-wb-head {
  padding: 16px 20px;
  border-bottom: 1px solid var(--color-ink-200);
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  background: linear-gradient(180deg, #fff 0%, #fafbfc 100%);
}

.sa-wb-avatar {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: var(--color-brand-50);
  color: var(--color-brand-600);
  font-size: 13px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

.sa-icon-btn {
  width: 32px;
  height: 32px;
  border: none;
  background: var(--color-ink-100);
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-ink-700);
  flex-shrink: 0;
}
.sa-icon-btn:hover {
  background: var(--color-brand-50);
  color: var(--color-brand-600);
}

.sa-wb-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.sa-row2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.sa-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.sa-field label {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-ink-700);
}
.sa-field input,
.sa-field textarea {
  font-size: 12px;
  border: 1px solid var(--color-ink-300);
  border-radius: 8px;
  padding: 8px 10px;
  font-family: inherit;
  color: var(--color-ink-900);
  width: 100%;
  background: var(--bg-elevated);
}
.sa-field textarea {
  resize: vertical;
  min-height: 180px;
  line-height: 1.55;
}
.sa-field .help {
  font-size: 10px;
  color: var(--color-ink-500);
}

.sa-wb-foot {
  padding: 12px 20px;
  border-top: 1px solid var(--color-ink-200);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  background: var(--color-ink-100);
}

@keyframes sa-fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}
@keyframes sa-pop-in {
  from {
    opacity: 0;
    transform: translateY(12px) scale(0.98);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@media (max-width: 560px) {
  .sa-row2 { grid-template-columns: 1fr; }
  .sa-wb-foot {
    flex-direction: column-reverse;
    align-items: stretch;
  }
  .sa-wb-foot > div { width: 100%; }
  .sa-wb-foot button { flex: 1; }
}

@media (prefers-reduced-motion: reduce) {
  .sa-card { transition: none; }
  .sa-card:hover { transform: none; }
  .sa-overlay,
  .sa-workbench { animation: none; }
}
</style>
