<script setup lang="ts">
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import api from "@/api/index";
import { parseErrorMsg } from "@/utils/httpError";

interface AuditItem {
  id: number;
  user_id: number | null;
  username: string;
  action: string;
  resource: string;
  resource_id: string | null;
  detail: string;
  ip_address: string;
  status_code: number;
  created_at: string;
}

const items = ref<AuditItem[]>([]);
const total = ref(0);
const loading = ref(false);

const filters = ref({
  action: "",
  resource: "",
  username: "",
});

const pagination = ref({ skip: 0, limit: 50 });

async function loadLogs() {
  loading.value = true;
  try {
    const params: Record<string, string | number> = {
      skip: pagination.value.skip,
      limit: pagination.value.limit,
    };
    if (filters.value.action) params.action = filters.value.action;
    if (filters.value.resource) params.resource = filters.value.resource;
    if (filters.value.username) params.username = filters.value.username;

    const { data } = await api.get("/audit/", { params });
    items.value = data.items;
    total.value = data.total;
  } catch (e) {
    ElMessage.error(parseErrorMsg(e, "加载审计日志失败"));
  } finally {
    loading.value = false;
  }
}

function actionLabel(action: string) {
  const m: Record<string, string> = {
    create: "创建",
    update: "更新",
    delete: "删除",
    acknowledge: "确认",
    batch_acknowledge: "批量确认",
  };
  return m[action] || action;
}

function actionTagType(action: string): "success" | "warning" | "danger" | "info" | "primary" {
  switch (action) {
    case "create": return "success";
    case "update": return "primary";
    case "delete": return "danger";
    case "acknowledge":
    case "batch_acknowledge": return "warning";
    default: return "info";
  }
}

function statusTagType(code: number): "success" | "danger" | "warning" | "info" {
  if (code < 300) return "success";
  if (code < 400) return "info";
  if (code < 500) return "warning";
  return "danger";
}

function handleSearch() {
  pagination.value.skip = 0;
  loadLogs();
}

function handleReset() {
  filters.value = { action: "", resource: "", username: "" };
  pagination.value = { skip: 0, limit: 50 };
  loadLogs();
}

function handlePageChange(page: number) {
  pagination.value.skip = (page - 1) * pagination.value.limit;
  loadLogs();
}

function formatTime(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString("zh-CN", { hour12: false });
}

onMounted(loadLogs);
</script>

<template>
  <div>
    <div class="page-header">
      <h2>审计日志</h2>
    </div>

    <el-card style="margin-bottom: 16px">
      <el-form :inline="true" :model="filters">
        <el-form-item label="操作类型">
          <el-select v-model="filters.action" clearable placeholder="全部">
            <el-option label="创建" value="create" />
            <el-option label="更新" value="update" />
            <el-option label="删除" value="delete" />
            <el-option label="确认" value="acknowledge" />
            <el-option label="批量确认" value="batch_acknowledge" />
          </el-select>
        </el-form-item>
        <el-form-item label="资源">
          <el-select v-model="filters.resource" clearable placeholder="全部">
            <el-option label="工单" value="workorder" />
            <el-option label="报警" value="alert" />
            <el-option label="SOP 模板" value="sop" />
            <el-option label="用户" value="user" />
            <el-option label="工位" value="station" />
            <el-option label="通知" value="notification" />
          </el-select>
        </el-form-item>
        <el-form-item label="用户名">
          <el-input v-model="filters.username" clearable placeholder="输入用户名" style="width: 120px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card v-loading="loading">
      <el-table :data="items" stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="username" label="用户" width="80" />
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-tag :type="actionTagType(row.action)" size="small">
              {{ actionLabel(row.action) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="resource" label="资源" width="100" />
        <el-table-column prop="resource_id" label="资源ID" width="80" />
        <el-table-column prop="detail" label="详情" min-width="200" show-overflow-tooltip />
        <el-table-column prop="ip_address" label="IP" width="130" />
        <el-table-column label="状态码" width="80">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status_code)" size="small">
              {{ row.status_code }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-if="total > pagination.limit"
        style="margin-top: 16px; justify-content: center"
        layout="total, prev, pager, next"
        :total="total"
        :page-size="pagination.limit"
        @current-change="handlePageChange"
      />
    </el-card>
  </div>
</template>
