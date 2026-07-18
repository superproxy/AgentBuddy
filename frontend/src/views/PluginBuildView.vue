<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { usePluginBuildStore, wizardSteps } from '../stores/pluginBuild'
import { useEnvStore } from '../stores/env'
import { useMcpStore } from '../stores/mcp'
import { useSkillStore } from '../stores/skill'
import { usePluginStore } from '../stores/plugin'
import { useAiGenerateStore } from '../stores/aiGenerate'

type CatKey = 'llm' | 'mcp' | 'skill' | 'agent' | 'rule' | 'cmd'

const pb = usePluginBuildStore()
const env = useEnvStore()
const mcp = useMcpStore()
const skill = useSkillStore()
const plugin = usePluginStore()
const ai = useAiGenerateStore()
const { dialogOpen, prompt, level, generating, output, generatedConfig } = storeToRefs(ai)

const {
  pluginForm, selectedSkills, selectedMcp, selectedLlm,
  selectedSubagents, selectedRules, selectedCommands, hooksEnabled,
  availableSubagents, availableRules, availableCommands,
  ideImport, ideImportStats, importedIdeMcp, wizardStep, buildMode, mcpFilterText, importing,
} = storeToRefs(pb)
const { mcpTemplate } = storeToRefs(mcp)
const { skillCategories, filteredLocalSkills, skillFilter } = storeToRefs(skill)
const { plugins, selectedPluginFile } = storeToRefs(plugin)

const {
  toggleSkill, toggleMcp, toggleLlm, toggleSubagent, toggleRule, toggleCommand,
  llmKey, wizardNext, wizardPrev, wizardGoto, newPlugin, loadBuildSources,
  importFromIde, applyImportedMcp, applyImportedSkills, applyImportedLlm,
  loadExistingPlugin, previewPlugin, savePluginFile, installPluginFile,
} = pb
const { loadLocalSkills } = skill
const { refreshPluginList } = plugin

const activeCat = ref<CatKey>('llm')
const listFilter = ref('')
const nameTouched = ref(false)

const CAT_META: Record<CatKey, { title: string; hint: string; label: string; sub: string }> = {
  llm: { title: '本地 LLM', hint: '勾选要打包的 Provider', label: 'LLM', sub: '模型 Provider' },
  mcp: { title: '本地 MCP', hint: '过滤并勾选 MCP 服务', label: 'MCP', sub: '工具服务' },
  skill: { title: '本地 Skill', hint: '按名称或描述搜索', label: 'Skill', sub: '技能包' },
  agent: { title: 'Subagent', hint: '选择要打包的角色', label: 'Agent', sub: '子代理' },
  rule: { title: 'Rules', hint: '选择规则文件', label: 'Rules', sub: '规则约束' },
  cmd: { title: 'Commands', hint: '选择斜杠命令', label: 'Cmd', sub: '斜杠命令' },
}

const localLlmList = computed(() => {
  const llm = env.envData.llm || {}
  const out: any[] = []
  for (const [provider, val] of Object.entries(llm)) {
    if (provider.startsWith('_') || provider === 'proxy') continue
    if (!val || typeof val !== 'object') continue
    for (const [protocol, raw] of Object.entries(val as any)) {
      const cfg = raw as { base_url?: string; api_key?: string; models?: Record<string, unknown> }
      if (!raw || typeof raw !== 'object') continue
      out.push({
        provider,
        protocol,
        base_url: cfg.base_url || '',
        has_key: !!cfg.api_key,
        model_count: Object.keys(cfg.models || {}).length,
        active: llm._active_provider === provider,
      })
    }
  }
  return out
})

const mcpNames = computed(() => Object.keys(mcpTemplate.value.mcpServers || {}))

const counts = computed(() => ({
  llm: selectedLlm.value.length,
  mcp: selectedMcp.value.length,
  skill: selectedSkills.value.length,
  agent: selectedSubagents.value.length,
  rule: selectedRules.value.length,
  cmd: selectedCommands.value.length,
}))

const totalSelected = computed(() =>
  counts.value.llm + counts.value.mcp + counts.value.skill
  + counts.value.agent + counts.value.rule + counts.value.cmd
  + (hooksEnabled.value ? 1 : 0),
)

const filledLayers = computed(() =>
  (['llm', 'mcp', 'skill', 'agent', 'rule', 'cmd'] as CatKey[]).filter(k => counts.value[k] > 0).length,
)

const completeness = computed(() => {
  const filled = filledLayers.value + (hooksEnabled.value ? 1 : 0)
  return Math.round((filled / 7) * 100)
})

const canGenerate = computed(() => completeness.value >= 70 && !!pluginForm.value.name.trim())

const catTitle = computed(() => CAT_META[activeCat.value].title)
const catHint = computed(() => CAT_META[activeCat.value].hint)

const catTotal = computed(() => {
  switch (activeCat.value) {
    case 'llm': return localLlmList.value.length
    case 'mcp': return mcpNames.value.length
    case 'skill': return filteredLocalSkills.value.length
    case 'agent': return availableSubagents.value.length
    case 'rule': return availableRules.value.length
    case 'cmd': return availableCommands.value.length
  }
})

const catSelected = computed(() => counts.value[activeCat.value])

const q = computed(() => listFilter.value.trim().toLowerCase())

const filteredLlms = computed(() => {
  const qq = q.value
  if (!qq) return localLlmList.value
  return localLlmList.value.filter(l =>
    l.provider.toLowerCase().includes(qq)
    || l.protocol.toLowerCase().includes(qq)
    || (l.base_url || '').toLowerCase().includes(qq),
  )
})

const filteredMcps = computed(() => {
  const qq = q.value || mcpFilterText.value.trim().toLowerCase()
  if (!qq) return mcpNames.value
  return mcpNames.value.filter(n => n.toLowerCase().includes(qq))
})

const filteredSkills = computed(() => {
  const qq = q.value
  if (!qq) return filteredLocalSkills.value
  return filteredLocalSkills.value.filter((s: any) =>
    (s.skill_name || '').toLowerCase().includes(qq)
    || (s.description || '').toLowerCase().includes(qq),
  )
})

const filteredAgents = computed(() => {
  const qq = q.value
  if (!qq) return availableSubagents.value
  return availableSubagents.value.filter((sa: any) =>
    (sa.name || '').toLowerCase().includes(qq)
    || (sa.desc || '').toLowerCase().includes(qq)
    || (sa.role || '').toLowerCase().includes(qq),
  )
})

const filteredRules = computed(() => {
  const qq = q.value
  if (!qq) return availableRules.value
  return availableRules.value.filter((r: any) =>
    (r.path || '').toLowerCase().includes(qq)
    || (r.description || '').toLowerCase().includes(qq),
  )
})

const filteredCmds = computed(() => {
  const qq = q.value
  if (!qq) return availableCommands.value
  return availableCommands.value.filter((c: any) =>
    (c.name || '').toLowerCase().includes(qq)
    || (c.description || '').toLowerCase().includes(qq),
  )
})

const packSections = computed(() => [
  { key: 'llm' as CatKey, label: 'LLM', items: selectedLlm.value.map(id => ({ id, label: id.split('@')[0] || id })) },
  { key: 'mcp' as CatKey, label: 'MCP', items: selectedMcp.value.map(id => ({ id, label: id })) },
  { key: 'skill' as CatKey, label: 'Skill', items: selectedSkills.value.map(id => ({ id, label: id })) },
  { key: 'agent' as CatKey, label: 'Agent', items: selectedSubagents.value.map(id => ({ id, label: id })) },
  { key: 'rule' as CatKey, label: 'Rules', items: selectedRules.value.map(id => ({ id, label: id.split(/[/\\]/).pop() || id })) },
  { key: 'cmd' as CatKey, label: 'Cmd', items: selectedCommands.value.map(id => ({ id, label: id })) },
])

function initials(text: string) {
  const t = (text || '?').replace(/[^a-zA-Z0-9\u4e00-\u9fa5]/g, '')
  return (t.slice(0, 2) || '?').toUpperCase()
}

function switchCat(key: CatKey) {
  activeCat.value = key
  listFilter.value = ''
  if (key !== 'mcp') mcpFilterText.value = ''
  if (key !== 'skill') {
    skillFilter.value.text = ''
  }
}

function removePack(key: CatKey, id: string) {
  switch (key) {
    case 'llm': toggleLlm(id); break
    case 'mcp': toggleMcp(id); break
    case 'skill': toggleSkill(id); break
    case 'agent': toggleSubagent(id); break
    case 'rule': toggleRule(id); break
    case 'cmd': toggleCommand(id); break
  }
}

