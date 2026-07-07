<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { usePluginBuildStore, wizardSteps } from '../stores/pluginBuild'
import { useEnvStore } from '../stores/env'
import { useMcpStore } from '../stores/mcp'
import { useSkillStore } from '../stores/skill'
import { usePluginStore } from '../stores/plugin'
const pb = usePluginBuildStore()
const env = useEnvStore()
const mcp = useMcpStore()
const skill = useSkillStore()
const plugin = usePluginStore()
const { pluginForm, selectedSkills, selectedMcp, selectedLlm, ideImport, ideImportStats, importedIdeMcp, importedIdeSkills, wizardStep, buildMode, mcpFilterText, importing } = storeToRefs(pb)
const { mcpTemplate } = storeToRefs(mcp)
const { localSkills, skillCategories, filteredLocalSkills, skillFilter } = storeToRefs(skill)
const { plugins, selectedPluginFile } = storeToRefs(plugin)
const { toggleSkill, toggleMcp, toggleLlm, llmKey, wizardNext, wizardPrev, wizardGoto, newPlugin, importFromIde, importAllIdeMcp, importAllIdeSkills, applyImportedMcp, applyImportedSkills, applyImportedLlm, loadExistingPlugin, previewPlugin, savePluginFile, installPluginFile } = pb
const localLlmList = computed(() => {
  const llm = env.envData.llm || {}
  const out: any[] = []
  for (const [provider, val] of Object.entries(llm)) {
    if (provider.startsWith('_') || provider === 'proxy') continue
    if (!val || typeof val !== 'object') continue
    for (const [protocol, cfg] of Object.entries(val as any)) {
      if (!cfg || typeof cfg !== 'object') continue
      out.push({ provider, protocol, base_url: cfg.base_url || '', has_key: !!(cfg.api_key), model_count: Object.keys(cfg.models || {}).length, active: llm._active_provider === provider })
    }
  }
  return out
})
</script>
<template>
  <div class="space-y-3">
    <div class="bg-white rounded-xl shadow-card p-3">
      <div class="flex items-center gap-3 flex-wrap">
        <span class="text-xs text-ink-500">构建来源:</span>
        <button @click="buildMode = 'local'" :class="['px-3 py-1 text-xs rounded-lg transition', buildMode === 'local' ? 'bg-brand-500 text-white' : 'bg-ink-100 text-ink-600 hover:bg-ink-200']">本地仓库</button>
        <button @click="buildMode = 'ide'" :class="['px-3 py-1 text-xs rounded-lg transition', buildMode === 'ide' ? 'bg-brand-500 text-white' : 'bg-ink-100 text-ink-600 hover:bg-ink-200']">IDE 导入向导</button>
        <div class="ml-auto flex items-center gap-2 text-[10px] text-ink-500">
          <span class="px-1.5 py-0.5 bg-brand-50 text-brand-600 rounded">LLM {{ selectedLlm.length }}</span>
          <span class="px-1.5 py-0.5 bg-brand-50 text-brand-600 rounded">MCP {{ selectedMcp.length }}</span>
          <span class="px-1.5 py-0.5 bg-brand-50 text-brand-600 rounded">Skill {{ selectedSkills.length }}</span>
        </div>
        <select v-model="selectedPluginFile" @change="loadExistingPlugin" class="px-2 py-1 text-[11px] border border-ink-300 rounded">
          <option value="">加载已有...</option>
          <option v-for="p in plugins" :key="p.file" :value="p.file">{{ p.name }}</option>
        </select>
        <button @click="newPlugin" class="text-[11px] text-brand-600 hover:underline">清空</button>
      </div>
    </div>
    <div v-show="buildMode === 'local'" class="grid grid-cols-[1fr_1fr_1fr_300px] gap-3">
      <div class="bg-white rounded-xl shadow-card p-3 max-h-[72vh] overflow-y-auto">
        <h3 class="text-xs font-semibold mb-2 pb-2 border-b border-gray-100">本地 LLM <span class="text-[10px] text-ink-500 font-normal">({{ localLlmList.length }})</span></h3>
        <div v-if="!localLlmList.length" class="text-center text-ink-400 text-xs py-6">未配置 LLM Provider<br>请到 LLM 配置 tab 添加</div>
        <div class="space-y-1">
          <div v-for="l in localLlmList" :key="llmKey(l)" @click="toggleLlm(llmKey(l))" :class="['p-1.5 border rounded-md cursor-pointer transition', selectedLlm.includes(llmKey(l)) ? 'border-brand-500 bg-brand-50' : 'border-ink-300 hover:border-brand-500']">
            <div class="flex items-center gap-1 flex-wrap">
              <input type="checkbox" :checked="selectedLlm.includes(llmKey(l))" @click.stop="toggleLlm(llmKey(l))" class="w-3 h-3 accent-brand-500">
              <span class="font-medium text-xs">{{ l.provider }}</span>
              <span class="text-[9px] px-1 py-0.5 bg-ink-100 rounded">{{ l.protocol }}</span>
              <span v-if="l.active" class="text-[9px] text-green-600">active</span>
              <span v-if="l.has_key" class="text-[9px] text-green-600 ml-auto">✓key</span>
            </div>
            <div class="text-[10px] text-ink-500 truncate mt-0.5">{{ l.base_url || '(无 base_url)' }}</div>
            <div class="text-[9px] text-ink-400">{{ l.model_count }} 模型</div>
          </div>
        </div>
      </div>
      <div class="bg-white rounded-xl shadow-card p-3 max-h-[72vh] overflow-y-auto">
        <h3 class="text-xs font-semibold mb-2 pb-2 border-b border-gray-100">本地 MCP <span class="text-[10px] text-ink-500 font-normal">({{ Object.keys(mcpTemplate.mcpServers || {}).length }})</span></h3>
        <input v-model="mcpFilterText" placeholder="过滤..." class="w-full px-2 py-1 text-[11px] border border-ink-300 rounded mb-2">
        <div class="space-y-1">
          <div v-for="(_, name) in (mcpTemplate.mcpServers || {})" :key="name" v-show="!mcpFilterText || name.toLowerCase().includes(mcpFilterText.toLowerCase())" @click="toggleMcp(name)" :class="['p-1.5 border rounded-md cursor-pointer transition', selectedMcp.includes(name) ? 'border-brand-500 bg-brand-50' : 'border-ink-300 hover:border-brand-500']">
            <div class="flex items-center gap-1"><input type="checkbox" :checked="selectedMcp.includes(name)" @click.stop="toggleMcp(name)" class="w-3 h-3 accent-brand-500"><span class="text-xs truncate">{{ name }}</span></div>
          </div>
        </div>
      </div>
      <div class="bg-white rounded-xl shadow-card p-3 max-h-[72vh] overflow-y-auto">
        <h3 class="text-xs font-semibold mb-2 pb-2 border-b border-gray-100">本地 Skill <span class="text-[10px] text-ink-500 font-normal">({{ localSkills.length }})</span></h3>
        <div class="flex gap-1 mb-2 flex-wrap">
          <select v-model="skillFilter.cat" class="px-1 py-0.5 text-[10px] border border-ink-300 rounded"><option value="">全部分类</option><option v-for="c in skillCategories" :key="c">{{ c }}</option></select>
          <input v-model="skillFilter.text" placeholder="搜索..." class="flex-1 min-w-[60px] px-1 py-0.5 text-[10px] border border-ink-300 rounded">
        </div>
        <div class="space-y-1">
          <div v-for="s in filteredLocalSkills" :key="s.skill_name" @click="toggleSkill(s.skill_name)" :class="['p-1.5 border rounded-md cursor-pointer transition', selectedSkills.includes(s.skill_name) ? 'border-brand-500 bg-brand-50' : 'border-ink-300 hover:border-brand-500']">
            <div class="flex items-center gap-1"><input type="checkbox" :checked="selectedSkills.includes(s.skill_name)" @click.stop="toggleSkill(s.skill_name)" class="w-3 h-3 accent-brand-500"><span class="font-medium text-xs truncate">{{ s.skill_name }}</span></div>
            <div class="text-[10px] text-ink-500 truncate">{{ s.description }}</div>
          </div>
        </div>
      </div>
      <div class="bg-white rounded-xl shadow-card p-3 max-h-[72vh] overflow-y-auto">
        <h3 class="text-xs font-semibold mb-2 pb-2 border-b border-gray-100">插件定义</h3>
        <div class="space-y-1.5">
          <div><label class="text-[10px] text-ink-500">name *</label><input v-model="pluginForm.name" placeholder="my-plugin" class="w-full px-2 py-1 text-xs border border-ink-300 rounded"></div>
          <div><label class="text-[10px] text-ink-500">version</label><input v-model="pluginForm.version" class="w-full px-2 py-1 text-xs border border-ink-300 rounded"></div>
          <div><label class="text-[10px] text-ink-500">desc</label><input v-model="pluginForm.description" class="w-full px-2 py-1 text-xs border border-ink-300 rounded"></div>
          <div><label class="text-[10px] text-ink-500">author</label><input v-model="pluginForm.author" class="w-full px-2 py-1 text-xs border border-ink-300 rounded"></div>
          <div><label class="text-[10px] text-ink-500">install script</label><textarea v-model="pluginForm.install_script" rows="2" placeholder="npm i -g xxx && xxx setup" class="w-full px-2 py-1 text-xs border border-ink-300 rounded font-mono"></textarea></div>
        </div>
        <div class="mt-2 space-y-1">
          <div class="text-[10px] text-ink-500">已选 LLM ({{ selectedLlm.length }})</div>
          <div class="border border-dashed border-ink-300 rounded p-1 min-h-[30px]"><span v-for="k in selectedLlm" :key="k" class="inline-block mr-1 mb-1 px-1.5 py-0.5 text-[10px] bg-brand-50 rounded">{{ k }}</span></div>
          <div class="text-[10px] text-ink-500">已选 MCP ({{ selectedMcp.length }})</div>
          <div class="border border-dashed border-ink-300 rounded p-1 min-h-[30px]"><span v-for="m in selectedMcp" :key="m" class="inline-block mr-1 mb-1 px-1.5 py-0.5 text-[10px] bg-brand-50 rounded">{{ m }}</span></div>
          <div class="text-[10px] text-ink-500">已选 Skill ({{ selectedSkills.length }})</div>
          <div class="border border-dashed border-ink-300 rounded p-1 min-h-[30px] max-h-[120px] overflow-y-auto"><span v-for="s in selectedSkills" :key="s" class="inline-block mr-1 mb-1 px-1.5 py-0.5 text-[10px] bg-brand-50 rounded">{{ s }}</span></div>
        </div>
        <div class="flex gap-1 mt-3 flex-wrap">
          <button @click="previewPlugin" class="px-2 py-1 text-[11px] bg-brand-500 text-white rounded hover:bg-brand-600">预览</button>
          <button @click="savePluginFile" class="px-2 py-1 text-[11px] bg-ink-100 rounded hover:bg-ink-300">保存</button>
          <button @click="installPluginFile" class="px-2 py-1 text-[11px] bg-green-500 text-white rounded hover:bg-green-600">生成配置</button>
        </div>
      </div>
    </div>
    <div v-show="buildMode === 'ide'">
      <div class="bg-white rounded-xl shadow-card p-3">
        <div class="flex items-center gap-1">
          <template v-for="(s, i) in wizardSteps" :key="i">
            <div @click="wizardGoto(i)" :class="['flex items-center gap-1.5 cursor-pointer px-2.5 py-1.5 rounded-lg transition', wizardStep === i ? 'bg-brand-500 text-white' : (wizardStep > i ? 'bg-brand-50 text-brand-600' : 'text-ink-500 hover:bg-ink-100')]">
              <span :class="['w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold', wizardStep === i ? 'bg-white text-brand-600' : (wizardStep > i ? 'bg-brand-500 text-white' : 'bg-ink-200 text-ink-500')]">{{ wizardStep > i ? '✓' : (i + 1) }}</span>
              <span class="text-xs font-medium">{{ s.title }}</span>
            </div>
            <span v-if="i < wizardSteps.length - 1" :class="['flex-1 h-0.5', wizardStep > i ? 'bg-brand-400' : 'bg-ink-200']"></span>
          </template>
        </div>
        <div class="text-[10px] text-ink-500 mt-1.5 ml-1">{{ wizardSteps[wizardStep] && wizardSteps[wizardStep].desc }}</div>
      </div>
      <div class="bg-white rounded-xl shadow-card p-4 min-h-[400px]">
        <div v-show="wizardStep === 0" class="space-y-3">
          <div class="text-center py-6">
            <div class="text-sm text-ink-700 mb-3">扫描本地所有 IDE 已配置的 LLM / MCP / Skill</div>
            <button @click="importFromIde" :disabled="importing" class="px-6 py-2.5 text-sm font-medium text-white rounded-lg bg-gradient-to-r from-brand-500 to-brand-600 hover:from-brand-600 hover:to-brand-700 disabled:opacity-50 shadow-sm">{{ importing ? '扫描中...' : (ideImportStats ? '重新扫描 IDE' : '一键扫描本地 IDE 配置') }}</button>
            <div v-if="ideImportStats" class="text-[11px] text-green-600 mt-3">✓ 扫描完成: {{ ideImportStats.mcp_count }} MCP、{{ ideImportStats.skill_count }} skill、{{ ideImportStats.llm_count }} LLM（{{ ideImportStats.files_scanned }} 文件 / {{ ideImportStats.dirs_scanned }} 目录）</div>
            <div v-else class="text-[11px] text-ink-500 mt-3">扫描后将可在后续步骤中勾选导入 LLM / MCP / Skill，最后一步命名生成插件</div>
          </div>
        </div>
        <div v-show="wizardStep === 1" class="space-y-2">
          <div class="flex items-center justify-between">
            <h3 class="text-xs font-semibold">LLM Provider <span class="text-[10px] text-ink-500 font-normal">({{ selectedLlm.length }}/{{ (ideImport.llm_providers || []).length }})</span></h3>
            <button v-if="ideImport.llm_providers && ideImport.llm_providers.length" @click="applyImportedLlm" class="text-[11px] text-brand-600 hover:underline">全选导入</button>
          </div>
          <div v-if="!(ideImport.llm_providers && ideImport.llm_providers.length)" class="text-center text-ink-400 text-xs py-8">未扫描到 LLM 配置，请回到第一步扫描 IDE</div>
          <div v-else class="grid grid-cols-2 gap-1.5">
            <label v-for="l in ideImport.llm_providers" :key="llmKey(l)" :class="['flex items-start gap-1.5 p-2 border rounded-lg cursor-pointer transition', selectedLlm.includes(llmKey(l)) ? 'border-brand-500 bg-brand-50' : 'border-ink-300 hover:border-brand-400']">
              <input type="checkbox" :checked="selectedLlm.includes(llmKey(l))" @change="toggleLlm(llmKey(l))" class="mt-0.5 w-3.5 h-3.5 accent-brand-500">
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-1 flex-wrap"><span class="font-medium text-xs">{{ l.provider }}</span><span class="text-[9px] px-1 py-0.5 bg-ink-100 rounded">{{ l.protocol }}</span><span v-if="l.active" class="text-[9px] px-1 py-0.5 bg-green-100 text-green-700 rounded">active</span><span v-if="l.has_key" class="text-[9px] text-green-600">✓key</span></div>
                <div class="text-[10px] text-ink-500 truncate">{{ l.base_url }}</div>
                <div class="text-[9px] text-ink-400">{{ l.model_count }} 模型</div>
              </div>
            </label>
          </div>
        </div>
        <div v-show="wizardStep === 2" class="space-y-2">
          <div class="flex items-center justify-between">
            <h3 class="text-xs font-semibold">MCP 服务 <span class="text-[10px] text-ink-500 font-normal">({{ selectedMcp.length }})</span></h3>
            <button v-if="ideImport.mcpServers" @click="applyImportedMcp" class="text-[11px] text-brand-600 hover:underline">导入扫描结果({{ importedIdeMcp.length }})</button>
          </div>
          <input v-model="mcpFilterText" placeholder="过滤 MCP..." class="w-full px-2 py-1 text-[11px] border border-ink-300 rounded mb-1">
          <div v-if="ideImport.mcpServers" class="mb-2">
            <div class="text-[10px] text-ink-500 mb-1">从 IDE 扫描到 ({{ Object.keys(ideImport.mcpServers).length }}):</div>
            <div class="grid grid-cols-2 gap-1">
              <label v-for="(cfg, name) in ideImport.mcpServers" :key="'ide_' + name" v-show="!mcpFilterText || name.toLowerCase().includes(mcpFilterText.toLowerCase())" :class="['flex items-center gap-1 p-1 border rounded text-[11px] cursor-pointer', importedIdeMcp.includes(name) ? 'border-brand-400 bg-brand-50/30' : 'border-ink-200 hover:border-brand-300']">
                <input type="checkbox" :value="name" v-model="importedIdeMcp" class="w-3 h-3 accent-brand-500">
                <span class="truncate flex-1">{{ name }}</span>
                <span v-if="selectedMcp.includes(name)" class="text-[9px] text-green-600">✓</span>
              </label>
            </div>
          </div>
          <div class="border-t border-gray-100 pt-2">
            <div class="text-[10px] text-ink-500 mb-1">本地仓库 MCP ({{ Object.keys(mcpTemplate.mcpServers || {}).length }}):</div>
            <div class="grid grid-cols-2 gap-1">
              <div v-for="(_, name) in (mcpTemplate.mcpServers || {})" :key="'tpl_' + name" v-show="!mcpFilterText || name.toLowerCase().includes(mcpFilterText.toLowerCase())" @click="toggleMcp(name)" :class="['p-1.5 border rounded-md cursor-pointer transition', selectedMcp.includes(name) ? 'border-brand-500 bg-brand-50' : 'border-ink-300 hover:border-brand-500']">
                <div class="flex items-center gap-1"><input type="checkbox" :checked="selectedMcp.includes(name)" @click.stop="toggleMcp(name)" class="w-3 h-3 accent-brand-500"><span class="text-xs truncate">{{ name }}</span></div>
              </div>
            </div>
          </div>
        </div>
        <div v-show="wizardStep === 3" class="space-y-2">
          <div class="flex items-center justify-between">
            <h3 class="text-xs font-semibold">技能 <span class="text-[10px] text-ink-500 font-normal">({{ selectedSkills.length }})</span></h3>
            <button v-if="ideImport.skills" @click="applyImportedSkills" class="text-[11px] text-brand-600 hover:underline">导入扫描结果</button>
          </div>
          <div class="flex gap-1.5 mb-1 flex-wrap">
            <select v-model="skillFilter.cat" class="px-2 py-1 text-[11px] border border-ink-300 rounded"><option value="">全部分类</option><option v-for="c in skillCategories" :key="c">{{ c }}</option></select>
            <input v-model="skillFilter.text" placeholder="搜索..." class="flex-1 min-w-[100px] px-2 py-1 text-[11px] border border-ink-300 rounded">
          </div>
          <div class="grid grid-cols-2 gap-1.5 max-h-[55vh] overflow-y-auto">
            <div v-for="s in filteredLocalSkills" :key="s.skill_name" @click="toggleSkill(s.skill_name)" :class="['p-2 border rounded-md cursor-pointer transition', selectedSkills.includes(s.skill_name) ? 'border-brand-500 bg-brand-50' : 'border-ink-300 hover:border-brand-500']">
              <div class="flex items-center gap-1.5"><input type="checkbox" :checked="selectedSkills.includes(s.skill_name)" @click.stop="toggleSkill(s.skill_name)" class="accent-brand-500"><span class="font-medium text-xs">{{ s.skill_name }}</span></div>
              <div class="text-[11px] text-ink-500 mt-0.5 line-clamp-2">{{ s.description }}</div>
            </div>
          </div>
        </div>
        <div v-show="wizardStep === 4" class="space-y-3">
          <h3 class="text-xs font-semibold">命名并生成插件</h3>
          <div class="grid grid-cols-3 gap-2 text-center">
            <div class="bg-brand-50 rounded-lg p-2"><div class="text-lg font-bold text-brand-600">{{ selectedLlm.length }}</div><div class="text-[10px] text-ink-500">LLM</div></div>
            <div class="bg-brand-50 rounded-lg p-2"><div class="text-lg font-bold text-brand-600">{{ selectedMcp.length }}</div><div class="text-[10px] text-ink-500">MCP</div></div>
            <div class="bg-brand-50 rounded-lg p-2"><div class="text-lg font-bold text-brand-600">{{ selectedSkills.length }}</div><div class="text-[10px] text-ink-500">Skills</div></div>
          </div>
          <div class="space-y-2">
            <div class="flex items-center gap-2"><label class="text-[11px] text-ink-500 w-16">name *</label><input v-model="pluginForm.name" placeholder="my-plugin" class="flex-1 px-2 py-1 text-xs border border-ink-300 rounded"></div>
            <div class="flex items-center gap-2"><label class="text-[11px] text-ink-500 w-16">version</label><input v-model="pluginForm.version" class="flex-1 px-2 py-1 text-xs border border-ink-300 rounded"></div>
            <div class="flex items-center gap-2"><label class="text-[11px] text-ink-500 w-16">desc</label><input v-model="pluginForm.description" class="flex-1 px-2 py-1 text-xs border border-ink-300 rounded"></div>
            <div class="flex items-center gap-2"><label class="text-[11px] text-ink-500 w-16">author</label><input v-model="pluginForm.author" class="flex-1 px-2 py-1 text-xs border border-ink-300 rounded"></div>
            <div><label class="text-[11px] text-ink-500 block mb-0.5">install script</label><textarea v-model="pluginForm.install_script" rows="2" placeholder="npm i -g xxx && xxx setup" class="w-full px-2 py-1 text-xs border border-ink-300 rounded font-mono"></textarea></div>
          </div>
          <div class="flex gap-1.5 flex-wrap">
            <button @click="previewPlugin" class="px-3 py-1.5 text-xs bg-brand-500 text-white rounded hover:bg-brand-600">预览 JSON</button>
            <button @click="savePluginFile" class="px-3 py-1.5 text-xs bg-ink-100 rounded hover:bg-ink-300">保存</button>
            <button @click="installPluginFile" class="px-3 py-1.5 text-xs bg-green-500 text-white rounded hover:bg-green-600">生成配置</button>
          </div>
        </div>
        <div class="flex justify-between mt-4 pt-3 border-t border-gray-100">
          <button @click="wizardPrev" :disabled="wizardStep === 0" class="px-3 py-1.5 text-xs bg-ink-100 rounded hover:bg-ink-300 disabled:opacity-40">← 上一步</button>
          <button v-if="wizardStep < wizardSteps.length - 1" @click="wizardNext" class="px-3 py-1.5 text-xs bg-brand-500 text-white rounded hover:bg-brand-600">下一步 →</button>
        </div>
      </div>
    </div>
  </div>
</template>
