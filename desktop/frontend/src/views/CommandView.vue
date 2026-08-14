<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useCmdStore } from '../stores/cmd'
import { useUiStore } from '../stores/ui'

const cmd = useCmdStore()
const ui = useUiStore()
const { cmdData } = storeToRefs(cmd)
const { loadCmd, saveCmd, addCmd, deleteCmd, exportCmd, importCmd, syncToOpencode } = cmd

const inputRef = ref<HTMLInputElement | null>(null)
const pageRef = ref<HTMLElement | null>(null)
const query = ref('')
const filter = ref<'all' | 'ready' | 'draft'>('all')
const openIdx = ref(0)

function isReady(c: { name?: string; prompt?: string }) {
  return !!(c.name?.trim() && c.prompt?.trim())
}

const visibleRows = computed(() => {
  const q = query.value.trim().toLowerCase()
  return cmdData.value.commands
    .map((c, i) => ({ c, i }))
    .filter(({ c }) => {
      if (filter.value === 'ready' && !isReady(c)) return false
      if (filter.value === 'draft' && isReady(c)) return false
      if (!q) return true
      return (
        (c.name || '').toLowerCase().includes(q)
        || (c.description || '').toLowerCase().includes(q)
        || (c.prompt || '').toLowerCase().includes(q)
      )
    })
})

const hasAny = computed(() => cmdData.value.commands.length > 0)
const emptyIsFilter = computed(() => hasAny.value && !visibleRows.value.length)

function toggleOpen(i: number) {
  openIdx.value = openIdx.value === i ? -1 : i
}

function collapseAll() {
  openIdx.value = -1
}

async function onAdd() {
  addCmd()
  query.value = ''
  filter.value = 'all'
  openIdx.value = 0
  await nextTick()
  pageRef.value?.querySelector<HTMLInputElement>('input.mono')?.focus()
}

async function onDelete(i: number) {
  const name = cmdData.value.commands[i]?.name?.trim() || '该命令'
  const ok = await ui.askConfirm({
    title: '删除命令',
    message: `确定删除「${name}」？`,
    detail: '删除后需保存才会写入 cmd.yaml。',
    confirmText: '删除',
    tone: 'danger',
  })
  if (!ok) return
  deleteCmd(i)
  if (openIdx.value === i) openIdx.value = -1
  else if (openIdx.value > i) openIdx.value -= 1
}

async function onImport(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]
  if (!f) return
  const content = await f.text()
  ;(e.target as HTMLInputElement).value = ''
  await importCmd(content)
  openIdx.value = cmdData.value.commands.length ? 0 : -1
}

onMounted(() => { loadCmd() })
</script>