function selectAllCat() {
  switch (activeCat.value) {
    case 'llm':
      for (const l of localLlmList.value) {
        const k = llmKey(l)
        if (!selectedLlm.value.includes(k)) toggleLlm(k)
      }
      break
    case 'mcp':
      for (const n of mcpNames.value) {
        if (!selectedMcp.value.includes(n)) toggleMcp(n)
      }
      break
    case 'skill':
      for (const s of filteredLocalSkills.value) {
        if (!selectedSkills.value.includes(s.skill_name)) toggleSkill(s.skill_name)
      }
      break
    case 'agent':
      for (const sa of availableSubagents.value) {
        if (!selectedSubagents.value.includes(sa.name)) toggleSubagent(sa.name)
      }
      break
    case 'rule':
      for (const r of availableRules.value) {
        if (!selectedRules.value.includes(r.path)) toggleRule(r.path)
      }
      break
    case 'cmd':
      for (const c of availableCommands.value) {
        if (!selectedCommands.value.includes(c.name)) toggleCommand(c.name)
      }
      break
  }
}

function clearCat() {
  switch (activeCat.value) {
    case 'llm':
      [...selectedLlm.value].forEach(k => toggleLlm(k))
      break
    case 'mcp':
      [...selectedMcp.value].forEach(n => toggleMcp(n))
      break
    case 'skill':
      [...selectedSkills.value].forEach(n => toggleSkill(n))
      break
    case 'agent':
      [...selectedSubagents.value].forEach(n => toggleSubagent(n))
      break
    case 'rule':
      [...selectedRules.value].forEach(p => toggleRule(p))
      break
    case 'cmd':
      [...selectedCommands.value].forEach(n => toggleCommand(n))
      break
  }
}

function onLoadPlugin() {
  if (selectedPluginFile.value) loadExistingPlugin()
}

function onClear() {
  nameTouched.value = false
  newPlugin()
}

onMounted(() => {
  loadLocalSkills()
  loadBuildSources()
  refreshPluginList()
})
</script>

