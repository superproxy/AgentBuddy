<script setup lang="ts">
import { onMounted } from 'vue'
import { useKeysStore } from '../stores/keys'

const keys = useKeysStore()
const { keysData, keysPath, keyEntries, keyCount, listQuery } = keys as any

onMounted(() => {
  keys.loadKeys()
})

function handleAdd() {
  keys.addKey()
}
function handleSave() {
  keys.saveKeys()
}
function handleDelete(key: string) {
  keys.deleteKey(key)
}
function reveal(e: Event) {
  const input = e.target as HTMLInputElement
  input.type = input.type === 'password' ? 'text' : 'password'
}
</script>

<template>
  <div class="keys-page">
    <header class="page-head">
      <div>
        <h1>密钥 / 环境变量</h1>
        <p class="text-xs text-ink-500 mt-1 mb-0">
          集中管理 MCP / LLM 配置中引用的密钥与环境变量。生成 mcp.json / IDE 配置时，作为
          <code v-pre>${KEY}</code> 占位符的 fallback。<br>
          <span class="text-ink-400">占位符优先取 OS 环境变量，其次取此处，最后用 <code v-pre>${VAR:-default}</code> 默认值。</span>
        </p>
      </div>
      <div class="actions">
        <button type="button" class="btn btn-soft" @click="handleAdd">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
          添加变量
        </button>
        <button type="button" class="btn btn-primary" @click="handleSave">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><path d="M17 21v-8H7v8M7 3v5h8"/></svg>
          保存
        </button>
      </div>
    </header>

    <div class="kpi-row">
      <div class="kpi"><b>{{ keyCount }}</b><span>变量总数</span><em>{{ keysPath || 'config/mcp/keys.yaml' }}</em></div>
    </div>

    <div class="toolbar">
      <input
        v-model="listQuery"
        type="search"
        class="search-input"
        placeholder="搜索变量名 / 值…"
        aria-label="搜索"
      />
      <code v-if="keysPath" class="path-hint">{{ keysPath }}</code>
    </div>

    <div class="keys-list">
      <div v-for="entry in keyEntries" :key="entry.key" class="key-row">
        <code class="key-name" :title="entry.key">{{ entry.key }}</code>
        <input
          :value="entry.value"
          @input="keys.updateValue(entry.key, ($event.target as HTMLInputElement).value)"
          type="password"
          class="value-input"
          placeholder="请输入值（如 sk-xxx）"
        />
        <button
          type="button"
          class="btn btn-icon btn-ghost btn-sm"
          aria-label="显示/隐藏"
          title="显示/隐藏"
          @click="reveal"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/></svg>
        </button>
        <button
          type="button"
          class="btn btn-danger btn-icon btn-sm"
          :aria-label="'删除 ' + entry.key"
          @click="handleDelete(entry.key)"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/></svg>
        </button>
      </div>
      <div v-if="!keyCount" class="m-empty">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3"/></svg>
        <p>暂无变量，点击右上方「添加变量」开始。</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.keys-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
}
.page-head h1 {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}
.actions {
  display: flex;
  gap: 8px;
}
.actions svg {
  width: 14px;
  height: 14px;
}

.kpi-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.kpi {
  background: var(--bg-elevated);
  border-radius: 10px;
  padding: 12px 16px;
  border: 1px solid var(--border-base);
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 160px;
}
.kpi b {
  font-size: 22px;
  font-weight: 600;
  color: var(--text-primary);
}
.kpi span {
  font-size: 12px;
  color: var(--text-secondary);
}
.kpi em {
  font-size: 10px;
  color: var(--text-tertiary);
  font-style: normal;
  margin-top: 4px;
  word-break: break-all;
}

.toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}
.search-input {
  flex: 1;
  min-width: 200px;
  max-width: 400px;
  padding: 6px 12px;
  border: 1px solid var(--border-base);
  border-radius: 8px;
  font-size: 13px;
  background: var(--bg-elevated);
  color: var(--text-primary);
}
.search-input:focus {
  outline: none;
  border-color: var(--brand-500, #3b82f6);
}
.path-hint {
  font-size: 11px;
  color: var(--text-tertiary);
  background: var(--bg-elevated);
  padding: 4px 8px;
  border-radius: 4px;
  border: 1px solid var(--border-base);
}

.keys-list {
  display: grid;
  gap: 8px;
}
.key-row {
  display: grid;
  grid-template-columns: minmax(140px, 220px) 1fr auto auto;
  gap: 8px;
  align-items: center;
  background: var(--bg-elevated);
  border: 1px solid var(--border-base);
  border-radius: 10px;
  padding: 10px 12px;
}
.key-name {
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size: 12px;
  color: var(--brand-600, #2563eb);
  background: rgba(59, 130, 246, 0.08);
  padding: 4px 8px;
  border-radius: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.value-input {
  width: 100%;
  padding: 6px 10px;
  border: 1px solid var(--border-base);
  border-radius: 6px;
  font-size: 13px;
  font-family: 'SF Mono', 'Consolas', monospace;
  background: var(--bg-base);
  color: var(--text-primary);
}
.value-input:focus {
  outline: none;
  border-color: var(--brand-500, #3b82f6);
}

.m-empty {
  text-align: center;
  padding: 48px 16px;
  color: var(--text-tertiary);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
.m-empty svg {
  width: 36px;
  height: 36px;
  opacity: 0.5;
}
.m-empty p {
  font-size: 13px;
  margin: 0;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.15s;
}
.btn-sm {
  padding: 4px 8px;
  font-size: 11px;
}
.btn-icon {
  padding: 4px;
}
.btn-primary {
  background: var(--brand-500, #3b82f6);
  color: white;
}
.btn-primary:hover {
  background: var(--brand-600, #2563eb);
}
.btn-soft {
  background: var(--bg-elevated);
  border-color: var(--border-base);
  color: var(--text-primary);
}
.btn-soft:hover {
  background: var(--bg-hover, #f3f4f6);
}
.btn-ghost {
  background: transparent;
  color: var(--text-secondary);
}
.btn-ghost:hover {
  background: var(--bg-hover, #f3f4f6);
}
.btn-danger {
  background: transparent;
  color: #ef4444;
  border-color: transparent;
}
.btn-danger:hover {
  background: rgba(239, 68, 68, 0.1);
}
</style>
