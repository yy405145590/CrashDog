<template>
  <el-container style="min-height: 100vh">
    <el-header style="background: #001529; display: flex; align-items: center; padding: 0 20px">
      <h1 style="color: #fff; margin: 0; font-size: 20px; cursor: pointer; margin-right: 40px"
          @click="$router.push('/')">
        CrashDog
      </h1>
      <el-menu
        :default-active="activeMenu"
        mode="horizontal"
        background-color="#001529"
        text-color="#ffffffa6"
        active-text-color="#fff"
        router
        style="border-bottom: none; flex: 1"
      >
        <el-menu-item index="/">崩溃管理</el-menu-item>
        <el-menu-item index="/symbols">符号管理</el-menu-item>
      </el-menu>
    </el-header>
    <el-main style="padding: 20px; background: #f0f2f5">
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const activeMenu = computed(() => {
  if (route.path.startsWith('/symbols')) return '/symbols'
  return '/'
})
</script>

<style>
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
</style>
