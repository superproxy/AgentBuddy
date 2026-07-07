<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useIdeStore } from '../stores/ide'

const ide = useIdeStore()
const {
  ideDetectStats, ideDetecting, ideInstallInfo, ideInstallInfoLoaded,
  installedIdes, notInstalledIdes, showNotInstalled,
  ideInstalling, ideUninstalling, ideReinstalling, ideSyncing,
  ideLaunching, ideResuming, ideOpeningConfig,
  expandedIde, expandedIdeCard, ideCardTab,
  ideSessionsMap, ideSessionsStatsMap, ideLoadingSessions,
  exportingSession, shareModalOpen, shareModalSession, shareTargetIde, shareImporting,
  shareTargetIdes,
} = storeToRefs(ide)
const {
  loadIdeDetect, launchIde, installIde, uninstallIde, reinstallIde, openIdeConfig,
  syncIdeConfig, toggleIdeSessions, toggleIdeCard, setIdeCardTab, exportSession,
  openShareModal, importSession,
} = ide
</script>

<template>
  <div class="space-y-4">
    <div class="bg-white rounded-xl shadow-card p-4">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-sm font-semibold flex items-center gap-2">
          <span class="w-1 h-4 bg-brand-500 rounded"></span>IDE 检测与会话管理
        </h2>
        <button @click="loadIdeDetect" :disabled="ideDetecting"
          class="px-3 py-1.5 text-xs bg-brand-50 text-brand-600 rounded-md hover:bg-brand-100 font-medium disabled:opacity-40">
          {{ ideDetecting ? '检测中...' : '重新检测' }}
        </button>
      </div>
      <div class="flex gap-4 text-xs text-ink-600">
        <span>总计: <b class="text-ink-900">{{ ideDetectStats.total }}</b></span>
        <span class="text-green-600">已安装: <b>{{ ideDetectStats.installed }}</b></span>
        <span class="text-ink-400">未安装: <b>{{ ideDetectStats.not_installed }}</b></span>
      </div>
    </div>
    <div v-if="ideDetecting || !ideInstallInfoLoaded" class="text-center py-12 text-ink-500 text-sm">
      {{ ideDetecting ? '检测 IDE 安装状态...' : '加载安装信息...' }}
    </div>
    <div v-else class="space-y-4">
      <div class="grid grid-cols-1 gap-3">
        <div v-for="it in installedIdes" :key="it.key"
             class="border rounded-lg overflow-hidden flex flex-col border-ink-300 hover:border-brand-400 bg-white hover:shadow-sm">
          <div class="flex flex-row">
            <!-- 品牌区 -->
            <div class="w-40 shrink-0 px-4 py-3 flex flex-col justify-center gap-1.5 border-r border-ink-200 bg-ink-50/60">
              <div class="flex items-center gap-1.5">
                <span class="font-bold text-base truncate" :title="it.label">{{ it.label }}</span>
                <span v-if="it.installed" class="w-2 h-2 rounded-full bg-green-500" title="已安装"></span>
              </div>
              <div class="flex items-center gap-1 flex-wrap">
                <button v-if="ideInstallInfo[it.key]?.cli" @click="setIdeCardTab(it.key, 'cli')"
                  :class="['px-1.5 py-0.5 text-[9px] rounded font-medium cursor-pointer', (ideCardTab[it.key] || 'cli') === 'cli' ? 'bg-blue-500 text-white' : 'bg-blue-100 text-blue-700 hover:bg-blue-200']">CLI</button>
                <button v-if="ideInstallInfo[it.key]?.app" @click="setIdeCardTab(it.key, 'app')"
                  :class="['px-1.5 py-0.5 text-[9px] rounded font-medium cursor-pointer', (ideCardTab[it.key] || 'cli') === 'app' ? 'bg-purple-500 text-white' : 'bg-purple-100 text-purple-700 hover:bg-purple-200']">App</button>
              </div>
              <div v-if="it.version" class="text-[10px] text-ink-500 truncate leading-tight" :title="it.version">{{ it.version }}</div>
            </div>
            <!-- 操作区 -->
            <div class="flex-1 min-w-0 flex flex-col">
              <!-- CLI 信息 + 按钮 -->
              <div v-if="(ideCardTab[it.key] || 'cli') === 'cli' && ideInstallInfo[it.key]?.cli" class="px-3 py-2 flex flex-col gap-1 text-xs">
                <div class="flex items-center gap-1.5 min-w-0">
                  <span :class="['text-[10px] shrink-0', it.exe_path ? 'text-green-600' : 'text-ink-400']">{{ it.exe_path ? '●' : '○' }}</span>
                  <code class="text-[10px] bg-ink-100 px-1 rounded text-ink-600 shrink-0">{{ ideInstallInfo[it.key].cli.method }}</code>
                  <span v-if="it.exe_path" class="text-[10px] text-ink-400 truncate flex-1 min-w-0" :title="it.exe_path">{{ it.exe_path }}</span>
                </div>
                <div class="flex gap-1 flex-wrap">
                  <button v-if="!it.exe_path && ideInstallInfo[it.key].cli.method !== 'manual'" @click="installIde(it.key, 'cli')"
                    :disabled="ideInstalling === it.key + ':cli'" class="px-2 py-0.5 text-[10px] text-white bg-blue-500 hover:bg-blue-600 rounded disabled:opacity-40">{{ ideInstalling === it.key + ':cli' ? '...' : '安装' }}</button>
                  <a v-else-if="!it.exe_path && ideInstallInfo[it.key].cli.url" :href="ideInstallInfo[it.key].cli.url" target="_blank" class="px-2 py-0.5 text-[10px] text-blue-600 bg-blue-50 hover:bg-blue-100 rounded">下载</a>
                  <button v-if="it.exe_path && ideInstallInfo[it.key].cli.method !== 'manual'" @click="reinstallIde(it.key, 'cli')"
                    :disabled="ideReinstalling === it.key + ':cli'" class="px-2 py-0.5 text-[10px] text-amber-600 bg-amber-50 hover:bg-amber-100 rounded disabled:opacity-40">{{ ideReinstalling === it.key + ':cli' ? '...' : '重装' }}</button>
                  <button v-if="it.exe_path && ideInstallInfo[it.key].cli.method !== 'manual'" @click="uninstallIde(it.key, 'cli')"
                    :disabled="ideUninstalling === it.key + ':cli'" class="px-2 py-0.5 text-[10px] text-red-500 bg-red-50 hover:bg-red-100 rounded disabled:opacity-40">{{ ideUninstalling === it.key + ':cli' ? '...' : '卸载' }}</button>
                  <button v-if="it.exe_path" @click="launchIde(it.key)" :disabled="!!ideLaunching || !!ideResuming" class="px-2 py-0.5 text-[10px] text-brand-600 bg-brand-50 hover:bg-brand-100 rounded disabled:opacity-40">{{ ideLaunching === it.key ? '...' : '打开' }}</button>
                  <button v-if="it.config_paths?.length" @click="openIdeConfig(it.key)" :disabled="!!ideOpeningConfig" class="px-2 py-0.5 text-[10px] text-ink-600 bg-ink-100 hover:bg-ink-200 rounded disabled:opacity-40">{{ ideOpeningConfig === it.key ? '...' : '配置目录' }}</button>
                  <button @click="syncIdeConfig(it.key)" :disabled="!!ideSyncing" class="px-2 py-0.5 text-[10px] text-brand-600 bg-brand-50 hover:bg-brand-100 rounded disabled:opacity-40">{{ ideSyncing === it.key ? '...' : '配置同步' }}</button>
                  <button v-if="it.sessions_dir" @click="toggleIdeSessions(it.key)" :disabled="!!ideLoadingSessions" class="px-2 py-0.5 text-[10px] text-ink-600 hover:bg-ink-200 rounded disabled:opacity-40">{{ ideLoadingSessions === it.key ? '...' : (expandedIde === it.key ? '收起' : '会话') }}<span v-if="ideSessionsStatsMap[it.key]" class="text-[9px] text-ink-400">({{ ideSessionsStatsMap[it.key].total }})</span></button>
                  <a v-if="ideInstallInfo[it.key].homepage" :href="ideInstallInfo[it.key].homepage" target="_blank" class="px-2 py-0.5 text-[10px] text-ink-500 bg-ink-100 hover:bg-ink-200 rounded">官网</a>
                </div>
              </div>
              <!-- App 信息 + 按钮 -->
              <div v-if="(ideCardTab[it.key] || 'cli') === 'app' && ideInstallInfo[it.key]?.app" class="px-3 py-2 flex flex-col gap-1 text-xs">
                <div class="flex items-center gap-1.5 min-w-0">
                  <span :class="['text-[10px] shrink-0', it.app_path ? 'text-green-600' : 'text-ink-400']">{{ it.app_path ? '●' : '○' }}</span>
                  <code class="text-[10px] bg-ink-100 px-1 rounded text-ink-600 shrink-0">{{ ideInstallInfo[it.key].app.method }}</code>
                  <span v-if="it.app_path" class="text-[10px] text-ink-400 truncate flex-1 min-w-0" :title="it.app_path">{{ it.app_path }}</span>
                </div>
                <div class="flex gap-1 flex-wrap">
                  <button v-if="!it.app_path && ideInstallInfo[it.key].app.method !== 'manual'" @click="installIde(it.key, 'app')"
                    :disabled="ideInstalling === it.key + ':app'" class="px-2 py-0.5 text-[10px] text-white bg-purple-500 hover:bg-purple-600 rounded disabled:opacity-40">{{ ideInstalling === it.key + ':app' ? '...' : '安装' }}</button>
                  <a v-else-if="!it.app_path && ideInstallInfo[it.key].app.url" :href="ideInstallInfo[it.key].app.url" target="_blank" class="px-2 py-0.5 text-[10px] text-purple-600 bg-purple-50 hover:bg-purple-100 rounded">下载</a>
                  <button v-if="it.app_path && ideInstallInfo[it.key].app.method !== 'manual'" @click="reinstallIde(it.key, 'app')"
                    :disabled="ideReinstalling === it.key + ':app'" class="px-2 py-0.5 text-[10px] text-amber-600 bg-amber-50 hover:bg-amber-100 rounded disabled:opacity-40">{{ ideReinstalling === it.key + ':app' ? '...' : '重装' }}</button>
                  <button v-if="it.app_path && ideInstallInfo[it.key].app.method !== 'manual'" @click="uninstallIde(it.key, 'app')"
                    :disabled="ideUninstalling === it.key + ':app'" class="px-2 py-0.5 text-[10px] text-red-500 bg-red-50 hover:bg-red-100 rounded disabled:opacity-40">{{ ideUninstalling === it.key + ':app' ? '...' : '卸载' }}</button>
                  <button v-if="it.app_path" @click="launchIde(it.key)" :disabled="!!ideLaunching || !!ideResuming" class="px-2 py-0.5 text-[10px] text-brand-600 bg-brand-50 hover:bg-brand-100 rounded disabled:opacity-40">{{ ideLaunching === it.key ? '...' : '打开' }}</button>
                  <button @click="syncIdeConfig(it.key)" :disabled="!!ideSyncing" class="px-2 py-0.5 text-[10px] text-brand-600 bg-brand-50 hover:bg-brand-100 rounded disabled:opacity-40">{{ ideSyncing === it.key ? '...' : '配置同步' }}</button>
                  <a v-if="ideInstallInfo[it.key].homepage" :href="ideInstallInfo[it.key].homepage" target="_blank" class="px-2 py-0.5 text-[10px] text-ink-500 bg-ink-100 hover:bg-ink-200 rounded">官网</a>
                </div>
              </div>
            </div>
          </div>
          <!-- 会话列表（展开时） -->
          <div v-if="expandedIde === it.key && ideSessionsMap[it.key]" class="border-t border-ink-200 bg-ink-50/50">
            <div v-if="!ideSessionsMap[it.key].length" class="p-3 text-xs text-ink-400 italic">暂无会话</div>
            <div v-else class="max-h-[300px] overflow-y-auto divide-y divide-ink-200">
              <div v-for="s in ideSessionsMap[it.key]" :key="s.id" class="px-3 py-2 hover:bg-white transition">
                <div class="flex items-start justify-between gap-2">
                  <div class="flex-1 min-w-0">
                    <div class="text-xs font-medium truncate">{{ s.title || s.id.slice(0, 8) }}</div>
                    <div class="text-[10px] text-ink-400 truncate">{{ s.id.slice(0, 12) }} · {{ s.messages_count }} 条 · {{ s.size_bytes }} bytes</div>
                    <div v-if="s.cwd" class="text-[10px] text-ink-400 truncate"><code>{{ s.cwd }}</code></div>
                    <div class="text-[10px] text-ink-400">{{ s.updated_at }}</div>
                  </div>
                  <div class="flex flex-col gap-1 shrink-0">
                    <button @click="launchIde(it.key, s)" :disabled="ideResuming === (it.key + ':' + s.id) || !!ideLaunching" class="px-2 py-1 text-[10px] text-green-600 hover:bg-green-50 rounded disabled:opacity-40">{{ ideResuming === (it.key + ':' + s.id) ? '...' : '继续' }}</button>
                    <button @click="exportSession(it.key, s)" :disabled="exportingSession === s.id" class="px-2 py-1 text-[10px] text-blue-600 hover:bg-blue-50 rounded disabled:opacity-40">{{ exportingSession === s.id ? '...' : '导出' }}</button>
                    <button @click="openShareModal(it.key, s)" class="px-2 py-1 text-[10px] text-purple-600 hover:bg-purple-50 rounded">共享</button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <!-- 未安装 IDE 区（可折叠） -->
      <div v-if="notInstalledIdes.length" class="border border-dashed border-ink-300 rounded-lg overflow-hidden">
        <button @click="showNotInstalled = !showNotInstalled" class="w-full flex items-center justify-between px-4 py-2.5 bg-ink-100/40 hover:bg-ink-100/70 text-left">
          <div class="flex items-center gap-2">
            <span class="w-2 h-2 rounded-full bg-ink-300"></span>
            <span class="text-sm font-medium text-ink-700">未安装 IDE</span>
            <span class="text-[10px] text-ink-500">({{ notInstalledIdes.length }})</span>
          </div>
          <span class="text-ink-500 text-xs">{{ showNotInstalled ? '▼' : '▶' }}</span>
        </button>
        <div v-show="showNotInstalled" class="grid grid-cols-1 gap-3 p-3">
          <div v-for="it in notInstalledIdes" :key="it.key" class="border rounded-lg overflow-hidden border-dashed border-ink-300 bg-ink-100/30">
            <div class="px-4 py-3 text-xs text-ink-500">
              <div class="font-bold text-base mb-1 text-ink-700">{{ it.label }}</div>
              <div class="text-[10px]">未安装 · 点击"安装"或"下载"获取</div>
              <div class="flex gap-1 flex-wrap mt-2">
                <button v-if="ideInstallInfo[it.key]?.cli && ideInstallInfo[it.key].cli.method !== 'manual'" @click="installIde(it.key, 'cli')" :disabled="ideInstalling === it.key + ':cli'" class="px-2 py-0.5 text-[10px] text-white bg-blue-500 hover:bg-blue-600 rounded disabled:opacity-40">{{ ideInstalling === it.key + ':cli' ? '...' : '安装 CLI' }}</button>
                <a v-else-if="ideInstallInfo[it.key]?.cli?.url" :href="ideInstallInfo[it.key].cli.url" target="_blank" class="px-2 py-0.5 text-[10px] text-blue-600 bg-blue-50 hover:bg-blue-100 rounded">下载 CLI</a>
                <button v-if="ideInstallInfo[it.key]?.app && ideInstallInfo[it.key].app.method !== 'manual'" @click="installIde(it.key, 'app')" :disabled="ideInstalling === it.key + ':app'" class="px-2 py-0.5 text-[10px] text-white bg-purple-500 hover:bg-purple-600 rounded disabled:opacity-40">{{ ideInstalling === it.key + ':app' ? '...' : '安装 App' }}</button>
                <a v-else-if="ideInstallInfo[it.key]?.app?.url" :href="ideInstallInfo[it.key].app.url" target="_blank" class="px-2 py-0.5 text-[10px] text-purple-600 bg-purple-50 hover:bg-purple-100 rounded">下载 App</a>
                <a v-if="ideInstallInfo[it.key]?.homepage" :href="ideInstallInfo[it.key].homepage" target="_blank" class="px-2 py-0.5 text-[10px] text-ink-500 bg-ink-100 hover:bg-ink-200 rounded">官网</a>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    <!-- 共享会话 Modal -->
    <div v-if="shareModalOpen" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50" @click.self="shareModalOpen = false">
      <div class="bg-white rounded-lg p-5 w-[500px] max-w-[90vw]">
        <h3 class="text-sm font-semibold mb-3">共享会话到其他 IDE</h3>
        <div v-if="shareModalSession" class="text-xs space-y-2 mb-3">
          <div><span class="text-ink-400">源 IDE:</span> {{ shareModalSession._source_ide }}</div>
          <div><span class="text-ink-400">会话:</span> {{ shareModalSession.title || shareModalSession.id.slice(0, 12) }}</div>
          <div><span class="text-ink-400">消息数:</span> {{ shareModalSession.messages_count }}</div>
        </div>
        <div class="mb-3">
          <label class="text-xs text-ink-500 block mb-1">选择目标 IDE</label>
          <select v-model="shareTargetIde" class="w-full px-2 py-1.5 text-xs border border-ink-300 rounded-md">
            <option value="">-- 选择 --</option>
            <option v-for="t in shareTargetIdes" :key="t.key" :value="t.key">{{ t.label }}</option>
          </select>
          <div v-if="!shareTargetIdes.length" class="text-[10px] text-orange-500 mt-1">无可用目标 IDE（需已安装且有会话目录）</div>
        </div>
        <div class="text-right">
          <button @click="shareModalOpen = false" class="px-3 py-1.5 text-xs bg-ink-100 rounded hover:bg-ink-300 mr-2">取消</button>
          <button @click="importSession" :disabled="!shareTargetIde || shareImporting" class="px-3 py-1.5 text-xs bg-brand-500 text-white rounded hover:bg-brand-600 disabled:opacity-40">{{ shareImporting ? '共享中...' : '确认共享' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>
