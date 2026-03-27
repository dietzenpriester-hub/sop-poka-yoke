<script setup lang="ts">
import { ref, onMounted, onUnmounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { alertApi, type AlertItem, type AlertStats } from "@/api/alert";

const alerts = ref<AlertItem[]>([]);
const stats = ref<AlertStats>({ total: 0, unacknowledged: 0, by_severity: {} });
const loading = ref(false);
const selectedIds = ref<number[]>([]);

const filters = ref({
  severity: "",
  alert_type: "",
  acknowledged: "",
});
const pagination = ref({ skip: 0, limit: 50 });

let refreshTimer: ReturnType<typeof setInterval> | null = null;

async function loadAlerts() {
  loading.value = true;
  try {
    const params: Record<string, unknown> = { ...pagination.value };
    if (filters.value.severity) params.severity = filters.value.severity;
    if (filters.value.alert_type) params.alert_type = filters.value.alert_type;
    if (filters.value.acknowledged) params.acknowledged = filters.value.acknowledged;
    const { data } = await alertApi.list(params as Parameters<typeof alertApi.list>[0]);
    alerts.value = data;
  } catch {
    ElMessage.error("加载报警列表失败");
  } finally {
    loading.value = false;
  }
}

async function loadStats() {
  try {
    const { data } = await alertApi.stats();
    stats.value = data;
  } catch {
    ElMessage.warning("统计数据加载失败，显示可能不准确");
  }
}

async function handleAcknowledge(id: number) {
  try {
    await alertApi.acknowledge(id);
    ElMessage.success("已确认");
    loadAlerts();
    loadStats();
  } catch {
    ElMessage.error("确认失败");
  }
}

async function handleBatchAcknowledge() {
  if (selectedIds.value.length === 0) {
    ElMessage.warning("请选择要确认的报警");
    return;
  }
  try {
    await ElMessageBox.confirm(
      `确认处理 ${selectedIds.value.length} 条报警？`,
      "批量确认",
      { type: "warning" }
    );
    await alertApi.batchAcknowledge(selectedIds.value);
    ElMessage.success(`已确认 ${selectedIds.value.length} 条`);
    selectedIds.value = [];
    loadAlerts();
    loadStats();
  } catch (e) {
    if (e !== "cancel") ElMessage.error("批量确认失败");
  }
}

function handleSelectionChange(rows: AlertItem[]) {
  selectedIds.value = rows.map((r) => r.id);
}

function severityTagType(severity: string): "" | "success" | "warning" | "danger" | "info" {
  switch (severity) {
    case "CRITICAL": return "danger";
    case "ERROR": return "danger";
    case "WARN": return "warning";
    case "INFO": return "info";
    default: return "";
  }
}

function formatTime(ts: string): string {
  return new Date(ts).toLocaleString("zh-CN");
}

function handleSearch() {
  pagination.value.skip = 0;
  loadAlerts();
}

function handleReset() {
  filters.value = { severity: "", alert_type: "", acknowledged: "" };
  pagination.value = { skip: 0, limit: 50 };
  loadAlerts();
}

onMounted(() => {
  loadAlerts();
  loadStats();
  refreshTimer = setInterval(() => {
    loadAlerts();
    loadStats();
  }, 15000);
});

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
});
</script>

<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center">
      <h2>报警管理</h2>
      <div>
        <el-button type="primary" @click="loadAlerts" :loading="loading">刷新</el-button>
        <el-button type="warning" @click="handleBatchAcknowledge" :disabled="selectedIds.length === 0">
          批量确认 ({{ selectedIds.length }})
        </el-button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover">
          <template #header>报警总数</template>
          <div style="font-size: 28px; font-weight: bold; color: #409eff">{{ stats.total }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover">
          <template #header>
            <el-badge :value="stats.unacknowledged" :hidden="stats.unacknowledged === 0" type="danger">
              未确认
            </el-badge>
          </template>
          <div style="font-size: 28px; font-weight: bold; color: #f56c6c">{{ stats.unacknowledged }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover">
          <template #header>ERROR</template>
          <div style="font-size: 28px; font-weight: bold; color: #f56c6c">
            {{ (stats.by_severity?.ERROR || 0) + (stats.by_severity?.CRITICAL || 0) }}
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover">
          <template #header>WARN</template>
          <div style="font-size: 28px; font-weight: bold; color: #e6a23c">{{ stats.by_severity?.WARN || 0 }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 筛选 -->
    <el-card style="margin-top: 16px">
      <el-form inline>
        <el-form-item label="严重度">
          <el-select v-model="filters.severity" clearable placeholder="全部" style="width: 120px">
            <el-option label="CRITICAL" value="CRITICAL" />
            <el-option label="ERROR" value="ERROR" />
            <el-option label="WARN" value="WARN" />
            <el-option label="INFO" value="INFO" />
          </el-select>
        </el-form-item>
        <el-form-item label="报警类型">
          <el-select v-model="filters.alert_type" clearable placeholder="全部" style="width: 140px">
            <el-option label="E001 步骤顺序" value="E001" />
            <el-option label="E002 步骤超时" value="E002" />
            <el-option label="E003 物料不匹配" value="E003" />
            <el-option label="E004 完工检验" value="E004" />
            <el-option label="W001 跳步警告" value="W001" />
            <el-option label="W002 低置信度" value="W002" />
            <el-option label="I001 人工放行" value="I001" />
            <el-option label="I002 工单完成" value="I002" />
            <el-option label="C001 系统离线" value="C001" />
            <el-option label="C002 GPU过热" value="C002" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filters.acknowledged" clearable placeholder="全部" style="width: 120px">
            <el-option label="未确认" value="0" />
            <el-option label="已确认" value="1" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 报警列表 -->
    <el-table
      :data="alerts"
      v-loading="loading"
      style="margin-top: 16px"
      @selection-change="handleSelectionChange"
      row-key="id"
    >
      <el-table-column type="selection" width="40" />
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="alert_type" label="报警代码" width="100" />
      <el-table-column prop="severity" label="严重度" width="100">
        <template #default="{ row }">
          <el-tag :type="severityTagType(row.severity)" size="small">{{ row.severity }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="message" label="消息" min-width="200" show-overflow-tooltip />
      <el-table-column prop="step_index" label="步骤" width="70" />
      <el-table-column prop="station_id" label="工位" width="80" />
      <el-table-column prop="acknowledged" label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.acknowledged === '1' ? 'success' : 'danger'" size="small">
            {{ row.acknowledged === "1" ? "已确认" : "未确认" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="时间" width="170">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="row.acknowledged === '0'"
            type="primary"
            size="small"
            @click="handleAcknowledge(row.id)"
          >
            确认
          </el-button>
          <span v-else style="color: #67c23a; font-size: 12px">已处理</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div style="margin-top: 16px; display: flex; justify-content: flex-end">
      <el-button :disabled="pagination.skip === 0" @click="pagination.skip = Math.max(0, pagination.skip - pagination.limit); loadAlerts()">
        上一页
      </el-button>
      <span style="line-height: 32px; margin: 0 12px; color: #666">
        第 {{ Math.floor(pagination.skip / pagination.limit) + 1 }} 页
      </span>
      <el-button :disabled="alerts.length < pagination.limit" @click="pagination.skip += pagination.limit; loadAlerts()">
        下一页
      </el-button>
    </div>
  </div>
</template>