<template>
  <div class="pb space-y-3.5">
    <!-- Header -->
    <div class="pb-head">
      <div>
        <h1 class="pb-title">插件构建</h1>
        <p class="pb-sub">按类型浏览本地组件，勾选后写入右侧装箱清单，核对后命名打包</p>
      </div>
      <div class="pb-actions">
        <select
          v-model="selectedPluginFile"
          class="pb-select"
          aria-label="加载已有插件"
          @change="onLoadPlugin"
        >
          <option value="">加载已有…</option>
          <option v-for="p in plugins" :key="p.file" :value="p.file">{{ p.name }}</option>
        </select>
        <button type="button" class="pb-btn pb-btn-ghost" @click="onClear">清空</button>
        <span class="pb-split" aria-hidden="true" />
        <button type="button" class="pb-btn pb-btn-soft" @click="previewPlugin">
          <svg viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" /></svg>
          预览
        </button>
        <button type="button" class="pb-btn pb-btn-secondary" @click="savePluginFile">保存</button>
        <button type="button" class="pb-btn pb-btn-success" @click="installPluginFile">
          <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></svg>
          生成配置
        </button>
      </div>
    </div>

    <!-- Toolbar -->
    <div class="pb-toolbar">
      <span class="pb-toolbar-label">构建来源</span>
      <div class="pb-seg" role="tablist">
        <button
          type="button"
          role="tab"
          :class="{ on: buildMode === 'local' }"
          :aria-selected="buildMode === 'local'"
          @click="buildMode = 'local'"
        >
          本地仓库
        </button>
        <button
          type="button"
          role="tab"
          :class="{ on: buildMode === 'ide' }"
          :aria-selected="buildMode === 'ide'"
          @click="buildMode = 'ide'"
        >
          IDE 导入
        </button>
        <button
          type="button"
          role="tab"
          :class="{ on: buildMode === 'ai' }"
          :aria-selected="buildMode === 'ai'"
          @click="buildMode = 'ai'"
        >
          AI 生成
        </button>
      </div>
      <div class="pb-chips" aria-live="polite">
        <span class="pb-chip" :class="{ has: counts.llm }">LLM {{ counts.llm }}</span>
        <span class="pb-chip" :class="{ has: counts.mcp }">MCP {{ counts.mcp }}</span>
        <span class="pb-chip" :class="{ has: counts.skill }">Skill {{ counts.skill }}</span>
        <span class="pb-chip" :class="{ has: counts.agent }">Agent {{ counts.agent }}</span>
        <span class="pb-chip" :class="{ has: counts.rule }">Rule {{ counts.rule }}</span>
        <span class="pb-chip" :class="{ has: counts.cmd }">Cmd {{ counts.cmd }}</span>
        <span v-if="hooksEnabled" class="pb-chip on">Hooks</span>
        <span class="pb-chip-meta" :title="`已填充类型 ${filledLayers}/6 · 装箱完整度 ${completeness}%`">
          {{ filledLayers }}/6 · {{ completeness }}%
        </span>
      </div>
    </div>

    <!-- 本地：资源台 -->
    <div v-show="buildMode === 'local'" class="pb-studio">
      <aside class="pb-rail" aria-label="组件类型">
        <div class="pb-rail-top">
          <div class="pb-rail-brand">
            <span class="mark" />
            <strong>组件库</strong>
            <em>BUILD</em>
          </div>
        </div>
        <div class="pb-rail-label">类型</div>
        <nav class="pb-rail-nav">
          <button
            v-for="key in (['llm','mcp','skill','agent','rule','cmd'] as CatKey[])"
            :key="key"
            type="button"
            class="pb-cat"
            :class="{ active: activeCat === key }"
            :aria-current="activeCat === key ? 'true' : 'false'"
            @click="switchCat(key)"
          >
            <span class="ico">
              <svg v-if="key === 'llm'" viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5z" /><path d="M2 17l10 5 10-5M2 12l10 5 10-5" /></svg>
              <svg v-else-if="key === 'mcp'" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3" /><path d="M12 2v4M12 18v4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M2 12h4M18 12h4M4.9 19.1l2.8-2.8M16.3 7.7l2.8-2.8" /></svg>
              <svg v-else-if="key === 'skill'" viewBox="0 0 24 24"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" /></svg>
              <svg v-else-if="key === 'agent'" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" /></svg>
              <svg v-else-if="key === 'rule'" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" /></svg>
              <svg v-else viewBox="0 0 24 24"><path d="M4 17l6-6-6-6M12 19h8" /></svg>
            </span>
            <span class="txt">{{ CAT_META[key].label }}<small>{{ CAT_META[key].sub }}</small></span>
            <span class="n" :class="{ empty: !counts[key] }">{{ counts[key] }}</span>
          </button>
        </nav>
        <div class="pb-rail-foot">切换类型浏览组件<br>右侧<strong>装箱清单</strong>实时汇总</div>
      </aside>

      <section class="pb-main" aria-label="组件列表">
        <div class="pb-main-top">
          <div class="pb-main-title">
            <h2>{{ catTitle }}</h2>
            <span class="pb-pill"><i />{{ catSelected }} / {{ catTotal }}</span>
            <span class="pb-hint">{{ catHint }}</span>
          </div>
          <div class="pb-main-tools">
            <div class="pb-search">
              <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="8" /><path d="M21 21l-4.3-4.3" /></svg>
              <input v-model="listFilter" type="search" placeholder="筛选名称或描述…" aria-label="搜索组件">
            </div>
            <template v-if="activeCat === 'skill'">
              <select v-model="skillFilter.cat" class="pb-select pb-select-sm">
                <option value="">全部分类</option>
                <option v-for="c in skillCategories" :key="c" :value="c">{{ c }}</option>
              </select>
            </template>
            <button type="button" class="pb-btn pb-btn-soft pb-btn-sm" @click="selectAllCat">全选</button>
            <button type="button" class="pb-btn pb-btn-ghost pb-btn-sm" @click="clearCat">取消本类</button>
          </div>
        </div>

        <div class="pb-list" role="listbox" aria-multiselectable="true">
          <!-- LLM -->
          <template v-if="activeCat === 'llm'">
            <div v-if="!filteredLlms.length" class="pb-empty">
              <div class="icon"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8" /><path d="M21 21l-4.3-4.3" /></svg></div>
              <strong>{{ localLlmList.length ? '没有匹配项' : '未配置 LLM Provider' }}</strong>
              <p>{{ localLlmList.length ? '换个关键词，或清空搜索查看全部' : '请到 LLM 配置 tab 添加' }}</p>
            </div>
            <button
              v-for="l in filteredLlms"
              :key="llmKey(l)"
              type="button"
              class="pb-item"
              :class="{ on: selectedLlm.includes(llmKey(l)) }"
              role="option"
              :aria-selected="selectedLlm.includes(llmKey(l))"
              @click="toggleLlm(llmKey(l))"
            >
              <span class="check" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5" /></svg></span>
              <span class="avatar">{{ initials(l.provider) }}</span>
              <span class="body">
                <span class="title">
                  {{ l.provider }}
                  <span class="tag">{{ l.protocol }}</span>
                  <span v-if="l.active" class="tag live">active</span>
                  <span v-if="l.has_key" class="tag live">key ✓</span>
                </span>
                <span class="meta">{{ l.base_url || '(无 base_url)' }} · {{ l.model_count }} 模型</span>
                <span class="foot">
                  <span class="dot" :class="{ on: l.active || l.has_key }" />
                  {{ selectedLlm.includes(llmKey(l)) ? '已加入装箱' : '点击加入装箱' }}
                </span>
              </span>
            </button>
          </template>

          <!-- MCP -->
          <template v-else-if="activeCat === 'mcp'">
            <div v-if="!filteredMcps.length" class="pb-empty">
              <div class="icon"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8" /><path d="M21 21l-4.3-4.3" /></svg></div>
              <strong>{{ mcpNames.length ? '没有匹配项' : '无可用 MCP' }}</strong>
              <p>{{ mcpNames.length ? '换个关键词试试' : '请到 MCP 配置 tab 添加' }}</p>
            </div>
            <button
              v-for="name in filteredMcps"
              :key="name"
              type="button"
              class="pb-item"
              :class="{ on: selectedMcp.includes(name) }"
              role="option"
              :aria-selected="selectedMcp.includes(name)"
              @click="toggleMcp(name)"
            >
              <span class="check" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5" /></svg></span>
              <span class="avatar">{{ initials(name) }}</span>
              <span class="body">
                <span class="title">{{ name }}</span>
                <span class="meta">MCP 服务</span>
                <span class="foot">
                  <span class="dot" :class="{ on: selectedMcp.includes(name) }" />
                  {{ selectedMcp.includes(name) ? '已加入装箱' : '点击加入装箱' }}
                </span>
              </span>
            </button>
          </template>

          <!-- Skill -->
          <template v-else-if="activeCat === 'skill'">
            <div v-if="!filteredSkills.length" class="pb-empty">
              <div class="icon"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8" /><path d="M21 21l-4.3-4.3" /></svg></div>
              <strong>没有匹配项</strong>
              <p>换个关键词或分类</p>
            </div>
            <button
              v-for="s in filteredSkills"
              :key="s.skill_name"
              type="button"
              class="pb-item"
              :class="{ on: selectedSkills.includes(s.skill_name) }"
              role="option"
              :aria-selected="selectedSkills.includes(s.skill_name)"
              @click="toggleSkill(s.skill_name)"
            >
              <span class="check" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5" /></svg></span>
              <span class="avatar">{{ initials(s.skill_name) }}</span>
              <span class="body">
                <span class="title">{{ s.skill_name }}</span>
                <span class="meta">{{ s.description || '无描述' }}</span>
                <span class="foot">
                  <span class="dot" :class="{ on: selectedSkills.includes(s.skill_name) }" />
                  {{ selectedSkills.includes(s.skill_name) ? '已加入装箱' : '点击加入装箱' }}
                </span>
              </span>
            </button>
          </template>

          <!-- Agent -->
          <template v-else-if="activeCat === 'agent'">
            <div v-if="!filteredAgents.length" class="pb-empty">
              <div class="icon"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8" /><path d="M21 21l-4.3-4.3" /></svg></div>
              <strong>{{ availableSubagents.length ? '没有匹配项' : '无可用 Subagent' }}</strong>
              <p>{{ availableSubagents.length ? '换个关键词试试' : '请到 Subagent tab 添加' }}</p>
            </div>
            <button
              v-for="sa in filteredAgents"
              :key="sa.name"
              type="button"
              class="pb-item"
              :class="{ on: selectedSubagents.includes(sa.name) }"
              role="option"
              :aria-selected="selectedSubagents.includes(sa.name)"
              @click="toggleSubagent(sa.name)"
            >
              <span class="check" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5" /></svg></span>
              <span class="avatar">{{ initials(sa.name) }}</span>
              <span class="body">
                <span class="title">{{ sa.name }}</span>
                <span class="meta">{{ sa.desc || sa.role || '无描述' }}</span>
                <span class="foot">
                  <span class="dot" :class="{ on: selectedSubagents.includes(sa.name) }" />
                  {{ selectedSubagents.includes(sa.name) ? '已加入装箱' : '点击加入装箱' }}
                </span>
              </span>
            </button>
          </template>

          <!-- Rules -->
          <template v-else-if="activeCat === 'rule'">
            <div v-if="!filteredRules.length" class="pb-empty">
              <div class="icon"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8" /><path d="M21 21l-4.3-4.3" /></svg></div>
              <strong>{{ availableRules.length ? '没有匹配项' : '无可用 Rule' }}</strong>
              <p>{{ availableRules.length ? '换个关键词试试' : '请到 Rules tab 添加' }}</p>
            </div>
            <button
              v-for="r in filteredRules"
              :key="r.path"
              type="button"
              class="pb-item"
              :class="{ on: selectedRules.includes(r.path) }"
              role="option"
              :aria-selected="selectedRules.includes(r.path)"
              @click="toggleRule(r.path)"
            >
              <span class="check" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5" /></svg></span>
              <span class="avatar">{{ initials(r.path) }}</span>
              <span class="body">
                <span class="title">{{ r.path }}</span>
                <span class="meta">{{ r.description || '无描述' }}</span>
                <span class="foot">
                  <span class="dot" :class="{ on: selectedRules.includes(r.path) }" />
                  {{ selectedRules.includes(r.path) ? '已加入装箱' : '点击加入装箱' }}
                </span>
              </span>
            </button>
          </template>

          <!-- Cmd -->
          <template v-else>
            <div v-if="!filteredCmds.length" class="pb-empty">
              <div class="icon"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8" /><path d="M21 21l-4.3-4.3" /></svg></div>
              <strong>{{ availableCommands.length ? '没有匹配项' : '无可用 Command' }}</strong>
              <p>{{ availableCommands.length ? '换个关键词试试' : '请到自定义命令 tab 添加' }}</p>
            </div>
            <button
              v-for="c in filteredCmds"
              :key="c.name"
              type="button"
              class="pb-item"
              :class="{ on: selectedCommands.includes(c.name) }"
              role="option"
              :aria-selected="selectedCommands.includes(c.name)"
              @click="toggleCommand(c.name)"
            >
              <span class="check" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5" /></svg></span>
              <span class="avatar">{{ initials(c.name) }}</span>
              <span class="body">
                <span class="title">{{ c.name }}</span>
                <span class="meta">{{ c.description || '无描述' }}</span>
                <span class="foot">
                  <span class="dot" :class="{ on: selectedCommands.includes(c.name) }" />
                  {{ selectedCommands.includes(c.name) ? '已加入装箱' : '点击加入装箱' }}
                </span>
              </span>
            </button>
          </template>
        </div>
      </section>

      <aside class="pb-manifest" aria-label="装箱清单">
        <div class="pb-manifest-head">
          <span class="pb-pill" :class="{ ready: canGenerate }">
            <i />{{ canGenerate ? '可生成' : '装箱中' }}
          </span>
          <div class="pb-pkg-row">
            <h3>{{ pluginForm.name.trim() || 'untitled' }}</h3>
            <span class="pb-pkg-ver">v{{ pluginForm.version.trim() || '0.0.0' }}</span>
          </div>
          <p class="pb-pkg-desc">{{ pluginForm.description.trim() || '填写描述，便于团队识别此插件' }}</p>
          <div class="pb-complete">
            完整度
            <div class="bar"><i :style="{ width: completeness + '%' }" /></div>
            <b>{{ completeness }}%</b>
          </div>
        </div>

        <div class="pb-form-block">
          <h4>插件定义</h4>
          <div class="pb-form">
            <div class="field span-2">
              <label for="pb-name">插件名 *</label>
              <input
                id="pb-name"
                v-model="pluginForm.name"
                placeholder="my-plugin"
                autocomplete="off"
                :class="{ err: nameTouched && !pluginForm.name.trim() }"
                @blur="nameTouched = true"
              >
              <div v-if="nameTouched && !pluginForm.name.trim()" class="field-err">插件名不能为空</div>
            </div>
            <div class="field">
              <label for="pb-ver">版本</label>
              <input id="pb-ver" v-model="pluginForm.version">
            </div>
            <div class="field">
              <label for="pb-author">作者</label>
              <input id="pb-author" v-model="pluginForm.author">
            </div>
            <div class="field span-2">
              <label for="pb-desc">描述</label>
              <input id="pb-desc" v-model="pluginForm.description">
            </div>
            <div class="field span-2">
              <label for="pb-script">安装脚本</label>
              <textarea id="pb-script" v-model="pluginForm.install_script" rows="2" placeholder="npm i -g xxx && xxx setup" />
            </div>
          </div>
        </div>

        <div class="pb-packing">
          <div
            v-for="sec in packSections"
            :key="sec.key"
            class="pb-pack-block"
            :class="{ empty: !sec.items.length }"
          >
            <button type="button" class="pb-pack-h" @click="switchCat(sec.key)">
              {{ sec.label }} <span>{{ sec.items.length }}</span>
              <span class="go">查看 →</span>
            </button>
            <div v-if="!sec.items.length" class="pb-pack-empty">
              <span>未选择</span>
              <button type="button" @click="switchCat(sec.key)">去选择 →</button>
            </div>
            <div v-else class="pb-pack-tags">
              <span v-for="it in sec.items" :key="it.id" class="pb-pack-tag" :title="it.id">
                <span class="txt">{{ it.label }}</span>
                <button type="button" class="x" :aria-label="'移除 ' + it.label" @click="removePack(sec.key, it.id)">
                  <svg viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12" /></svg>
                </button>
              </span>
            </div>
          </div>

          <label class="pb-hooks" :class="{ on: hooksEnabled }">
            <input v-model="hooksEnabled" type="checkbox">
            <span>打包 Hooks 配置</span>
            <span class="hook-meta">hooks.json</span>
          </label>
        </div>

        <div class="pb-manifest-foot">
          <button type="button" class="pb-btn pb-btn-success pb-btn-block" @click="installPluginFile">
            <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></svg>
            生成配置
          </button>
          <div class="row">
            <button type="button" class="pb-btn pb-btn-soft" style="flex:1" @click="previewPlugin">预览</button>
            <button type="button" class="pb-btn pb-btn-secondary" style="flex:1" @click="savePluginFile">保存</button>
          </div>
          <p class="hint-line">生成前会校验插件名</p>
        </div>
      </aside>
    </div>

    <!-- IDE 向导（保留功能，样式对齐） -->
    <div v-show="buildMode === 'ide'" class="pb-ide">
      <div class="pb-wizard-bar">
        <template v-for="(s, i) in wizardSteps" :key="i">
          <button
            type="button"
            class="pb-wiz-step"
            :class="{ active: wizardStep === i, done: wizardStep > i }"
            @click="wizardGoto(i)"
          >
            <span class="num">{{ wizardStep > i ? '✓' : (i + 1) }}</span>
            <span class="lab">{{ s.title }}</span>
          </button>
          <span v-if="i < wizardSteps.length - 1" class="pb-wiz-line" :class="{ on: wizardStep > i }" />
        </template>
      </div>
      <p class="pb-wiz-desc">{{ wizardSteps[wizardStep]?.desc }}</p>

      <div class="pb-wizard-body">
        <div v-show="wizardStep === 0" class="pb-scan">
          <div class="pb-scan-icon">
            <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8" /><path d="M21 21l-4.3-4.3" /></svg>
          </div>
          <h3>扫描本地 IDE 配置</h3>
          <p>一键扫描 Cursor / Claude / Codex 等已配置的 LLM、MCP、Skill</p>
          <button type="button" class="pb-btn pb-btn-primary" :disabled="importing" @click="importFromIde">
            {{ importing ? '扫描中…' : (ideImportStats ? '重新扫描 IDE' : '一键扫描本地 IDE 配置') }}
          </button>
          <div v-if="ideImportStats" class="pb-scan-ok">
            ✓ 扫描完成: {{ ideImportStats.mcp_count }} MCP、{{ ideImportStats.skill_count }} skill、{{ ideImportStats.llm_count }} LLM
            （{{ ideImportStats.files_scanned }} 文件 / {{ ideImportStats.dirs_scanned }} 目录）
          </div>
          <p v-else class="pb-hint">扫描后可在后续步骤勾选导入，最后一步命名生成插件</p>
        </div>

        <div v-show="wizardStep === 1" class="space-y-2">
          <div class="flex items-center justify-between">
            <h3 class="text-xs font-semibold">LLM Provider <span class="text-[10px] text-ink-500 font-normal">({{ selectedLlm.length }}/{{ (ideImport.llm_providers || []).length }})</span></h3>
            <button v-if="ideImport.llm_providers?.length" type="button" class="pb-btn pb-btn-ghost pb-btn-sm" @click="applyImportedLlm">全选导入</button>
          </div>
          <div v-if="!(ideImport.llm_providers?.length)" class="pb-empty"><strong>未扫描到 LLM</strong><p>请回到第一步扫描 IDE</p></div>
          <div v-else class="grid grid-cols-2 gap-2">
            <button
              v-for="l in ideImport.llm_providers"
              :key="llmKey(l)"
              type="button"
              class="pb-item"
              :class="{ on: selectedLlm.includes(llmKey(l)) }"
              @click="toggleLlm(llmKey(l))"
            >
              <span class="check"><svg viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5" /></svg></span>
              <span class="body">
                <span class="title">{{ l.provider }} <span class="tag">{{ l.protocol }}</span></span>
                <span class="meta">{{ l.base_url }} · {{ l.model_count }} 模型</span>
              </span>
            </button>
          </div>
        </div>

        <div v-show="wizardStep === 2" class="space-y-2">
          <div class="flex items-center justify-between">
            <h3 class="text-xs font-semibold">MCP 服务 <span class="text-[10px] text-ink-500 font-normal">({{ selectedMcp.length }})</span></h3>
            <button v-if="ideImport.mcpServers" type="button" class="pb-btn pb-btn-ghost pb-btn-sm" @click="applyImportedMcp">导入扫描结果({{ importedIdeMcp.length }})</button>
          </div>
          <input v-model="mcpFilterText" placeholder="过滤 MCP…" class="pb-input">
          <div v-if="ideImport.mcpServers" class="mb-2">
            <div class="text-[10px] text-ink-500 mb-1">从 IDE 扫描到 ({{ Object.keys(ideImport.mcpServers).length }}):</div>
            <div class="grid grid-cols-2 gap-1.5">
              <label
                v-for="name in Object.keys(ideImport.mcpServers || {})"
                :key="'ide_' + name"
                v-show="!mcpFilterText || name.toLowerCase().includes(mcpFilterText.toLowerCase())"
                class="pb-check-row"
                :class="{ on: importedIdeMcp.includes(name) }"
              >
                <input v-model="importedIdeMcp" type="checkbox" :value="name">
                <span class="truncate flex-1">{{ name }}</span>
                <span v-if="selectedMcp.includes(name)" class="text-[9px] text-green-600">✓</span>
              </label>
            </div>
          </div>
          <div class="border-t border-ink-100 pt-2">
            <div class="text-[10px] text-ink-500 mb-1">本地仓库 MCP ({{ mcpNames.length }}):</div>
            <div class="grid grid-cols-2 gap-1.5">
              <button
                v-for="name in mcpNames"
                :key="'tpl_' + name"
                v-show="!mcpFilterText || name.toLowerCase().includes(mcpFilterText.toLowerCase())"
                type="button"
                class="pb-item"
                :class="{ on: selectedMcp.includes(name) }"
                @click="toggleMcp(name)"
              >
                <span class="check"><svg viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5" /></svg></span>
                <span class="body"><span class="title">{{ name }}</span></span>
              </button>
            </div>
          </div>
        </div>

        <div v-show="wizardStep === 3" class="space-y-2">
          <div class="flex items-center justify-between">
            <h3 class="text-xs font-semibold">技能 <span class="text-[10px] text-ink-500 font-normal">({{ selectedSkills.length }})</span></h3>
            <button v-if="ideImport.skills" type="button" class="pb-btn pb-btn-ghost pb-btn-sm" @click="applyImportedSkills">导入扫描结果</button>
          </div>
          <div class="flex gap-1.5 mb-1 flex-wrap">
            <select v-model="skillFilter.cat" class="pb-select pb-select-sm">
              <option value="">全部分类</option>
              <option v-for="c in skillCategories" :key="c" :value="c">{{ c }}</option>
            </select>
            <input v-model="skillFilter.text" placeholder="搜索…" class="pb-input flex-1 min-w-[100px]">
          </div>
          <div class="grid grid-cols-2 gap-2 max-h-[55vh] overflow-y-auto">
            <button
              v-for="s in filteredLocalSkills"
              :key="s.skill_name"
              type="button"
              class="pb-item"
              :class="{ on: selectedSkills.includes(s.skill_name) }"
              @click="toggleSkill(s.skill_name)"
            >
              <span class="check"><svg viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5" /></svg></span>
              <span class="body">
                <span class="title">{{ s.skill_name }}</span>
                <span class="meta line-clamp-2">{{ s.description }}</span>
              </span>
            </button>
          </div>
        </div>

        <div v-show="wizardStep === 4" class="space-y-2">
          <h3 class="text-xs font-semibold">Subagent <span class="text-[10px] text-ink-500 font-normal">({{ selectedSubagents.length }}/{{ availableSubagents.length }})</span></h3>
          <div v-if="!availableSubagents.length" class="pb-empty"><strong>无可用 Subagent</strong></div>
          <div v-else class="grid grid-cols-2 gap-2 max-h-[55vh] overflow-y-auto">
            <button
              v-for="sa in availableSubagents"
              :key="sa.name"
              type="button"
              class="pb-item"
              :class="{ on: selectedSubagents.includes(sa.name) }"
              @click="toggleSubagent(sa.name)"
            >
              <span class="check"><svg viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5" /></svg></span>
              <span class="body">
                <span class="title">{{ sa.name }}</span>
                <span class="meta line-clamp-2">{{ sa.desc || sa.role }}</span>
              </span>
            </button>
          </div>
        </div>

        <div v-show="wizardStep === 5" class="space-y-3">
          <h3 class="text-xs font-semibold">Rules <span class="text-[10px] text-ink-500 font-normal">({{ selectedRules.length }}/{{ availableRules.length }})</span></h3>
          <div v-if="!availableRules.length" class="pb-empty py-4"><strong>无可用 Rule</strong></div>
          <div v-else class="grid grid-cols-2 gap-2 max-h-[25vh] overflow-y-auto">
            <button
              v-for="r in availableRules"
              :key="r.path"
              type="button"
              class="pb-item"
              :class="{ on: selectedRules.includes(r.path) }"
              @click="toggleRule(r.path)"
            >
              <span class="check"><svg viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5" /></svg></span>
              <span class="body">
                <span class="title truncate">{{ r.path }}</span>
                <span class="meta line-clamp-2">{{ r.description }}</span>
              </span>
            </button>
          </div>
          <h3 class="text-xs font-semibold">Commands <span class="text-[10px] text-ink-500 font-normal">({{ selectedCommands.length }}/{{ availableCommands.length }})</span></h3>
          <div v-if="!availableCommands.length" class="pb-empty py-4"><strong>无可用 Command</strong></div>
          <div v-else class="grid grid-cols-2 gap-2 max-h-[25vh] overflow-y-auto">
            <button
              v-for="c in availableCommands"
              :key="c.name"
              type="button"
              class="pb-item"
              :class="{ on: selectedCommands.includes(c.name) }"
              @click="toggleCommand(c.name)"
            >
              <span class="check"><svg viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5" /></svg></span>
              <span class="body">
                <span class="title">{{ c.name }}</span>
                <span class="meta line-clamp-2">{{ c.description }}</span>
              </span>
            </button>
          </div>
          <label class="pb-hooks" :class="{ on: hooksEnabled }">
            <input v-model="hooksEnabled" type="checkbox">
            <span>打包 Hooks 配置（config/hooks/hooks.json）</span>
          </label>
        </div>

        <div v-show="wizardStep === 6" class="space-y-3">
          <h3 class="text-xs font-semibold">命名并生成插件</h3>
          <div class="grid grid-cols-3 gap-2 text-center">
            <div class="bg-brand-50 rounded-lg p-2"><div class="text-lg font-bold text-brand-600">{{ selectedLlm.length }}</div><div class="text-[10px] text-ink-500">LLM</div></div>
            <div class="bg-brand-50 rounded-lg p-2"><div class="text-lg font-bold text-brand-600">{{ selectedMcp.length }}</div><div class="text-[10px] text-ink-500">MCP</div></div>
            <div class="bg-brand-50 rounded-lg p-2"><div class="text-lg font-bold text-brand-600">{{ selectedSkills.length }}</div><div class="text-[10px] text-ink-500">Skills</div></div>
            <div class="bg-brand-50 rounded-lg p-2"><div class="text-lg font-bold text-brand-600">{{ selectedSubagents.length }}</div><div class="text-[10px] text-ink-500">Agent</div></div>
            <div class="bg-brand-50 rounded-lg p-2"><div class="text-lg font-bold text-brand-600">{{ selectedRules.length }}</div><div class="text-[10px] text-ink-500">Rules</div></div>
            <div class="bg-brand-50 rounded-lg p-2"><div class="text-lg font-bold text-brand-600">{{ selectedCommands.length }}</div><div class="text-[10px] text-ink-500">Cmd</div></div>
          </div>
          <div class="pb-form max-w-md">
            <div class="field span-2"><label>插件名 *</label><input v-model="pluginForm.name" placeholder="my-plugin"></div>
            <div class="field"><label>版本</label><input v-model="pluginForm.version"></div>
            <div class="field"><label>作者</label><input v-model="pluginForm.author"></div>
            <div class="field span-2"><label>描述</label><input v-model="pluginForm.description"></div>
            <div class="field span-2"><label>安装脚本</label><textarea v-model="pluginForm.install_script" rows="2" placeholder="npm i -g xxx && xxx setup" /></div>
          </div>
          <div class="flex gap-2 flex-wrap">
            <button type="button" class="pb-btn pb-btn-soft" @click="previewPlugin">预览 JSON</button>
            <button type="button" class="pb-btn pb-btn-secondary" @click="savePluginFile">保存</button>
            <button type="button" class="pb-btn pb-btn-success" @click="installPluginFile">生成配置</button>
          </div>
        </div>

        <div class="pb-wiz-foot">
          <button type="button" class="pb-btn pb-btn-secondary" :disabled="wizardStep === 0" @click="wizardPrev">← 上一步</button>
          <button v-if="wizardStep < wizardSteps.length - 1" type="button" class="pb-btn pb-btn-primary" @click="wizardNext">下一步 →</button>
        </div>
      </div>
    </div>

    <!-- AI 生成 -->
    <div v-show="buildMode === 'ai'" class="pb-ai">
      <div class="pb-ai-hero">
        <div class="pb-ai-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24"><path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3zM19 14l.8 2.2L22 17l-2.2.8L19 20l-.8-2.2L16 17l2.2-.8L19 14z"/></svg>
        </div>
        <div>
          <h3>用自然语言生成插件</h3>
          <p>描述你想要的智能体能力，LLM 会自动挑选 LLM / MCP / Skill / Subagent 组合并生成 plugin.yaml。</p>
        </div>
      </div>

      <div class="pb-ai-form">
        <label class="pb-ai-label">需求描述</label>
        <textarea
          v-model="prompt"
          :disabled="generating"
          rows="4"
          placeholder="例如：一个 Java 后端开发智能体，精通 Spring Boot / MyBatis / MySQL，需要文件系统和搜索能力"
          class="pb-ai-textarea"
        />

        <div class="pb-ai-row">
          <span class="pb-ai-label">工具集级别</span>
          <div class="pb-ai-seg">
            <button
              v-for="lv in ['basic', 'standard', 'expert']"
              :key="lv"
              type="button"
              :disabled="generating"
              :class="['pb-ai-lv', level === lv ? 'on' : '']"
              @click="level === lv ? (level = '') : (level = lv)"
            >
              {{ lv === 'basic' ? '基础' : lv === 'standard' ? '进阶' : '专家' }}
            </button>
          </div>
          <span class="pb-ai-hint">不选则自动判断</span>
        </div>

        <div class="pb-ai-actions">
          <button
            type="button"
            class="pb-btn pb-btn-primary"
            :disabled="generating || !prompt.trim()"
            @click="ai.generate()"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
            {{ generating ? '生成中…' : '开始生成' }}
          </button>
          <span v-if="generating" class="pb-ai-status">LLM 正在生成 plugin.yaml…</span>
        </div>
      </div>

      <div v-if="output" class="pb-ai-out">
        <div class="pb-ai-out-head">
          <span>生成输出</span>
          <em v-if="generating">streaming…</em>
        </div>
        <pre class="pb-ai-stream">{{ output }}</pre>
      </div>

      <div v-if="generatedConfig" class="pb-ai-result">
        <div class="pb-ai-out-head">
          <span>plugin.yaml 预览</span>
          <em class="ok">✓ 生成完成</em>
        </div>
        <pre class="pb-ai-yaml">{{ generatedConfig }}</pre>
        <div class="pb-ai-result-actions">
          <button type="button" class="pb-btn pb-btn-ghost" @click="ai.closeDialog()">丢弃</button>
          <button type="button" class="pb-btn pb-btn-success" @click="ai.save()">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12l5 5L20 7"/></svg>
            保存到插件配置
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pb-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; }
.pb-title { margin: 0 0 4px; font-size: 18px; font-weight: 700; letter-spacing: -.02em; color: var(--color-ink-900); }
.pb-sub { margin: 0; font-size: 12.5px; color: var(--color-ink-500); }
.pb-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.pb-split { width: 1px; height: 20px; background: var(--color-ink-200); }

