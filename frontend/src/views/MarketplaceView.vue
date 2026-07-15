<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useMarketplaceStore } from '../stores/marketplace'
import { useAiGenerateStore } from '../stores/aiGenerate'

const mkt = useMarketplaceStore()
const ai = useAiGenerateStore()
const { items, loading, searchQuery, installing } = storeToRefs(mkt)
const { dialogOpen, prompt, level, generating, output, generatedConfig } = storeToRefs(ai)

type SortKey = 'new' | 'hot' | 'name'
type ViewMode = 'grid' | 'list'

const activeTags = ref<string[]>([])
const activeAuthor = ref('')
const sort = ref<SortKey>('new')
const view = ref<ViewMode>('grid')

let searchTimer: ReturnType<typeof setTimeout> | null = null

function onSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => mkt.browse(), 300)
}

function formatSize(bytes: number): string {
  if (!bytes) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

function formatDate(iso: string): string {
  if (!iso) return '-'
  try {
    return new Date(iso).toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
  } catch {
    return iso
  }
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (!parts.length) return '?'
  return parts.slice(0, 2).map((w) => w[0]!.toUpperCase()).join('')
}

const tagCounts = computed(() => {
  const map: Record<string, number> = {}
  for (const item of items.value) {
    for (const t of item.tags || []) map[t] = (map[t] || 0) + 1
  }
  return Object.entries(map)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([tag, count]) => ({ tag, count }))
})

const authorCounts = computed(() => {
  const map: Record<string, number> = {}
  for (const item of items.value) {
    const a = item.author || 'unknown'
    map[a] = (map[a] || 0) + 1
  }
  return Object.entries(map)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([author, count]) => ({ author, count }))
})

const suggestTags = computed(() => tagCounts.value.slice(0, 6).map((t) => t.tag))

const totalDownloads = computed(() => items.value.reduce((s, i) => s + (i.downloads || 0), 0))

const hasFilters = computed(
  () => activeTags.value.length > 0 || !!activeAuthor.value || !!searchQuery.value.trim(),
)

const filteredItems = computed(() => {
  let list = items.value.slice()
  if (activeTags.value.length) {
    list = list.filter((item) => activeTags.value.every((t) => (item.tags || []).includes(t)))
  }
  if (activeAuthor.value) {
    list = list.filter((item) => item.author === activeAuthor.value)
  }
  if (sort.value === 'hot') list.sort((a, b) => (b.downloads || 0) - (a.downloads || 0))
  else if (sort.value === 'name') list.sort((a, b) => a.name.localeCompare(b.name))
  else list.sort((a, b) => (b.published_at || '').localeCompare(a.published_at || ''))
  return list
})

function toggleTag(tag: string) {
  const i = activeTags.value.indexOf(tag)
  if (i >= 0) activeTags.value = activeTags.value.filter((t) => t !== tag)
  else activeTags.value = [...activeTags.value, tag]
}

function toggleAuthor(author: string) {
  activeAuthor.value = activeAuthor.value === author ? '' : author
}

function clearFilters() {
  activeTags.value = []
  activeAuthor.value = ''
  searchQuery.value = ''
  mkt.browse('')
}

function setView(mode: ViewMode) {
  view.value = mode
}

function setSort(key: SortKey) {
  sort.value = key
}

function applySuggest(tag: string) {
  toggleTag(tag)
}

onMounted(() => { mkt.browse() })
</script>

