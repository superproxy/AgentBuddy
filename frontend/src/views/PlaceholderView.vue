<script setup lang="ts">
defineProps<{ label?: string }>()
</script>

<template>
  <div class="bg-white rounded-xl shadow-card p-10 text-center">
    <div class="text-ink-500 text-sm mb-2">
      {{ label || '该模块' }}正在迁移到 Vue 3 + Vite
    </div>
    <div class="text-ink-400 text-xs mb-4">
      第一阶段已迁移「IDE 管理」tab，其他 tab 陆续迁移中
    </div>
    <a
      href="/old"
      target="_blank"
      class="inline-block px-4 py-2 text-xs bg-brand-50 text-brand-600 rounded-md hover:bg-brand-100"
    >
      访问旧版完整功能 →
    </a>
  </div>
</template>
