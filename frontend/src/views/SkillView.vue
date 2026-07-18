<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import {
  useSkillStore,
  SKILL_SOURCE_ORDER,
  SKILL_SOURCE_LABELS,
  type SkillSourceId,
} from '../stores/skill'
import { useUiStore } from '../stores/ui'

const skill = useSkillStore()
const ui = useUiStore()
const {
  skillTab, skillMarketSources, skillSearchQ, skillSearchResults, skillSearched, skillSearching,
  skillSearchMeta, manualSkillInput, manualPreview, manualSelected, manualPreviewing, manualInstalling,
  installedSkills, enabledInstalledCount, disabledInstalledCount,
  filteredInstalled, filteredLocalSkills, localSkills, localFilterQ, listFilter, listQuery,
} = storeToRefs(skill)
const {
  searchSkills, toggleSkillSource, installFromSearch,
  loadLocalSkills, loadInstalledSkills, viewSkillMd, uninstallSkill, syncToIde,
  onToggleSkill, toggleAllInstalled,
  previewManualSource, clearManualPreview, toggleManualSkill, selectAllManualSkills, installSelectedManualSkills,
} = skill

const drawerOpen = ref(false)
const marketInput = ref<HTMLInputElement | null>(null)
const localFilterInput = ref<HTMLInputElement | null>(null)
const manualInput = ref<HTMLInputElement | null>(null)
const previewItem = ref<any>(null)
const filterPanelOpen = ref(false)
/** 高级筛选：多选来源（空 = 全部） */
const filterSources = ref<SkillSourceId[]>([])
/** 结果内二次关键词 */
const filterQuery = ref('')
type SkillSortBy = 'name' | 'heat'
type SkillSortDir = 'asc' | 'desc'
const sortBy = ref<SkillSortBy>('heat')
const sortDir = ref<SkillSortDir>('desc')

const SUGGESTS = ['react', '设计', 'API', 'testing', 'docx']

const drawerSub = computed(() => {
  if (skillTab.value === 'market') return '选中技能后，右侧预览可直接安装'
  if (skillTab.value === 'local') return '本地预置（template + config + .agents 三源合并）'
  return '先解析仓库技能，再勾选安装'
})

const manualSelectedCount = computed(() => manualSelected.value.length)
const manualCanInstall = computed(() => !!manualPreview.value && manualSelectedCount.value > 0)

watch(() => manualSkillInput.value, () => {
  if (manualPreview.value) clearManualPreview()
})

const sourceMetaItems = computed(() => {
  const sources = skillSearchMeta.value?.sources || {}
  return SKILL_SOURCE_ORDER
    .filter((src) => skillMarketSources.value.includes(src) || sources[src])
    .map((src) => {
      const info = sources[src] || {}
      return {
        id: src,
        label: info.label || SKILL_SOURCE_LABELS[src],
        count: info.count ?? 0,
        error: info.error || '',
      }
    })
    // 不展示失败源；无结果的源也不占位
    .filter((m) => !m.error && m.count > 0)
})

const filterActive = computed(() => {
  return filterSources.value.length > 0 || !!filterQuery.value.trim()
})

function skillHeat(s: any): number {
  const n = Number(s?.install_count)
  return Number.isFinite(n) ? n : -1
}

function skillNameKey(s: any): string {
  return String(s?.name || s?.skill_name || '').trim()
}

function compareSkills(a: any, b: any): number {
  let cmp = 0
  if (sortBy.value === 'heat') {
    cmp = skillHeat(a) - skillHeat(b)
  }
  if (cmp === 0) {
    cmp = skillNameKey(a).localeCompare(skillNameKey(b), undefined, {
      sensitivity: 'base',
      numeric: true,
    })
  }
  if (cmp === 0) {
    cmp = skillItemKey(a).localeCompare(skillItemKey(b))
  }
  // 比较器绝不能返回 NaN，否则浏览器排序会乱序
  if (!Number.isFinite(cmp)) cmp = 0
  return sortDir.value === 'asc' ? cmp : -cmp
}

const displayedSkillResults = computed(() => {
  let list = (skillSearchResults.value || []).slice()
  if (filterSources.value.length) {
    const set = new Set(filterSources.value.map(String))
    list = list.filter((s) => set.has(String(s.source || '')))
  }
  const q = filterQuery.value.trim().toLowerCase()
  if (q) {
    list = list.filter((s) => {
      const blob = [s.name, s.author, s.description, s.install_command, s.source_label, s.source]
        .map((x) => String(x || '').toLowerCase())
        .join(' ')
      return blob.includes(q)
    })
  }
  // 依赖 sortBy / sortDir，确保切换升序降序必重算
  void sortBy.value
  void sortDir.value
  list.sort(compareSkills)
  return list
})

const displayedSkillCount = computed(() => displayedSkillResults.value.length)

function isSourceOn(src: SkillSourceId) {
  return skillMarketSources.value.includes(src)
}

function isFilterSourceOn(src: SkillSourceId) {
  return filterSources.value.includes(src)
}

function toggleFilterSource(src: SkillSourceId) {
  if (filterSources.value.includes(src)) {
    filterSources.value = filterSources.value.filter((s) => s !== src)
  } else {
    filterSources.value = [...filterSources.value, src]
  }
}

function resetAdvancedFilter() {
  filterSources.value = []
  filterQuery.value = ''
  sortBy.value = 'heat'
  sortDir.value = 'desc'
}

function setSortBy(by: SkillSortBy) {
  if (sortBy.value === by) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
    return
  }
  sortBy.value = by
  sortDir.value = by === 'name' ? 'asc' : 'desc'
}

function setSortDir(dir: SkillSortDir) {
  sortDir.value = dir
}

async function runSkillSearch() {
  resetAdvancedFilter()
  filterPanelOpen.value = false
  clearPreview()
  await searchSkills()
}

function sourceTagClass(source: string) {
  return String(source || '').toLowerCase().replace(/[^a-z0-9]/g, '')
}

function sourceLabel(s: any) {
  return s.source_label || SKILL_SOURCE_LABELS[s.source as SkillSourceId] || s.source || 'market'
}

function skillItemKey(s: any) {
  if (s?.skill_name) return 'local:' + s.skill_name
  return String(s?.source || '') + ':' + String(s?.name || '') + ':' + String(s?.install_command || '')
}

function isPreviewSelected(s: any) {
  return !!previewItem.value && skillItemKey(previewItem.value) === skillItemKey(s)
}

function clearPreview() {
  previewItem.value = null
}

function selectSkillItem(s: any) {
  if (s.skill_name) {
    previewItem.value = {
      source: 'local',
      name: s.skill_name,
      description: s.description,
      category: s.category,
      install_command: '',
      skill_name: s.skill_name,
    }
    return
  }
  previewItem.value = s
}

async function installPreview() {
  if (!previewItem.value) return
  await installFromSearch(previewItem.value)
}

