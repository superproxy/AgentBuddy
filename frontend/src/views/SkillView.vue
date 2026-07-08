<script setup lang="ts">
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useSkillStore } from '../stores/skill'
import { useUiStore } from '../stores/ui'
const skill = useSkillStore()
const ui = useUiStore()
const { skillTab, skillSources, skillSearchQ, skillSearchResults, skillSearchHint, skillSearched, manualSkillInput, installedSkills, enabledInstalledCount, localSkills } = storeToRefs(skill)
const { searchSkills, installFromSearch, installManualSkill, loadLocalSkills, loadInstalledSkills, viewSkillMd, uninstallSkill, syncToIde, onToggleSkill, toggleAllInstalled } = skill
async function refreshInstalled() { await loadLocalSkills(); await loadInstalledSkills(); ui.toast('已刷新技能列表') }
onMounted(() => { loadLocalSkills(); loadInstalledSkills() })
</script>
<template>
  <div class="space-y-4">
    <div class="bg-white rounded-xl shadow-card p-5">
      <div class="flex items-center justify-between mb-3 pb-3 border-b border-gray-100">
        <div class="flex items-center gap-1">
          <button @click="skillTab = 'market'" :class="['px-3 py-1 text-xs font-medium rounded-t border-b-2 -mb-px', skillTab === 'market' ? 'border-brand-500 text-brand-600' : 'border-transparent text-ink-500 hover:text-ink-700']">市场检索</button>
          <button @click="skillTab = 'manual'" :class="['px-3 py-1 text-xs font-medium rounded-t border-b-2 -mb-px', skillTab === 'manual' ? 'border-brand-500 text-brand-600' : 'border-transparent text-ink-500 hover:text-ink-700']">手动安装</button>
        </div>
        <span class="text-[10px] text-ink-500">{{ skillTab === 'market' ? '从市场搜索并安装技能' : '输入 owner/repo 或 GitHub URL 安装' }}</span>
      </div>
      <div v-show="skillTab === 'market'">
        <div class="flex gap-4 mb-3 items-center">
          <label v-for="t in [{k:'modelscope',l:'ModelScope 市场'},{k:'skillssh',l:'skills.sh'},{k:'local',l:'本地预置'}]" :key="t.k" class="flex items-center gap-1.5 text-xs cursor-pointer">
            <input type="checkbox" v-model="skillSources[t.k]" class="rounded text-brand-500">
            <span>{{ t.l }}</span>
          </label>
        </div>
        <div class="flex gap-2 mb-3 items-center">
          <input v-model="skillSearchQ" @keydown.enter="searchSkills" placeholder="关键词，如：react、设计、API..." class="flex-1 px-3 py-1.5 text-xs border border-ink-300 rounded-md">
          <button @click="searchSkills" class="px-4 py-1.5 text-xs bg-brand-500 text-white rounded-md hover:bg-brand-600">搜索</button>
          <span class="text-[11px] text-ink-500">{{ skillSearchHint }}</span>
        </div>
        <div class="grid grid-cols-2 gap-2">
          <div v-for="s in skillSearchResults" :key="s.source + s.name" class="border border-ink-300 rounded-md p-3 hover:border-brand-500 transition">
            <div class="flex justify-between items-start mb-1">
              <div class="font-medium text-sm">{{ s.name }}</div>
              <span class="px-1.5 py-0.5 text-[10px] bg-ink-100 rounded">{{ s.source }}</span>
            </div>
            <div class="text-[11px] text-ink-500 mb-1">{{ s.author ? '作者: ' + s.author + ' | ' : '' }}安装量: {{ s.install_count || 0 }}</div>
            <div class="text-xs text-ink-700 line-clamp-2 mb-2">{{ s.description }}</div>
            <div class="flex justify-between items-center gap-2">
              <code class="text-[10px] text-ink-500 flex-1 truncate">{{ s.install_command }}</code>
              <button @click="installFromSearch(s)" class="px-2 py-1 text-[11px] bg-brand-50 text-brand-600 rounded hover:bg-brand-100 shrink-0">安装</button>
            </div>
          </div>
          <div v-if="!skillSearchResults.length && skillSearched" class="col-span-2 text-center text-ink-500 py-6 text-xs">无结果</div>
        </div>
      </div>
      <div v-show="skillTab === 'manual'">
        <div class="flex gap-2">
          <input v-model="manualSkillInput" @keydown.enter="installManualSkill" placeholder="owner/repo 或 owner/repo@skill 或 GitHub URL" class="flex-1 px-3 py-1.5 text-xs border border-ink-300 rounded-md">
          <button @click="installManualSkill" class="px-4 py-1.5 text-xs bg-brand-500 text-white rounded-md hover:bg-brand-600">安装</button>
        </div>
        <p class="text-[11px] text-ink-500 mt-2">支持 vercel-labs/skills、vercel-labs/skills@find-skills、https://github.com/owner/repo</p>
      </div>
    </div>
    <!-- 本地预置技能（template/skills）-->
    <div class="bg-white rounded-xl shadow-card p-5">
      <div class="flex justify-between items-center mb-3 pb-3 border-b border-gray-100">
        <h2 class="text-sm font-semibold flex items-center gap-2">
          <span class="w-1 h-4 bg-brand-500 rounded"></span>本地预置技能
          <span class="text-[10px] text-ink-500 font-normal">{{ localSkills.length }} 个</span>
        </h2>
        <button @click="refreshInstalled" class="px-2 py-1.5 text-[11px] bg-ink-100 rounded hover:bg-ink-300">刷新</button>
      </div>
      <div class="grid grid-cols-2 gap-2 max-h-[400px] overflow-y-auto">
        <div v-for="s in localSkills" :key="s.skill_name" class="border border-ink-300 rounded-md p-2 hover:border-brand-500 transition">
          <div class="flex items-center justify-between mb-0.5">
            <span class="font-medium text-xs truncate">{{ s.skill_name }}</span>
            <button @click="viewSkillMd(s.skill_name)" class="text-[10px] text-brand-600 hover:underline shrink-0">查看</button>
          </div>
          <div class="text-[10px] text-ink-500 line-clamp-2">{{ s.description }}</div>
          <div class="flex items-center gap-1 mt-1">
            <span v-if="s.category" class="text-[9px] px-1 py-0.5 bg-brand-50 text-brand-600 rounded">{{ s.category }}</span>
            <button @click="installFromSearch({ source: 'local', name: s.skill_name, description: s.description, install_command: '' })" class="text-[10px] text-green-600 hover:underline ml-auto">安装</button>
          </div>
        </div>
      </div>
      <div v-if="!localSkills.length" class="text-center text-ink-500 text-xs py-6">暂无本地预置技能</div>
    </div>
    <!-- 已安装技能 -->
    <div class="bg-white rounded-xl shadow-card p-5">
      <div class="flex justify-between items-center mb-3 pb-3 border-b border-gray-100">
        <h2 class="text-sm font-semibold">已安装技能 ({{ installedSkills.length }} · 已启用 {{ enabledInstalledCount }})</h2>
        <div class="flex gap-2">
          <button @click="refreshInstalled" class="px-2 py-1.5 text-[11px] bg-ink-100 rounded hover:bg-ink-300">刷新</button>
          <button @click="toggleAllInstalled(true)" class="px-2 py-1.5 text-[11px] bg-ink-100 rounded hover:bg-ink-300">全选</button>
          <button @click="toggleAllInstalled(false)" class="px-2 py-1.5 text-[11px] bg-ink-100 rounded hover:bg-ink-300">全不选</button>
          <button @click="syncToIde" class="px-2 py-1.5 text-[11px] bg-brand-50 text-brand-600 rounded hover:bg-brand-100">同步到 IDE</button>
        </div>
      </div>
      <div class="space-y-1.5">
        <div v-for="s in installedSkills" :key="s.name" :class="['flex items-center gap-3 border rounded-lg px-3 py-2 transition', s.enabled ? 'border-brand-400 bg-brand-50/30' : 'border-ink-300']">
          <input type="checkbox" :checked="s.enabled" @change="onToggleSkill(s, $event.target.checked)" class="w-4 h-4 accent-brand-500 cursor-pointer flex-shrink-0">
          <div class="flex-1 min-w-0">
            <div class="font-medium text-sm">{{ s.name }}</div>
            <div class="text-[11px] text-ink-500 truncate">{{ s.path }}</div>
          </div>
          <div class="flex gap-2 flex-shrink-0">
            <button @click="viewSkillMd(s.name)" class="text-[11px] text-brand-600 hover:underline">查看</button>
            <button @click="uninstallSkill(s.name)" class="text-[11px] text-red-500 hover:underline">卸载</button>
          </div>
        </div>
        <div v-if="!installedSkills.length" class="text-center text-ink-500 py-6 text-xs">暂无本地可用技能</div>
      </div>
    </div>
  </div>
</template>
