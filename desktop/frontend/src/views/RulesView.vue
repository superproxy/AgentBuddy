<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useRulesStore } from '../stores/rules'

const rules = useRulesStore()
const {
  rules: ruleList,
  groupedRules,
  filteredRules,
  selectedRulePath,
  editingContent,
  editingMeta,
  dirty,
  selectedRule,
  listQuery,
  sourceFilter,
  roleFilter,
  usedRoles,
  roleCatalog,
} = storeToRefs(rules)
const {
  loadRules,
  selectRule,
  onContentChange,
  setRole,
  discardChanges,
  saveRule,
  deleteRule,
  newRule,
  clearFilters,
  syncRules,
  exportRules,
  importRules,
} = rules

const inputRef = ref<HTMLInputElement | null>(null)
const roleInputRef = ref<HTMLInputElement | null>(null)
const roleComboRef = ref<HTMLElement | null>(null)

const roleOpen = ref(false)
const roleQuery = ref('')
const roleActiveIdx = ref(0)

const hideGroupHeader = computed(
  () => roleFilter.value !== 'all' && groupedRules.value.length <= 1,
)

const roleOptions = computed(() => {
  const q = roleQuery.value.trim().toLowerCase()
  const all = roleCatalog.value
  const matched = q ? all.filter((x) => x.name.toLowerCase().includes(q)) : all
  const exact = all.some((x) => x.name.toLowerCase() === q)
  const createName = roleQuery.value.trim()
  return {
    matched,
    canCreate: !!createName && !exact,
    createName,
    total: matched.length + (createName && !exact ? 1 : 0),
  }
})

const roleHint = computed(() => {
  const role = editingMeta.value.role
  if (role) return `当前岗位「${role}」· 左侧列表按此分组`
  return '从已有岗位中选择，或直接输入后回车新建'
})

function triggerImport() {
  inputRef.value?.click()
}

function openRoleMenu() {
  roleOpen.value = true
  roleQuery.value = ''
  roleActiveIdx.value = 0
}

function closeRoleMenu() {
  roleOpen.value = false
  roleQuery.value = ''
  roleActiveIdx.value = -1
}

function pickRole(name: string) {
  setRole(name)
  closeRoleMenu()
}

function clearRole() {
  setRole('')
  nextTick(() => {
    roleInputRef.value?.focus()
    openRoleMenu()
  })
}

function toggleRoleMenu() {
  if (roleOpen.value) {
    closeRoleMenu()
    return
  }
  roleInputRef.value?.focus()
  openRoleMenu()
}

function onRoleInput() {
  if (!roleOpen.value) openRoleMenu()
  roleActiveIdx.value = 0
}

function onRoleKeydown(e: KeyboardEvent) {
  const { matched, canCreate, createName, total } = roleOptions.value
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    if (!roleOpen.value) openRoleMenu()
    else if (total) roleActiveIdx.value = (roleActiveIdx.value + 1) % total
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    if (!roleOpen.value) openRoleMenu()
    else if (total) roleActiveIdx.value = (roleActiveIdx.value - 1 + total) % total
  } else if (e.key === 'Enter') {
    e.preventDefault()
    if (!roleOpen.value) {
      openRoleMenu()
      return
    }
    if (roleActiveIdx.value >= 0 && roleActiveIdx.value < matched.length) {
      pickRole(matched[roleActiveIdx.value].name)
    } else if (canCreate) {
      pickRole(createName)
    } else if (createName) {
      pickRole(createName)
    }
  } else if (e.key === 'Escape') {
    e.preventDefault()
    closeRoleMenu()
    roleInputRef.value?.blur()
  } else if (e.key === 'Backspace' && !roleQuery.value && editingMeta.value.role) {
    clearRole()
  }
}

function onDocMouseDown(e: MouseEvent) {
  if (!roleComboRef.value?.contains(e.target as Node)) closeRoleMenu()
}

function onGlobalKey(e: KeyboardEvent) {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') {
    if (!selectedRulePath.value || !dirty.value) return
    e.preventDefault()
    void saveRule()
  }
}

