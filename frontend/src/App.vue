<script setup lang="ts">
import { ref, onMounted } from 'vue'
import Header from './components/Header.vue'
import Toast from './components/Toast.vue'
import Modal from './components/Modal.vue'
import LogPanel from './components/LogPanel.vue'
import IdeView from './views/IdeView.vue'
import PlaceholderView from './views/PlaceholderView.vue'
import { useIdeStore } from './stores/ide'

const tab = ref('ide')
const tabs = [
  { key: 'ide', label: 'IDE 管理' },
  { key: 'env', label: 'LLM 配置' },
  { key: 'mcp', label: 'MCP 配置' },
  { key: 'skill', label: 'Skills 配置' },
  { key: 'plugin', label: '插件配置' },
  { key: 'plugin-build', label: '插件构建' },
]

const ide = useIdeStore()
onMounted(() => {
  ide.loadIdeDetect()
})
</script>

<template>
  <Header :tab="tab" :tabs="tabs" @update:tab="tab = $event" />
  <main class="max-w-[1600px] mx-auto px-6 py-5">
    <IdeView v-if="tab === 'ide'" />
    <PlaceholderView v-else :label="tabs.find((t) => t.key === tab)?.label" />
  </main>
  <Toast />
  <Modal />
  <LogPanel />
</template>
