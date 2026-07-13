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

const SUGGESTS = ['react', '设计', 'API', 'testing', 'docx']

const drawerSub = computed(() => {
  if (skillTab.value === 'market') return '多源聚合 · skills.sh / Smithery / ModelScope / SkillsMP / ClawHub / Anthropic / GitHub'
  if (skillTab.value === 'local') return '本地预置（template + config + .agents 三源合并）'
  return '先解析仓库技能，再勾选安装'
})

const manualSelectedCount = computed(() => manualSelected.value.length)
const manualCanInstall = computed(() => !!manualPreview.value && manualSelectedCount.value > 0)

watch(() => manualSkillInput.value, () => {
  // 源变更后清空旧预览，避免装错包
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
})

function isSourceOn(src: SkillSourceId) {
  return skillMarketSources.value.includes(src)
}

function sourceTagClass(source: string) {
  return String(source || '').toLowerCase().replace(/[^a-z0-9]/g, '')
}

function sourceLabel(s: any) {
  return s.source_label || SKILL_SOURCE_LABELS[s.source as SkillSourceId] || s.source || 'market'
}

async function openDrawer(tab: 'market' | 'local' | 'manual' = 'market') {
  skillTab.value = tab
  if (tab === 'local') await loadLocalSkills()
  drawerOpen.value = true
  await nextTick()
  if (tab === 'market') marketInput.value?.focus()
  else if (tab === 'local') localFilterInput.value?.focus()
  else manualInput.value?.focus()
}

