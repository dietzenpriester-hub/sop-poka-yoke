<script setup lang="ts">
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { materialCheckApi, type MaterialCheckItem, type MaterialCheckStats } from "@/api/materialCheck";

function parseErrorMsg(e: unknown, fallback: string): string {
  const resp = (e as { response?: { data?: { detail?: string | unknown } } })?.response;
  const d = resp?.data?.detail;
  if (typeof d === "string") return d;
  return fallback;
}

const rows = ref<MaterialCheckItem[]>([]);
const total = ref(0);
const stats = ref<MaterialCheckStats>({
  total: 0,
  ok_count: 0,
  ng_count: 0,
  warn_count: 0,
  pass_rate: 0,
});
const loading = ref(false);

const filters = ref({
  workorder_id: null as number | null,
  result: "",
  bom_item: "",
});
const page = ref(1);
const pageSize = ref(50);

function formatTime(ts: string): string {
  return new Date(ts).toLocaleString("zh-CN");
}

function resultTagType(r: string): "success" | "warning" | "danger" | "info" {
  switch (r) {
    case "OK":
      return "success";
    case "NG":
      return "danger";
    case "WARN":
      return "warning";
    default:
      return "info";
  }
}

function confidencePercent(c: number): string {
  const p = c <= 1 ? c * 100 : c;
  return `${Number.isFinite(p) ? p.toFixed(1) : "0"}%`;
}

async function loadList() {
  loading.value = true;
  try {
    const skip = (page.value - 1) * pageSize.value;
    const params: Record<string, unknown> = { skip, limit: pageSize.value };
    if (filters.value.workorder_id != null) {
      params.workorder_id = filters.value.workorder_id;
    }
    if (filters.value.result) params.result = filters.value.result;
    if (filters.value.bom_item) params.bom_item = filters.value.bom_item;
    const { data } = await materialCheckApi.list(
      params as Parameters<typeof materialCheckApi.list>[0]
    );
    rows.value = data.items;
    total.value = data.total;
  } catch (e) {
    ElMessage.error(parseErrorMsg(e, "加载物料校验列表失败"));
  } finally {
    loading.value = false;
  }
}

async function loadStats() {
  try {
    const params =
      filters.value.workorder_id != null ? { workorder_id: filters.value.workorder_id } : undefined;
    const { data } = await materialCheckApi.stats(params);
    stats.value = data;
  } catch (e) {
    ElMessage.warning(parseErrorMsg(e, "统计数据加载失败，显示可能不准确"));
  }
}

function handleReset() {
  filters.value = { workorder_id: null, result: "", bom_item: "" };
  page.value = 1;
  loadList();
  loadStats();
}

function handlePageSizeChange() {
  page.value = 1;
  loadList();
}

onMounted(() => {
  loadList();
  loadStats();
});
</script>

<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center">
      <h2>物料校验记录</h2>
      <el-button type="primary" @click="loadList(); loadStats()" :loading="loading">刷新</el-button>
    </div>

    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :xs="12" :sm="8" :md="5">
        <el-card shadow="hover">
          <template #header>检验总数</template>
          <div style="font-size: 28px; font-weight: bold; color: #409eff">{{ stats.total }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="5">
        <el-card shadow="hover">
          <template #header>OK 数</template>
          <div style="font-size: 28px; font-weight: bold; color: #67c23a">{{ stats.ok_count }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="5">
        <el-card shadow="hover">
          <template #header>NG 数</template>
          <div style="font-size: 28px; font-weight: bold; color: #f56c6c">{{ stats.ng_count }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="5">
        <el-card shadow="hover">
          <template #header>WARN 数</template>
          <div style="font-size: 28px; font-weight: bold; color: #e6a23c">{{ stats.warn_count }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="4">
        <el-card shadow="hover">
          <template #header>通过率</template>
          <div style="font-size: 28px; font-weight: bold; color: #409eff">{{ stats.pass_rate }}%</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card style="margin-top: 16px">
      <el-form inline>
        <el-form-item label="工单 ID">
          <el-input-number
            v-model="filters.workorder_id"
            :min="1"
            :step="1"
            controls-position="right"
            placeholder="全部"
            clearable
            style="width: 140px"
          />
        </el-form-item>
        <el-form-item label="结果">
          <el-select v-model="filters.result" clearable placeholder="全部" style="width: 120px">
            <el-option label="OK" value="OK" />
            <el-option label="NG" value="NG" />
            <el-option label="WARN" value="WARN" />
          </el-select>
        </el-form-item>
        <el-form-item label="BOM 物料">
          <el-input v-model="filters.bom_item" clearable placeholder="模糊匹配" style="width: 180px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="page = 1; loadList(); loadStats()">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-table :data="rows" v-loading="loading" style="margin-top: 16px">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="workorder_id" label="工单 ID" width="90" />
      <el-table-column prop="bom_item" label="BOM 物料" min-width="120" show-overflow-tooltip />
      <el-table-column prop="detected_material" label="检测物料" min-width="120" show-overflow-tooltip />
      <el-table-column prop="result" label="结果" width="90">
        <template #default="{ row }">
          <el-tag :type="resultTagType(row.result)" size="small">{{ row.result }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="confidence" label="置信度" width="100">
        <template #default="{ row }">{{ confidencePercent(row.confidence) }}</template>
      </el-table-column>
      <el-table-column label="快照" width="90">
        <template #default="{ row }">
          <el-image
            v-if="row.snapshot_url"
            style="width: 56px; height: 56px"
            :src="row.snapshot_url"
            :preview-src-list="[row.snapshot_url]"
            fit="cover"
            preview-teleported
          />
          <span v-else style="color: #ccc">—</span>
        </template>
      </el-table-column>
      <el-table-column prop="detail" label="详情" min-width="120">
        <template #default="{ row }">
          <el-tooltip v-if="row.detail" :content="row.detail" placement="top" :show-after="300">
            <span class="detail-ellipsis">{{ row.detail }}</span>
          </el-tooltip>
          <span v-else style="color: #ccc">—</span>
        </template>
      </el-table-column>
      <el-table-column prop="checked_at" label="检验时间" width="170">
        <template #default="{ row }">{{ formatTime(row.checked_at) }}</template>
      </el-table-column>
    </el-table>

    <div style="margin-top: 16px; display: flex; justify-content: flex-end">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[20, 50, 100, 200]"
        layout="total, sizes, prev, pager, next, jumper"
        background
        @current-change="loadList"
        @size-change="handlePageSizeChange"
      />
    </div>
  </div>
</template>

<style scoped>
.detail-ellipsis {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
}
</style>
