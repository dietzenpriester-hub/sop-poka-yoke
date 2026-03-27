<script setup lang="ts">
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { completionCheckApi, type CompletionCheckItem, type CompletionCheckStats } from "@/api/completionCheck";

function parseErrorMsg(e: unknown, fallback: string): string {
  const resp = (e as { response?: { data?: { detail?: string | unknown } } })?.response;
  const d = resp?.data?.detail;
  if (typeof d === "string") return d;
  return fallback;
}

const rows = ref<CompletionCheckItem[]>([]);
const total = ref(0);
const stats = ref<CompletionCheckStats>({ total: 0, pass_count: 0, fail_count: 0, rework_count: 0, pass_rate: 0 });
const loading = ref(false);

const filters = ref({ workorder_id: null as number | null, result: "" });
const page = ref(1);
const pageSize = ref(50);

const showDetailDialog = ref(false);
const detailItem = ref<CompletionCheckItem | null>(null);

function formatTime(ts: string): string {
  return new Date(ts).toLocaleString("zh-CN");
}

function resultTagType(r: string): "success" | "warning" | "danger" | "info" {
  switch (r) {
    case "PASS": return "success";
    case "FAIL": return "danger";
    case "REWORK": return "warning";
    default: return "info";
  }
}

function resultLabel(r: string): string {
  switch (r) {
    case "PASS": return "通过";
    case "FAIL": return "不通过";
    case "REWORK": return "返工";
    default: return r;
  }
}

function similarityPercent(s: number): string {
  const p = s <= 1 ? s * 100 : s;
  return `${Number.isFinite(p) ? p.toFixed(1) : "0"}%`;
}

async function loadList() {
  loading.value = true;
  try {
    const skip = (page.value - 1) * pageSize.value;
    const params: Record<string, unknown> = { skip, limit: pageSize.value };
    if (filters.value.workorder_id != null) params.workorder_id = filters.value.workorder_id;
    if (filters.value.result) params.result = filters.value.result;
    const { data } = await completionCheckApi.list(params as Parameters<typeof completionCheckApi.list>[0]);
    rows.value = data.items;
    total.value = data.total;
  } catch (e: unknown) {
    ElMessage.error(parseErrorMsg(e, "加载完工检验列表失败"));
  } finally {
    loading.value = false;
  }
}

function handleSearch() {
  page.value = 1;
  loadList();
  loadStats();
}

async function loadStats() {
  try {
    const params =
      filters.value.workorder_id != null ? { workorder_id: filters.value.workorder_id } : undefined;
    const { data } = await completionCheckApi.stats(params);
    stats.value = data;
  } catch {
    ElMessage.warning("统计数据加载失败");
  }
}

function handleReset() {
  filters.value = { workorder_id: null, result: "" };
  page.value = 1;
  loadList();
  loadStats();
}

function handlePageSizeChange() {
  page.value = 1;
  loadList();
}

function openDetail(item: CompletionCheckItem) {
  detailItem.value = item;
  showDetailDialog.value = true;
}

onMounted(() => {
  loadList();
  loadStats();
});
</script>

