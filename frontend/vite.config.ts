import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

// Vite 配置：
// - base: './' 相对路径，Flask 静态托管 + pywebview 加载 dist/index.html 兼容
// - outDir: 产物输出到 tools/dist-ui，被 PyInstaller collect_dir('tools') 自动打包
// - dev proxy: /api + /static 转发到 Flask(5000)，开发时前端跑 5173
export default defineConfig({
  base: './',
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    outDir: '../tools/dist-ui',
    emptyOutDir: true,
    // 产物用相对路径加载资源（配合 base: './'）
    assetsDir: 'assets',
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
      '/static': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
    },
  },
})
