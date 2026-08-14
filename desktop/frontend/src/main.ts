import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import './style.css'
import { useThemeStore } from './stores/theme'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)

// 初始化主题（必须在 mount 之前应用 data-theme，避免闪烁）
useThemeStore(pinia)

app.mount('#app')