async function setSkillTab(tab: 'market' | 'local' | 'manual') {
  skillTab.value = tab
  clearPreview()
  if (tab === 'local') await loadLocalSkills()
  await nextTick()
  if (tab === 'market') marketInput.value?.focus()
  else if (tab === 'local') localFilterInput.value?.focus()
  else manualInput.value?.focus()
}

async function openDrawer(tab: 'market' | 'local' | 'manual' = 'market') {
  skillTab.value = tab
  clearPreview()
  if (tab === 'local') await loadLocalSkills()
  drawerOpen.value = true
  await nextTick()
  if (tab === 'market') marketInput.value?.focus()
  else if (tab === 'local') localFilterInput.value?.focus()
  else manualInput.value?.focus()
}

function closeDrawer() {
  clearPreview()
  drawerOpen.value = false
}

async function onManualPrimary() {
  if (!manualPreview.value) {
    await previewManualSource()
    return
  }
  await installSelectedManualSkills()
}

async function refreshInstalled() {
  await loadLocalSkills()
  await loadInstalledSkills()
  ui.toast('已刷新技能列表')
}

function suggestSearch(q: string) {
  skillSearchQ.value = q
  runSkillSearch()
}

watch([displayedSkillResults, filteredLocalSkills], () => {
  if (!previewItem.value) return
  if (skillTab.value === 'market') {
    const still = displayedSkillResults.value.some((s) => skillItemKey(s) === skillItemKey(previewItem.value))
    if (!still) clearPreview()
  } else if (skillTab.value === 'local') {
    const still = filteredLocalSkills.value.some((s) => skillItemKey(s) === skillItemKey(previewItem.value))
    if (!still) clearPreview()
  }
})

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && drawerOpen.value) {
    e.preventDefault()
    closeDrawer()
  }
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  loadLocalSkills()
  loadInstalledSkills()
})
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="skill-page">
    <div class="skill-head flex flex-wrap items-start justify-between gap-4">
      <div class="min-w-0">
        <h1 class="text-[15px] font-semibold text-ink-900 m-0">技能配置</h1>
        <p class="text-xs text-ink-500 mt-1 mb-0">集中管理 Agent Skills · 安装、启停与同步到 IDE</p>
      </div>
      <div class="btn-cluster">
        <button type="button" class="btn btn-secondary" @click="refreshInstalled">
          <svg viewBox="0 0 24 24"><path d="M21 12a9 9 0 1 1-2.6-6.3"/><path d="M21 3v6h-6"/></svg>
          刷新
        </button>
        <button type="button" class="btn btn-soft" @click="openDrawer('market')">
          <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>
          添加技能
        </button>
        <span class="split" aria-hidden="true" />
        <button type="button" class="btn btn-primary" @click="syncToIde">
          <svg viewBox="0 0 24 24"><path d="M12 2v10"/><path d="m8 8 4 4 4-4"/><path d="M4 14v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4"/></svg>
          同步到 IDE
        </button>
      </div>
    </div>

    <div class="kpis">
      <div class="kpi brand"><b>{{ installedSkills.length }}</b><span>已安装</span><em>.agents / config 并集</em></div>
      <div class="kpi live"><b>{{ enabledInstalledCount }}</b><span>启用中</span><em>写入 skill.yaml</em></div>
      <div class="kpi"><b>{{ localSkills.length }}</b><span>本地预置</span><em>三源合并</em></div>
      <div class="kpi warn"><b>{{ disabledInstalledCount }}</b><span>已禁用</span><em>不会同步到 IDE</em></div>
    </div>

    <section class="panel">
      <div class="toolbar">
        <div class="toolbar-left">
          <label class="search">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#86909c" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3-3"/></svg>
            <input v-model="listQuery" placeholder="筛选名称 / 路径" />
          </label>
          <div class="seg" role="group" aria-label="启停筛选">
            <button type="button" :class="{ on: listFilter === 'all' }" @click="listFilter = 'all'">全部</button>
            <button type="button" :class="{ on: listFilter === 'on' }" @click="listFilter = 'on'">启用</button>
            <button type="button" :class="{ on: listFilter === 'off' }" @click="listFilter = 'off'">禁用</button>
          </div>
        </div>
        <div class="btn-cluster">
          <div class="btn-pair" role="group" aria-label="批量启停">
            <button type="button" class="btn btn-ghost btn-sm" @click="toggleAllInstalled(true)">
              <svg viewBox="0 0 24 24"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
              全选
            </button>
            <button type="button" class="btn btn-ghost btn-sm" @click="toggleAllInstalled(false)">
              <svg viewBox="0 0 24 24"><path d="M18 6 6 18M6 6l12 12"/></svg>
              全不选
            </button>
          </div>
        </div>
      </div>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th style="width:72px">启用</th>
              <th>技能</th>
              <th>路径</th>
              <th style="width:90px">状态</th>
              <th style="width:148px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in filteredInstalled" :key="s.name" :class="{ disabled: !s.enabled }">
              <td>
                <button
                  type="button"
                  class="switch"
                  :class="{ on: s.enabled }"
                  :aria-label="(s.enabled ? '禁用' : '启用') + ' ' + s.name"
                  @click="onToggleSkill(s, !s.enabled)"
                />
              </td>
              <td><div class="name">{{ s.name }}</div></td>
              <td><div class="cmd" :title="s.path">{{ s.path || '—' }}</div></td>
              <td>
                <span class="status" :class="s.enabled ? 'on' : 'off'"><i />{{ s.enabled ? '启用' : '禁用' }}</span>
              </td>
              <td>
                <div class="ops">
                  <button type="button" class="btn btn-soft btn-sm" @click="viewSkillMd(s.name)">
                    <svg viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8S1 12 1 12z"/><circle cx="12" cy="12" r="3"/></svg>
                    查看
                  </button>
                  <button type="button" class="btn btn-danger btn-icon btn-sm" :aria-label="'卸载 ' + s.name" title="卸载" @click="uninstallSkill(s.name)">
                    <svg viewBox="0 0 24 24"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/><path d="M10 11v6M14 11v6"/></svg>
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!filteredInstalled.length">
              <td colspan="5" class="empty-cell">
                {{ installedSkills.length ? '无匹配结果' : '暂无已安装技能，点击「添加技能」开始' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <div class="keys-bar">
      <div>
        <h2>获取更多技能</h2>
        <p>从市场检索、安装本地预置，或通过 GitHub 源手动安装。</p>
      </div>
      <button type="button" class="btn btn-soft" @click="openDrawer('market')">
        <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>
        打开添加面板
      </button>
    </div>

    <Teleport to="body">
      <Transition name="skill-studio">
        <div v-if="drawerOpen" class="drawer-root">
          <div class="drawer-overlay" @click="closeDrawer" />
          <div
            class="studio"
            role="dialog"
            aria-modal="true"
            aria-labelledby="skill-drawer-title"
          >
            <aside class="studio-nav">
              <div class="nav-brand">
                <b>Catalog</b>
                <button type="button" class="btn btn-icon btn-ghost" aria-label="关闭" @click="closeDrawer">
                  <svg viewBox="0 0 24 24"><path d="M18 6 6 18M6 6l12 12"/></svg>
                </button>
              </div>
              <div>
                <div class="section-label">方式</div>
                <div class="mode-list">
                  <button type="button" class="mode" :class="{ on: skillTab === 'market' }" @click="setSkillTab('market')">
                    <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3-3"/></svg>
                    市场搜索
                  </button>
                  <button type="button" class="mode" :class="{ on: skillTab === 'local' }" @click="setSkillTab('local')">
                    <svg viewBox="0 0 24 24"><path d="M3 7h18M3 12h18M3 17h18"/></svg>
                    本地预置
                  </button>
                  <button type="button" class="mode" :class="{ on: skillTab === 'manual' }" @click="setSkillTab('manual')">
                    <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>
                    手动安装
                  </button>
                </div>
              </div>
              <div v-show="skillTab === 'market'">
                <div class="section-label">数据源</div>
                <div class="src-list" role="group" aria-label="数据源过滤">
                  <button
                    v-for="src in SKILL_SOURCE_ORDER"
                    :key="src"
                    type="button"
                    class="nav-src"
                    :class="{ on: isSourceOn(src) }"
                    :data-src="src"
                    :aria-pressed="isSourceOn(src)"
                    :title="src === 'github' || src === 'anthropics' ? '配置 GITHUB_TOKEN 后可用（Anthropic 官方库 / GitHub 代码搜索）' : undefined"
                    @click="toggleSkillSource(src)"
                  >
                    <span class="box" aria-hidden="true">
                      <svg v-if="isSourceOn(src)" viewBox="0 0 24 24"><path d="M5 12l5 5L20 7"/></svg>
                    </span>
                    {{ SKILL_SOURCE_LABELS[src] }}
                  </button>
                </div>
              </div>
            </aside>

            <section class="studio-catalog">
              <div class="cat-h">
                <div>
                  <h3 id="skill-drawer-title">添加技能</h3>
                  <p class="sub">{{ drawerSub }}</p>
                </div>
              </div>

              <template v-if="skillTab === 'market'">
                <div class="cat-search">
                  <input
                    ref="marketInput"
                    v-model="skillSearchQ"
                    placeholder="关键词，如：react、设计、API…"
                    @keydown.enter="runSkillSearch"
                  />
                  <button type="button" class="btn btn-primary" :disabled="skillSearching" @click="runSkillSearch">
                    <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3-3"/></svg>
                    搜索
                  </button>
                </div>
                <div class="meta-bar">
                  <template v-if="skillSearching"><span>正在并行查询各源…</span></template>
                  <template v-else-if="skillSearched">
                    <span>
                      共 <strong>{{ displayedSkillCount }}</strong>
                      <template v-if="filterActive && displayedSkillCount !== skillSearchResults.length">
                        / {{ skillSearchResults.length }}
                      </template>
                      条 · 已跨源去重
                    </span>
                    <button
                      type="button"
                      class="adv-toggle"
                      :class="{ on: filterPanelOpen || filterActive }"
                      @click="filterPanelOpen = !filterPanelOpen"
                    >
                      高级筛选
                      <svg viewBox="0 0 24 24" :class="{ open: filterPanelOpen }"><path d="M6 9l6 6 6-6"/></svg>
                    </button>
                  </template>
                  <template v-else>
                    <span>并行检索已选市场；搜完后可用高级筛选与排序</span>
                  </template>
                </div>
                <div v-if="skillSearched && !skillSearching && filterPanelOpen" class="adv-panel">
                  <div class="adv-row">
                    <span class="adv-label">来源</span>
                    <div class="adv-chips" role="group" aria-label="多选来源">
                      <button
                        type="button"
                        class="adv-chip"
                        :class="{ on: filterSources.length === 0 }"
                        @click="filterSources = []"
                      >全部</button>
                      <button
                        v-for="m in sourceMetaItems"
                        :key="m.id"
                        type="button"
                        class="adv-chip"
                        :class="{ on: isFilterSourceOn(m.id) }"
                        :data-src="m.id"
                        @click="toggleFilterSource(m.id)"
                      >{{ m.label }} · {{ m.count }}</button>
                    </div>
                  </div>
                  <div class="adv-row">
                    <span class="adv-label">关键词</span>
                    <input
                      v-model="filterQuery"
                      class="adv-input"
                      placeholder="在结果中筛选名称 / 作者 / 描述…"
                    />
                  </div>
                  <div class="adv-row">
                    <span class="adv-label">排序</span>
                    <div class="adv-sort" role="group" aria-label="排序方式">
                      <button
                        type="button"
                        class="adv-chip"
                        :class="{ on: sortBy === 'name' }"
                        @click="setSortBy('name')"
                      >
                        字母
                        <span v-if="sortBy === 'name'" class="dir">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
                      </button>
                      <button
                        type="button"
                        class="adv-chip"
                        :class="{ on: sortBy === 'heat' }"
                        @click="setSortBy('heat')"
                      >
                        热度
                        <span v-if="sortBy === 'heat'" class="dir">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
                      </button>
                      <button
                        type="button"
                        class="adv-chip"
                        :class="{ on: sortDir === 'asc' }"
                        @click="setSortDir('asc')"
                      >升序</button>
                      <button
                        type="button"
                        class="adv-chip"
                        :class="{ on: sortDir === 'desc' }"
                        @click="setSortDir('desc')"
                      >降序</button>
                    </div>
                  </div>
                  <div class="adv-actions">
                    <button type="button" class="btn btn-soft" @click="resetAdvancedFilter">重置</button>
                  </div>
                </div>
                <div v-if="skillSearched && sourceMetaItems.length && !filterPanelOpen" class="src-meta-bar">
                  <span
                    v-for="m in sourceMetaItems"
                    :key="m.id"
                    class="src-meta-tag"
                  >{{ m.label }} · {{ m.count }}</span>
                </div>
                <div class="results">
                  <div v-if="skillSearching" class="m-loading">
                    <div class="spinner" aria-hidden="true" />
                    聚合搜索中…
                  </div>
                  <div v-else-if="!skillSearched" class="m-hint">
                    输入关键词，从多个 Skills 市场一次搜齐。<br />选中结果后在右侧预览并安装。
                    <div class="suggest-row">
                      <button v-for="s in SUGGESTS" :key="s" type="button" class="suggest" @click="suggestSearch(s)">{{ s }}</button>
                    </div>
                  </div>
                  <div v-else-if="!skillSearchResults.length" class="m-empty">无结果。换个关键词，或调整左侧数据源。</div>
                  <div v-else-if="!displayedSkillResults.length" class="m-empty">
                    当前筛选无结果。
                    <button type="button" class="suggest" style="margin-top:10px" @click="resetAdvancedFilter">重置筛选</button>
                  </div>
                  <template v-else>
                    <article
                      v-for="s in displayedSkillResults"
                      :key="skillItemKey(s)"
                      class="m-card"
                      :class="['from-' + sourceTagClass(s.source), { sel: isPreviewSelected(s) }]"
                      tabindex="0"
                      @click="selectSkillItem(s)"
                      @keydown.enter.prevent="selectSkillItem(s)"
                    >
                      <div class="m-card-top">
                        <h4 :title="s.name">{{ s.name }}</h4>
                        <div class="m-tags">
                          <span
                            class="src-tag"
                            :class="sourceTagClass(s.source)"
                            :title="'来源：' + sourceLabel(s)"
                          >
                            <span class="dot" aria-hidden="true" />
                            {{ sourceLabel(s) }}
                          </span>
                        </div>
                      </div>
                      <div class="meta" :title="[s.author, s.install_count != null ? '安装量/星标 ' + s.install_count : ''].filter(Boolean).join(' · ')">
                        {{ [s.author ? '作者 ' + s.author : '', s.install_count != null ? '热度 ' + s.install_count : ''].filter(Boolean).join(' · ') || '—' }}
                      </div>
                      <p>{{ s.description || '暂无描述' }}</p>
                      <div v-if="s.install_command" class="cmd-line" :title="s.install_command">{{ s.install_command }}</div>
                    </article>
                  </template>
                </div>
              </template>

              <template v-else-if="skillTab === 'local'">
                <div class="cat-search">
                  <input
                    ref="localFilterInput"
                    v-model="localFilterQ"
                    placeholder="筛选本地预置…"
                  />
                </div>
                <div class="meta-bar">
                  <span>共 <strong>{{ filteredLocalSkills.length }}</strong> / {{ localSkills.length }} 个预置</span>
                </div>
                <div class="results">
                  <div v-if="!filteredLocalSkills.length" class="m-empty">
                    {{ localSkills.length ? '无匹配预置技能' : '暂无本地预置技能' }}
                  </div>
                  <template v-else>
                    <article
                      v-for="s in filteredLocalSkills"
                      :key="s.skill_name"
                      class="m-card from-local"
                      :class="{ sel: isPreviewSelected(s) }"
                      tabindex="0"
                      @click="selectSkillItem(s)"
                      @keydown.enter.prevent="selectSkillItem(s)"
                    >
                      <div class="m-card-top">
                        <h4 :title="s.skill_name">{{ s.skill_name }}</h4>
                        <div class="m-tags">
                          <span v-if="s.category" class="src-tag local">
                            <span class="dot" aria-hidden="true" />
                            {{ s.category }}
                          </span>
                          <span class="host-tag">本地</span>
                        </div>
                      </div>
                      <p>{{ s.description || '暂无描述' }}</p>
                    </article>
                  </template>
                </div>
              </template>

              <template v-else>
                <div class="results form-pad">
                  <div class="field full">
                    <label>安装源 *</label>
                    <div class="cat-search" style="margin:0">
                      <input
                        ref="manualInput"
                        v-model="manualSkillInput"
                        placeholder="owner/repo 或 GitHub URL（也可 owner/repo@skill）"
                        @keydown.enter.prevent="onManualPrimary"
                      />
                      <button
                        type="button"
                        class="btn btn-soft"
                        :disabled="manualPreviewing || !manualSkillInput.trim()"
                        @click="previewManualSource"
                      >
                        <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3-3"/></svg>
                        {{ manualPreviewing ? '解析中…' : '解析技能' }}
                      </button>
                    </div>
                  </div>
                  <p class="keys-hint">
                    多技能仓库会先列出可选技能，勾选后再安装。已写 <code>@skill</code> 则只安装该技能。
                  </p>

                  <div v-if="manualPreviewing" class="m-loading">
                    <div class="spinner" aria-hidden="true" />
                    正在解析仓库中的技能…
                  </div>

                  <template v-else-if="manualPreview">
                    <div class="picker-bar">
                      <div class="picker-meta">
                        发现 <strong>{{ manualPreview.count }}</strong> 个技能
                        <span class="muted">· {{ manualPreview.source }}</span>
                      </div>
                      <div class="btn-pair" role="group" aria-label="批量选择">
                        <button type="button" class="btn btn-ghost btn-sm" @click="selectAllManualSkills(true)">全选</button>
                        <button type="button" class="btn btn-ghost btn-sm" @click="selectAllManualSkills(false)">清空</button>
                      </div>
                    </div>

                    <div v-if="!manualPreview.skills.length" class="m-empty">未发现可安装技能</div>
                    <div v-else class="pick-list" role="group" aria-label="选择要安装的技能">
                      <label
                        v-for="s in manualPreview.skills"
                        :key="s.name"
                        class="pick-row"
                        :class="{ on: manualSelected.includes(s.name) }"
                      >
                        <input
                          type="checkbox"
                          class="pick-check"
                          :checked="manualSelected.includes(s.name)"
                          @change="toggleManualSkill(s.name)"
                        />
                        <div class="pick-body">
                          <div class="pick-name">{{ s.name }}</div>
                          <div v-if="s.description" class="pick-desc">{{ s.description }}</div>
                        </div>
                      </label>
                    </div>
                  </template>
                </div>
              </template>
            </section>

            <aside class="studio-preview">
              <template v-if="skillTab === 'manual'">
                <div class="prev-h">
                  <div class="eyebrow">手动安装</div>
                  <h4>{{ manualPreview ? `已发现 ${manualPreview.count} 个` : '解析仓库' }}</h4>
                  <div class="id">{{ manualSkillInput.trim() || '填写 owner/repo 后解析' }}</div>
                </div>
                <div class="prev-b">
                  <p class="desc">勾选中间列表中的技能，再点下方安装。也可在源里写 <code>@skill</code> 只装单个。</p>
                  <div class="kv" v-if="manualPreview">
                    <div><label>已选</label><b>{{ manualSelectedCount }} / {{ manualPreview.count }}</b></div>
                    <div><label>来源</label><b>{{ manualPreview.source }}</b></div>
                  </div>
                </div>
                <div class="prev-f">
                  <div class="row">
                    <button type="button" class="btn btn-secondary" @click="closeDrawer">取消</button>
                    <button
                      v-if="!manualPreview"
                      type="button"
                      class="btn btn-primary"
                      :disabled="manualPreviewing || !manualSkillInput.trim()"
                      @click="previewManualSource"
                    >
                      <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3-3"/></svg>
                      解析技能
                    </button>
                    <button
                      v-else
                      type="button"
                      class="btn btn-primary"
                      :disabled="!manualCanInstall || manualInstalling"
                      @click="installSelectedManualSkills"
                    >
                      <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>
                      {{ manualInstalling ? '安装中…' : `安装已选 (${manualSelectedCount})` }}
                    </button>
                  </div>
                </div>
              </template>

              <template v-else-if="previewItem">
                <div class="prev-h">
                  <div class="eyebrow">技能预览</div>
                  <h4>{{ previewItem.name || previewItem.skill_name }}</h4>
                  <div class="id">{{ sourceLabel(previewItem) }}</div>
                </div>
                <div class="prev-b">
                  <p class="desc">{{ previewItem.description || '暂无描述' }}</p>
                  <div class="kv">
                    <div v-if="previewItem.author"><label>作者</label><b>{{ previewItem.author }}</b></div>
                    <div v-if="previewItem.category"><label>分类</label><b>{{ previewItem.category }}</b></div>
                    <div v-if="previewItem.install_count != null"><label>热度</label><b>{{ previewItem.install_count }}</b></div>
                  </div>
                  <pre v-if="previewItem.install_command" class="code">{{ previewItem.install_command }}</pre>
                </div>
                <div class="prev-f">
                  <div class="row">
                    <button
                      v-if="previewItem.skill_name || previewItem.source === 'local'"
                      type="button"
                      class="btn btn-secondary"
                      @click="viewSkillMd(previewItem.skill_name || previewItem.name)"
                    >查看</button>
                    <button type="button" class="btn btn-primary" @click="installPreview">
                      <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>
                      安装
                    </button>
                  </div>
                </div>
              </template>

              <div v-else class="empty-prev">
                <p>在中间列表选中一条技能<br />即可在此预览并安装</p>
              </div>
            </aside>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.skill-page,
.drawer-root {
  --red: #f53f3f;
  --red-bg: #ffece8;
  --red-border: #f9c2c0;
  --green: #00b42a;
  --green-bg: #e8ffea;
  --amber: #ff7d00;
  --amber-bg: #fff7e8;
}
.skill-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding-bottom: 12px;
}
.skill-head { margin: 0; }

.btn {
  height: 34px; padding: 0 12px; border-radius: 8px; font-size: 12px; font-weight: 600;
  display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  white-space: nowrap; border: 1px solid transparent; cursor: pointer;
  transition: background .18s ease, color .18s ease, border-color .18s ease;
  background: none; color: inherit; user-select: none;
}
.btn svg { width: 14px; height: 14px; flex-shrink: 0; stroke: currentColor; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.btn:disabled { opacity: .45; cursor: not-allowed; }
.btn-sm { height: 28px; padding: 0 10px; font-size: 11px; border-radius: 7px; }
.btn-sm svg { width: 13px; height: 13px; }
.btn-icon { width: 32px; padding: 0; }
.btn-icon.btn-sm { width: 28px; }
.btn-primary { background: var(--primary); color: #fff; box-shadow: 0 1px 2px rgba(22,93,255,.22); }
.btn-primary:hover:not(:disabled) { background: var(--primary-hover); }
.btn-soft { background: var(--primary-container); color: var(--primary-hover); border-color: var(--primary-container-strong); }
.btn-soft:hover:not(:disabled) { background: #d9e6ff; }
.btn-secondary { background: var(--bg-elevated); color: var(--text-secondary); border-color: var(--border-base); }
.btn-secondary:hover:not(:disabled) { background: var(--bg-base); border-color: var(--border-strong); }
.btn-ghost { background: transparent; color: var(--text-secondary); }
.btn-ghost:hover:not(:disabled) { background: var(--bg-base); color: var(--text-primary); }
.btn-danger { background: transparent; color: var(--text-tertiary); }
.btn-danger:hover:not(:disabled), .btn-danger:focus-visible { background: var(--red-bg); color: var(--red); border-color: var(--red-border); }

.btn-cluster { display: inline-flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.btn-cluster .split { width: 1px; height: 20px; background: var(--border-base); margin: 0 2px; }
.btn-pair {
  display: inline-flex; border-radius: 8px; overflow: hidden;
  border: 1px solid var(--border-base); background: var(--bg-elevated);
}
.btn-pair .btn { border-radius: 0; border: none; height: 32px; border-right: 1px solid var(--border-base); }
.btn-pair .btn:last-child { border-right: none; }

.kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.kpi {
  background: var(--bg-elevated); border-radius: 12px; padding: 16px 18px;
  box-shadow: 0 1px 2px rgba(0,0,0,.04), 0 4px 12px rgba(0,0,0,.06);
  border: 1px solid rgba(0,0,0,.03); position: relative; overflow: hidden;
}
.kpi::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--border-strong); }
.kpi.live::before { background: var(--green); }
.kpi.warn::before { background: var(--amber); }
.kpi.brand::before { background: var(--primary); }
.kpi b { display: block; font-size: 22px; font-variant-numeric: tabular-nums; line-height: 1.1; color: var(--text-primary); }
.kpi span { font-size: 12px; color: var(--text-tertiary); }
.kpi em { font-style: normal; font-size: 11px; color: var(--text-tertiary); margin-top: 6px; display: block; }

.panel {
  background: var(--bg-elevated); border-radius: 14px;
  box-shadow: 0 1px 2px rgba(0,0,0,.04), 0 4px 12px rgba(0,0,0,.06);
  border: 1px solid rgba(0,0,0,.03); overflow: hidden;
}
.toolbar {
  display: flex; justify-content: space-between; gap: 14px; flex-wrap: wrap;
  padding: 14px 18px; border-bottom: 1px solid var(--border-base); align-items: center;
}
.toolbar-left { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
.search {
  display: flex; align-items: center; gap: 8px; height: 34px; padding: 0 10px;
  border: 1px solid var(--border-strong); border-radius: 8px; background: var(--bg-elevated); min-width: 220px;
}
.search input { border: none; outline: none; flex: 1; font-size: 12px; min-width: 0; background: transparent; }
.seg { display: inline-flex; background: var(--bg-base); padding: 3px; border-radius: 8px; }
.seg button {
  height: 28px; padding: 0 10px; border-radius: 6px; font-size: 12px; font-weight: 600;
  color: var(--text-tertiary); border: none; background: transparent; cursor: pointer;
}
.seg button.on { background: var(--bg-elevated); color: var(--primary-hover); box-shadow: 0 1px 2px rgba(0,0,0,.06); }

.table-wrap { max-height: min(560px, 62vh); overflow: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th {
  text-align: left; font-size: 11px; font-weight: 600; color: var(--text-tertiary); text-transform: uppercase;
  letter-spacing: .04em; padding: 11px 18px; background: var(--bg-base); border-bottom: 1px solid var(--border-base);
  position: sticky; top: 0; z-index: 1;
}
td { padding: 13px 18px; border-bottom: 1px solid #f7f8fa; vertical-align: middle; }
tr:hover td { background: var(--bg-base); }
tr.disabled td { opacity: .62; }
.name { font-weight: 650; color: var(--text-primary); }
.cmd {
  font-family: 'JetBrains Mono', Consolas, monospace; font-size: 11px; color: var(--text-tertiary);
  max-width: 420px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.status { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 600; }
.status i { width: 7px; height: 7px; border-radius: 50%; background: var(--border-strong); display: inline-block; }
.status.on { color: var(--green); }
.status.on i { background: var(--green); box-shadow: 0 0 0 3px var(--green-bg); }
.status.off { color: var(--text-tertiary); }
.switch {
  width: 36px; height: 20px; border-radius: 999px; background: var(--border-strong); position: relative;
  border: none; cursor: pointer; transition: background .2s; padding: 0;
}
.switch::after {
  content: ""; position: absolute; top: 2px; left: 2px; width: 16px; height: 16px; border-radius: 50%;
  background: var(--bg-elevated); transition: transform .2s; box-shadow: 0 1px 2px rgba(0,0,0,.15);
}
.switch.on { background: var(--primary); }
.switch.on::after { transform: translateX(16px); }
.ops { display: inline-flex; align-items: center; gap: 4px; padding: 2px; border-radius: 9px; }
tr:hover .ops { background: var(--bg-base); }
.ops .btn-soft { border-color: transparent; background: transparent; color: var(--primary-hover); }
.ops .btn-soft:hover { background: var(--bg-elevated); border-color: var(--primary-container-strong); }
.empty-cell { text-align: center; color: var(--text-tertiary); padding: 36px !important; }

.keys-bar {
  background: var(--bg-elevated); border-radius: 14px; padding: 16px 18px;
  box-shadow: 0 1px 2px rgba(0,0,0,.04), 0 4px 12px rgba(0,0,0,.06);
  border: 1px solid rgba(0,0,0,.03);
  display: flex; justify-content: space-between; align-items: center; gap: 14px; flex-wrap: wrap;
}
.keys-bar h2 { margin: 0 0 2px; font-size: 14px; color: var(--text-primary); }
.keys-bar p { margin: 0; font-size: 12px; color: var(--text-tertiary); }

.drawer-root {
  position: fixed; inset: 0; z-index: 60;
  display: flex; align-items: center; justify-content: center;
  padding: 24px; box-sizing: border-box;
}
.drawer-overlay { position: absolute; inset: 0; background: rgba(31,35,41,.4); }

.studio {
  position: relative; z-index: 1;
  width: min(980px, 100%); height: min(640px, calc(100vh - 48px));
  background: var(--bg-elevated); border-radius: 18px;
  box-shadow: 0 28px 72px rgba(15,20,30,.28);
  display: flex; align-items: stretch; overflow: hidden;
}
.studio-nav {
  width: 180px; flex: 0 0 180px;
  background: linear-gradient(180deg, #f7f9fd, #eef3fb);
  border-right: 1px solid var(--border-base);
  padding: 14px 12px; display: flex; flex-direction: column; gap: 14px;
  overflow: auto; min-height: 0; z-index: 2;
}
.nav-brand {
  display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 0 4px 4px;
}
.nav-brand b {
  font-size: 12px; font-weight: 700; color: var(--primary-hover); letter-spacing: .04em; text-transform: uppercase;
}
.section-label {
  font-size: 10px; font-weight: 700; color: var(--text-tertiary);
  letter-spacing: .06em; text-transform: uppercase; padding: 0 6px; margin-bottom: 6px;
}
.mode-list { display: flex; flex-direction: column; gap: 4px; }
.mode {
  height: 34px; border: none; border-radius: 9px; background: transparent;
  font-size: 12px; font-weight: 600; color: var(--text-secondary);
  display: flex; align-items: center; gap: 8px; padding: 0 10px; cursor: pointer; text-align: left;
  transition: background .15s, color .15s;
}
.mode svg { width: 15px; height: 15px; stroke: currentColor; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; opacity: .7; }
.mode:hover { background: rgba(22,93,255,.06); color: var(--primary-hover); }
.mode.on { background: var(--bg-elevated); color: var(--primary-hover); box-shadow: 0 1px 2px rgba(0,0,0,.06); }
.mode.on svg { opacity: 1; }
.src-list { display: flex; flex-direction: column; gap: 4px; }
.nav-src {
  height: 30px; border-radius: 8px; border: 1px solid transparent; background: transparent;
  font-size: 11px; font-weight: 600; color: var(--text-tertiary);
  display: flex; align-items: center; gap: 8px; padding: 0 8px; cursor: pointer; text-align: left;
}
.nav-src .box {
  width: 14px; height: 14px; border-radius: 4px; border: 1.5px solid var(--border-strong);
  display: grid; place-items: center; background: var(--bg-elevated); flex-shrink: 0;
}
.nav-src .box svg { width: 9px; height: 9px; stroke: #fff; fill: none; stroke-width: 3; }
.nav-src.on { color: var(--text-primary); background: rgba(255,255,255,.7); }
.nav-src.on .box { background: var(--primary); border-color: var(--primary); }
.nav-src[data-src="smithery"].on .box { background: #722ed1; border-color: #722ed1; }
.nav-src[data-src="modelscope"].on .box { background: #00b42a; border-color: #00b42a; }
.nav-src[data-src="skillsmp"].on .box { background: var(--primary-hover); border-color: var(--primary-hover); }
.nav-src[data-src="clawhub"].on .box { background: #ff7d00; border-color: #ff7d00; }
.nav-src[data-src="anthropics"].on .box { background: #d97706; border-color: #d97706; }
.nav-src[data-src="github"].on .box { background: #4e5969; border-color: var(--text-secondary); }

.studio-catalog {
  flex: 1 1 0%;
  min-width: 260px; min-height: 0;
  display: flex; flex-direction: column;
  background: var(--bg-elevated); overflow: hidden; z-index: 1;
}
.cat-h {
  padding: 14px 16px 10px; border-bottom: 1px solid var(--border-base);
  display: flex; justify-content: space-between; align-items: flex-start; gap: 10px;
}
.cat-h h3 { margin: 0 0 4px; font-size: 15px; font-weight: 700; color: var(--text-primary); }
.cat-h .sub { margin: 0; font-size: 12px; color: var(--text-tertiary); line-height: 1.4; }
.cat-search { margin: 12px 16px 0; display: flex; gap: 8px; }
.cat-search input {
  flex: 1; height: 38px; border: 1.5px solid var(--border-strong); border-radius: 10px;
  padding: 0 12px; font-size: 13px; background: var(--bg-elevated); min-width: 0;
}
.cat-search input:focus {
  outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px rgba(22,93,255,.15);
}
.cat-search .btn { height: 38px; border-radius: 10px; padding: 0 14px; flex-shrink: 0; }
.meta-bar {
  display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 10px 16px; font-size: 11px; color: var(--text-tertiary);
}
.meta-bar strong { color: var(--text-primary); }
.adv-toggle {
  height: 26px; padding: 0 10px; border-radius: 7px; border: 1px solid var(--border-base); background: var(--bg-elevated);
  font-size: 11px; font-weight: 600; color: var(--text-secondary); cursor: pointer;
  display: inline-flex; align-items: center; gap: 4px;
}
.adv-toggle svg {
  width: 12px; height: 12px; stroke: currentColor; fill: none; stroke-width: 2;
  stroke-linecap: round; stroke-linejoin: round; transition: transform .15s;
}
.adv-toggle svg.open { transform: rotate(180deg); }
.adv-toggle:hover, .adv-toggle.on {
  color: var(--primary-hover); border-color: #bedaff; background: var(--primary-container);
}
.adv-panel {
  margin: 0 16px 8px; padding: 12px; border: 1px solid var(--border-base); border-radius: 12px;
  background: #fafbfc; display: grid; gap: 10px;
}
.adv-row { display: flex; align-items: flex-start; gap: 10px; }
.adv-label {
  flex: 0 0 42px; padding-top: 5px;
  font-size: 11px; font-weight: 700; color: var(--text-tertiary);
}
.adv-chips, .adv-sort { display: flex; flex-wrap: wrap; gap: 6px; flex: 1; }
.adv-chip {
  height: 28px; padding: 0 10px; border-radius: 8px; border: 1px solid var(--border-base); background: var(--bg-elevated);
  font-size: 11px; font-weight: 600; color: var(--text-secondary); cursor: pointer;
  display: inline-flex; align-items: center; gap: 4px;
}
.adv-chip:hover { border-color: var(--border-strong); color: var(--text-primary); }
.adv-chip.on {
  color: var(--primary-hover); border-color: #bedaff; background: var(--primary-container);
}
.adv-chip .dir { font-size: 12px; line-height: 1; }
.adv-input {
  flex: 1; height: 32px; border: 1px solid var(--border-base); border-radius: 8px;
  padding: 0 10px; font-size: 12px; background: var(--bg-elevated); color: var(--text-primary);
}
.adv-input:focus {
  outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px rgba(22,93,255,.12);
}
.adv-actions { display: flex; justify-content: flex-end; }
.src-meta-bar {
  display: flex; flex-wrap: wrap; gap: 4px; padding: 0 16px 8px;
}
.src-meta-tag {
  padding: 2px 7px; border-radius: 6px; background: var(--bg-base); border: 1px solid var(--border-base);
  font-size: 11px; font-weight: 600; color: var(--text-tertiary);
}

.results {
  flex: 1 1 0%; min-height: 0; min-width: 0;
  overflow-x: hidden; overflow-y: auto;
  overscroll-behavior: contain;
  padding: 8px 20px 20px;
  display: flex; flex-direction: column; gap: 10px;
  align-items: stretch;
  box-sizing: border-box;
}
.results.form-pad { padding: 12px 20px 20px; overflow-y: auto; }
.m-card {
  border: 1px solid var(--border-base);
  border-left: 3px solid var(--border-strong);
  border-radius: 12px;
  padding: 12px 14px;
  background: var(--bg-elevated);
  width: 100%; max-width: 100%;
  box-sizing: border-box;
  flex: 0 0 auto;
  cursor: pointer;
  transition: border-color .15s, box-shadow .15s, background .15s;
}
.m-card.from-skillssh { border-left-color: var(--primary); }
.m-card.from-smithery { border-left-color: #722ed1; }
.m-card.from-modelscope { border-left-color: #00b42a; }
.m-card.from-skillsmp { border-left-color: var(--primary-hover); }
.m-card.from-clawhub { border-left-color: #ff7d00; }
.m-card.from-anthropics { border-left-color: #d97706; }
.m-card.from-github { border-left-color: var(--text-secondary); }
.m-card.from-local { border-left-color: #722ed1; }
.m-card:hover {
  border-top-color: #d9e6ff;
  border-right-color: #d9e6ff;
  border-bottom-color: #d9e6ff;
  box-shadow: 0 1px 2px rgba(0,0,0,.04), 0 4px 12px rgba(0,0,0,.06);
}
.m-card.sel {
  border-color: var(--primary);
  background: var(--primary-container);
  outline: 2px solid rgba(22,93,255,.28);
  outline-offset: 1px;
}
.m-card.sel.from-skillssh { border-left-color: var(--primary); }
.m-card.sel.from-smithery { border-left-color: #722ed1; }
.m-card.sel.from-modelscope { border-left-color: #00b42a; }
.m-card.sel.from-skillsmp { border-left-color: var(--primary-hover); }
.m-card.sel.from-clawhub { border-left-color: #ff7d00; }
.m-card.sel.from-anthropics { border-left-color: #d97706; }
.m-card.sel.from-github { border-left-color: var(--text-secondary); }
.m-card.sel.from-local { border-left-color: #722ed1; }
.m-card-top {
  display: flex; justify-content: space-between; align-items: flex-start; gap: 8px;
  margin-bottom: 6px; min-width: 0;
}
.m-card h4 {
  margin: 0; font-size: 13px; font-weight: 650; line-height: 1.3;
  flex: 1 1 auto; min-width: 0; overflow-wrap: anywhere; word-break: break-word; color: var(--text-primary);
}
.m-tags { display: flex; flex-wrap: wrap; gap: 4px; justify-content: flex-end; flex: 0 1 auto; max-width: 46%; }
.src-tag {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 10px; font-weight: 700; padding: 3px 8px; border-radius: 999px;
  border: 1px solid transparent; white-space: nowrap;
}
.src-tag .dot { width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0; }
.src-tag.skillssh { background: var(--primary-container); color: var(--primary-hover); border-color: var(--primary-container-strong); }
.src-tag.skillssh .dot { background: var(--primary); }
.src-tag.smithery { background: #f5e8ff; color: #722ed1; border-color: #e6d0ff; }
.src-tag.smithery .dot { background: #722ed1; }
.src-tag.modelscope { background: #e8ffea; color: #00b42a; border-color: #b7ebc4; }
.src-tag.modelscope .dot { background: #00b42a; }
.src-tag.skillsmp { background: var(--primary-container); color: var(--primary-hover); border-color: var(--primary-container-strong); }
.src-tag.skillsmp .dot { background: var(--primary-hover); }
.src-tag.clawhub { background: #fff7e8; color: #ff7d00; border-color: #ffe0b3; }
.src-tag.clawhub .dot { background: #ff7d00; }
.src-tag.anthropics { background: #fff7ed; color: #c2410c; border-color: #fed7aa; }
.src-tag.anthropics .dot { background: #d97706; }
.src-tag.github { background: var(--bg-base); color: var(--text-primary); border-color: var(--border-strong); }
.src-tag.github .dot { background: #4e5969; }
.src-tag.local { background: #f5e8ff; color: #722ed1; border-color: #e6d0ff; }
.src-tag.local .dot { background: #722ed1; }
.host-tag {
  font-size: 10px; font-weight: 700; padding: 3px 7px; border-radius: 999px;
  background: #e8ffea; color: #00b42a; border: 1px solid #b7ebc4; white-space: nowrap;
}
.m-card .meta {
  font-size: 11px; color: var(--text-tertiary); margin-bottom: 6px;
  font-family: 'JetBrains Mono', Consolas, monospace;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0;
}
.m-card p {
  margin: 0; font-size: 12px; color: var(--text-secondary); line-height: 1.45;
  display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.cmd-line {
  font-family: 'JetBrains Mono', Consolas, monospace; font-size: 10px; color: var(--text-tertiary);
  margin-top: 8px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0;
}

.studio-preview {
  width: 280px; flex: 0 0 280px;
  border-left: 1px solid var(--border-base);
  background: linear-gradient(180deg, #fafbfd, #f3f6fb);
  display: flex; flex-direction: column; min-width: 0; min-height: 0; overflow: hidden; z-index: 2;
}
.prev-h { padding: 16px 16px 12px; border-bottom: 1px solid var(--border-base); }
.prev-h .eyebrow {
  font-size: 10px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
  color: var(--primary); margin-bottom: 6px;
}
.prev-h h4 { margin: 0 0 6px; font-size: 15px; font-weight: 700; line-height: 1.25; word-break: break-word; }
.prev-h .id { font-family: 'JetBrains Mono', Consolas, monospace; font-size: 11px; color: var(--text-tertiary); word-break: break-all; }
.prev-b { flex: 1; overflow: auto; padding: 14px 16px; }
.desc { font-size: 13px; line-height: 1.55; color: var(--text-secondary); margin: 0 0 14px; }
.desc code {
  font-size: 11px; padding: 0 4px; border-radius: 4px; background: var(--bg-base);
  font-family: 'JetBrains Mono', Consolas, monospace;
}
.kv { display: grid; gap: 10px; margin-bottom: 14px; }
.kv div {
  background: var(--bg-elevated); border: 1px solid var(--border-base); border-radius: 10px; padding: 10px 12px;
}
.kv label {
  display: block; font-size: 10px; font-weight: 700; color: var(--text-tertiary);
  letter-spacing: .04em; text-transform: uppercase; margin-bottom: 4px;
}
.kv b { font-size: 12px; font-weight: 600; color: var(--text-primary); word-break: break-word; }
.code {
  font-family: 'JetBrains Mono', Consolas, monospace; font-size: 11px; line-height: 1.5;
  background: var(--text-primary); color: #d7e3ff; border-radius: 10px; padding: 12px; overflow: auto; margin: 0;
  white-space: pre-wrap; word-break: break-word;
}
.prev-f {
  padding: 12px 16px; border-top: 1px solid var(--border-base);
  background: rgba(255,255,255,.7);
}
.prev-f .row { display: flex; gap: 8px; }
.prev-f .btn { flex: 1; }
.empty-prev {
  flex: 1; display: grid; place-items: center; text-align: center;
  padding: 24px; color: var(--text-tertiary); font-size: 13px; line-height: 1.5;
}

.m-empty, .m-loading, .m-hint {
  text-align: center; padding: 36px 16px; color: var(--text-tertiary); font-size: 13px; line-height: 1.5;
}
.m-loading { display: flex; flex-direction: column; align-items: center; gap: 10px; }
.spinner {
  width: 22px; height: 22px; border: 2.5px solid var(--primary-container-strong); border-top-color: var(--primary);
  border-radius: 50%; animation: skill-spin .7s linear infinite;
}
@keyframes skill-spin { to { transform: rotate(360deg); } }
.suggest-row { display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; margin-top: 12px; }
.suggest {
  height: 28px; padding: 0 10px; border-radius: 999px; font-size: 12px; font-weight: 600;
  background: var(--bg-elevated); border: 1px solid var(--border-base); color: var(--text-secondary); cursor: pointer;
}
.suggest:hover { border-color: var(--primary-container-strong); color: var(--primary-hover); background: var(--primary-container); }

.field { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
.field.full { grid-column: 1 / -1; }
.field label { font-size: 12px; font-weight: 600; color: var(--text-secondary); }
.keys-hint { margin: 0 0 12px; font-size: 12px; color: var(--text-tertiary); line-height: 1.5; }
.keys-hint code {
  font-size: 11px; padding: 0 4px; border-radius: 4px; background: var(--bg-base);
  font-family: 'JetBrains Mono', Consolas, monospace;
}

.picker-bar {
  display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap;
  margin: 4px 0 10px;
}
.picker-meta { font-size: 12px; color: var(--text-secondary); }
.picker-meta strong { color: var(--text-primary); font-weight: 700; }
.picker-meta .muted { color: var(--text-tertiary); margin-left: 4px; word-break: break-all; }

.pick-list { display: grid; gap: 8px; max-height: min(360px, 42vh); overflow: auto; padding-right: 2px; }
.pick-row {
  display: flex; gap: 10px; align-items: flex-start;
  padding: 10px 12px; border: 1px solid var(--border-base); border-radius: 10px;
  background: var(--bg-elevated); cursor: pointer; transition: border-color .15s, background .15s;
}
.pick-row:hover { border-color: var(--primary-container-strong); background: var(--bg-base); }
.pick-row.on { border-color: #a8c5ff; background: var(--primary-container); }
.pick-check {
  width: 16px; height: 16px; margin-top: 2px; flex-shrink: 0;
  accent-color: var(--primary); cursor: pointer;
}
.pick-body { min-width: 0; flex: 1; }
.pick-name { font-size: 13px; font-weight: 650; color: var(--text-primary); line-height: 1.3; }
.pick-desc {
  margin-top: 4px; font-size: 12px; color: var(--text-tertiary); line-height: 1.45;
  display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}

.skill-studio-enter-active, .skill-studio-leave-active { transition: opacity .2s ease; }
.skill-studio-enter-active .studio, .skill-studio-leave-active .studio {
  transition: transform .22s ease-out, opacity .22s ease-out;
}
.skill-studio-enter-from, .skill-studio-leave-to { opacity: 0; }
.skill-studio-enter-from .studio, .skill-studio-leave-to .studio {
  transform: translateY(8px) scale(.98); opacity: 0;
}

@media (max-width: 900px) {
  .kpis { grid-template-columns: 1fr 1fr; }
  .cmd { max-width: 160px; }
  .drawer-root { padding: 12px; align-items: stretch; }
  .studio {
    width: 100%; height: min(92vh, 760px);
    flex-direction: column;
  }
  .studio-nav {
    width: 100%; flex: 0 0 auto;
    flex-direction: row; flex-wrap: wrap; align-items: flex-start;
    border-right: none; border-bottom: 1px solid var(--border-base); gap: 10px;
    max-height: 160px;
  }
  .mode-list, .src-list { flex-direction: row; flex-wrap: wrap; }
  .studio-catalog { flex: 1 1 0%; min-height: 0; }
  .studio-preview {
    width: 100%; flex: 0 0 auto; max-height: 38%;
    border-left: none; border-top: 1px solid var(--border-base);
  }
}
@media (prefers-reduced-motion: reduce) {
  .btn, .switch, .switch::after, .spinner,
  .skill-studio-enter-active, .skill-studio-leave-active,
  .skill-studio-enter-active .studio, .skill-studio-leave-active .studio {
    transition: none !important; animation: none !important;
  }
}
</style>
