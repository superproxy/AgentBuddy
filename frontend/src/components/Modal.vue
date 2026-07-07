<script setup lang="ts">
import { useUiStore } from '../stores/ui'
const ui = useUiStore()
</script>

<template>
  <div
    v-if="ui.modalVisible"
    class="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
    @click.self="ui.modalVisible = false"
  >
    <div class="bg-white rounded-lg p-5 w-[80%] max-w-[700px] max-h-[80vh] overflow-auto">
      <h3 class="text-sm font-semibold mb-3">{{ ui.modalTitle }}</h3>
      <pre class="bg-ink-900 text-gray-200 p-3 rounded text-xs overflow-auto">{{ ui.modalContent }}</pre>
      <div class="text-right mt-3">
        <button
          @click="ui.modalVisible = false"
          class="px-3 py-1.5 text-xs bg-ink-100 rounded hover:bg-ink-300"
        >
          关闭
        </button>
      </div>
    </div>
  </div>
</template>
