<script setup lang="ts">
import { ref, onMounted } from 'vue'
import Header from './components/Header.vue'
import Toast from './components/Toast.vue'
import Modal from './components/Modal.vue'
import LogPanel from './components/LogPanel.vue'
import IdeView from './views/IdeView.vue'
import EnvView from './views/EnvView.vue'
import McpView from './views/McpView.vue'
import SkillView from './views/SkillView.vue'
import PluginView from './views/PluginView.vue'
import PluginBuildView from './views/PluginBuildView.vue'
import CommandView from './views/CommandView.vue'
import { useIdeStore } from './stores/ide'
import { useEnvStore } from './stores/env'
import { useMcpStore } from './stores/mcp'

const tab = ref('ide')
const tabs = [
  { key: 'ide', label: 'IDE 管理' },
  { key: 'env', label: 'LLM 配置' },
  { key: 'mcp', label: 'MCP 配置' },
  { key: 'skill', label: 'Skills 配置' },
  { key: 'plugin', label: '插件配置' },
  { key: 'plugin-build', label: '插件构建' },
  { key: 'command', label: '常用命令' },
]

const ide = useIdeStore()
const env = useEnvStore()
const mcp = useMcpStore()
onMounted(() => {
  ide.loadIdeDetect()
  env.loadEnv()
  mcp.loadMcpCatalog()
  mcp.loadMcpConfig()
})
</script>

<template>
  <Header :tab="tab" :tabs="tabs" @update:tab="tab = $event" />
  <main class="max-w-[1600px] mx-auto px-6 py-5">
    <IdeView v-if="tab === 'ide'" />
    <EnvView v-else-if="tab === 'env'" />
    <McpView v-else-if="tab === 'mcp'" />
    <SkillView v-else-if="tab === 'skill'" />
    <PluginView v-else-if="tab === 'plugin'" />
    <PluginBuildView v-else-if="tab === 'plugin-build'" />
    <CommandView v-else-if="tab === 'command'" />
  </main>
  <Toast />
  <Modal />
  <LogPanel />
</template>
