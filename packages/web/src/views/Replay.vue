<script setup lang="ts">
import { ref } from "vue";

const searchSN = ref("");
const clips = ref<unknown[]>([]);

async function search() {
  clips.value = [];
}
</script>

<template>
  <div>
    <h2>视频回放</h2>
    <el-form inline style="margin-top: 20px">
      <el-form-item label="SN 号">
        <el-input v-model="searchSN" placeholder="输入产品序列号" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="search">查询</el-button>
      </el-form-item>
    </el-form>
    <el-empty v-if="clips.length === 0" description="暂无视频记录" />
  </div>
</template>