<template>
  <div ref="pageRef" class="cmd-page">
    <div class="cmd-head">
      <div class="min-w-0">
        <h1>自定义命令</h1>
        <p class="sub">管理斜杠命令 · 折叠浏览、展开编辑 Prompt · 同步到支持的 IDE</p>
      </div>
      <div class="actions">
        <button type="button" class="btn btn-soft" @click="onAdd">
          <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></svg>
          添加
        </button>
        <button type="button" class="btn btn-secondary" @click="exportCmd">导出</button>
        <button type="button" class="btn btn-ghost" @click="inputRef?.click()">导入</button>
        <input ref="inputRef" type="file" accept=".yaml,.yml" class="hidden" @change="onImport">
        <button type="button" class="btn btn-primary" @click="saveCmd()">
          <svg viewBox="0 0 24 24"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" /><path d="M17 21v-8H7v8M7 3v5h8" /></svg>
          保存
        </button>
      </div>
    </div>

    <div class="toolbar">
      <div class="toolbar-left">
        <label class="search">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#86909c" stroke-width="2"><circle cx="11" cy="11" r="7" /><path d="M20 20l-3-3" /></svg>
          <input v-model="query" type="search" placeholder="搜索命令名 / 描述 / Prompt" />
        </label>
        <div class="seg" role="group" aria-label="状态筛选">
          <button type="button" :class="{ on: filter === 'all' }" @click="filter = 'all'">全部</button>
          <button type="button" :class="{ on: filter === 'ready' }" @click="filter = 'ready'">已就绪</button>
          <button type="button" :class="{ on: filter === 'draft' }" @click="filter = 'draft'">草稿</button>
        </div>
        <span class="count-pill">{{ visibleRows.length }} 条</span>
      </div>
      <div class="actions">
        <button type="button" class="btn btn-ghost btn-sm" @click="collapseAll">全部折叠</button>
        <button type="button" class="btn btn-secondary btn-sm" @click="syncToOpencode">同步到 IDE</button>
      </div>
    </div>

    <div v-if="!hasAny" class="empty">
      <h3>暂无命令</h3>
      <p>点击「添加」创建第一条斜杠命令。</p>
      <button type="button" class="btn btn-soft" style="margin-top:12px" @click="onAdd">+ 添加命令</button>
    </div>

    <div v-else-if="emptyIsFilter" class="empty">
      <h3>没有匹配的命令</h3>
      <p>换个关键词，或切换筛选条件。</p>
      <button type="button" class="btn btn-soft" style="margin-top:12px" @click="onAdd">+ 添加命令</button>
    </div>

    <div v-else class="stack">
      <article
        v-for="({ c, i }, n) in visibleRows"
        :key="i"
        class="card"
        :class="{ open: openIdx === i }"
      >
        <button
          type="button"
          class="card-head"
          :aria-expanded="openIdx === i"
          @click="toggleOpen(i)"
        >
          <span class="idx">{{ String(n + 1).padStart(2, '0') }}</span>
          <span class="head-main">
            <div class="title-row">
              <span class="slash"><b>/</b>{{ c.name || 'untitled' }}</span>
            </div>
            <div class="desc">{{ c.description || '暂无描述' }}</div>
          </span>
          <span class="head-meta">
            <span class="chars">{{ (c.prompt || '').length }} 字</span>
            <span class="chev" aria-hidden="true">
              <svg viewBox="0 0 24 24"><path d="m6 9 6 6 6-6" /></svg>
            </span>
          </span>
        </button>

        <div v-if="openIdx === i" class="card-body">
          <div class="fields">
            <div class="field">
              <label>命令名</label>
              <input
                v-model="c.name"
                class="mono"
                type="text"
                placeholder="commit"
              >
            </div>
            <div class="field">
              <label>描述</label>
              <input v-model="c.description" type="text" placeholder="提交代码变更">
            </div>
          </div>
          <div class="field">
            <label>Prompt</label>
            <textarea v-model="c.prompt" placeholder="AI 执行提示词" rows="5" />
          </div>
          <div class="body-foot">
            <span class="hint">触发形态 <strong>/{{ c.name || '…' }}</strong></span>
            <button type="button" class="btn btn-danger btn-sm" @click="onDelete(i)">
              <svg viewBox="0 0 24 24"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" /></svg>
              删除
            </button>
          </div>
        </div>
      </article>
    </div>
  </div>
</template>

<style scoped>
.cmd-page {
  --red: #f53f3f;
  --red-bg: #ffece8;
  --red-border: #f9c2c0;
  --mono: 'JetBrains Mono', Consolas, monospace;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding-bottom: 12px;
}

.cmd-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  flex-wrap: wrap;
}
.cmd-head h1 {
  margin: 0 0 4px;
  font-size: 15px;
  font-weight: 650;
  color: var(--text-primary);
}
.sub {
  margin: 0;
  font-size: 12px;
  color: var(--text-tertiary);
}

.actions {
  display: inline-flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}

