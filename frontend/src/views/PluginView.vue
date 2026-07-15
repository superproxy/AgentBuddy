<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import { usePluginStore } from '../stores/plugin'
import { useUiStore } from '../stores/ui'

const emit = defineEmits<{ 'go-tab': [key: string] }>()

const plugin = usePluginStore()
const ui = useUiStore()
const { plugins, installingPlugin, selectedForExport } = storeToRefs(plugin)
const {
  refreshPluginList, exportPlugin, onImportPluginFile, importPluginFile,
  onTogglePlugin, editPlugin, toggleSelectForExport, selectFilesForExport,
  clearExportSelection, exportSelectedPlugins, publishToMarketplace,
} = plugin

const inputRef = ref<HTMLInputElement | null>(null)
const listQuery = ref('')
const listFilter = ref<'all' | 'on' | 'off'>('all')
const exportMenu = ref<string | null>(null)
const dropDragging = ref(false)

const installedCount = computed(() => plugins.value.filter((p) => p.installed).length)
const skillsTotal = computed(() => plugins.value.reduce((a, p) => a + (p.skills_count || 0), 0))
const installedRatio = computed(() =>
  plugins.value.length ? Math.round((installedCount.value / plugins.value.length) * 100) : 0,
)
const skillsBarRatio = computed(() => {
  if (!skillsTotal.value) return 0
  const max = Math.max(...plugins.value.map((p) => p.skills_count || 0), 1)
  return Math.min(100, Math.round((skillsTotal.value / (max * Math.max(plugins.value.length, 1))) * 100) || 36)
})

const filteredPlugins = computed(() => {
  const q = listQuery.value.trim().toLowerCase()
  return plugins.value.filter((p) => {
    if (listFilter.value === 'on' && !p.installed) return false
    if (listFilter.value === 'off' && p.installed) return false
    if (!q) return true
    return p.name.toLowerCase().includes(q) || (p.description || '').toLowerCase().includes(q)
  })
})

function initials(name: string) {
  const parts = name.trim().split(/[\s\-_]+/).filter(Boolean)
  if (!parts.length) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[1][0]).toUpperCase()
}

function triggerImport() { inputRef.value?.click() }

function selectVisible() {
  selectFilesForExport(filteredPlugins.value.map((p) => p.file))
}

function goBuild() {
  emit('go-tab', 'plugin-build')
}

function onEdit(file: string) {
  editPlugin(file)
  emit('go-tab', 'plugin-build')
}

function toggleExportMenu(file: string) {
  exportMenu.value = exportMenu.value === file ? null : file
}

function doExport(file: string, format: 'zip' | 'yaml') {
  exportPlugin(file, format)
  exportMenu.value = null
}

function onDocClick(e: MouseEvent) {
  const t = e.target as HTMLElement
  if (!t.closest('.export-menu')) exportMenu.value = null
}

async function onDrop(e: DragEvent) {
  e.preventDefault()
  dropDragging.value = false
  const f = e.dataTransfer?.files?.[0]
  if (!f) return
  const ok = /\.(ya?ml|zip)$/i.test(f.name)
  if (!ok) {
    ui.toast('仅支持 .zip / .yaml / .yml', 'warn')
    return
  }
  await importPluginFile(f)
}

onMounted(() => {
  refreshPluginList()
  document.addEventListener('click', onDocClick)
})
onUnmounted(() => document.removeEventListener('click', onDocClick))
</script>

