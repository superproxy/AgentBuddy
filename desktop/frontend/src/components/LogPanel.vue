<script setup lang="ts">
import { useUiStore } from '../stores/ui'
const ui = useUiStore()
</script>

<template>
  <div
    v-if="ui.logVisible"
    class="fixed bottom-4 right-4 w-[600px] max-w-[90vw] bg-ink-900 text-gray-200 rounded-lg shadow-2xl z-40"
  >
    <div class="flex justify-between items-center px-3 py-2 border-b border-white/10">
      <span class="text-xs font-medium">日志</span>
      <button @click="ui.logVisible = false" class="text-white/60 hover:text-white">×</button>
    </div>
    <div class="log-panel p-3 text-xs max-h-[300px] overflow-y-auto whitespace-pre-wrap">
      {{ ui.logText }}
    </div>
  </div>
</template>