async function handleNewRule() {
  newRule()
  await nextTick()
  roleInputRef.value?.focus()
  openRoleMenu()
}

onMounted(async () => {
  document.addEventListener('mousedown', onDocMouseDown)
  window.addEventListener('keydown', onGlobalKey)
  await loadRules()
  if (ruleList.value.length) {
    await selectRule(ruleList.value[0].path, true)
  }
})

onUnmounted(() => {
  document.removeEventListener('mousedown', onDocMouseDown)
  window.removeEventListener('keydown', onGlobalKey)
})
</script>

<template>
  <div class="rules-page">
    <div class="shell">
      <header class="header">
        <div class="header-left">
          <div class="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 12h6M9 16h6M7 4h10a2 2 0 012 2v14l-7-3-7 3V6a2 2 0 012-2z"/></svg>
          </div>
          <div class="title-block">
            <h1>Rules 管理</h1>
            <p>定义 Agent 行为边界与规范 · 多种规则类型 · 一键同步到支持的 IDE</p>
          </div>
        </div>
        <div class="header-actions">
          <button type="button" class="btn btn-ghost" @click="triggerImport">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3v12m0 0l-4-4m4 4l4-4M4 21h16"/></svg>
            导入
          </button>
          <button type="button" class="btn btn-ghost" @click="exportRules">导出</button>
          <button type="button" class="btn btn-ghost" @click="syncRules">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 12v7a1 1 0 001 1h14a1 1 0 001-1v-7M12 3v13m0 0l-4-4m4 4l4-4"/></svg>
            同步到 IDE
          </button>
          <button type="button" class="btn btn-primary" @click="handleNewRule">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
            新建规则
          </button>
          <input ref="inputRef" type="file" accept=".zip,.md" class="hidden" @change="importRules">
        </div>
      </header>

      <div v-if="dirty" class="dirty-bar" role="status">
        <span><strong>有未保存更改</strong> — 离开前请保存，避免丢失编辑</span>
        <div class="dirty-actions">
          <button type="button" class="btn btn-ghost" @click="discardChanges">放弃</button>
          <button type="button" class="btn btn-amber" @click="saveRule">保存更改</button>
        </div>
      </div>

      <div class="body">
        <aside class="rail" aria-label="规则列表">
          <div class="rail-tools">
            <label class="search">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3-3"/></svg>
              <input v-model="listQuery" type="search" placeholder="搜索规则名称或描述…" aria-label="搜索规则">
            </label>

            <div class="filter-block">
              <div class="filter-label">来源</div>
              <div class="chips" role="tablist" aria-label="来源筛选">
                <button type="button" class="chip" :class="{ active: sourceFilter === 'all' }" @click="sourceFilter = 'all'">全部</button>
                <button type="button" class="chip" :class="{ active: sourceFilter === 'custom' }" @click="sourceFilter = 'custom'">自定义</button>
                <button type="button" class="chip" :class="{ active: sourceFilter === 'template' }" @click="sourceFilter = 'template'">预置</button>
                <button type="button" class="chip" :class="{ active: sourceFilter === 'always' }" @click="sourceFilter = 'always'">始终生效</button>
              </div>
            </div>

            <div class="filter-block">
              <div class="filter-label">岗位</div>
              <div class="chips" role="tablist" aria-label="岗位筛选">
                <button
                  type="button"
                  class="chip chip-role"
                  :class="{ active: roleFilter === 'all' }"
                  @click="roleFilter = 'all'"
                >
                  全部<span class="chip-n">{{ ruleList.length }}</span>
                </button>
                <button
                  v-for="item in usedRoles.list"
                  :key="item.name"
                  type="button"
                  class="chip chip-role"
                  :class="{ active: roleFilter === item.name }"
                  @click="roleFilter = item.name"
                >
                  {{ item.name }}<span class="chip-n">{{ item.count }}</span>
                </button>
                <button
                  v-if="usedRoles.none > 0"
                  type="button"
                  class="chip chip-role"
                  :class="{ active: roleFilter === '__none__' }"
                  @click="roleFilter = '__none__'"
                >
                  未分类<span class="chip-n">{{ usedRoles.none }}</span>
                </button>
              </div>
            </div>
          </div>

          <div class="rail-list">
            <template v-if="filteredRules.length">
              <div v-for="group in groupedRules" :key="group.key" class="group">
                <div v-if="!hideGroupHeader" class="cat-label">
                  <span>{{ group.key }}</span>
                  <span class="n">{{ group.items.length }}</span>
                </div>
                <div
                  v-for="r in group.items"
                  :key="r.path"
                  class="rule-item"
                  :class="{ active: selectedRulePath === r.path }"
                  role="button"
                  tabindex="0"
                  @click="selectRule(r.path)"
                  @keydown.enter.prevent="selectRule(r.path)"
                  @keydown.space.prevent="selectRule(r.path)"
                >
                  <div class="rule-top">
                    <span class="rule-name">{{ r.name }}</span>
                    <span v-if="r.alwaysApply" class="badge badge-always">always</span>
                    <span class="badge" :class="r.source === 'template' ? 'badge-tpl' : 'badge-custom'">
                      {{ r.source === 'template' ? '预置' : '自定义' }}
                    </span>
                  </div>
                  <div v-if="r.description" class="rule-desc">{{ r.description }}</div>
                </div>
              </div>
            </template>
            <div v-else class="rail-empty">
              无匹配规则
              <button type="button" class="link-btn" @click="clearFilters">清除筛选</button>
            </div>
          </div>

          <div class="rail-footer">
            <span>{{ filteredRules.length }} 个规则</span>
            <button type="button" class="link-btn" @click="handleNewRule">+ 新建</button>
          </div>
        </aside>

        <main class="editor">
          <div v-if="!selectedRulePath" class="editor-placeholder">
            暂无规则 — 点击「新建规则」开始
          </div>

          <div v-else class="editor-inner">
            <div class="editor-head">
              <div>
                <h2>{{ selectedRule?.name || '—' }}</h2>
                <div class="path">{{ selectedRulePath }}</div>
              </div>
              <button type="button" class="btn btn-primary" :disabled="!dirty" @click="saveRule">保存</button>
            </div>

            <div class="meta">
              <div class="field">
                <label for="roleInput">岗位 <span class="hint">用于左侧分组</span></label>
                <div ref="roleComboRef" class="combo">
                  <div class="combo-control" :class="{ open: roleOpen, 'has-value': !!editingMeta.role }">
                    <span v-if="editingMeta.role && !roleOpen" class="combo-tag show">
                      <span>{{ editingMeta.role }}</span>
                      <button type="button" aria-label="清除岗位" @click.stop="clearRole">×</button>
                    </span>
                    <input
                      id="roleInput"
                      ref="roleInputRef"
                      v-model="roleQuery"
                      type="text"
                      :placeholder="editingMeta.role ? '更换岗位…' : '选择或输入新岗位…'"
                      autocomplete="off"
                      role="combobox"
                      :aria-expanded="roleOpen"
                      aria-controls="roleMenu"
                      aria-autocomplete="list"
                      @focus="openRoleMenu"
                      @input="onRoleInput"
                      @keydown="onRoleKeydown"
                    >
                    <button type="button" class="combo-chevron" aria-label="展开岗位列表" @click.stop="toggleRoleMenu">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
                    </button>
                  </div>
                  <div v-show="roleOpen" id="roleMenu" class="combo-menu open" role="listbox">
                    <template v-if="roleOptions.matched.length">
                      <div class="combo-section">已有岗位</div>
                      <button
                        v-for="(item, i) in roleOptions.matched"
                        :key="item.name"
                        type="button"
                        class="combo-option"
                        :class="{ active: i === roleActiveIdx }"
                        role="option"
                        @mousedown.prevent="pickRole(item.name)"
                      >
                        {{ item.name }}
                        <span v-if="item.count" class="count">{{ item.count }}</span>
                      </button>
                    </template>
                    <div v-else-if="!roleOptions.canCreate" class="combo-empty">
                      暂无岗位，输入名称后回车创建
                    </div>
                    <button
                      v-if="roleOptions.canCreate"
                      type="button"
                      class="combo-option create"
                      :class="{ active: roleActiveIdx === roleOptions.matched.length }"
                      role="option"
                      @mousedown.prevent="pickRole(roleOptions.createName)"
                    >
                      <span class="plus">+</span>
                      创建岗位「{{ roleOptions.createName }}」
                    </button>
                  </div>
                </div>
                <div class="combo-hint">{{ roleHint }}</div>
              </div>

              <div class="field span-2">
                <label for="metaDesc">描述 <span class="hint">何时使用此规则</span></label>
                <input
                  id="metaDesc"
                  v-model="editingMeta.description"
                  type="text"
                  placeholder="例如：编写后端代码时使用此规则"
                  @input="onContentChange"
                >
              </div>

              <div class="field">
                <label for="metaGlobs">文件匹配 <span class="hint">globs，逗号分隔</span></label>
                <input
                  id="metaGlobs"
                  v-model="editingMeta.globs"
                  type="text"
                  placeholder="**/*.java,**/*.py"
                  @input="onContentChange"
                >
              </div>
              <div class="field">
                <label for="metaScene">场景 <span class="hint">scene</span></label>
                <input
                  id="metaScene"
                  v-model="editingMeta.scene"
                  type="text"
                  placeholder="git_message"
                  @input="onContentChange"
                >
              </div>
              <div class="field">
                <label>生效方式</label>
                <div class="switch-row">
                  <label class="switch">
                    <input v-model="editingMeta.alwaysApply" type="checkbox" @change="onContentChange">
                    <span />
                  </label>
                  <span class="switch-label">始终生效</span>
                </div>
              </div>
            </div>

            <div class="body-label">
              <span>规则正文 · Markdown</span>
              <button
                v-if="selectedRule?.source !== 'template'"
                type="button"
                class="danger"
                @click="deleteRule(selectedRulePath)"
              >
                删除
              </button>
            </div>
            <div class="editor-body">
              <textarea
                v-model="editingContent"
                spellcheck="false"
                placeholder="在此编写规则内容…"
                @input="onContentChange"
              />
            </div>
          </div>
        </main>
      </div>
    </div>
  </div>
