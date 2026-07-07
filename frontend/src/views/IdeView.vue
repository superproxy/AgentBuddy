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
        <div v-for="it in installedIdes" :key="it.key" class="border rounded-lg p-3 bg-white">
          <div class="flex justify-between items-center">
            <div class="font-medium text-sm">{{ it.label }}</div>
            <div class="flex gap-1">
              <button v-if="it.exe_path || it.app_path" @click="launchIde(it.key)" :disabled="!!ideLaunching"
                class="px-2 py-0.5 text-[10px] text-brand-600 bg-brand-50 rounded">{{ ideLaunching === it.key ? '...' : '打开' }}</button>
              <button @click="syncIdeConfig(it.key)" :disabled="!!ideSyncing"
                class="px-2 py-0.5 text-[10px] text-brand-600 bg-brand-50 rounded">{{ ideSyncing === it.key ? '...' : '配置同步' }}</button>
              <button v-if="it.sessions_dir" @click="toggleIdeSessions(it.key)" class="px-2 py-0.5 text-[10px] text-ink-600 rounded">会话</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