.btn {
  height: 34px;
  padding: 0 12px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 1px solid transparent;
  cursor: pointer;
  transition: background .18s ease, color .18s ease, border-color .18s ease, filter .18s ease;
  background: none;
  color: inherit;
  user-select: none;
}
.btn svg {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  stroke: currentColor;
  fill: none;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.btn-sm { height: 28px; padding: 0 10px; font-size: 11px; border-radius: 7px; }
.btn-sm svg { width: 13px; height: 13px; }
.btn-primary {
  background: linear-gradient(180deg, #2f72ff, #165dff 45%, #1454e8);
  color: #fff;
  border-color: rgba(10, 46, 156, .2);
  box-shadow: 0 1px 2px rgba(22, 93, 255, .22);
}
.btn-primary:hover { filter: brightness(.96); }
.btn-soft { background: var(--primary-container); color: var(--primary-hover); border-color: var(--primary-container-strong); }
.btn-soft:hover { background: #d9e6ff; }
.btn-secondary { background: var(--bg-elevated); color: var(--text-secondary); border-color: var(--border-base); }
.btn-secondary:hover { background: var(--bg-base); border-color: var(--border-strong); }
.btn-ghost { color: var(--text-secondary); }
.btn-ghost:hover { background: var(--bg-base); color: var(--text-primary); }
.btn-danger { color: var(--text-tertiary); }
.btn-danger:hover { background: var(--red-bg); color: var(--red); border-color: var(--red-border); }

.toolbar {
  background: rgba(255, 255, 255, .92);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(0, 0, 0, .04);
  border-radius: 14px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, .04), 0 4px 12px rgba(0, 0, 0, .06);
  padding: 12px 14px;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
  position: sticky;
  top: 12px;
  z-index: 5;
}
.toolbar-left {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
}
.search {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 34px;
  padding: 0 10px;
  min-width: 220px;
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  background: var(--bg-elevated);
}
.search:focus-within {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(22, 93, 255, .15);
}
.search input {
  border: none;
  outline: none;
  flex: 1;
  font-size: 12px;
  min-width: 0;
  background: transparent;
  box-shadow: none !important;
}
.seg {
  display: inline-flex;
  background: var(--bg-base);
  padding: 3px;
  border-radius: 8px;
}
.seg button {
  height: 28px;
  padding: 0 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-tertiary);
  border: none;
  background: transparent;
  cursor: pointer;
}
.seg button.on {
  background: var(--bg-elevated);
  color: var(--primary-hover);
  box-shadow: 0 1px 2px rgba(0, 0, 0, .06);
}
.count-pill {
  font-size: 11px;
  font-weight: 650;
  color: var(--text-secondary);
  background: var(--bg-base);
  border-radius: 999px;
  padding: 4px 9px;
}

.stack {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.card {
  background: var(--bg-elevated);
  border-radius: 14px;
  border: 1px solid rgba(0, 0, 0, .04);
  box-shadow: 0 1px 2px rgba(0, 0, 0, .04), 0 4px 12px rgba(0, 0, 0, .06);
  overflow: hidden;
  transition: border-color .18s ease, box-shadow .18s ease;
}
.card.open {
  border-color: var(--primary-container-strong);
  box-shadow: 0 1px 2px rgba(0, 0, 0, .04), 0 4px 12px rgba(0, 0, 0, .06), 0 0 0 1px rgba(22, 93, 255, .08);
}
.card-head {
  width: 100%;
  display: grid;
  grid-template-columns: 36px 1fr auto;
  gap: 10px;
  align-items: center;
  padding: 12px 14px;
  border: none;
  background: transparent;
  cursor: pointer;
  text-align: left;
  color: inherit;
  transition: background .15s ease;
}
.card-head:hover { background: var(--bg-base); }
.card.open .card-head {
  background: linear-gradient(180deg, #eef4ff, #fff);
  border-bottom: 1px solid var(--border-base);
}
.idx {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 700;
  color: var(--primary-hover);
  background: var(--primary-container);
  border: 1px solid var(--primary-container-strong);
}
.card.open .idx {
  background: var(--primary);
  color: #fff;
  border-color: var(--primary);
}
.head-main { min-width: 0; }
.title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.slash {
  font-family: var(--mono);
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.slash b { color: var(--primary); font-weight: 700; }
.desc {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.head-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.chars {
  font-size: 11px;
  color: var(--text-tertiary);
  font-variant-numeric: tabular-nums;
  background: var(--bg-base);
  padding: 3px 7px;
  border-radius: 6px;
}
.chev {
  width: 28px;
  height: 28px;
  border-radius: 7px;
  display: grid;
  place-items: center;
  color: var(--text-tertiary);
  transition: transform .2s ease, background .15s ease;
}
.card.open .chev {
  transform: rotate(180deg);
  background: var(--bg-elevated);
  color: var(--primary-hover);
}
.chev svg {
  width: 16px;
  height: 16px;
  stroke: currentColor;
  fill: none;
  stroke-width: 2;
}

.card-body {
  padding: 14px 16px 16px;
  animation: cmd-in .18s ease;
}
@keyframes cmd-in {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: none; }
}
.fields {
  display: grid;
  grid-template-columns: 1fr 1.35fr;
  gap: 12px;
  margin-bottom: 12px;
}
.field label {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 6px;
}
.field input,
.field textarea {
  width: 100%;
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  padding: 9px 11px;
  font-size: 12.5px;
  color: var(--text-primary);
  background: var(--bg-elevated);
  transition: .15s;
}
.field input.mono,
.field textarea {
  font-family: var(--mono);
}
.field textarea {
  min-height: 120px;
  resize: vertical;
  line-height: 1.55;
}
.body-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
  flex-wrap: wrap;
}
.hint { font-size: 11.5px; color: var(--text-tertiary); }
.hint strong { color: var(--text-secondary); font-weight: 650; }

.empty {
  text-align: center;
  padding: 48px 20px;
  background: var(--bg-elevated);
  border-radius: 14px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, .04), 0 4px 12px rgba(0, 0, 0, .06);
  border: 1px solid rgba(0, 0, 0, .03);
  color: var(--text-tertiary);
  font-size: 13px;
}
.empty h3 {
  margin: 0 0 6px;
  color: var(--text-primary);
  font-size: 15px;
}
.empty p { margin: 0; }

@media (max-width: 640px) {
  .fields { grid-template-columns: 1fr; }
  .search { min-width: 0; width: 100%; }
}
@media (prefers-reduced-motion: reduce) {
  .card,
  .card-head,
  .chev,
  .btn,
  .card-body { transition: none !important; animation: none !important; }
}
</style>