<template>
  <div class="plugin-page">
    <div class="plugin-head flex flex-wrap items-start justify-between gap-4">
      <div class="min-w-0">
        <h1 class="text-[15px] font-semibold text-ink-900 m-0">插件配置</h1>
        <p class="text-xs text-ink-500 mt-1 mb-0">以卡片浏览本地智能体插件 · 安装、导入导出与分享到市场</p>
      </div>
      <div class="btn-cluster">
        <button type="button" class="btn btn-secondary" @click="refreshPluginList">
          <svg viewBox="0 0 24 24"><path d="M21 12a9 9 0 1 1-2.6-6.3"/><path d="M21 3v6h-6"/></svg>
          刷新
        </button>
        <button type="button" class="btn btn-primary" @click="goBuild">
          <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>
          构建插件
        </button>
      </div>
    </div>

    <div class="hero-stats">
      <div class="stat-hero">
        <div class="label">插件库</div>
        <div class="num">{{ plugins.length }}</div>
        <div class="hint">
          本地可用 · 导入或构建后出现在这里
          <span v-if="installingPlugin" class="installing"> · 安装中 {{ installingPlugin }}</span>
        </div>
      </div>
      <div class="stat">
        <b>{{ installedCount }}</b>
        <span>已安装</span>
        <div class="bar"><i :style="{ width: installedRatio + '%' }" /></div>
      </div>
      <div class="stat">
        <b>{{ skillsTotal }}</b>
        <span>Skills 合计</span>
        <div class="bar"><i class="skills" :style="{ width: Math.max(skillsBarRatio, skillsTotal ? 28 : 0) + '%' }" /></div>
      </div>
    </div>

    <div class="toolbar">
      <div class="toolbar-left">
        <label class="search">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#86909c" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3-3"/></svg>
          <input v-model="listQuery" type="search" placeholder="搜索插件…" />
        </label>
        <div class="seg" role="group" aria-label="安装状态">
          <button type="button" :class="{ on: listFilter === 'all' }" @click="listFilter = 'all'">全部</button>
          <button type="button" :class="{ on: listFilter === 'on' }" @click="listFilter = 'on'">已安装</button>
          <button type="button" :class="{ on: listFilter === 'off' }" @click="listFilter = 'off'">未安装</button>
        </div>
      </div>
      <div class="btn-cluster">
        <button type="button" class="btn btn-ghost btn-sm" @click="selectVisible">全选可见</button>
        <button type="button" class="btn btn-soft btn-sm" @click="triggerImport">
          <svg viewBox="0 0 24 24"><path d="M12 3v12"/><path d="m8 11 4 4 4-4"/><path d="M4 19h16"/></svg>
          导入插件
        </button>
        <input ref="inputRef" type="file" accept=".yaml,.yml,.zip" class="hidden" @change="onImportPluginFile">
      </div>
    </div>

    <div class="grid">
      <article
        v-for="p in filteredPlugins"
        :key="p.file"
        class="card"
        :class="{ installed: p.installed, selected: selectedForExport.has(p.file) }"
      >
        <div class="card-top">
          <div class="avatar" aria-hidden="true">{{ initials(p.name) }}</div>
          <input
            type="checkbox"
            class="pick"
            :checked="selectedForExport.has(p.file)"
            :aria-label="'选择 ' + p.name"
            @change="toggleSelectForExport(p.file)"
          >
        </div>
        <div>
          <h2 class="title">
            {{ p.name }}
            <span class="ver">v{{ p.version }}</span>
          </h2>
          <p class="desc" :title="p.description">{{ p.description || '暂无描述' }}</p>
        </div>
        <div class="meta">
          <span class="chip" :class="p.installed ? 'ok' : 'idle'">{{ p.installed ? '已安装' : '未安装' }}</span>
          <span class="chip brand">{{ p.skills_count }} skills</span>
          <span class="chip">{{ p.mcp_count }} mcp</span>
        </div>
        <div class="card-foot">
          <button
            v-if="!p.installed"
            type="button"
            class="btn btn-primary btn-sm"
            :disabled="!!installingPlugin"
            @click="onTogglePlugin(p, true)"
          >
            {{ installingPlugin === p.name || installingPlugin === p.file ? '安装中…' : '安装' }}
          </button>
          <button
            v-else
            type="button"
            class="btn btn-secondary btn-sm"
            :disabled="!!installingPlugin"
            @click="onTogglePlugin(p, false)"
          >
            卸载
          </button>
          <div class="card-ops">
            <button type="button" class="btn btn-ghost btn-sm" @click="onEdit(p.file)">编辑</button>
            <div class="export-menu relative">
              <button type="button" class="btn btn-ghost btn-sm" @click.stop="toggleExportMenu(p.file)">导出</button>
              <div v-if="exportMenu === p.file" class="menu-panel" @click.stop>
                <button type="button" @click="doExport(p.file, 'zip')">ZIP（含 Skills）</button>
                <button type="button" @click="doExport(p.file, 'yaml')">YAML（仅配置）</button>
              </div>
            </div>
            <button type="button" class="btn btn-ghost btn-sm" title="发布到本地市场" @click="publishToMarketplace(p.file)">分享</button>
          </div>
        </div>
      </article>

      <div
        class="dropzone"
        :class="{ drag: dropDragging }"
        role="button"
        tabindex="0"
        aria-label="导入插件"
        @click="triggerImport"
        @keydown.enter.prevent="triggerImport"
        @dragover.prevent="dropDragging = true"
        @dragleave.prevent="dropDragging = false"
        @drop="onDrop"
      >
        <svg viewBox="0 0 24 24"><path d="M12 3v12"/><path d="m8 11 4 4 4-4"/><path d="M4 19h16"/></svg>
        <strong>拖入或点击导入</strong>
        <span>支持 .zip（含 Skills）或 .yaml</span>
      </div>

      <div v-if="!plugins.length" class="empty-hint">
        暂无可用插件。点击「构建插件」或拖入文件开始。
      </div>
      <div v-else-if="!filteredPlugins.length" class="empty-hint">
        无匹配结果，试试清空筛选。
      </div>
    </div>

    <Teleport to="body">
      <div class="float-bar" :class="{ show: selectedForExport.size > 0 }">
        <span>已选 {{ selectedForExport.size }} 个插件</span>
        <button type="button" class="btn btn-ghost btn-sm" @click="clearExportSelection">取消</button>
        <button type="button" class="btn btn-primary btn-sm" @click="exportSelectedPlugins">导出 ZIP</button>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.plugin-page {
  --green: #00b42a;
  --green-bg: #e8ffea;
  --amber: #ff7d00;
  --amber-bg: #fff7e8;
  --red: #f53f3f;
  --red-bg: #ffece8;
  --red-border: #f9c2c0;
  --glow: 0 0 0 3px rgba(22, 93, 255, 0.15);
  --card: 0 1px 2px rgba(0, 0, 0, 0.04), 0 4px 12px rgba(0, 0, 0, 0.06);
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-bottom: 56px;
}

