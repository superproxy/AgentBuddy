<script setup lang="ts">
import { useUiStore } from '../stores/ui'
const ui = useUiStore()
</script>

<template>
  <transition-group name="fade" tag="div" class="fixed top-16 right-4 space-y-2 z-50">
    <div
      v-for="t in ui.toasts"
      :key="t.id"
      :class="[
        'px-4 py-2 rounded-md shadow-lg text-sm text-white',
        t.type === 'err' ? 'bg-red-500' : t.type === 'warn' ? 'bg-orange-500' : 'bg-green-500',
      ]"
    >
      {{ t.msg }}
    </div>
  </transition-group>
</template>
