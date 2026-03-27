<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Refresh } from "@element-plus/icons-vue";
import {
  lifecycleApi,
  type StorageStats,
  type RetentionPolicy,
  type CleanupLog,
} from "@/api/lifecycle";

function parseErrorMsg(e: unknown, fallback: string): string {
  const resp = (e as { response?: { data?: { detail?: string } } })?.response;
  return resp?.data?.detail || fallback;
}

const loading = ref(false);
const stats = ref<StorageStats | null>(null);
const policies = ref<RetentionPolicy[]>([]);
const history = ref<CleanupLog[]>([]);

const expiredKeys = [
  { key: "step_ok", label: "OK 截图" },
  { key: "step_ng", label: "NG 视频" },
  { key: "step_skip", label: "SKIP 视频" },
  { key: "alert", label: "报警视频" },
  { key: "material_check", label: "物料校验" },
  { key: "completion_check", label: "完工检验" },
  { key: "override_log", label: "放行审计" },
];

const expiredRows = computed(() =>
  expiredKeys.map(({ key, label }) => ({
    key,
    label,
    count: stats.value?.expired_counts?.[key] ?? 0,
  }))
);

function statusTagType(s: string): "" | "success" | "warning" | "danger" | "info" {
  switch (s) {
    case "completed":
      return "success";
    case "failed":
      return "danger";
    case "running":
      return "warning";
    default:
      return "info";
  }
}

async function loadAll() {
  loading.value = true;
  try {
    const results = await Promise.allSettled([
      lifecycleApi.getStats(),
      lifecycleApi.getPolicies(),
      lifecycleApi.getHistory({ limit: 50 }),
    ]);
    if (results[0].status === "fulfilled") stats.value = results[0].value.data;
    if (results[1].status === "fulfilled") policies.value = results[1].value.data.policies;
    if (results[2].status === "fulfilled") history.value = results[2].value.data;
    const failures = results.filter((r) => r.status === "rejected");
    if (failures.length === results.length) {
      ElMessage.error("所有数据加载失败");
    } else if (failures.length > 0) {
      ElMessage.warning("部分数据加载失败");
    }
  } finally {
    loading.value = false;
  }
}

async function previewCleanup() {
  try {
    await ElMessageBox.confirm(
      "预览模式不会删除任何对象，仅统计将要清理的记录与对象数量。是否继续？",
      "预览清理",
      { type: "info", confirmButtonText: "开始预览", cancelButtonText: "取消" }
    );
    loading.value = true;
    const { data } = await lifecycleApi.runCleanup(true);
    ElMessage.success(data.message);
    await loadAll();
  } catch (e: unknown) {
    if (e !== "cancel") ElMessage.error(parseErrorMsg(e, "预览失败"));
  } finally {
    loading.value = false;
  }
}

async function executeCleanup() {
  try {
    await ElMessageBox.confirm(
      "将按保留策略永久删除过期媒体文件并清空数据库中的 URL，此操作不可恢复。确定执行？",
      "执行清理",
      { type: "warning", confirmButtonText: "确定执行", cancelButtonText: "取消" }
    );
    loading.value = true;
    const { data } = await lifecycleApi.runCleanup(false);
    ElMessage.success(data.message);
    await loadAll();
  } catch (e: unknown) {
    if (e !== "cancel") ElMessage.error(parseErrorMsg(e, "清理失败"));
  } finally {
    loading.value = false;
  }
}

function formatTime(ts: string | null): string {
  if (!ts) return "—";
  return new Date(ts).toLocaleString("zh-CN");
}

onMounted(() => loadAll());
</script>

<template>
  <div v-loading="loading">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px">
      <h2 style="margin: 0">数据生命周期</h2>
      <el-button type="primary" :icon="Refresh" @click="loadAll">刷新</el-button>
    </div>

    <el-row :gutter="16" style="margin-bottom: 16px">
      <el-col :xs="24" :sm="12" :md="8" :lg="4" style="margin-bottom: 12px">
        <el-card shadow="hover">
          <el-statistic title="步骤记录" :value="stats?.total_step_records ?? 0" />
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="8" :lg="4" style="margin-bottom: 12px">
        <el-card shadow="hover">
          <el-statistic title="报警事件" :value="stats?.total_alerts ?? 0" />
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="8" :lg="4" style="margin-bottom: 12px">
        <el-card shadow="hover">
          <el-statistic title="物料校验" :value="stats?.total_material_checks ?? 0" />
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="8" :lg="4" style="margin-bottom: 12px">
        <el-card shadow="hover">
          <el-statistic title="完工检验" :value="stats?.total_completion_checks ?? 0" />
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="8" :lg="4" style="margin-bottom: 12px">
        <el-card shadow="hover">
          <el-statistic title="放行审计" :value="stats?.total_override_logs ?? 0" />
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :xs="24" :lg="12" style="margin-bottom: 16px">
        <el-card shadow="never">
          <template #header>保留策略</template>
          <el-table :data="policies" stripe size="small" max-height="360">
            <el-table-column prop="type_name" label="类型" width="140" />
            <el-table-column prop="retention_days" label="保留天数" width="100" />
            <el-table-column prop="description" label="说明" />
          </el-table>
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="12" style="margin-bottom: 16px">
        <el-card shadow="never">
          <template #header>已过期待清理（估算）</template>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item v-for="row in expiredRows" :key="row.key" :label="row.label">
              <el-tag :type="row.count > 0 ? 'danger' : 'success'" size="small">
                {{ row.count }} 条
              </el-tag>
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" style="margin-bottom: 16px">
      <template #header>
        <span>清理操作</span>
      </template>
      <el-space wrap>
        <el-button type="info" @click="previewCleanup">预览清理</el-button>
        <el-button type="danger" plain @click="executeCleanup">执行清理</el-button>
      </el-space>
    </el-card>

    <el-card shadow="never">
      <template #header>清理历史</template>
      <el-table :data="history" stripe size="small" max-height="420">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="cleanup_type" label="类型" width="100" />
        <el-table-column prop="records_cleaned" label="记录数" width="90" />
        <el-table-column prop="objects_deleted" label="对象数" width="90" />
        <el-table-column prop="bytes_freed" label="释放(MB)" width="100" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="error_message" label="错误" min-width="120" show-overflow-tooltip />
        <el-table-column prop="started_at" label="开始时间" width="170">
          <template #default="{ row }">{{ formatTime(row.started_at) }}</template>
        </el-table-column>
        <el-table-column prop="completed_at" label="结束时间" width="170">
          <template #default="{ row }">{{ formatTime(row.completed_at) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>