.plugin-head { margin: 0; }

.btn {
  height: 34px; padding: 0 12px; border-radius: 8px; font-size: 12px; font-weight: 600;
  display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  white-space: nowrap; border: 1px solid transparent; cursor: pointer;
  transition: background .18s ease, color .18s ease, border-color .18s ease;
  background: none; color: inherit; user-select: none;
}
.btn svg { width: 14px; height: 14px; flex-shrink: 0; stroke: currentColor; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.btn:disabled { opacity: .45; cursor: not-allowed; }
.btn-sm { height: 30px; padding: 0 10px; font-size: 11px; border-radius: 7px; }
.btn-sm svg { width: 13px; height: 13px; }
.btn-primary { background: #165dff; color: #fff; box-shadow: 0 1px 2px rgba(22, 93, 255, .22); }
.btn-primary:hover:not(:disabled) { background: #0e42d2; }
.btn-soft { background: #eef4ff; color: #0e42d2; border-color: #d9e6ff; }
.btn-soft:hover:not(:disabled) { background: #d9e6ff; }
.btn-secondary { background: #fff; color: #4e5969; border-color: #e5e6eb; }
.btn-secondary:hover:not(:disabled) { background: #f7f8fa; border-color: #c9cdd4; }
.btn-ghost { background: transparent; color: #4e5969; }
.btn-ghost:hover:not(:disabled) { background: #f7f8fa; color: #1f2329; }
.btn:focus-visible { outline: none; box-shadow: var(--glow); }

.btn-cluster { display: inline-flex; align-items: center; gap: 8px; flex-wrap: wrap; }

.hero-stats {
  display: grid;
  grid-template-columns: 1.4fr 1fr 1fr;
  gap: 12px;
}
.stat-hero, .stat {
  background: #fff;
  border-radius: 16px;
  box-shadow: var(--card);
  border: 1px solid rgba(0, 0, 0, .03);
}
.stat-hero {
  padding: 20px 22px;
  position: relative;
  overflow: hidden;
  background: linear-gradient(135deg, #165dff 0%, #0e42d2 55%, #0a2e9c 100%);
  color: #fff;
}
.stat-hero::after {
  content: "";
  position: absolute;
  right: -40px; top: -40px;
  width: 160px; height: 160px;
  border-radius: 50%;
  background: rgba(255, 255, 255, .08);
}
.stat-hero .label { font-size: 12px; opacity: .85; margin-bottom: 8px; position: relative; }
.stat-hero .num {
  font-size: 36px; font-weight: 750; letter-spacing: -.04em; line-height: 1;
  font-variant-numeric: tabular-nums; position: relative;
}
.stat-hero .hint { margin-top: 10px; font-size: 12px; opacity: .8; position: relative; }
.stat-hero .installing { opacity: 1; font-weight: 600; }
.stat { padding: 18px 20px; }
.stat b { display: block; font-size: 24px; font-variant-numeric: tabular-nums; color: #1f2329; }
.stat span { font-size: 12px; color: #86909c; }
.stat .bar {
  margin-top: 12px; height: 6px; border-radius: 999px; background: #f7f8fa; overflow: hidden;
}
.stat .bar i {
  display: block; height: 100%; border-radius: inherit; background: #165dff;
  transition: width .25s ease;
}
.stat .bar i.skills { background: #00b42a; }

.toolbar {
  display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; align-items: center;
  padding: 12px 14px; background: #fff;
  border: 1px solid rgba(0, 0, 0, .04); border-radius: 14px; box-shadow: var(--card);
}
.toolbar-left { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
.search {
  display: flex; align-items: center; gap: 8px; height: 34px; padding: 0 10px;
  border: 1px solid #c9cdd4; border-radius: 8px; background: #fff; min-width: 220px;
}
.search:focus-within { border-color: #165dff; box-shadow: var(--glow); }
.search input { border: none; outline: none; flex: 1; font-size: 12px; min-width: 0; background: transparent; }
.seg { display: inline-flex; background: #f7f8fa; padding: 3px; border-radius: 8px; }
.seg button {
  height: 28px; padding: 0 10px; border-radius: 6px; font-size: 12px; font-weight: 600;
  color: #86909c; border: none; background: transparent; cursor: pointer;
}
.seg button.on { background: #fff; color: #0e42d2; box-shadow: 0 1px 2px rgba(0, 0, 0, .06); }

.grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  position: relative;
}
.card {
  background: #fff; border-radius: 16px; box-shadow: var(--card);
  border: 1px solid rgba(0, 0, 0, .03);
  padding: 16px; display: flex; flex-direction: column; gap: 12px;
  transition: border-color .18s ease, box-shadow .18s ease;
}
.card:hover { border-color: #d9e6ff; box-shadow: 0 4px 16px rgba(22, 93, 255, .08); }
.card.selected { border-color: #165dff; box-shadow: var(--glow); }
.card-top { display: flex; justify-content: space-between; gap: 10px; align-items: flex-start; }
.avatar {
  width: 40px; height: 40px; border-radius: 12px; display: grid; place-items: center;
  background: #eef4ff; color: #0e42d2; font-weight: 750; font-size: 14px;
  border: 1px solid #d9e6ff; flex-shrink: 0;
}
.card.installed .avatar { background: var(--green-bg); color: var(--green); border-color: #b7f0c0; }
.pick { width: 18px; height: 18px; accent-color: #165dff; cursor: pointer; margin-top: 2px; }
.title { font-size: 14px; font-weight: 700; letter-spacing: -.01em; margin: 0; color: #1f2329; }
.ver {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 11px; color: #86909c; margin-left: 6px; font-weight: 500;
}
.desc {
  margin: 6px 0 0; font-size: 12.5px; color: #86909c; line-height: 1.45;
  display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; min-height: 2.9em;
}
.meta { display: flex; flex-wrap: wrap; gap: 6px; }
.chip {
  font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 999px;
  background: #f7f8fa; color: #4e5969;
}
.chip.ok { background: var(--green-bg); color: var(--green); }
.chip.idle { background: var(--amber-bg); color: var(--amber); }
.chip.brand { background: #eef4ff; color: #0e42d2; }
.card-foot {
  margin-top: auto; display: flex; justify-content: space-between; align-items: center; gap: 8px;
  padding-top: 12px; border-top: 1px solid #f7f8fa; flex-wrap: wrap;
}
.card-ops { display: flex; gap: 2px; flex-wrap: wrap; align-items: center; }

.menu-panel {
  position: absolute; right: 0; top: calc(100% + 4px); min-width: 148px;
  background: #fff; border: 1px solid #e5e6eb; border-radius: 10px; box-shadow: var(--card);
  z-index: 20; overflow: hidden;
}
.menu-panel button {
  display: block; width: 100%; text-align: left; padding: 9px 12px; border: none; background: none;
  font-size: 12px; color: #4e5969; cursor: pointer;
}
.menu-panel button:hover { background: #eef4ff; color: #0e42d2; }

.dropzone {
  border: 1.5px dashed #c9cdd4; border-radius: 16px; padding: 22px 16px;
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px;
  color: #86909c; text-align: center; cursor: pointer; background: #fafbfd;
  transition: .18s ease; min-height: 180px;
}
.dropzone:hover, .dropzone.drag {
  border-color: #165dff; background: #eef4ff; color: #0e42d2;
}
.dropzone:focus-visible { outline: none; box-shadow: var(--glow); border-color: #165dff; }
.dropzone svg { width: 28px; height: 28px; stroke: currentColor; fill: none; stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }
.dropzone strong { font-size: 13px; color: inherit; }
.dropzone span { font-size: 11.5px; }

.empty-hint {
  grid-column: 1 / -1;
  text-align: center; color: #86909c; font-size: 12.5px; padding: 8px 0 4px;
}

.float-bar {
  position: fixed; left: 50%; bottom: 22px; transform: translateX(-50%) translateY(20px);
  background: #1f2329; color: #fff; border-radius: 14px; padding: 10px 12px 10px 16px;
  display: flex; align-items: center; gap: 12px; box-shadow: 0 10px 30px rgba(0, 0, 0, .22);
  opacity: 0; pointer-events: none; transition: .2s ease; z-index: 40; max-width: calc(100vw - 32px);
}
.float-bar.show { opacity: 1; transform: translateX(-50%) translateY(0); pointer-events: auto; }
.float-bar span { font-size: 12.5px; white-space: nowrap; }
.float-bar .btn { height: 30px; color: #fff; border-color: rgba(255, 255, 255, .2); }
.float-bar .btn-primary { background: #165dff; border-color: transparent; }
.float-bar .btn-ghost:hover:not(:disabled) { background: rgba(255, 255, 255, .1); color: #fff; }

@media (max-width: 960px) {
  .hero-stats { grid-template-columns: 1fr 1fr; }
  .stat-hero { grid-column: 1 / -1; }
  .grid { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 620px) {
  .grid { grid-template-columns: 1fr; }
  .hero-stats { grid-template-columns: 1fr; }
}
@media (prefers-reduced-motion: reduce) {
  .btn, .card, .dropzone, .float-bar, .stat .bar i { transition: none !important; }
}
</style>