<template>
  <div class="mkt-page">
    <!-- Hero：搜索优先 -->
    <header class="mkt-hero">
      <div class="mkt-eyebrow">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h10M4 17h14"/></svg>
        插件市场
      </div>
      <h1>找到下一个可复用智能体</h1>
      <p>按名称、描述或标签检索本地市场中的完整插件包，一键安装到当前工作区。</p>

      <div class="mkt-search">
        <span class="mkt-search-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3-3"/></svg>
        </span>
        <input
          v-model="searchQuery"
          type="search"
          placeholder="搜索插件名称、描述、标签…"
          autocomplete="off"
          aria-label="搜索插件"
          @input="onSearch"
          @keyup.enter="mkt.browse()"
        />
        <button type="button" class="mkt-search-go" :disabled="loading" @click="mkt.browse()">
          {{ loading ? '…' : '搜索' }}
        </button>
      </div>

      <div v-if="suggestTags.length" class="mkt-suggests">
        <span>试试</span>
        <button
          v-for="tag in suggestTags"
          :key="tag"
          type="button"
          class="mkt-chip"
          :class="{ on: activeTags.includes(tag) }"
          @click="applySuggest(tag)"
        >{{ tag }}</button>
      </div>

      <div class="mkt-hero-actions">
        <button type="button" class="mkt-btn mkt-btn-primary" @click="ai.openDialog()">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3zM19 14l.8 2.2L22 17l-2.2.8L19 20l-.8-2.2L16 17l2.2-.8L19 14z"/></svg>
          AI 创建插件
        </button>
        <button type="button" class="mkt-btn mkt-btn-ghost" :disabled="loading" @click="mkt.browse()">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12a9 9 0 1 1-2.6-6.3M21 3v6h-6"/></svg>
          {{ loading ? '加载中…' : '刷新' }}
        </button>
      </div>
    </header>

    <!-- 概览 -->
    <div class="mkt-stats" aria-label="市场概览">
      <div class="mkt-stat"><b>{{ items.length }}</b><span>可用插件</span></div>
      <div class="mkt-stat"><b>{{ totalDownloads }}</b><span>累计安装</span></div>
      <div class="mkt-stat"><b>{{ tagCounts.length }}</b><span>活跃标签</span></div>
    </div>

    <div class="mkt-workspace">
      <div class="mkt-main">
        <div class="mkt-toolbar">
          <h2>全部插件<em>· {{ filteredItems.length }} 个</em></h2>
          <div class="mkt-toolbar-right">
            <div class="mkt-view-toggle" role="group" aria-label="视图切换">
              <button
                type="button"
                :class="{ on: view === 'grid' }"
                title="卡片视图"
                :aria-pressed="view === 'grid'"
                @click="setView('grid')"
              >
                <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
              </button>
              <button
                type="button"
                :class="{ on: view === 'list' }"
                title="列表视图"
                :aria-pressed="view === 'list'"
                @click="setView('list')"
              >
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"/></svg>
              </button>
            </div>
            <div class="mkt-sort" role="group" aria-label="排序">
              <button type="button" :class="{ on: sort === 'new' }" @click="setSort('new')">最新</button>
              <button type="button" :class="{ on: sort === 'hot' }" @click="setSort('hot')">最热</button>
              <button type="button" :class="{ on: sort === 'name' }" @click="setSort('name')">名称</button>
            </div>
          </div>
        </div>

        <div v-if="loading && !items.length" class="mkt-empty">
          <div class="mkt-spinner" aria-hidden="true" />
          <h3>加载中…</h3>
        </div>

        <div v-else-if="!items.length" class="mkt-empty">
          <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
          <h3>市场暂无插件</h3>
          <p>在「插件配置」页点击「分享到市场」即可发布，或用 AI 创建。</p>
          <button type="button" class="mkt-btn mkt-btn-primary" @click="ai.openDialog()">AI 创建插件</button>
        </div>

        <div v-else-if="!filteredItems.length" class="mkt-empty">
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3-3"/></svg>
          <h3>没有匹配的插件</h3>
          <p>换个关键词，或清除右侧筛选后再试。</p>
          <button type="button" class="mkt-btn mkt-btn-primary" @click="clearFilters">清除筛选</button>
        </div>

        <div
          v-else
          class="mkt-grid"
          :class="{ 'view-list': view === 'list' }"
          aria-live="polite"
        >
          <article v-for="item in filteredItems" :key="item.id" class="mkt-card">
            <div class="mkt-card-top">
              <div class="mkt-avatar" aria-hidden="true">{{ initials(item.name) }}</div>
              <div class="min-w-0">
                <h3>
                  {{ item.name }}
                  <span class="mkt-ver">v{{ item.version }}</span>
                </h3>
                <p class="mkt-desc">{{ item.description || '无描述' }}</p>
              </div>
            </div>

            <div v-if="item.tags?.length" class="mkt-tags">
              <span v-for="tag in item.tags" :key="tag" class="mkt-tag">{{ tag }}</span>
            </div>

            <div class="mkt-meta">
              <span>
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                {{ item.author || '-' }}
              </span>
              <span>
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
                {{ item.downloads || 0 }}
              </span>
              <span>{{ formatSize(item.size) }}</span>
              <span>{{ formatDate(item.published_at) }}</span>
            </div>

            <div class="mkt-actions">
              <button
                type="button"
                class="mkt-btn mkt-btn-primary"
                :disabled="!!installing"
                @click="mkt.install(item.id)"
              >
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12M8 11l4 4 4-4M5 21h14"/></svg>
                {{ installing === item.id ? '安装中…' : '安装' }}
              </button>
              <a
                class="mkt-btn mkt-btn-ghost"
                :href="'/api/marketplace/download?id=' + encodeURIComponent(item.id)"
              >下载</a>
              <button type="button" class="mkt-btn mkt-btn-danger" @click="mkt.remove(item.id)">移除</button>
            </div>
          </article>
        </div>
      </div>

      <!-- 右侧筛选 -->
      <aside class="mkt-filter" aria-label="市场筛选">
        <div class="mkt-filter-h">
          <strong>市场筛选</strong>
          <button type="button" class="mkt-filter-clear" :disabled="!hasFilters" @click="clearFilters">清除</button>
        </div>

        <div class="mkt-filter-section">
          <div class="mkt-filter-label">标签</div>
          <div v-if="!tagCounts.length" class="mkt-filter-empty">暂无标签</div>
          <div v-else class="mkt-filter-tags">
            <button
              v-for="{ tag, count } in tagCounts"
              :key="tag"
              type="button"
              class="mkt-filter-tag"
              :class="{ on: activeTags.includes(tag) }"
              :aria-pressed="activeTags.includes(tag)"
              @click="toggleTag(tag)"
            >
              <span class="box" aria-hidden="true">
                <svg viewBox="0 0 24 24"><path d="M5 12l5 5L20 7"/></svg>
              </span>
              {{ tag }}
              <span class="n">{{ count }}</span>
            </button>
          </div>
        </div>

        <div class="mkt-filter-section">
          <div class="mkt-filter-label">作者</div>
          <div v-if="!authorCounts.length" class="mkt-filter-empty">暂无作者</div>
          <div v-else class="mkt-filter-authors">
            <button
              v-for="{ author, count } in authorCounts"
              :key="author"
              type="button"
              class="mkt-filter-author"
              :class="{ on: activeAuthor === author }"
              :aria-pressed="activeAuthor === author"
              @click="toggleAuthor(author)"
            >
              {{ author }}
              <span class="n">{{ count }}</span>
            </button>
          </div>
        </div>

        <div class="mkt-filter-hint">
          可多选标签，与顶部搜索、建议标签联动。没有想要的包？在「插件配置」页分享到市场。
        </div>
      </aside>
    </div>

    <!-- AI 创建插件对话框 -->
    <div v-if="dialogOpen" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40" @click.self="ai.closeDialog()">
      <div class="bg-white rounded-xl shadow-2xl w-[700px] max-w-[90vw] max-h-[85vh] flex flex-col">
        <div class="flex items-center justify-between px-5 py-3 border-b border-gray-100">
          <h3 class="text-sm font-semibold flex items-center gap-2">AI 创建插件</h3>
          <button type="button" class="text-ink-500 hover:text-ink-700 text-lg leading-none cursor-pointer" @click="ai.closeDialog()">&times;</button>
        </div>

        <div class="flex-1 overflow-y-auto p-5 space-y-3">
          <div>
            <label class="text-[11px] text-ink-500 block mb-1">需求描述</label>
            <textarea
              v-model="prompt"
              :disabled="generating"
              rows="3"
              placeholder="例如：一个 Java 后端开发智能体，精通 Spring Boot / MyBatis / MySQL，需要文件系统和搜索能力"
              class="w-full px-3 py-2 text-xs border border-ink-300 rounded-lg focus:outline-none focus:border-brand-500 disabled:bg-ink-100"
            />
          </div>

          <div class="flex items-center gap-2">
            <label class="text-[11px] text-ink-500">工具集级别：</label>
            <div class="flex gap-1">
              <button
                v-for="lv in ['basic', 'standard', 'expert']"
                :key="lv"
                type="button"
                :disabled="generating"
                :class="[
                  'px-2.5 py-1 text-[10px] rounded-md transition border cursor-pointer',
                  level === lv
                    ? 'bg-brand-500 text-white border-brand-500'
                    : 'bg-white text-ink-700 border-ink-300 hover:border-brand-500 disabled:opacity-50',
                ]"
                @click="level === lv ? (level = '') : (level = lv)"
              >
                {{ lv === 'basic' ? '基础' : lv === 'standard' ? '进阶' : '专家' }}
              </button>
              <span class="text-[10px] text-ink-500 ml-1">（不选则自动判断）</span>
            </div>
          </div>

          <div class="flex items-center gap-2">
            <button
              type="button"
              :disabled="generating || !prompt.trim()"
              class="px-4 py-1.5 text-xs font-medium text-white rounded-lg bg-brand-500 hover:bg-brand-600 disabled:opacity-50 cursor-pointer"
              @click="ai.generate()"
            >
              {{ generating ? '生成中…' : '开始生成' }}
            </button>
            <span v-if="generating" class="text-[10px] text-ink-500">LLM 正在生成 plugin.yaml…</span>
          </div>

          <div v-if="output" class="space-y-2">
            <div class="text-[10px] text-ink-500">生成输出：</div>
            <pre class="bg-gray-900 text-green-400 p-3 rounded-lg text-[11px] max-h-[200px] overflow-y-auto whitespace-pre-wrap font-mono">{{ output }}</pre>
          </div>

          <div v-if="generatedConfig" class="space-y-2">
            <div class="text-[10px] text-green-600 font-medium">生成完成，预览 plugin.yaml：</div>
            <pre class="bg-ink-100 border border-ink-200 p-3 rounded-lg text-[11px] max-h-[250px] overflow-y-auto whitespace-pre-wrap font-mono">{{ generatedConfig }}</pre>
          </div>
        </div>

        <div v-if="generatedConfig" class="flex items-center justify-end gap-2 px-5 py-3 border-t border-gray-100">
          <button type="button" class="px-3 py-1.5 text-xs text-ink-700 hover:text-ink-900 cursor-pointer" @click="ai.closeDialog()">取消</button>
          <button
            type="button"
            class="px-4 py-1.5 text-xs font-medium text-white rounded-lg bg-green-500 hover:bg-green-600 cursor-pointer"
            @click="ai.save()"
          >
            保存到插件配置
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mkt-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.mkt-hero {
  text-align: center;
  padding: 8px 4px 4px;
}
.mkt-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: .04em;
  text-transform: uppercase;
  color: var(--color-brand-600, #0e42d2);
  background: var(--color-brand-50, #eef4ff);
  border: 1px solid var(--color-brand-100, #d9e6ff);
  padding: 5px 10px;
  border-radius: 999px;
  margin-bottom: 12px;
}
.mkt-eyebrow svg {
  width: 14px;
  height: 14px;
  stroke: currentColor;
  fill: none;
  stroke-width: 2;
}
.mkt-hero h1 {
  margin: 0 0 8px;
  font-size: clamp(22px, 3.2vw, 30px);
  font-weight: 800;
  letter-spacing: -.03em;
  line-height: 1.2;
  color: var(--color-ink-900, #1f2329);
}
.mkt-hero > p {
  margin: 0 auto 18px;
  max-width: 460px;
  color: var(--color-ink-700, #4e5969);
  font-size: 13px;
  line-height: 1.55;
}

.mkt-search {
  position: relative;
  max-width: 640px;
  margin: 0 auto;
}
.mkt-search input {
  width: 100%;
  height: 48px;
  padding: 0 108px 0 44px;
  border: 1.5px solid var(--color-ink-300, #c9cdd4);
  border-radius: 14px;
  background: #fff;
  font-size: 14px;
  font-weight: 500;
  color: var(--color-ink-900, #1f2329);
  box-shadow: var(--shadow-card, 0 1px 2px rgba(0,0,0,.04), 0 4px 12px rgba(0,0,0,.06));
  transition: border-color .2s ease, box-shadow .2s ease;
}
.mkt-search input::placeholder {
  color: var(--color-ink-500, #86909c);
  font-weight: 400;
}
.mkt-search input:focus {
  outline: none;
  border-color: var(--color-brand-500, #165dff);
  box-shadow: 0 0 0 3px rgba(22, 93, 255, .15), var(--shadow-card, 0 1px 2px rgba(0,0,0,.04), 0 4px 12px rgba(0,0,0,.06));
}
.mkt-search-icon {
  position: absolute;
  left: 14px;
  top: 50%;
  transform: translateY(-50%);
  width: 18px;
  height: 18px;
  color: var(--color-ink-500, #86909c);
  pointer-events: none;
}
.mkt-search-icon svg {
  width: 100%;
  height: 100%;
  stroke: currentColor;
  fill: none;
  stroke-width: 2;
}
.mkt-search-go {
  position: absolute;
  right: 7px;
  top: 50%;
  transform: translateY(-50%);
  height: 34px;
  padding: 0 14px;
  border: 0;
  border-radius: 10px;
  background: var(--color-brand-500, #165dff);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background .2s ease;
}
.mkt-search-go:hover:not(:disabled) { background: var(--color-brand-600, #0e42d2); }
.mkt-search-go:disabled { opacity: .55; cursor: not-allowed; }

.mkt-suggests {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
  margin-top: 12px;
}
.mkt-suggests > span {
  font-size: 12px;
  color: var(--color-ink-500, #86909c);
  align-self: center;
}
.mkt-chip {
  border: 1px solid var(--color-ink-200, #e5e6eb);
  background: #fff;
  color: var(--color-ink-700, #4e5969);
  font-size: 12px;
  font-weight: 500;
  padding: 6px 11px;
  border-radius: 999px;
  cursor: pointer;
  transition: border-color .2s, color .2s, background .2s;
}
.mkt-chip:hover,
.mkt-chip.on {
  border-color: var(--color-brand-500, #165dff);
  color: var(--color-brand-600, #0e42d2);
  background: var(--color-brand-50, #eef4ff);
}

.mkt-hero-actions {
  display: flex;
  justify-content: center;
  gap: 8px;
  margin-top: 14px;
  flex-wrap: wrap;
}

.mkt-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}
.mkt-stat {
  background: #fff;
  border: 1px solid var(--color-ink-200, #e5e6eb);
  border-radius: 12px;
  padding: 12px 14px;
  box-shadow: var(--shadow-card, 0 1px 2px rgba(0,0,0,.04), 0 4px 12px rgba(0,0,0,.06));
}
.mkt-stat b {
  display: block;
  font-size: 20px;
  font-weight: 800;
  letter-spacing: -.02em;
  color: var(--color-brand-600, #0e42d2);
}
.mkt-stat span {
  font-size: 12px;
  color: var(--color-ink-500, #86909c);
}

.mkt-workspace {
  display: grid;
  grid-template-columns: 1fr 240px;
  gap: 14px;
  align-items: start;
}
.mkt-main { min-width: 0; }

.mkt-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.mkt-toolbar h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--color-ink-900, #1f2329);
}
.mkt-toolbar h2 em {
  font-style: normal;
  color: var(--color-ink-500, #86909c);
  font-weight: 500;
  margin-left: 6px;
}
.mkt-toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.mkt-sort,
.mkt-view-toggle {
  display: flex;
  gap: 3px;
  background: #fff;
  border: 1px solid var(--color-ink-200, #e5e6eb);
  border-radius: 10px;
  padding: 3px;
}
.mkt-sort button {
  border: 0;
  background: transparent;
  color: var(--color-ink-500, #86909c);
  font-size: 12px;
  font-weight: 500;
  padding: 7px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background .15s, color .15s;
}
.mkt-sort button.on {
  background: var(--color-brand-50, #eef4ff);
  color: var(--color-brand-600, #0e42d2);
}
.mkt-view-toggle button {
  border: 0;
  background: transparent;
  width: 32px;
  height: 28px;
  border-radius: 8px;
  color: var(--color-ink-500, #86909c);
  display: grid;
  place-items: center;
  cursor: pointer;
  transition: background .15s, color .15s;
}
.mkt-view-toggle button svg {
  width: 15px;
  height: 15px;
  stroke: currentColor;
  fill: none;
  stroke-width: 1.8;
}
.mkt-view-toggle button.on {
  background: var(--color-brand-50, #eef4ff);
  color: var(--color-brand-600, #0e42d2);
}

.mkt-filter {
  position: sticky;
  top: 12px;
  background: #fff;
  border: 1px solid var(--color-ink-200, #e5e6eb);
  border-radius: 14px;
  padding: 14px 12px 16px;
  box-shadow: var(--shadow-card, 0 1px 2px rgba(0,0,0,.04), 0 4px 12px rgba(0,0,0,.06));
}
.mkt-filter-h {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 0 4px 12px;
  border-bottom: 1px solid var(--color-ink-200, #e5e6eb);
  margin-bottom: 12px;
}
.mkt-filter-h strong {
  font-size: 13px;
  font-weight: 700;
}
.mkt-filter-clear {
  border: 0;
  background: transparent;
  color: var(--color-brand-600, #0e42d2);
  font-size: 11px;
  font-weight: 600;
  padding: 4px;
  cursor: pointer;
}
.mkt-filter-clear:hover:not(:disabled) { text-decoration: underline; }
.mkt-filter-clear:disabled {
  color: var(--color-ink-300, #c9cdd4);
  cursor: not-allowed;
  text-decoration: none;
}
.mkt-filter-section + .mkt-filter-section { margin-top: 14px; }
.mkt-filter-label {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: var(--color-ink-500, #86909c);
  padding: 0 4px;
  margin: 0 0 8px;
}
.mkt-filter-empty {
  font-size: 12px;
  color: var(--color-ink-500, #86909c);
  padding: 4px 8px;
}
.mkt-filter-tags,
.mkt-filter-authors {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.mkt-filter-tag {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  border: 0;
  background: transparent;
  text-align: left;
  padding: 8px;
  border-radius: 8px;
  font-size: 12.5px;
  font-weight: 500;
  color: var(--color-ink-700, #4e5969);
  cursor: pointer;
  transition: background .15s, color .15s;
}
.mkt-filter-tag:hover { background: var(--color-ink-100, #f7f8fa); }
.mkt-filter-tag.on {
  background: var(--color-brand-50, #eef4ff);
  color: var(--color-brand-700, #0a2e9c);
}
.mkt-filter-tag .box {
  width: 14px;
  height: 14px;
  border: 1.5px solid var(--color-ink-300, #c9cdd4);
  border-radius: 3px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.mkt-filter-tag.on .box {
  background: var(--color-brand-500, #165dff);
  border-color: var(--color-brand-500, #165dff);
}
.mkt-filter-tag .box svg {
  width: 10px;
  height: 10px;
  stroke: #fff;
  fill: none;
  stroke-width: 3;
  opacity: 0;
}
.mkt-filter-tag.on .box svg { opacity: 1; }
.mkt-filter-tag .n,
.mkt-filter-author .n {
  margin-left: auto;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-ink-500, #86909c);
}
.mkt-filter-tag.on .n { color: var(--color-brand-600, #0e42d2); }
.mkt-filter-author {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  border: 1px solid transparent;
  background: transparent;
  text-align: left;
  padding: 8px;
  border-radius: 8px;
  font-size: 12.5px;
  font-weight: 500;
  color: var(--color-ink-700, #4e5969);
  cursor: pointer;
  transition: background .15s, border-color .15s, color .15s;
}
.mkt-filter-author:hover { background: var(--color-ink-100, #f7f8fa); }
.mkt-filter-author.on {
  background: var(--color-brand-50, #eef4ff);
  border-color: var(--color-brand-100, #d9e6ff);
  color: var(--color-brand-700, #0a2e9c);
}
.mkt-filter-hint {
  margin-top: 14px;
  padding: 10px;
  background: var(--color-ink-100, #f7f8fa);
  border-radius: 8px;
  font-size: 11.5px;
  line-height: 1.45;
  color: var(--color-ink-700, #4e5969);
}

.mkt-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}
.mkt-grid.view-list {
  grid-template-columns: 1fr;
  gap: 8px;
}

.mkt-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: #fff;
  border: 1px solid var(--color-ink-200, #e5e6eb);
  border-radius: 14px;
  padding: 16px;
  box-shadow: var(--shadow-card, 0 1px 2px rgba(0,0,0,.04), 0 4px 12px rgba(0,0,0,.06));
  transition: border-color .2s ease, transform .2s ease, box-shadow .2s ease;
}
.mkt-card:hover {
  border-color: var(--color-brand-100, #d9e6ff);
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(22, 93, 255, .08);
}
.mkt-grid.view-list .mkt-card {
  flex-direction: row;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px 16px;
  padding: 12px 14px;
}
.mkt-grid.view-list .mkt-card:hover { transform: none; }
.mkt-grid.view-list .mkt-card-top {
  flex: 1;
  min-width: 200px;
}
.mkt-grid.view-list .mkt-desc {
  -webkit-line-clamp: 1;
}
.mkt-grid.view-list .mkt-actions {
  margin-top: 0;
  padding-top: 0;
  margin-left: auto;
}
.mkt-grid.view-list .mkt-btn-danger { margin-left: 0; }

.mkt-card-top {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}
.mkt-avatar {
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  border-radius: 11px;
  background: linear-gradient(145deg, var(--color-brand-100, #d9e6ff), var(--color-brand-50, #eef4ff));
  color: var(--color-brand-600, #0e42d2);
  display: grid;
  place-items: center;
  font-weight: 800;
  font-size: 14px;
}
.mkt-card h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  letter-spacing: -.01em;
  color: var(--color-ink-900, #1f2329);
}
.mkt-ver {
  font-size: 11px;
  color: var(--color-ink-500, #86909c);
  font-weight: 500;
  margin-left: 6px;
}
.mkt-desc {
  margin: 4px 0 0;
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--color-ink-700, #4e5969);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.mkt-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.mkt-tag {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-brand-600, #0e42d2);
  background: var(--color-brand-50, #eef4ff);
  padding: 3px 8px;
  border-radius: 6px;
}
.mkt-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  font-size: 11px;
  color: var(--color-ink-500, #86909c);
}
.mkt-meta span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.mkt-meta svg {
  width: 12px;
  height: 12px;
  stroke: currentColor;
  fill: none;
  stroke-width: 2;
}

.mkt-actions {
  display: flex;
  gap: 8px;
  margin-top: auto;
  padding-top: 4px;
  align-items: center;
}

.mkt-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 32px;
  padding: 0 12px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  border: 1px solid transparent;
  cursor: pointer;
  text-decoration: none;
  transition: background .15s, border-color .15s, color .15s, opacity .15s;
}
.mkt-btn svg {
  width: 14px;
  height: 14px;
  stroke: currentColor;
  fill: none;
  stroke-width: 2;
}
.mkt-btn-primary {
  background: var(--color-brand-500, #165dff);
  color: #fff;
}
.mkt-btn-primary:hover:not(:disabled) { background: var(--color-brand-600, #0e42d2); }
.mkt-btn-primary:disabled { opacity: .55; cursor: not-allowed; }
.mkt-btn-ghost {
  background: #fff;
  border-color: var(--color-ink-300, #c9cdd4);
  color: var(--color-ink-700, #4e5969);
}
.mkt-btn-ghost:hover:not(:disabled) {
  border-color: var(--color-brand-500, #165dff);
  color: var(--color-brand-600, #0e42d2);
}
.mkt-btn-ghost:disabled { opacity: .55; cursor: not-allowed; }
.mkt-btn-danger {
  margin-left: auto;
  background: transparent;
  color: var(--color-ink-500, #86909c);
  border: 0;
  padding: 0 6px;
}
.mkt-btn-danger:hover { color: #f53f3f; }

.mkt-empty {
  text-align: center;
  padding: 48px 20px;
  background: #fff;
  border: 1px dashed var(--color-ink-300, #c9cdd4);
  border-radius: 14px;
}
.mkt-empty svg {
  width: 40px;
  height: 40px;
  stroke: var(--color-brand-500, #165dff);
  fill: none;
  stroke-width: 1.6;
  margin-bottom: 12px;
}
.mkt-empty h3 {
  margin: 0 0 6px;
  font-size: 15px;
  color: var(--color-ink-900, #1f2329);
}
.mkt-empty p {
  margin: 0 0 16px;
  font-size: 13px;
  color: var(--color-ink-500, #86909c);
}
.mkt-spinner {
  width: 28px;
  height: 28px;
  margin: 0 auto 12px;
  border: 2.5px solid var(--color-brand-100, #d9e6ff);
  border-top-color: var(--color-brand-500, #165dff);
  border-radius: 50%;
  animation: mkt-spin .7s linear infinite;
}
@keyframes mkt-spin { to { transform: rotate(360deg); } }

@media (max-width: 1000px) {
  .mkt-workspace { grid-template-columns: 1fr; }
  .mkt-filter { position: static; }
}
@media (max-width: 640px) {
  .mkt-stats { grid-template-columns: 1fr; }
  .mkt-grid:not(.view-list) { grid-template-columns: 1fr; }
  .mkt-search input { padding-right: 88px; height: 44px; font-size: 13px; }
  .mkt-grid.view-list .mkt-card {
    flex-direction: column;
    align-items: stretch;
  }
  .mkt-grid.view-list .mkt-actions { margin-left: 0; }
}
@media (prefers-reduced-motion: reduce) {
  .mkt-card,
  .mkt-chip,
  .mkt-btn,
  .mkt-search input { transition: none; }
  .mkt-spinner { animation: none; }
}
</style>
