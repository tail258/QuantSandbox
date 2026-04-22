<template>
  <div class="app-container">
    <el-menu mode="horizontal" background-color="#545c64" text-color="#fff" router>
      <el-menu-item index="/">📈 量化回测总览</el-menu-item>
    </el-menu>
    <router-view></router-view>
  </div>
</template>

<style>
body { margin: 0; font-family: sans-serif; background-color: #f5f7fa; }
.app-container { min-height: 100vh; }
</style>