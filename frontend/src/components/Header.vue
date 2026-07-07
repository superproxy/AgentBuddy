<script setup lang="ts">
interface TabItem {
  key: string
  label: string
}
defineProps<{ tab: string; tabs: TabItem[] }>()
const emit = defineEmits<{ (e: 'update:tab', v: string): void }>()
</script>

<template>
  <header class="gradient-bg text-white shadow-lg sticky top-0 z-30">
    <div class="max-w-[1600px] mx-auto px-6 py-3 flex items-center justify-between">
      <div class="flex items-center gap-3">
        <div
          class="w-9 h-9 rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center font-bold text-lg shadow-md"
        >
          A
        </div>
        <div>
          <h1 class="text-base font-semibold">AgentBuddy 配置工具</h1>
          <div class="text-xs text-white/60">Vue 3 + Vite 重构中 · IDE 管理 tab 已迁移</div>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <a
          href="https://www.modelscope.cn/mcp"
          target="_blank"
          class="text-xs px-3 py-1.5 rounded-md glass hover:bg-white/20 transition"
          >MCP 市场</a
        >
        <a
          href="https://www.modelscope.cn/skills"
          target="_blank"
          class="text-xs px-3 py-1.5 rounded-md glass hover:bg-white/20 transition"
          >Skills 市场</a
        >
        <a
          href="/old"
          target="_blank"
          class="text-xs px-3 py-1.5 rounded-md glass hover:bg-white/20 transition"
          >旧版 UI</a
        >
      </div>
    </div>
    <nav class="max-w-[1600px] mx-auto px-6 flex gap-1">
      <button
        v-for="t in tabs"
        :key="t.key"
        @click="emit('update:tab', t.key)"
        :class="[
          'px-5 py-2.5 text-sm font-medium border-b-2 transition',
          tab === t.key
            ? 'border-white text-white'
            : 'border-transparent text-white/60 hover:text-white/90',
        ]"
      >
        {{ t.label }}
      </button>
    </nav>
  </header>
</template>