.pb-btn {
  height: 34px; padding: 0 12px; border-radius: 8px; font-size: 12px; font-weight: 600;
  display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  border: 1px solid transparent; transition: .18s ease; background: none; color: inherit;
  font-family: inherit; cursor: pointer;
}
.pb-btn svg { width: 14px; height: 14px; stroke: currentColor; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.pb-btn:disabled { opacity: .45; cursor: not-allowed; }
.pb-btn-primary { background: var(--color-brand-500); color: #fff; box-shadow: 0 1px 2px rgba(22,93,255,.22); }
.pb-btn-primary:hover:not(:disabled) { background: var(--color-brand-600); }
.pb-btn-soft { background: var(--color-brand-50); color: var(--color-brand-600); border-color: var(--color-brand-100); }
.pb-btn-soft:hover:not(:disabled) { background: var(--color-brand-100); }
.pb-btn-secondary { background: var(--bg-elevated); color: var(--color-ink-700); border-color: var(--color-ink-200); }
.pb-btn-secondary:hover:not(:disabled) { background: var(--color-ink-100); border-color: var(--color-ink-300); }
.pb-btn-ghost { color: var(--color-ink-700); }
.pb-btn-ghost:hover:not(:disabled) { background: var(--color-ink-100); }
.pb-btn-success { background: #00b42a; color: #fff; }
.pb-btn-success:hover:not(:disabled) { filter: brightness(.96); }
.pb-btn-sm { height: 30px; padding: 0 10px; font-size: 11px; }
.pb-btn-block { width: 100%; }

.pb-select {
  height: 34px; padding: 0 10px; border: 1px solid var(--color-ink-300); border-radius: 8px;
  font-size: 12px; background: var(--bg-elevated); color: var(--color-ink-700); min-width: 140px; font-family: inherit;
}
.pb-select:focus { outline: none; border-color: var(--color-brand-500); box-shadow: var(--shadow-glow); }
.pb-select-sm { height: 30px; min-width: 100px; font-size: 11px; }
.pb-input {
  width: 100%; height: 34px; padding: 0 10px; border: 1px solid var(--color-ink-300); border-radius: 8px;
  font-size: 12px; background: var(--bg-elevated); font-family: inherit;
}
.pb-input:focus { outline: none; border-color: var(--color-brand-500); box-shadow: var(--shadow-glow); }

/* Toolbar */
.pb-toolbar {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  background: var(--bg-elevated); border-radius: 12px; padding: 10px 14px;
  box-shadow: var(--shadow-card); border: 1px solid rgba(0,0,0,.03);
}
.pb-toolbar-label { font-size: 12px; color: var(--color-ink-500); font-weight: 500; }
.pb-seg { display: inline-flex; background: var(--color-ink-100); padding: 3px; border-radius: 8px; }
.pb-seg button {
  height: 28px; padding: 0 14px; border: none; border-radius: 6px; font-size: 12px; font-weight: 600;
  background: transparent; color: var(--color-ink-500); transition: .15s; font-family: inherit; cursor: pointer;
}
.pb-seg button.on { background: var(--bg-elevated); color: var(--color-brand-600); box-shadow: 0 1px 2px rgba(0,0,0,.06); }
.pb-seg button:hover:not(.on) { color: var(--color-ink-900); }
.pb-chips { display: flex; gap: 6px; flex-wrap: wrap; margin-left: auto; }
.pb-chip {
  font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 6px;
  background: var(--color-ink-100); color: var(--color-ink-700); font-variant-numeric: tabular-nums;
  border: 1px solid transparent;
}
.pb-chip.has { background: var(--color-brand-50); color: var(--color-brand-600); border-color: var(--color-brand-100); }
.pb-chip.on { background: #e8ffea; color: #00b42a; }
.pb-chip-meta {
  font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 6px;
  background: transparent; color: var(--color-ink-500);
  border: 1px dashed var(--color-ink-300);
  font-variant-numeric: tabular-nums; letter-spacing: -.01em;
  margin-left: 4px; cursor: help;
}

/* Studio */
.pb-studio {
  display: grid; grid-template-columns: 200px minmax(0, 1fr) 340px;
  min-height: 580px; background: var(--bg-elevated); border-radius: 14px;
  box-shadow: var(--shadow-card); border: 1px solid rgba(0,0,0,.03); overflow: hidden;
}

.pb-rail { border-right: 1px solid var(--color-ink-200); display: flex; flex-direction: column; background: var(--bg-elevated); min-width: 0; }
.pb-rail-top { padding: 14px; border-bottom: 1px solid var(--color-ink-200); }
.pb-rail-brand { display: flex; align-items: center; gap: 8px; }
.pb-rail-brand .mark { width: 10px; height: 10px; border-radius: 2px; background: var(--color-brand-500); flex-shrink: 0; }
.pb-rail-brand strong { font-size: 13px; font-weight: 700; letter-spacing: -.01em; }
.pb-rail-brand em { margin-left: auto; font-style: normal; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 10px; color: var(--color-ink-500); }
.pb-rail-label { padding: 12px 14px 6px; font-size: 10px; font-weight: 700; color: var(--color-ink-500); letter-spacing: .06em; text-transform: uppercase; }
.pb-rail-nav { padding: 0 8px 8px; display: flex; flex-direction: column; gap: 2px; flex: 1; }
.pb-cat {
  display: flex; align-items: center; gap: 10px; width: 100%;
  padding: 9px 10px; border: 1px solid transparent; border-radius: 10px;
  background: transparent; text-align: left; color: var(--color-ink-700);
  font-size: 12.5px; font-weight: 600; transition: .15s; font-family: inherit; cursor: pointer;
}
.pb-cat:hover { background: var(--color-ink-100); }
.pb-cat.active { background: var(--color-brand-50); border-color: var(--color-brand-100); color: var(--color-brand-600); }
.pb-cat .ico {
  width: 30px; height: 30px; border-radius: 8px; flex-shrink: 0;
  display: grid; place-items: center; background: var(--color-ink-100); color: var(--color-ink-700); transition: .15s;
}
.pb-cat.active .ico { background: var(--bg-elevated); color: var(--color-brand-600); box-shadow: 0 1px 2px rgba(22,93,255,.12); }
.pb-cat .ico svg { width: 15px; height: 15px; stroke: currentColor; fill: none; stroke-width: 2; }
.pb-cat .txt { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.pb-cat .txt small { font-size: 10px; font-weight: 500; color: var(--color-ink-500); }
.pb-cat.active .txt small { color: var(--color-brand-500); }
.pb-cat .n {
  font-size: 11px; font-weight: 700; min-width: 22px; height: 20px; padding: 0 6px;
  display: inline-flex; align-items: center; justify-content: center; border-radius: 6px;
  background: var(--color-ink-100); color: var(--color-ink-700); font-variant-numeric: tabular-nums;
}
.pb-cat.active .n { background: var(--color-brand-500); color: #fff; }
.pb-cat .n.empty { background: transparent; color: var(--color-ink-300); }
.pb-rail-foot { padding: 12px 14px; border-top: 1px solid var(--color-ink-200); font-size: 11px; color: var(--color-ink-500); line-height: 1.45; background: var(--bg-base); }
.pb-rail-foot strong { color: var(--color-ink-700); }

.pb-main { display: flex; flex-direction: column; min-width: 0; border-right: 1px solid var(--color-ink-200); }
.pb-main-top { padding: 14px 16px; border-bottom: 1px solid var(--color-ink-200); display: flex; flex-direction: column; gap: 12px; background: var(--bg-elevated); }
.pb-main-title { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.pb-main-title h2 { margin: 0; font-size: 15px; font-weight: 700; letter-spacing: -.01em; }
.pb-pill {
  display: inline-flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 700;
  padding: 3px 9px; border-radius: 999px; background: var(--color-brand-50); color: var(--color-brand-600);
}
.pb-pill i { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.pb-pill.ready { background: #e8ffea; color: #00b42a; }
.pb-hint { font-size: 12px; color: var(--color-ink-500); }
.pb-main-tools { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.pb-search {
  display: flex; align-items: center; gap: 8px; height: 34px; padding: 0 10px;
  border: 1px solid var(--color-ink-300); border-radius: 8px; background: var(--bg-elevated);
  flex: 1; min-width: 160px; max-width: 280px;
}
.pb-search:focus-within { border-color: var(--color-brand-500); box-shadow: var(--shadow-glow); }
.pb-search svg { width: 14px; height: 14px; stroke: var(--color-ink-500); fill: none; stroke-width: 2; flex-shrink: 0; }
.pb-search input { border: none; outline: none; flex: 1; font-size: 12px; min-width: 0; background: transparent; font-family: inherit; }

.pb-list {
  flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 8px;
  background: linear-gradient(180deg, #fff 0%, #fafbfd 100%); max-height: 62vh;
}
.pb-item {
  display: flex; align-items: flex-start; gap: 12px; padding: 12px 14px;
  border: 1px solid var(--color-ink-200); border-radius: 10px; background: var(--bg-elevated);
  cursor: pointer; transition: border-color .2s, box-shadow .2s, transform .2s;
  text-align: left; width: 100%; font-family: inherit; color: inherit;
}
.pb-item:hover { border-color: var(--color-brand-100); box-shadow: 0 4px 16px rgba(22,93,255,.08); transform: translateY(-1px); }
.pb-item.on { border-color: var(--color-brand-500); background: var(--color-brand-50); box-shadow: 0 2px 8px rgba(22,93,255,.1); transform: none; }
.pb-item .check {
  width: 18px; height: 18px; border-radius: 5px; border: 1.5px solid var(--color-ink-300);
  margin-top: 7px; flex-shrink: 0; display: grid; place-items: center; transition: .15s; background: var(--bg-elevated);
}
.pb-item.on .check { background: var(--color-brand-500); border-color: var(--color-brand-500); }
.pb-item .check svg { width: 11px; height: 11px; stroke: #fff; fill: none; stroke-width: 3; opacity: 0; }
.pb-item.on .check svg { opacity: 1; }
.pb-item .avatar {
  width: 36px; height: 36px; border-radius: 9px; flex-shrink: 0;
  display: grid; place-items: center; font-size: 12px; font-weight: 700;
  background: var(--color-brand-50); color: var(--color-brand-600);
}
.pb-item.on .avatar { background: var(--bg-elevated); box-shadow: 0 1px 3px rgba(22,93,255,.15); }
.pb-item .body { flex: 1; min-width: 0; }
.pb-item .title { font-size: 13px; font-weight: 650; color: var(--color-ink-900); display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.pb-item.on .title { color: var(--color-brand-600); }
.pb-item .meta { font-size: 11.5px; color: var(--color-ink-500); margin-top: 4px; line-height: 1.35; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block; }
.pb-item .foot { margin-top: 6px; font-size: 10.5px; color: var(--color-ink-500); display: flex; align-items: center; gap: 8px; }
.pb-item .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--color-ink-300); flex-shrink: 0; }
.pb-item .dot.on { background: #00b42a; box-shadow: 0 0 0 3px #e8ffea; }
.tag { font-size: 10px; font-weight: 600; padding: 1px 6px; border-radius: 4px; background: var(--color-ink-100); color: var(--color-ink-700); }
.tag.live { background: #e8ffea; color: #00b42a; }

.pb-empty {
  flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 8px; padding: 48px 20px; text-align: center; color: var(--color-ink-500);
}
.pb-empty .icon {
  width: 48px; height: 48px; border-radius: 12px; background: var(--color-ink-100);
  display: grid; place-items: center; margin-bottom: 4px;
}
.pb-empty svg { width: 22px; height: 22px; stroke: var(--color-ink-300); fill: none; stroke-width: 1.6; }
.pb-empty strong { font-size: 14px; color: var(--color-ink-700); font-weight: 600; }
.pb-empty p { margin: 0; font-size: 12px; max-width: 240px; line-height: 1.45; }

/* Manifest */
.pb-manifest { display: flex; flex-direction: column; min-width: 0; background: linear-gradient(180deg, #fff 0%, #fafbfd 100%); }
.pb-manifest-head { padding: 16px 18px 14px; border-bottom: 1px solid var(--color-ink-200); background: var(--bg-elevated); }
.pb-manifest-head .pb-pill { margin-bottom: 8px; }
.pb-pkg-row { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.pb-pkg-row h3 { margin: 0; font-size: 16px; font-weight: 720; letter-spacing: -.02em; font-family: 'JetBrains Mono', Consolas, monospace; }
.pb-pkg-ver { font-size: 11px; font-weight: 600; color: var(--color-ink-500); background: var(--color-ink-100); padding: 2px 7px; border-radius: 5px; font-family: 'JetBrains Mono', Consolas, monospace; }
.pb-pkg-desc { margin: 6px 0 0; font-size: 12.5px; color: var(--color-ink-500); line-height: 1.45; }
.pb-complete { display: flex; align-items: center; gap: 8px; margin-top: 12px; font-size: 11px; color: var(--color-ink-500); }
.pb-complete .bar { flex: 1; height: 6px; border-radius: 3px; background: var(--color-ink-200); overflow: hidden; }
.pb-complete .bar i { display: block; height: 100%; background: var(--color-brand-500); border-radius: 3px; transition: width .3s ease; }
.pb-complete b { color: var(--color-brand-600); font-variant-numeric: tabular-nums; min-width: 32px; text-align: right; }

.pb-form-block { margin: 12px 14px 0; background: var(--bg-elevated); border: 1px solid var(--color-ink-200); border-radius: 12px; padding: 12px 14px; }
.pb-form-block h4 { margin: 0 0 10px; font-size: 11px; font-weight: 700; color: var(--color-ink-500); text-transform: uppercase; letter-spacing: .04em; }
.pb-form { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.pb-form .field.span-2 { grid-column: 1 / -1; }
.pb-form .field label { display: block; font-size: 10px; font-weight: 600; color: var(--color-ink-500); margin-bottom: 3px; }
.pb-form .field input,
.pb-form .field textarea {
  width: 100%; border: 1px solid var(--color-ink-300); border-radius: 8px;
  padding: 7px 9px; font-size: 12px; color: var(--color-ink-900); background: var(--bg-elevated); transition: .15s; font-family: inherit;
}
.pb-form .field input:focus,
.pb-form .field textarea:focus { border-color: var(--color-brand-500); box-shadow: var(--shadow-glow); outline: none; }
.pb-form .field input.err { border-color: #f53f3f; }
.pb-form .field textarea { resize: vertical; min-height: 48px; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 11px; }
.field-err { font-size: 10px; color: #f53f3f; margin-top: 3px; }

.pb-packing { flex: 1; overflow-y: auto; padding: 12px 14px; display: flex; flex-direction: column; gap: 8px; max-height: 280px; }
.pb-pack-block { background: var(--bg-elevated); border: 1px solid var(--color-ink-200); border-radius: 10px; padding: 10px 12px; transition: border-color .15s; }
.pb-pack-block:hover { border-color: var(--color-brand-100); }
.pb-pack-block.empty { background: var(--color-ink-100); border-style: dashed; }
.pb-pack-h {
  display: flex; align-items: center; gap: 6px; width: 100%;
  padding: 0; margin: 0 0 8px; border: none; background: none; color: var(--color-ink-500);
  font-size: 11px; font-weight: 700; letter-spacing: .03em; text-transform: uppercase; cursor: pointer; font-family: inherit;
}
.pb-pack-h:hover { color: var(--color-brand-600); }
.pb-pack-h span { font-variant-numeric: tabular-nums; color: var(--color-brand-600); text-transform: none; letter-spacing: 0; }
.pb-pack-h .go { margin-left: auto; font-weight: 600; opacity: 0; font-size: 11px; }
.pb-pack-h:hover .go { opacity: 1; }
.pb-pack-empty { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 12px; color: var(--color-ink-500); }
.pb-pack-empty button { border: none; background: none; color: var(--color-brand-600); font-size: 11px; font-weight: 600; padding: 0; cursor: pointer; font-family: inherit; }
.pb-pack-empty button:hover { text-decoration: underline; }
.pb-pack-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.pb-pack-tag {
  display: inline-flex; align-items: center; gap: 2px; max-width: 100%;
  font-size: 12px; font-weight: 600; padding: 4px 4px 4px 10px; border-radius: 8px;
  background: var(--color-brand-50); color: var(--color-brand-600); border: 1px solid var(--color-brand-100);
}
.pb-pack-tag .txt { max-width: 130px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pb-pack-tag .x {
  width: 20px; height: 20px; border: none; border-radius: 5px; background: transparent;
  color: var(--color-brand-600); display: grid; place-items: center; padding: 0; opacity: .5; cursor: pointer; transition: .12s;
}
.pb-pack-tag .x:hover { opacity: 1; background: var(--color-brand-100); }
.pb-pack-tag .x svg { width: 10px; height: 10px; stroke: currentColor; fill: none; stroke-width: 2.5; }

.pb-hooks {
  display: flex; align-items: center; gap: 10px; padding: 12px 14px;
  border: 1px solid var(--color-ink-200); border-radius: 10px; background: var(--bg-elevated);
  font-size: 12.5px; color: var(--color-ink-700); cursor: pointer; transition: .15s; user-select: none;
}
.pb-hooks:hover { border-color: var(--color-brand-100); }
.pb-hooks.on { border-color: #00b42a; background: #e8ffea; color: #00b42a; }
.pb-hooks input { accent-color: var(--color-brand-500); width: 15px; height: 15px; }
.pb-hooks .hook-meta { margin-left: auto; font-size: 11px; opacity: .7; }

.pb-manifest-foot {
  margin-top: auto; padding: 14px 16px; border-top: 1px solid var(--color-ink-200);
  display: flex; flex-direction: column; gap: 8px; background: var(--bg-elevated);
}
.pb-manifest-foot .row { display: flex; gap: 8px; }
.pb-manifest-foot .hint-line { margin: 0; font-size: 11px; color: var(--color-ink-500); text-align: center; }

/* IDE wizard */
.pb-ide { display: flex; flex-direction: column; gap: 10px; }
.pb-wizard-bar {
  display: flex; align-items: center; gap: 4px; flex-wrap: wrap;
  background: var(--bg-elevated); border-radius: 12px; padding: 10px 12px; box-shadow: var(--shadow-card);
}
.pb-wiz-step {
  display: flex; align-items: center; gap: 6px; padding: 6px 10px; border-radius: 8px;
  border: none; background: transparent; cursor: pointer; font-family: inherit; color: var(--color-ink-500); transition: .15s;
}
.pb-wiz-step:hover { background: var(--color-ink-100); }
.pb-wiz-step.active { background: var(--color-brand-500); color: #fff; }
.pb-wiz-step.done { background: var(--color-brand-50); color: var(--color-brand-600); }
.pb-wiz-step .num {
  width: 20px; height: 20px; border-radius: 50%; display: grid; place-items: center;
  font-size: 10px; font-weight: 700; background: var(--color-ink-200); color: var(--color-ink-500);
}
.pb-wiz-step.active .num { background: var(--bg-elevated); color: var(--color-brand-600); }
.pb-wiz-step.done .num { background: var(--color-brand-500); color: #fff; }
.pb-wiz-step .lab { font-size: 12px; font-weight: 600; }
.pb-wiz-line { flex: 1; min-width: 12px; height: 2px; background: var(--color-ink-200); }
.pb-wiz-line.on { background: var(--color-brand-500); }
.pb-wiz-desc { margin: 0; font-size: 11px; color: var(--color-ink-500); padding-left: 4px; }
.pb-wizard-body {
  background: var(--bg-elevated); border-radius: 14px; box-shadow: var(--shadow-card); padding: 16px;
  min-height: 400px; border: 1px solid rgba(0,0,0,.03);
}
.pb-wiz-foot {
  display: flex; justify-content: space-between; margin-top: 16px; padding-top: 12px;
  border-top: 1px solid var(--color-ink-100);
}
.pb-scan {
  text-align: center; padding: 40px 20px; display: flex; flex-direction: column; align-items: center; gap: 10px;
}
.pb-scan-icon {
  width: 56px; height: 56px; border-radius: 14px; background: var(--color-brand-50);
  display: grid; place-items: center; color: var(--color-brand-500);
}
.pb-scan-icon svg { width: 26px; height: 26px; stroke: currentColor; fill: none; stroke-width: 1.8; }
.pb-scan h3 { margin: 0; font-size: 15px; }
.pb-scan p { margin: 0; font-size: 12px; color: var(--color-ink-500); max-width: 360px; }
.pb-scan-ok { font-size: 12px; color: #00b42a; font-weight: 600; }
.pb-check-row {
  display: flex; align-items: center; gap: 8px; padding: 8px 10px; border: 1px solid var(--color-ink-200);
  border-radius: 8px; font-size: 11px; cursor: pointer;
}
.pb-check-row.on { border-color: var(--color-brand-100); background: var(--color-brand-50); }
.pb-check-row input { accent-color: var(--color-brand-500); }

/* AI 生成 */
.pb-ai {
  display: flex; flex-direction: column; gap: 14px;
  padding: 18px 20px;
  background: var(--bg-elevated);
  border: 1px solid var(--border-base);
  border-radius: 12px;
  box-shadow: var(--shadow-sm);
}
.pb-ai-hero {
  display: flex; align-items: flex-start; gap: 12px;
  padding-bottom: 12px;
  border-bottom: 1px dashed var(--border-base);
}
.pb-ai-icon {
  width: 36px; height: 36px; flex-shrink: 0;
  border-radius: 10px;
  background: var(--primary-container);
  color: var(--primary);
  display: inline-flex; align-items: center; justify-content: center;
}
.pb-ai-icon svg { width: 20px; height: 20px; fill: currentColor; }
.pb-ai-hero h3 {
  margin: 0 0 4px; font-size: 14px; font-weight: 700;
  color: var(--text-primary); letter-spacing: -0.01em;
}
.pb-ai-hero p {
  margin: 0; font-size: 12px; line-height: 1.5;
  color: var(--text-secondary);
}
.pb-ai-form {
  display: flex; flex-direction: column; gap: 10px;
}
.pb-ai-label {
  font-size: 11px; font-weight: 600;
  color: var(--text-secondary);
}
.pb-ai-textarea {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--border-base);
  border-radius: 10px;
  background: var(--bg-input);
  font-size: 12.5px; line-height: 1.5;
  color: var(--text-primary);
  font-family: inherit;
  resize: vertical;
  min-height: 88px;
  transition: border-color .2s, box-shadow .2s;
}
.pb-ai-textarea:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px var(--primary-container);
}
.pb-ai-textarea::placeholder { color: var(--text-tertiary); }
.pb-ai-row {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
}
.pb-ai-seg {
  display: inline-flex;
  border: 1px solid var(--border-base);
  border-radius: 8px;
  overflow: hidden;
  background: var(--bg-sunken);
}
.pb-ai-lv {
  padding: 5px 12px;
  font-size: 11.5px; font-weight: 500;
  background: transparent;
  color: var(--text-secondary);
  border: 0;
  cursor: pointer;
  transition: all .15s;
}
.pb-ai-lv + .pb-ai-lv { border-left: 1px solid var(--border-base); }
.pb-ai-lv:hover:not(:disabled) { color: var(--primary); }
.pb-ai-lv.on {
  background: var(--primary);
  color: var(--text-inverse);
  font-weight: 600;
}
.pb-ai-lv:disabled { opacity: .5; cursor: not-allowed; }
.pb-ai-hint {
  font-size: 11px; color: var(--text-tertiary);
}
.pb-ai-actions {
  display: flex; align-items: center; gap: 12px;
  margin-top: 4px;
}
.pb-ai-status {
  font-size: 11.5px; color: var(--text-tertiary);
}
.pb-ai-out,
.pb-ai-result {
  display: flex; flex-direction: column; gap: 6px;
}
.pb-ai-out-head {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 11px; font-weight: 600;
  color: var(--text-secondary);
}
.pb-ai-out-head em {
  font-style: normal;
  font-size: 10.5px;
  color: var(--text-tertiary);
  font-family: 'JetBrains Mono', Consolas, monospace;
}
.pb-ai-out-head em.ok { color: var(--success); font-weight: 600; }
.pb-ai-stream {
  margin: 0;
  padding: 10px 12px;
  background: #0d1117;
  color: #7ee787;
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 11px;
  line-height: 1.55;
  border-radius: 8px;
  max-height: 200px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
.pb-ai-yaml {
  margin: 0;
  padding: 12px 14px;
  background: var(--bg-sunken);
  border: 1px solid var(--border-base);
  border-radius: 8px;
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 11.5px;
  line-height: 1.55;
  color: var(--text-primary);
  max-height: 280px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
.pb-ai-result-actions {
  display: flex; gap: 8px; justify-content: flex-end;
  margin-top: 4px;
}

@media (max-width: 1060px) {
  .pb-studio { grid-template-columns: 1fr; min-height: auto; }
  .pb-rail { border-right: none; border-bottom: 1px solid var(--color-ink-200); }
  .pb-rail-nav { flex-direction: row; overflow-x: auto; padding-bottom: 10px; }
  .pb-cat { width: auto; white-space: nowrap; flex-shrink: 0; }
  .pb-cat .txt small { display: none; }
  .pb-rail-foot { display: none; }
  .pb-main { border-right: none; border-bottom: 1px solid var(--color-ink-200); min-height: 320px; }
  .pb-manifest { min-height: 420px; }
}
@media (max-width: 560px) {
  .pb-form { grid-template-columns: 1fr; }
}
@media (prefers-reduced-motion: reduce) {
  .pb-item, .pb-complete .bar i { transition: none !important; }
}
</style>
