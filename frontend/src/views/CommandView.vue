<script setup lang="ts">
import { onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useCmdStore } from '../stores/cmd'
const cmd = useCmdStore()
const { cmdData } = storeToRefs(cmd)
const { loadCmd, saveCmd, addCmd, deleteCmd, copyCmd } = cmd
onMounted(() => { loadCmd() })
</script>
<template>
  <div class="space-y-4">
    <div class="bg-white rounded-xl shadow-card p-5">
      <div class="flex items-center justify-between mb-3 pb-3 border-b border-gray-100">
        <h2 class="text-sm font-semibold flex items-center gap-2">
          <span class="w-1 h-4 bg-brand-500 rounded"></span>常用命令
          <span class="text-[10px] text-ink-500 font-normal">cmd.yaml · {{ cmdData.commands.length }} 条</span>
        </h2>
        <div class="flex gap-2">
          <button @click="addCmd" class="px-3 py-1.5 text-xs bg-brand-50 text-brand-600 rounded-md hover:bg-brand-100 font-medium">+ 添加</button>
          <button @click="saveCmd()" class="px-3 py-1.5 text-xs bg-brand-500 text-white rounded-md hover:bg-brand-600 font-medium">保存</button>
        </div>
      </div>
      <div class="space-y-2">
        <div v-for="(c, i) in cmdData.commands" :key="i" class="border border-ink-300 rounded-md p-3">
          <div class="grid grid-cols-3 gap-2 mb-2">
            <input v-model="c.name" placeholder="名称" class="px-2 py-1 text-xs border border-ink-300 rounded">
            <input v-model="c.category" placeholder="分类" class="px-2 py-1 text-xs border border-ink-300 rounded">
            <button @click="deleteCmd(i)" class="px-2 py-1 text-xs text-red-500 bg-red-50 rounded hover:bg-red-100">删除</button>
          </div>
          <input v-model="c.command" placeholder="命令" class="w-full px-2 py-1 text-xs border border-ink-300 rounded font-mono mb-2">
          <div class="flex gap-2 items-center">
            <input v-model="c.desc" placeholder="描述" class="flex-1 px-2 py-1 text-xs border border-ink-300 rounded">
            <button @click="copyCmd(c.command)" class="px-2 py-1 text-xs text-brand-600 bg-brand-50 rounded hover:bg-brand-100">复制</button>
          </div>
        </div>
        <div v-if="!cmdData.commands.length" class="text-center text-ink-500 text-xs py-6">暂无命令，点击 "+ 添加" 创建</div>
      </div>
    </div>
  </div>
</template>