</template>

<style scoped>
.rules-page {
  --green: #00b42a;
  --green-bg: #e8ffea;
  --amber: #ff7d00;
  --amber-bg: #fff7e8;
  --red: #f53f3f;
  height: calc(100vh - 120px);
  min-height: 520px;
}
.shell {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg-elevated);
  border: 1px solid var(--border-base);
  border-radius: 16px;
  box-shadow: 0 1px 2px rgba(31, 35, 41, 0.04), 0 4px 16px rgba(31, 35, 41, 0.06);
  overflow: hidden;
}
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border-base);
  flex-shrink: 0;
}
.header-left { display: flex; align-items: center; gap: 12px; min-width: 0; }
.brand-mark {
  width: 32px; height: 32px; border-radius: 9px;
  background: linear-gradient(135deg, #165dff, #0a2e9c);
  display: grid; place-items: center; color: #fff; flex-shrink: 0;
}
.brand-mark svg { width: 16px; height: 16px; }
.title-block h1 { font-size: 15px; font-weight: 700; letter-spacing: -0.01em; margin: 0; color: var(--text-primary); }
.title-block p { font-size: 12px; color: var(--text-tertiary); margin: 1px 0 0; }
.header-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; flex-wrap: wrap; }

.btn {
  display: inline-flex; align-items: center; gap: 6px;
  height: 32px; padding: 0 12px; border-radius: 8px;
  font-size: 12px; font-weight: 600;
  border: 1px solid transparent; cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s, box-shadow 0.15s;
  background: transparent; color: inherit;
}
.btn:focus-visible { outline: none; box-shadow: 0 0 0 3px rgba(22, 93, 255, 0.28); }
.btn-ghost { color: var(--text-secondary); border-color: var(--border-base); }
.btn-ghost:hover { background: var(--bg-base); border-color: var(--border-strong); }
.btn-primary { background: var(--primary); color: #fff; }
.btn-primary:hover:not(:disabled) { background: var(--primary-hover); }
.btn-primary:disabled { opacity: 0.45; cursor: not-allowed; }
.btn-amber { background: var(--amber); color: #fff; border: none; }
.btn-amber:hover { filter: brightness(0.95); }
.btn svg { width: 14px; height: 14px; }

.dirty-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 20px;
  background: var(--amber-bg);
  border-bottom: 1px solid #ffe4c2;
  font-size: 12px;
  color: #a35400;
  flex-shrink: 0;
}
.dirty-actions { display: flex; gap: 8px; }

.body { display: flex; flex: 1; min-height: 0; }
.rail {
  width: 300px; flex-shrink: 0;
  border-right: 1px solid var(--border-base);
  display: flex; flex-direction: column;
  background: #fbfcfe;
}
.rail-tools {
  padding: 12px;
  border-bottom: 1px solid var(--border-base);
  display: flex; flex-direction: column; gap: 10px;
}
.search {
  display: flex; align-items: center; gap: 8px;
  height: 36px; padding: 0 10px;
  background: var(--bg-elevated); border: 1px solid var(--border-base);
  border-radius: 8px; transition: border-color 0.15s, box-shadow 0.15s;
}
.search:focus-within {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px var(--primary-container-strong);
}
.search svg { width: 14px; height: 14px; color: var(--text-tertiary); flex-shrink: 0; }
.search input {
  flex: 1; border: none; outline: none; background: transparent;
  font: inherit; font-size: 12px; color: var(--text-primary); min-width: 0;
}
.filter-block { display: flex; flex-direction: column; gap: 6px; }
.filter-label {
  font-size: 10px; font-weight: 700; letter-spacing: 0.04em;
  text-transform: uppercase; color: var(--text-tertiary);
}
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip {
  height: 26px; padding: 0 10px; border-radius: 999px;
  border: 1px solid var(--border-base); background: var(--bg-elevated);
  font-size: 11px; font-weight: 600; color: var(--text-secondary);
  cursor: pointer; transition: all 0.15s;
}
.chip:hover { border-color: var(--primary-container-strong); color: var(--primary-hover); }
.chip.active {
  background: var(--primary-container); border-color: var(--primary-container-strong); color: var(--primary-hover);
}
.chip.chip-role.active {
  background: var(--text-primary); border-color: var(--text-primary); color: #fff;
}
.chip-n { margin-left: 4px; font-size: 10px; font-weight: 600; opacity: 0.65; }

.rail-list { flex: 1; overflow-y: auto; padding: 8px; }
.cat-label {
  font-size: 10px; font-weight: 700; letter-spacing: 0.06em;
  text-transform: uppercase; color: var(--text-tertiary);
  padding: 8px 8px 4px;
  display: flex; align-items: center; gap: 6px;
}
.cat-label .n {
  font-weight: 600; letter-spacing: 0; text-transform: none;
  color: var(--text-secondary); margin-left: auto;
}
.rule-item {
  display: flex; flex-direction: column; gap: 4px;
  padding: 10px; border-radius: 10px;
  cursor: pointer; border: 1px solid transparent;
  transition: background 0.15s, border-color 0.15s;
}
.rule-item:hover { background: var(--bg-elevated); border-color: var(--border-base); }
.rule-item.active { background: var(--primary-container); border-color: var(--primary-container-strong); }
.rule-item:focus-visible { outline: none; box-shadow: 0 0 0 3px rgba(22, 93, 255, 0.28); }
.rule-top { display: flex; align-items: center; gap: 8px; }
.rule-name {
  font-size: 13px; font-weight: 600; flex: 1; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-primary);
}
.badge {
  font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 4px; flex-shrink: 0;
}
.badge-always { background: var(--green-bg); color: var(--green); }
.badge-tpl { background: var(--bg-base); color: var(--text-tertiary); }
.badge-custom { background: var(--primary-container); color: var(--primary-hover); }
.rule-desc {
  font-size: 11px; color: var(--text-tertiary); line-height: 1.35;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.rail-empty {
  padding: 24px; text-align: center; color: var(--text-tertiary); font-size: 12px;
  display: flex; flex-direction: column; align-items: center; gap: 8px;
}
.rail-footer {
  padding: 10px 12px; border-top: 1px solid var(--border-base);
  display: flex; align-items: center; justify-content: space-between;
  font-size: 11px; color: var(--text-tertiary);
}
.link-btn {
  background: none; border: none; color: var(--primary-hover);
  font: inherit; font-size: 11px; font-weight: 600; cursor: pointer;
}
.link-btn:hover { text-decoration: underline; }

.editor {
  flex: 1; min-width: 0; display: flex; flex-direction: column;
  background: var(--bg-elevated); min-height: 0;
}
.editor-placeholder {
  flex: 1; display: flex; align-items: center; justify-content: center;
  padding: 24px; color: var(--text-tertiary); font-size: 13px;
}
.editor-inner {
  flex: 1; min-height: 0; display: flex; flex-direction: column;
}
.editor-head {
  padding: 14px 20px 0;
  display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;
  flex-shrink: 0;
}
.editor-head h2 {
  font-size: 18px; font-weight: 700; letter-spacing: -0.02em;
  margin: 0; color: var(--text-primary);
}
.path {
  font-size: 11px; color: var(--text-tertiary); margin-top: 4px;
  font-family: 'JetBrains Mono', Consolas, monospace;
}

.meta {
  margin: 12px 20px 0;
  padding: 14px;
  background: var(--bg-base);
  border: 1px solid var(--border-base);
  border-radius: 12px;
  display: grid;
  grid-template-columns: 1.1fr 1fr 1fr;
  gap: 12px;
  flex-shrink: 0;
}
.field { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.field.span-2 { grid-column: span 2; }
.field label { font-size: 11px; font-weight: 600; color: var(--text-secondary); }
.field .hint { font-weight: 400; color: var(--text-tertiary); }
.field input[type='text'] {
  height: 34px; padding: 0 10px; border-radius: 8px;
  border: 1px solid var(--border-base); background: var(--bg-elevated);
  font: inherit; font-size: 12px; color: var(--text-primary); width: 100%;
}
.field input:focus {
  outline: none; border-color: var(--primary);
  box-shadow: 0 0 0 3px var(--primary-container-strong);
}

.combo { position: relative; }
.combo-control {
  display: flex; align-items: center; gap: 6px;
  height: 34px; padding: 0 8px 0 10px;
  border-radius: 8px; border: 1px solid var(--border-base);
  background: var(--bg-elevated); cursor: text;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.combo-control.open,
.combo-control:focus-within {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px var(--primary-container-strong);
}
.combo-control.has-value { padding-left: 8px; }
.combo-tag {
  display: none; align-items: center; gap: 4px;
  max-width: 55%; height: 22px; padding: 0 6px 0 8px;
  border-radius: 5px; background: var(--primary-container); color: var(--primary-hover);
  font-size: 11px; font-weight: 600; flex-shrink: 0;
}
.combo-tag.show { display: inline-flex; }
.combo-tag button {
  width: 16px; height: 16px; border: none; border-radius: 4px;
  background: transparent; color: var(--primary-hover); cursor: pointer;
  display: grid; place-items: center; padding: 0; font-size: 12px; line-height: 1;
}
.combo-tag button:hover { background: #d9e6ff; }
.combo-control input {
  flex: 1; min-width: 0; height: 100%; border: none !important;
  outline: none !important; box-shadow: none !important;
  background: transparent !important; padding: 0 !important;
  font: inherit; font-size: 12px; color: var(--text-primary);
}
.combo-chevron {
  width: 28px; height: 28px; border: none; border-radius: 6px;
  background: transparent; color: var(--text-tertiary); cursor: pointer;
  display: grid; place-items: center; flex-shrink: 0;
}
.combo-chevron:hover { background: var(--bg-base); color: var(--text-secondary); }
.combo-chevron svg { width: 14px; height: 14px; transition: transform 0.15s; }
.combo-control.open .combo-chevron svg { transform: rotate(180deg); }
.combo-menu {
  position: absolute; left: 0; right: 0; top: calc(100% + 4px);
  max-height: 240px; overflow-y: auto; z-index: 30;
  background: var(--bg-elevated); border: 1px solid var(--border-base);
  border-radius: 10px;
  box-shadow: 0 1px 2px rgba(31, 35, 41, 0.04), 0 4px 16px rgba(31, 35, 41, 0.06);
  padding: 4px;
}
.combo-section {
  font-size: 10px; font-weight: 700; letter-spacing: 0.04em;
  text-transform: uppercase; color: var(--text-tertiary);
  padding: 8px 10px 4px;
}
.combo-option {
  display: flex; align-items: center; gap: 8px;
  width: 100%; padding: 8px 10px; border: none; border-radius: 7px;
  background: transparent; font: inherit; font-size: 12px;
  color: var(--text-primary); cursor: pointer; text-align: left;
}
.combo-option:hover,
.combo-option.active { background: var(--primary-container); color: var(--primary-hover); }
.combo-option .count {
  margin-left: auto; font-size: 10px; font-weight: 600;
  color: var(--text-tertiary); background: var(--bg-base);
  padding: 1px 6px; border-radius: 999px;
}
.combo-option.create {
  color: var(--primary-hover); font-weight: 600;
  border-top: 1px solid var(--border-base); margin-top: 2px;
  border-radius: 0 0 7px 7px;
}
.combo-option.create .plus {
  width: 18px; height: 18px; border-radius: 5px;
  background: var(--primary-container); color: var(--primary-hover);
  display: grid; place-items: center; font-size: 14px; flex-shrink: 0;
}
.combo-empty {
  padding: 12px 10px; font-size: 12px; color: var(--text-tertiary); text-align: center;
}
.combo-hint {
  font-size: 10px; color: var(--text-tertiary); margin-top: 2px; line-height: 1.35;
}

.switch-row { display: flex; align-items: center; gap: 10px; height: 34px; }
.switch { position: relative; width: 36px; height: 20px; flex-shrink: 0; }
.switch input { opacity: 0; width: 0; height: 0; }
.switch span {
  position: absolute; inset: 0; border-radius: 999px;
  background: var(--border-strong); cursor: pointer; transition: 0.15s;
}
.switch span::after {
  content: ''; position: absolute; width: 16px; height: 16px;
  left: 2px; top: 2px; border-radius: 50%; background: var(--bg-elevated);
  transition: 0.15s; box-shadow: 0 1px 2px rgba(0, 0, 0, 0.15);
}
.switch input:checked + span { background: var(--primary); }
.switch input:checked + span::after { transform: translateX(16px); }
.switch input:focus-visible + span { box-shadow: 0 0 0 3px rgba(22, 93, 255, 0.28); }
.switch-label { font-size: 12px; color: var(--text-secondary); font-weight: 500; }

.body-label {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 20px 8px; font-size: 11px; font-weight: 600; color: var(--text-tertiary);
  flex-shrink: 0;
}
.danger {
  background: none; border: none; color: var(--red);
  font: inherit; font-size: 11px; font-weight: 600; cursor: pointer;
}
.danger:hover { text-decoration: underline; }
.editor-body { flex: 1; min-height: 0; padding: 0 20px 20px; display: flex; }
.editor-body textarea {
  width: 100%; height: 100%; resize: none;
  border: 1px solid var(--border-base); border-radius: 12px;
  padding: 14px 16px; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 12px;
  line-height: 1.6; color: var(--text-primary); background: var(--bg-elevated);
}
.editor-body textarea:focus {
  outline: none; border-color: var(--primary);
  box-shadow: 0 0 0 3px var(--primary-container-strong);
}

@media (max-width: 1000px) {
  .meta { grid-template-columns: 1fr 1fr; }
  .field.span-2 { grid-column: 1 / -1; }
}
@media (max-width: 900px) {
  .rules-page { height: auto; min-height: 0; }
  .shell { min-height: 70vh; }
  .body { flex-direction: column; }
  .rail { width: 100%; max-height: 38vh; border-right: none; border-bottom: 1px solid var(--border-base); }
  .meta { grid-template-columns: 1fr; }
  .field.span-2 { grid-column: auto; }
  .editor-body textarea { min-height: 280px; }
}
@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; }
}
</style>
