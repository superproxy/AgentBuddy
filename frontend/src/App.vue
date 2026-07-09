<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { storeToRefs } from 'pinia'
import Header from './components/Header.vue'
import SyncBar from './components/SyncBar.vue'
import Toast from './components/Toast.vue'
import Modal from './components/Modal.vue'
import AppDialog from './components/AppDialog.vue'
import LogPanel from './components/LogPanel.vue'
import IdeView from './views/IdeView.vue'
import EnvView from './views/EnvView.vue'
import McpView from './views/McpView.vue'
import SkillView from './views/SkillView.vue'
import CommandView from './views/CommandView.vue'
import SubagentView from './views/SubagentView.vue'
import PluginView from './views/PluginView.vue'
import PluginBuildView from './views/PluginBuildView.vue'
import { useIdeStore } from './stores/ide'
import { useEnvStore } from './stores/env'
import { useMcpStore } from './stores/mcp'
import { useSyncLayoutStore } from './stores/syncLayout'

const tab = ref('ide')
const tabs = [
  { key: 'ide', label: 'AIDE 管理' },
  { key: 'env', label: 'LLM 配置' },
  { key: 'mcp', label: 'MCP 配置' },
  { key: 'skill', label: 'Skills 配置' },
  { key: 'command', label: '自定义命令' },
  { key: 'subagent', label: 'Subagent' },
  { key: 'plugin', label: '插件配置' },
  { key: 'plugin-build', label: '插件构建' },
]

const ide = useIdeStore()
const env = useEnvStore()
const mcp = useMcpStore()
const syncLayout = useSyncLayoutStore()
const { placement, dockSize } = storeToRefs(syncLayout)

const syncVisible = computed(() => tab.value !== 'plugin-build' && tab.value !== 'ide')

/** 为停靠面板预留空间，避免遮挡主内容 */
const mainStyle = computed(() => {
  if (!syncVisible.value) return undefined
  const pad: Record<string, string> = {}
  switch (placement.value) {
    case 'left':
      pad.paddingLeft = `${Math.round(dockSize.value.width || 360)}px`
      break
    case 'right':
      pad.paddingRight = `${Math.round(dockSize.value.width || 360)}px`
      break
    case 'bottom':
      pad.paddingBottom = `${Math.round(dockSize.value.height || 280)}px`
      break
    case 'top':
      pad.paddingTop = `${Math.round(dockSize.value.height || 0)}px`
      break
    default:
      break
  }
  return Object.keys(pad).length ? pad : undefined
})

onMounted(() => {
  ide.loadIdeDetect()
  env.loadEnv()
  mcp.loadMcpCatalog()
  mcp.loadMcpConfig()
})
</script>

<template>
  <div class="app-root min-h-screen">
    <Header :tab="tab" :tabs="tabs" @update:tab="tab = $event" />

    <main
      class="max-w-[1600px] w-full mx-auto px-6 py-5 transition-[padding] duration-200"
      :style="mainStyle"
    >
      <IdeView v-if="tab === 'ide'" />
      <EnvView v-else-if="tab === 'env'" />
      <McpView v-else-if="tab === 'mcp'" />
      <SkillView v-else-if="tab === 'skill'" />
      <CommandView v-else-if="tab === 'command'" />
      <SubagentView v-else-if="tab === 'subagent'" />
      <PluginView v-else-if="tab === 'plugin'" />
      <PluginBuildView v-else-if="tab === 'plugin-build'" />
    </main>

    <SyncBar :tab="tab" />

    <Toast />
    <Modal />
    <AppDialog />
    <LogPanel />
  </div>
</template>