<template>
  <div>
    <h2>完工检验记录</h2>

    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover">
          <template #header>检验总数</template>
          <div style="font-size: 28px; font-weight: bold; color: #409eff">{{ stats.total }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover">
          <template #header>PASS</template>
          <div style="font-size: 28px; font-weight: bold; color: #67c23a">{{ stats.pass_count }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover">
          <template #header>FAIL</template>
          <div style="font-size: 28px; font-weight: bold; color: #f56c6c">{{ stats.fail_count }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover">
          <template #header>通过率</template>
          <div style="font-size: 28px; font-weight: bold; color: #e6a23c">{{ stats.pass_rate }}%</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card style="margin-top: 16px">
      <el-form inline>
        <el-form-item label="工单 ID">
          <el-input-number v-model="filters.workorder_id" :min="1" controls-position="right" clearable placeholder="工单ID" style="width: 140px" />
        </el-form-item>
        <el-form-item label="结果">
          <el-select v-model="filters.result" clearable placeholder="全部" style="width: 120px">
            <el-option label="通过 (PASS)" value="PASS" />
            <el-option label="不通过 (FAIL)" value="FAIL" />
            <el-option label="返工 (REWORK)" value="REWORK" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-table :data="rows" v-loading="loading" style="margin-top: 16px">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="workorder_id" label="工单 ID" width="90" />
      <el-table-column prop="result" label="结果" width="100">
        <template #default="{ row }">
          <el-tag :type="resultTagType(row.result)" size="small">{{ resultLabel(row.result) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="相似度" width="100">
        <template #default="{ row }">{{ similarityPercent(row.similarity_score) }}</template>
      </el-table-column>
      <el-table-column prop="defects" label="缺陷描述" min-width="180" show-overflow-tooltip />
      <el-table-column label="完工照片" width="90">
        <template #default="{ row }">
          <el-image v-if="row.completion_photo_url" :src="row.completion_photo_url" :preview-src-list="[row.completion_photo_url]" fit="cover" style="width: 56px; height: 56px; border-radius: 4px" />
          <span v-else style="color: #999">—</span>
        </template>
      </el-table-column>
      <el-table-column label="参考照片" width="90">
        <template #default="{ row }">
          <el-image v-if="row.reference_photo_url" :src="row.reference_photo_url" :preview-src-list="[row.reference_photo_url]" fit="cover" style="width: 56px; height: 56px; border-radius: 4px" />
          <span v-else style="color: #999">—</span>
        </template>
      </el-table-column>
      <el-table-column prop="checked_at" label="检验时间" width="170">
        <template #default="{ row }">{{ formatTime(row.checked_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="80" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openDetail(row)">详情</el-button>
        </template>
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

    <el-dialog v-model="showDetailDialog" title="完工检验详情" width="800px" destroy-on-close>
      <template v-if="detailItem">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="ID">{{ detailItem.id }}</el-descriptions-item>
          <el-descriptions-item label="工单 ID">{{ detailItem.workorder_id }}</el-descriptions-item>
          <el-descriptions-item label="结果">
            <el-tag :type="resultTagType(detailItem.result)" size="small">{{ resultLabel(detailItem.result) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="相似度">{{ similarityPercent(detailItem.similarity_score) }}</el-descriptions-item>
          <el-descriptions-item label="缺陷描述" :span="2">{{ detailItem.defects || "无" }}</el-descriptions-item>
          <el-descriptions-item label="检验时间" :span="2">{{ formatTime(detailItem.checked_at) }}</el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">照片对比</el-divider>
        <el-row :gutter="16">
          <el-col :span="12">
            <div style="text-align: center; margin-bottom: 8px; font-weight: bold">完工照片</div>
            <el-image v-if="detailItem.completion_photo_url" :src="detailItem.completion_photo_url" :preview-src-list="[detailItem.completion_photo_url]" fit="contain" style="width: 100%; max-height: 300px; border: 1px solid #eee; border-radius: 8px" />
            <el-empty v-else description="无完工照片" :image-size="60" />
          </el-col>
          <el-col :span="12">
            <div style="text-align: center; margin-bottom: 8px; font-weight: bold">参考照片</div>
            <el-image v-if="detailItem.reference_photo_url" :src="detailItem.reference_photo_url" :preview-src-list="[detailItem.reference_photo_url]" fit="contain" style="width: 100%; max-height: 300px; border: 1px solid #eee; border-radius: 8px" />
            <el-empty v-else description="无参考照片" :image-size="60" />
          </el-col>
        </el-row>

        <template v-if="detailItem.check_items && detailItem.check_items.length > 0">
          <el-divider content-position="left">检查项目</el-divider>
          <pre style="background: #f5f5f5; padding: 12px; border-radius: 8px; overflow-x: auto; font-size: 13px">{{ JSON.stringify(detailItem.check_items, null, 2) }}</pre>
        </template>
      </template>
    </el-dialog>
  </div>
</template>
