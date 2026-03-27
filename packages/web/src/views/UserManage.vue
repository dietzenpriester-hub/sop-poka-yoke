<script setup lang="ts">
import { ref } from "vue";

const users = ref([
  { id: 1, name: "张三", role: "admin", badge: "B001" },
  { id: 2, name: "李四", role: "operator", badge: "B002" },
  { id: 3, name: "王五", role: "supervisor", badge: "B003" },
]);
</script>

<template>
  <div>
    <h2>用户管理</h2>
    <el-table :data="users" style="margin-top: 20px">
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="name" label="姓名" />
      <el-table-column prop="role" label="角色">
        <template #default="{ row }">
          <el-tag :type="row.role === 'admin' ? 'danger' : row.role === 'supervisor' ? 'warning' : 'info'">
            {{ row.role }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="badge" label="工牌号" />
    </el-table>
  </div>
</template>
