<script setup lang="ts">
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useSubagentStore } from '../stores/subagent'
const sa = useSubagentStore()
const { subagentData } = storeToRefs(sa)
const { loadSubagent, saveSubagent, addSubagent, deleteSubagent } = sa
onMounted(() => { loadSubagent() })
</script>
<template>
  <div class="space-y-4">
    <div class="bg-white rounded-xl shadow-card p-5">
      <div class="flex items-center justify-between mb-3 pb-3 border-b border-gray-100">
        <h2 class="text-sm font-semibold flex items-center gap-2">
          <span class="w-1 h-4 bg-brand-500 rounded"></span>Subagent 角色
          <span class="text-[10px] text-ink-500 font-normal">subagent.yaml · {{ subagentData.subagents.length }} 个</span>
        </h2>
        <div class="flex gap-2">
          <button @click="addSubagent" class="px-3 py-1.5 text-xs bg-brand-50 text-brand-600 rounded-md hover:bg-brand-100 font-medium">+ 添加</button>
          <button @click="saveSubagent()" class="px-3 py-1.5 text-xs bg-brand-500 text-white rounded-md hover:bg-brand-600 font-medium">保存</button>
        </div>
      </div>
      <div class="space-y-2">
        <div v-for="(s, i) in subagentData.subagents" :key="i" class="border border-ink-300 rounded-md p-3">
          <div class="grid grid-cols-3 gap-2 mb-2">
            <input v-model="s.name" placeholder="name（如 java-dev）" class="px-2 py-1 text-xs border border-ink-300 rounded font-mono">
            <input v-model="s.role" placeholder="角色（如 Java 开发）" class="px-2 py-1 text-xs border border-ink-300 rounded">
            <input v-model="s.category" placeholder="分类" class="px-2 py-1 text-xs border border-ink-300 rounded">
          </div>
          <input v-model="s.desc" placeholder="描述" class="w-full px-2 py-1 text-xs border border-ink-300 rounded mb-2">
          <textarea v-model="s.prompt" rows="3" placeholder="角色 prompt（系统提示词）" class="w-full px-2 py-1 text-xs border border-ink-300 rounded font-mono"></textarea>
          <div class="text-right mt-1">
            <button @click="deleteSubagent(i)" class="px-2 py-1 text-xs text-red-500 bg-red-50 rounded hover:bg-red-100">删除</button>
          </div>
        </div>
        <div v-if="!subagentData.subagents.length" class="text-center text-ink-500 text-xs py-6">暂无角色，点击 "+ 添加" 创建</div>
      </div>
    </div>
  </div>
</template>
