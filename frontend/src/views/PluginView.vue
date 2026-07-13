<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { usePluginStore } from '../stores/plugin'
const plugin = usePluginStore()
const { plugins, installingPlugin } = storeToRefs(plugin)
const { refreshPluginList, exportPlugin, exportAllPlugins, onImportPluginFile, onTogglePlugin, editPlugin } = plugin
const inputRef = ref<HTMLInputElement | null>(null)
// 导出下拉菜单状态
const exportMenu = ref<string | null>(null)
function toggleExportMenu(file: string) {
  exportMenu.value = exportMenu.value === file ? null : file
}
function doExport(file: string, format: 'zip' | 'yaml') {
  exportPlugin(file, format)
  exportMenu.value = null
}
function triggerImport() { inputRef.value?.click() }
onMounted(() => { refreshPluginList() })
</script>
<template>
  <div class="space-y-3">
    <div class="bg-white rounded-xl shadow-card p-4">
      <div class="flex items-center justify-between mb-3 pb-2 border-b border-gray-100">
        <h3 class="text-sm font-semibold flex items-center gap-2">
          <span class="w-1 h-4 bg-brand-500 rounded"></span>可用插件列表
          <span class="text-[10px] text-ink-500 font-normal">{{ plugins.length }} 个</span>
          <span v-if="installingPlugin" class="text-[10px] text-brand-600 font-normal">安装中: {{ installingPlugin }}</span>
        </h3>
        <div class="flex items-center gap-2">
          <button @click="exportAllPlugins" class="text-[11px] text-ink-600 hover:text-brand-600" title="导出全部插件及关联 Skills 为 zip">导出全部</button>
          <button @click="triggerImport" class="text-[11px] text-brand-600 hover:underline" title="导入插件（支持 .zip 含 Skills 包 或 .yaml）">导入</button>
          <input ref="inputRef" type="file" accept=".yaml,.yml,.zip" @change="onImportPluginFile" class="hidden">
          <button @click="refreshPluginList" class="text-[11px] text-brand-600 hover:underline">刷新</button>
        </div>
      </div>
      <div class="space-y-1.5">
        <div v-for="p in plugins" :key="p.file"
             :class="['flex items-center gap-3 border rounded-lg px-3 py-2 transition', p.installed ? 'border-green-400 bg-green-50/30' : 'border-ink-300 hover:border-brand-500']">
          <input type="checkbox" :checked="p.installed" @change="onTogglePlugin(p, $event.target.checked)" :disabled="installingPlugin === p.file" class="w-4 h-4 accent-brand-500 cursor-pointer flex-shrink-0">
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
              <span class="font-medium text-xs text-ink-900 truncate">{{ p.name }}</span>
              <span class="text-[10px] text-ink-500">v{{ p.version }}</span>
              <span v-if="p.installed" class="text-[10px] text-green-600">✓ 已安装</span>
            </div>
            <div class="text-[11px] text-ink-500 truncate">{{ p.description }}</div>
          </div>
          <div class="flex gap-1.5 text-[10px] flex-shrink-0">
            <span class="px-1.5 py-0.5 bg-brand-50 text-brand-600 rounded">{{ p.skills_count }} skills</span>
            <span class="px-1.5 py-0.5 bg-brand-50 text-brand-600 rounded">{{ p.mcp_count }} mcp</span>
          </div>
          <!-- 导出下拉菜单 -->
          <div class="relative flex-shrink-0">
            <button @click="toggleExportMenu(p.file)" class="text-[10px] text-ink-500 hover:text-brand-600">导出 ▾</button>
            <div v-if="exportMenu === p.file" class="absolute right-0 top-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-10 min-w-[120px]">
              <button @click="doExport(p.file, 'zip')" class="block w-full text-left px-3 py-1.5 text-[10px] text-ink-700 hover:bg-brand-50 hover:text-brand-600">
                📦 ZIP（含 Skills）
              </button>
              <button @click="doExport(p.file, 'yaml')" class="block w-full text-left px-3 py-1.5 text-[10px] text-ink-700 hover:bg-brand-50 hover:text-brand-600 border-t border-gray-100">
                📄 YAML（仅配置）
              </button>
            </div>
          </div>
          <button @click="editPlugin(p.file)" class="text-[10px] text-brand-600 hover:underline flex-shrink-0">编辑</button>
        </div>
        <div v-if="!plugins.length" class="text-center text-ink-500 text-xs py-6">暂无可用插件</div>
      </div>
    </div>
  </div>
</template>