function closeDrawer() {
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
  searchSkills()
}

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
      <Transition name="skill-drawer">
        <div v-if="drawerOpen" class="drawer-root">
          <div class="drawer-overlay" @click="closeDrawer" />
          <aside
            class="drawer-panel wide"
            role="dialog"
            aria-modal="true"
            aria-labelledby="skill-drawer-title"
          >
            <div class="drawer-h">
              <div>
                <h3 id="skill-drawer-title">添加技能</h3>
                <p class="sub">{{ drawerSub }}</p>
              </div>
              <button type="button" class="btn btn-icon btn-ghost" aria-label="关闭抽屉" @click="closeDrawer">
                <svg viewBox="0 0 24 24"><path d="M18 6 6 18M6 6l12 12"/></svg>
              </button>
            </div>

            <div class="drawer-b">
              <div class="tabs">
                <button type="button" :class="{ on: skillTab === 'market' }" @click="skillTab = 'market'">市场搜索</button>
                <button type="button" :class="{ on: skillTab === 'local' }" @click="skillTab = 'local'; loadLocalSkills()">本地预置</button>
                <button type="button" :class="{ on: skillTab === 'manual' }" @click="skillTab = 'manual'">手动安装</button>
              </div>

              <div v-show="skillTab === 'market'">
                <div class="agg-search">
                  <input
                    ref="marketInput"
                    v-model="skillSearchQ"
                    placeholder="关键词，如：react、设计、API…"
                    @keydown.enter="searchSkills"
                  />
                  <button type="button" class="btn btn-primary" :disabled="skillSearching" @click="searchSkills">
                    <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3-3"/></svg>
                    搜索
                  </button>
                </div>

                <div class="src-filters" role="group" aria-label="数据源过滤">
                  <button
                    v-for="src in SKILL_SOURCE_ORDER"
                    :key="src"
                    type="button"
                    class="src-chip"
                    :class="{ on: isSourceOn(src) }"
                    :data-src="src"
                    :aria-pressed="isSourceOn(src)"
                    :title="src === 'github' ? '配置 GITHUB_TOKEN 可启用 filename:SKILL.md code search' : undefined"
                    @click="toggleSkillSource(src)"
                  >
                    <span class="check" aria-hidden="true">
                      <svg v-if="isSourceOn(src)" viewBox="0 0 24 24"><path d="M5 12l5 5L20 7"/></svg>
                    </span>
                    {{ SKILL_SOURCE_LABELS[src] }}
                  </button>
                </div>

                <div v-if="skillSearched && sourceMetaItems.length" class="src-meta">
                  <span
                    v-for="m in sourceMetaItems"
                    :key="m.id"
                    class="src-meta-item"
                    :class="{ err: !!m.error }"
                    :title="m.error || undefined"
                  >
                    {{ m.label }} · <span class="n">{{ m.error ? '失败' : m.count }}</span>
                  </span>
                </div>

                <div class="agg-status">
                  <template v-if="skillSearching"><span>正在并行查询各源…</span></template>
                  <template v-else-if="skillSearched">
                    <span>共 <strong>{{ skillSearchResults.length }}</strong> 条（已跨源去重）</span>
                    <span>标签标明来源</span>
                  </template>
                  <template v-else>
                    <span>并行检索已选市场；GitHub / SkillsMP 可配可选 Key</span>
                  </template>
                </div>

                <div v-if="skillSearching" class="m-loading">
                  <div class="spinner" aria-hidden="true" />
                  聚合搜索中…
                </div>
                <div v-else-if="!skillSearched" class="m-hint">
                  输入关键词，从多个 Skills 市场一次搜齐。<br />每条结果带<strong>来源标签</strong>。
                  <div class="suggest-row">
                    <button v-for="s in SUGGESTS" :key="s" type="button" class="suggest" @click="suggestSearch(s)">{{ s }}</button>
                  </div>
                </div>
                <div v-else-if="!skillSearchResults.length" class="m-empty">无结果。换个关键词，或调整上方数据源。</div>
                <div v-else class="m-list">
                  <article
                    v-for="s in skillSearchResults"
                    :key="(s.source || '') + ':' + (s.name || '') + ':' + (s.install_command || '')"
                    class="m-card"
                    :class="'src-' + sourceTagClass(s.source)"
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
                    <div class="btn-cluster">
                      <button type="button" class="btn btn-soft btn-sm" @click="installFromSearch(s)">
                        <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>
                        安装
                      </button>
                    </div>
                  </article>
                </div>
              </div>

              <div v-show="skillTab === 'local'">
                <div class="agg-search">
                  <input
                    ref="localFilterInput"
                    v-model="localFilterQ"
                    placeholder="筛选本地预置…"
                  />
                </div>
                <div class="agg-status">
                  <span>共 <strong>{{ filteredLocalSkills.length }}</strong> / {{ localSkills.length }} 个预置</span>
                </div>
                <div v-if="!filteredLocalSkills.length" class="m-empty">
                  {{ localSkills.length ? '无匹配预置技能' : '暂无本地预置技能' }}
                </div>
                <div v-else class="m-list">
                  <article
                    v-for="s in filteredLocalSkills"
                    :key="s.skill_name"
                    class="m-card src-local"
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
                    <div class="btn-cluster">
                      <button type="button" class="btn btn-secondary btn-sm" @click="viewSkillMd(s.skill_name)">
                        <svg viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8S1 12 1 12z"/><circle cx="12" cy="12" r="3"/></svg>
                        查看
                      </button>
                      <button
                        type="button"
                        class="btn btn-soft btn-sm"
                        @click="installFromSearch({ source: 'local', name: s.skill_name, description: s.description, install_command: '' })"
                      >
                        <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>
                        安装
                      </button>
                    </div>
                  </article>
                </div>
              </div>

              <div v-show="skillTab === 'manual'" class="manual-form">
                <div class="field full">
                  <label>安装源 *</label>
                  <div class="agg-search" style="margin-bottom:0">
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
            </div>

            <div class="drawer-f">
              <template v-if="skillTab === 'market' || skillTab === 'local'">
                <button type="button" class="btn btn-secondary" @click="closeDrawer">关闭</button>
              </template>
              <template v-else>
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
              </template>
            </div>
          </aside>
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
.btn-primary { background: #165dff; color: #fff; box-shadow: 0 1px 2px rgba(22,93,255,.22); }
.btn-primary:hover:not(:disabled) { background: #0e42d2; }
.btn-soft { background: #eef4ff; color: #0e42d2; border-color: #d9e6ff; }
.btn-soft:hover:not(:disabled) { background: #d9e6ff; }
.btn-secondary { background: #fff; color: #4e5969; border-color: #e5e6eb; }
.btn-secondary:hover:not(:disabled) { background: #f7f8fa; border-color: #c9cdd4; }
.btn-ghost { background: transparent; color: #4e5969; }
.btn-ghost:hover:not(:disabled) { background: #f7f8fa; color: #1f2329; }
.btn-danger { background: transparent; color: #86909c; }
.btn-danger:hover:not(:disabled), .btn-danger:focus-visible { background: var(--red-bg); color: var(--red); border-color: var(--red-border); }

.btn-cluster { display: inline-flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.btn-cluster .split { width: 1px; height: 20px; background: #e5e6eb; margin: 0 2px; }
.btn-pair {
  display: inline-flex; border-radius: 8px; overflow: hidden;
  border: 1px solid #e5e6eb; background: #fff;
}
.btn-pair .btn { border-radius: 0; border: none; height: 32px; border-right: 1px solid #e5e6eb; }
.btn-pair .btn:last-child { border-right: none; }

.kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.kpi {
  background: #fff; border-radius: 12px; padding: 16px 18px;
  box-shadow: 0 1px 2px rgba(0,0,0,.04), 0 4px 12px rgba(0,0,0,.06);
  border: 1px solid rgba(0,0,0,.03); position: relative; overflow: hidden;
}
.kpi::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: #c9cdd4; }
.kpi.live::before { background: var(--green); }
.kpi.warn::before { background: var(--amber); }
.kpi.brand::before { background: #165dff; }
.kpi b { display: block; font-size: 22px; font-variant-numeric: tabular-nums; line-height: 1.1; color: #1f2329; }
.kpi span { font-size: 12px; color: #86909c; }
.kpi em { font-style: normal; font-size: 11px; color: #86909c; margin-top: 6px; display: block; }

.panel {
  background: #fff; border-radius: 14px;
  box-shadow: 0 1px 2px rgba(0,0,0,.04), 0 4px 12px rgba(0,0,0,.06);
  border: 1px solid rgba(0,0,0,.03); overflow: hidden;
}
.toolbar {
  display: flex; justify-content: space-between; gap: 14px; flex-wrap: wrap;
  padding: 14px 18px; border-bottom: 1px solid #e5e6eb; align-items: center;
}
.toolbar-left { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
.search {
  display: flex; align-items: center; gap: 8px; height: 34px; padding: 0 10px;
  border: 1px solid #c9cdd4; border-radius: 8px; background: #fff; min-width: 220px;
}
.search input { border: none; outline: none; flex: 1; font-size: 12px; min-width: 0; background: transparent; }
.seg { display: inline-flex; background: #f7f8fa; padding: 3px; border-radius: 8px; }
.seg button {
  height: 28px; padding: 0 10px; border-radius: 6px; font-size: 12px; font-weight: 600;
  color: #86909c; border: none; background: transparent; cursor: pointer;
}
.seg button.on { background: #fff; color: #0e42d2; box-shadow: 0 1px 2px rgba(0,0,0,.06); }

.table-wrap { max-height: min(560px, 62vh); overflow: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th {
  text-align: left; font-size: 11px; font-weight: 600; color: #86909c; text-transform: uppercase;
  letter-spacing: .04em; padding: 11px 18px; background: #f7f8fa; border-bottom: 1px solid #e5e6eb;
  position: sticky; top: 0; z-index: 1;
}
td { padding: 13px 18px; border-bottom: 1px solid #f7f8fa; vertical-align: middle; }
tr:hover td { background: #fafbfd; }
tr.disabled td { opacity: .62; }
.name { font-weight: 650; color: #1f2329; }
.cmd {
  font-family: 'JetBrains Mono', Consolas, monospace; font-size: 11px; color: #86909c;
  max-width: 420px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.status { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 600; }
.status i { width: 7px; height: 7px; border-radius: 50%; background: #c9cdd4; display: inline-block; }
.status.on { color: var(--green); }
.status.on i { background: var(--green); box-shadow: 0 0 0 3px var(--green-bg); }
.status.off { color: #86909c; }
.switch {
  width: 36px; height: 20px; border-radius: 999px; background: #c9cdd4; position: relative;
  border: none; cursor: pointer; transition: background .2s; padding: 0;
}
.switch::after {
  content: ""; position: absolute; top: 2px; left: 2px; width: 16px; height: 16px; border-radius: 50%;
  background: #fff; transition: transform .2s; box-shadow: 0 1px 2px rgba(0,0,0,.15);
}
.switch.on { background: #165dff; }
.switch.on::after { transform: translateX(16px); }
.ops { display: inline-flex; align-items: center; gap: 4px; padding: 2px; border-radius: 9px; }
tr:hover .ops { background: #f7f8fa; }
.ops .btn-soft { border-color: transparent; background: transparent; color: #0e42d2; }
.ops .btn-soft:hover { background: #fff; border-color: #d9e6ff; }
.empty-cell { text-align: center; color: #86909c; padding: 36px !important; }

.keys-bar {
  background: #fff; border-radius: 14px; padding: 16px 18px;
  box-shadow: 0 1px 2px rgba(0,0,0,.04), 0 4px 12px rgba(0,0,0,.06);
  border: 1px solid rgba(0,0,0,.03);
  display: flex; justify-content: space-between; align-items: center; gap: 14px; flex-wrap: wrap;
}
.keys-bar h2 { margin: 0 0 2px; font-size: 14px; color: #1f2329; }
.keys-bar p { margin: 0; font-size: 12px; color: #86909c; }

.drawer-root { position: fixed; inset: 0; z-index: 60; }
.drawer-overlay { position: absolute; inset: 0; background: rgba(31,35,41,.36); }
.drawer-panel {
  position: absolute; top: 0; right: 0; width: min(440px, 100%); height: 100%; background: #fff;
  box-shadow: -8px 0 32px rgba(0,0,0,.12); display: flex; flex-direction: column;
}
.drawer-panel.wide { width: min(560px, 100%); }
.drawer-h {
  padding: 18px 20px 16px; border-bottom: 1px solid #e5e6eb;
  display: flex; justify-content: space-between; align-items: flex-start; gap: 12px;
}
.drawer-h h3 { margin: 0 0 4px; font-size: 15px; font-weight: 650; color: #1f2329; }
.drawer-h .sub { margin: 0; font-size: 12px; color: #86909c; line-height: 1.4; }
.drawer-b { flex: 1; overflow: auto; padding: 18px 20px; }
.drawer-f {
  padding: 14px 20px; border-top: 1px solid #e5e6eb;
  display: flex; gap: 8px; justify-content: flex-end; background: #f7f8fa;
}

.tabs { display: flex; gap: 4px; margin-bottom: 14px; background: #f7f8fa; padding: 3px; border-radius: 10px; }
.tabs button {
  flex: 1; height: 32px; border-radius: 8px; font-size: 12px; font-weight: 600;
  color: #86909c; border: none; background: transparent; cursor: pointer;
}
.tabs button.on { background: #fff; color: #0e42d2; box-shadow: 0 1px 2px rgba(0,0,0,.06); }

.agg-search { display: flex; gap: 8px; margin-bottom: 12px; }
.agg-search input {
  flex: 1; height: 40px; border: 1px solid #c9cdd4; border-radius: 10px; padding: 0 12px; font-size: 13px;
}
.agg-search .btn { height: 40px; padding: 0 14px; border-radius: 10px; }

.src-filters { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.src-chip {
  height: 30px; padding: 0 12px 0 8px; border-radius: 999px; font-size: 12px; font-weight: 650;
  border: 1.5px solid #e5e6eb; background: #fff; color: #86909c;
  display: inline-flex; align-items: center; gap: 6px; cursor: pointer;
  transition: background .15s ease, color .15s ease, border-color .15s ease, box-shadow .15s ease;
}
.src-chip .check {
  width: 16px; height: 16px; border-radius: 50%; flex-shrink: 0;
  display: grid; place-items: center;
  border: 1.5px solid #c9cdd4; background: #fff;
}
.src-chip .check svg {
  width: 10px; height: 10px; stroke: #fff; fill: none; stroke-width: 3;
  stroke-linecap: round; stroke-linejoin: round;
}
.src-chip:hover:not(.on) { border-color: #c9cdd4; color: #4e5969; background: #f7f8fa; }
.src-chip.on { color: #fff; box-shadow: 0 1px 2px rgba(31, 35, 41, 0.12); }
.src-chip.on .check { border-color: rgba(255, 255, 255, 0.35); background: rgba(255, 255, 255, 0.22); }
.src-chip[data-src="skillssh"].on { background: #165dff; border-color: #165dff; }
.src-chip[data-src="smithery"].on { background: #722ed1; border-color: #722ed1; }
.src-chip[data-src="modelscope"].on { background: #00b42a; border-color: #00b42a; }
.src-chip[data-src="skillsmp"].on { background: #0e42d2; border-color: #0e42d2; }
.src-chip[data-src="clawhub"].on { background: #ff7d00; border-color: #ff7d00; }
.src-chip[data-src="anthropics"].on { background: #d97706; border-color: #d97706; }
.src-chip[data-src="github"].on { background: #4e5969; border-color: #4e5969; }
.src-chip.on:hover { filter: brightness(1.05); }

.src-meta {
  display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px;
  padding: 8px 10px; border-radius: 10px; background: #f7f8fa;
}
.src-meta-item {
  font-size: 11px; color: #4e5969; display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 8px; border-radius: 6px; background: #fff; border: 1px solid #e5e6eb;
}
.src-meta-item.err { color: var(--red); border-color: var(--red-border); background: var(--red-bg); }
.src-meta-item .n { font-weight: 700; font-variant-numeric: tabular-nums; color: #1f2329; }
.src-meta-item.err .n { color: var(--red); }

.agg-status {
  font-size: 12px; color: #86909c; margin-bottom: 10px;
  display: flex; justify-content: space-between; gap: 8px; flex-wrap: wrap;
}
.agg-status strong { color: #1f2329; font-weight: 650; }

.m-list { display: grid; gap: 10px; }
.m-card {
  border: 1px solid #e5e6eb; border-radius: 12px; padding: 12px 12px 12px 14px;
  position: relative; overflow: hidden; transition: border-color .15s, box-shadow .15s;
}
.m-card::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: #c9cdd4; }
.m-card.src-skillssh::before { background: #165dff; }
.m-card.src-smithery::before { background: #722ed1; }
.m-card.src-modelscope::before { background: #00b42a; }
.m-card.src-skillsmp::before { background: #0e42d2; }
.m-card.src-clawhub::before { background: #ff7d00; }
.m-card.src-anthropics::before { background: #d97706; }
.m-card.src-github::before { background: #4e5969; }
.m-card.src-local::before { background: #722ed1; }
.m-card:hover { border-color: #d9e6ff; box-shadow: 0 1px 2px rgba(0,0,0,.04), 0 4px 12px rgba(0,0,0,.06); }
.m-card-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 6px; }
.m-card h4 { margin: 0; font-size: 13px; font-weight: 650; line-height: 1.3; min-width: 0; word-break: break-word; color: #1f2329; }
.m-tags { display: flex; flex-wrap: wrap; gap: 4px; justify-content: flex-end; flex-shrink: 0; }
.src-tag {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 10px; font-weight: 700; padding: 3px 8px; border-radius: 999px;
  border: 1px solid transparent; white-space: nowrap;
}
.src-tag .dot { width: 5px; height: 5px; border-radius: 50%; }
.src-tag.skillssh { background: #eef4ff; color: #0e42d2; border-color: #d9e6ff; }
.src-tag.skillssh .dot { background: #165dff; }
.src-tag.smithery { background: #f5e8ff; color: #722ed1; border-color: #e6d0ff; }
.src-tag.smithery .dot { background: #722ed1; }
.src-tag.modelscope { background: #e8ffea; color: #00b42a; border-color: #b7ebc4; }
.src-tag.modelscope .dot { background: #00b42a; }
.src-tag.skillsmp { background: #eef4ff; color: #0e42d2; border-color: #d9e6ff; }
.src-tag.skillsmp .dot { background: #0e42d2; }
.src-tag.clawhub { background: #fff7e8; color: #ff7d00; border-color: #ffe0b3; }
.src-tag.clawhub .dot { background: #ff7d00; }
.src-tag.anthropics { background: #fff7ed; color: #c2410c; border-color: #fed7aa; }
.src-tag.anthropics .dot { background: #d97706; }
.src-tag.github { background: #f7f8fa; color: #1f2329; border-color: #c9cdd4; }
.src-tag.github .dot { background: #4e5969; }
.src-tag.local { background: #f5e8ff; color: #722ed1; border-color: #e6d0ff; }
.src-tag.local .dot { background: #722ed1; }
.host-tag {
  font-size: 10px; font-weight: 700; padding: 3px 7px; border-radius: 999px;
  background: #e8ffea; color: #00b42a; border: 1px solid #b7ebc4;
}
.m-card .meta {
  font-size: 11px; color: #86909c; margin-bottom: 6px;
  font-family: 'JetBrains Mono', Consolas, monospace;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.m-card p {
  margin: 0 0 10px; font-size: 12px; color: #4e5969; line-height: 1.45;
  display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.cmd-line {
  font-family: 'JetBrains Mono', Consolas, monospace; font-size: 10px; color: #86909c;
  margin: -4px 0 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.m-empty, .m-loading, .m-hint {
  text-align: center; padding: 36px 16px; color: #86909c; font-size: 13px; line-height: 1.5;
}
.m-loading { display: flex; flex-direction: column; align-items: center; gap: 10px; }
.spinner {
  width: 22px; height: 22px; border: 2.5px solid #d9e6ff; border-top-color: #165dff;
  border-radius: 50%; animation: skill-spin .7s linear infinite;
}
@keyframes skill-spin { to { transform: rotate(360deg); } }
.suggest-row { display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; margin-top: 12px; }
.suggest {
  height: 28px; padding: 0 10px; border-radius: 999px; font-size: 12px; font-weight: 600;
  background: #fff; border: 1px solid #e5e6eb; color: #4e5969; cursor: pointer;
}
.suggest:hover { border-color: #d9e6ff; color: #0e42d2; background: #eef4ff; }

.manual-form { display: grid; grid-template-columns: 1fr; gap: 12px; }
.field { display: flex; flex-direction: column; gap: 6px; margin-bottom: 0; }
.field.full { grid-column: 1 / -1; }
.field label { font-size: 12px; font-weight: 600; color: #4e5969; }
.field input {
  width: 100%; border: 1px solid #c9cdd4; border-radius: 8px; padding: 9px 11px; font-size: 13px;
  background: #fff; color: #1f2329;
}
.keys-hint { margin: 0; font-size: 12px; color: #86909c; line-height: 1.5; }
.keys-hint code {
  font-size: 11px; padding: 0 4px; border-radius: 4px; background: #f7f8fa;
  font-family: 'JetBrains Mono', Consolas, monospace;
}

.picker-bar {
  display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap;
  margin-top: 4px;
}
.picker-meta { font-size: 12px; color: #4e5969; }
.picker-meta strong { color: #1f2329; font-weight: 700; }
.picker-meta .muted { color: #86909c; margin-left: 4px; word-break: break-all; }

.pick-list { display: grid; gap: 8px; max-height: min(420px, 48vh); overflow: auto; padding-right: 2px; }
.pick-row {
  display: flex; gap: 10px; align-items: flex-start;
  padding: 10px 12px; border: 1px solid #e5e6eb; border-radius: 10px;
  background: #fff; cursor: pointer; transition: border-color .15s, background .15s;
}
.pick-row:hover { border-color: #d9e6ff; background: #fafbfd; }
.pick-row.on { border-color: #a8c5ff; background: #eef4ff; }
.pick-check {
  width: 16px; height: 16px; margin-top: 2px; flex-shrink: 0;
  accent-color: #165dff; cursor: pointer;
}
.pick-body { min-width: 0; flex: 1; }
.pick-name { font-size: 13px; font-weight: 650; color: #1f2329; line-height: 1.3; }
.pick-desc {
  margin-top: 4px; font-size: 12px; color: #86909c; line-height: 1.45;
  display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}

.skill-drawer-enter-active, .skill-drawer-leave-active { transition: opacity .2s ease; }
.skill-drawer-enter-active .drawer-panel, .skill-drawer-leave-active .drawer-panel {
  transition: transform .22s ease-out;
}
.skill-drawer-enter-from, .skill-drawer-leave-to { opacity: 0; }
.skill-drawer-enter-from .drawer-panel, .skill-drawer-leave-to .drawer-panel { transform: translateX(100%); }

@media (max-width: 900px) {
  .kpis { grid-template-columns: 1fr 1fr; }
  .cmd { max-width: 160px; }
}
@media (prefers-reduced-motion: reduce) {
  .btn, .switch, .switch::after, .spinner,
  .skill-drawer-enter-active, .skill-drawer-leave-active,
  .skill-drawer-enter-active .drawer-panel, .skill-drawer-leave-active .drawer-panel {
    transition: none !important; animation: none !important;
  }
}
</style>
