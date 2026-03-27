<script setup lang="ts">
import { ref } from "vue";

const stations = ref([
  { id: 1, name: "ST-01", line: "产线 A", status: "running", currentStep: "拧螺丝" },
  { id: 2, name: "ST-02", line: "产线 A", status: "idle", currentStep: "-" },
  { id: 3, name: "ST-03", line: "产线 B", status: "error", currentStep: "物料校验" },
]);
</script>

<template>
  <div>
    <h2>工位管理</h2>
    <el-table :data="stations" style="margin-top: 20px">
      <el-table-column prop="name" label="工位" />
      <el-table-column prop="line" label="产线" />
      <el-table-column prop="status" label="状态">
        <template #default="{ row }">
          <el-tag :type="row.status === 'running' ? 'success' : row.status === 'error' ? 'danger' : 'info'">
            {{ row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="currentStep" label="当前步骤" />
    </el-table>
  </div>
</template>
