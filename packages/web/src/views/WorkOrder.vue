<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { workorderApi, type WorkOrderItem, type StepRecordItem } from "@/api/workorder";
import { stationApi, type StationItem } from "@/api/station";
import { sopApi, type SOPTemplate } from "@/api/sop";
import { parseErrorMsg } from "@/utils/httpError";
import { formatDateTime } from "@/utils/date";

const workorders = ref<WorkOrderItem[]>([]);
const loading = ref(false);
const stations = ref<StationItem[]>([]);
const templates = ref<SOPTemplate[]>([]);

const filters = ref({
  sn: "",
  status: "",
  dateRange: null as [string, string] | null,
});

const pagination = ref({ skip: 0, limit: 50 });

let detailReqId = 0;
const showCreateDialog = ref(false);
const createForm = ref({
  sn: "",
  station_id: undefined as number | undefined,
  sop_template_id: undefined as number | undefined,
});

const showDetailDialog = ref(false);
const detailLoading = ref(false);
const detailWorkorder = ref<WorkOrderItem | null>(null);
const detailSteps = ref<StepRecordItem[]>([]);

const stationNameById = computed(() => {
  const m = new Map<number, string>();
  for (const s of stations.value) m.set(s.id, s.name);
  return m;
});

function statusTagType(
  status: string
): "success" | "warning" | "info" | "danger" | "primary" {
  switch (status) {
    case "running":
      return "primary";
    case "done":
      return "success";
    case "aborted":
      return "danger";
    default:
      return "info";
  }
}

function resultTagType(
  result: string
): "success" | "warning" | "info" | "danger" | "primary" {
  const r = result?.toUpperCase() || "";
  if (r === "OK") return "success";
  if (r === "NG") return "danger";
  if (r === "SKIP") return "info";
  if (r === "OVERRIDE") return "warning";
  return "info";
}

async function loadStationsAndTemplates() {
  try {
    const [stRes, tplRes] = await Promise.all([stationApi.list(), sopApi.list()]);
    stations.value = stRes.data;
    templates.value = tplRes.data;
  } catch (e: unknown) {
    ElMessage.warning(parseErrorMsg(e, "加载工位或模板列表失败"));
  }
}

async function loadWorkorders() {
  loading.value = true;
  try {
    const params: Record<string, unknown> = { ...pagination.value };
    if (filters.value.sn) params.sn = filters.value.sn;
    if (filters.value.status) params.status = filters.value.status;
    if (filters.value.dateRange?.length === 2) {
      params.start_date = filters.value.dateRange[0];
      params.end_date = filters.value.dateRange[1];
    }
    const { data } = await workorderApi.list(params as Parameters<typeof workorderApi.list>[0]);
    workorders.value = data;
  } catch (e: unknown) {
    ElMessage.error(parseErrorMsg(e, "加载工单列表失败"));
  } finally {
    loading.value = false;
  }
}

function handleSearch() {
  pagination.value.skip = 0;
  loadWorkorders();
}

function handleReset() {
  filters.value = { sn: "", status: "", dateRange: null };
  pagination.value = { skip: 0, limit: 50 };
  loadWorkorders();
}

const currentPage = computed(() => Math.floor(pagination.value.skip / pagination.value.limit) + 1);

function prevPage() {
  pagination.value.skip = Math.max(0, pagination.value.skip - pagination.value.limit);
  loadWorkorders();
}

function nextPage() {
  pagination.value.skip += pagination.value.limit;
  loadWorkorders();
}

async function handleCreate() {
  if (!createForm.value.sn?.trim()) {
    ElMessage.warning("请填写 SN");
    return;
  }
  try {
    await workorderApi.create({
      sn: createForm.value.sn.trim(),
      station_id: createForm.value.station_id,
      sop_template_id: createForm.value.sop_template_id,
    });
    ElMessage.success("工单已创建");
    showCreateDialog.value = false;
    createForm.value = { sn: "", station_id: undefined, sop_template_id: undefined };
    loadWorkorders();
  } catch (e: unknown) {
    ElMessage.error(parseErrorMsg(e, "创建失败"));
  }
}

async function openDetail(row: WorkOrderItem) {
  detailWorkorder.value = row;
  detailSteps.value = [];
  showDetailDialog.value = true;
  detailLoading.value = true;
  const reqId = ++detailReqId;
  try {
    const [{ data: wo }, { data: steps }] = await Promise.all([
      workorderApi.get(row.id),
      workorderApi.steps(row.id),
    ]);
    if (reqId !== detailReqId) return;
    detailWorkorder.value = wo;
    detailSteps.value = steps;
  } catch (e: unknown) {
    if (reqId !== detailReqId) return;
    ElMessage.error(parseErrorMsg(e, "加载工单详情失败"));
    showDetailDialog.value = false;
  } finally {
    if (reqId === detailReqId) detailLoading.value = false;
  }
}

async function handleComplete(row: WorkOrderItem) {
  try {
    await ElMessageBox.confirm(`确定将工单 #${row.id}（${row.sn}）标记为已完成？`, "完成工单", {
      type: "warning",
    });
    await workorderApi.complete(row.id);
    ElMessage.success("工单已完成");
    loadWorkorders();
  } catch (e: unknown) {
    if (e !== "cancel") ElMessage.error(parseErrorMsg(e, "操作失败"));
  }
}

async function handleDelete(row: WorkOrderItem) {
  try {
    await ElMessageBox.confirm(`确定删除工单 #${row.id}（${row.sn}）？此操作不可恢复。`, "确认删除", {
      type: "warning",
    });
    await workorderApi.delete(row.id);
    ElMessage.success("工单已删除");
    loadWorkorders();
  } catch (e: unknown) {
    if (e !== "cancel") ElMessage.error(parseErrorMsg(e, "删除失败"));
  }
}

onMounted(() => {
  loadStationsAndTemplates();
  loadWorkorders();
});
</script>

<template>
  <div>
    <div class="page-header">
      <h2>工单管理</h2>
      <div class="page-header-actions">
        <el-button type="primary" @click="showCreateDialog = true">新建工单</el-button>
      </div>
    </div>

    <el-card class="filter-card">
      <el-form inline>
        <el-form-item label="SN">
          <el-input v-model="filters.sn" placeholder="模糊搜索" clearable style="width: 180px" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filters.status" clearable placeholder="全部" style="width: 120px">
            <el-option label="进行中" value="running" />
            <el-option label="已完成" value="done" />
            <el-option label="已中止" value="aborted" />
          </el-select>
        </el-form-item>
        <el-form-item label="开始时间">
          <el-date-picker
            v-model="filters.dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="YYYY-MM-DD"
            style="width: 280px"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <div class="data-table">
      <el-table :data="workorders" v-loading="loading">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="sn" label="SN" min-width="120" show-overflow-tooltip />
        <el-table-column prop="station_id" label="工位 ID" width="90" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="start_time" label="开始时间" width="170">
          <template #default="{ row }">{{ formatDateTime(row.start_time) }}</template>
        </el-table-column>
        <el-table-column prop="end_time" label="结束时间" width="170">
          <template #default="{ row }">{{ formatDateTime(row.end_time) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openDetail(row)">详情</el-button>
            <el-button v-if="row.status === 'running'" size="small" type="success" @click="handleComplete(row)">
              完成
            </el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="pagination-bar">
      <el-button :disabled="pagination.skip === 0" @click="prevPage">上一页</el-button>
      <span class="page-info">第 {{ currentPage }} 页</span>
      <el-button :disabled="workorders.length < pagination.limit" @click="nextPage">下一页</el-button>
    </div>

    <!-- 新建 -->
    <el-dialog v-model="showCreateDialog" title="新建工单" width="520px" destroy-on-close>
      <el-form :model="createForm" label-width="110px">
        <el-form-item label="SN" required>
          <el-input v-model="createForm.sn" placeholder="产品序列号" />
        </el-form-item>
        <el-form-item label="工位">
          <el-select
            v-model="createForm.station_id"
            clearable
            placeholder="可选"
            style="width: 100%"
          >
            <el-option
              v-for="s in stations"
              :key="s.id"
              :label="`${s.name} (#${s.id})`"
              :value="s.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="SOP 模板">
          <el-select
            v-model="createForm.sop_template_id"
            clearable
            placeholder="可选"
            style="width: 100%"
          >
            <el-option
              v-for="t in templates"
              :key="t.id"
              :label="`${t.name} v${t.version} (#${t.id})`"
              :value="t.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 详情 -->
    <el-dialog
      v-model="showDetailDialog"
      title="工单详情"
      width="800px"
      destroy-on-close
      @closed="detailWorkorder = null"
    >
      <div v-loading="detailLoading">
        <template v-if="detailWorkorder">
          <el-descriptions :column="2" border>
            <el-descriptions-item label="SN">{{ detailWorkorder.sn }}</el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag :type="statusTagType(detailWorkorder.status)" size="small">
                {{ detailWorkorder.status }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="工位">
              <span v-if="detailWorkorder.station_id != null">
                {{ stationNameById.get(detailWorkorder.station_id) || "—" }}
                (#{{ detailWorkorder.station_id }})
              </span>
              <span v-else>—</span>
            </el-descriptions-item>
            <el-descriptions-item label="SOP 模板 ID">
              {{ detailWorkorder.sop_template_id ?? "—" }}
            </el-descriptions-item>
            <el-descriptions-item label="开始时间">
              {{ formatDateTime(detailWorkorder.start_time) }}
            </el-descriptions-item>
            <el-descriptions-item label="结束时间">
              {{ formatDateTime(detailWorkorder.end_time) }}
            </el-descriptions-item>
          </el-descriptions>

          <h4 style="margin: 16px 0 8px">步骤记录</h4>
          <el-table :data="detailSteps" size="small" max-height="360">
            <el-table-column prop="step_index" label="#" width="50" />
            <el-table-column prop="step_name" label="步骤名" min-width="100" show-overflow-tooltip />
            <el-table-column prop="result" label="结果" width="100">
              <template #default="{ row: r }">
                <el-tag :type="resultTagType(r.result)" size="small">{{ r.result }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="confidence" label="置信度" width="90" />
            <el-table-column prop="created_at" label="时间" width="160">
              <template #default="{ row: r }">{{ formatDateTime(r.created_at) }}</template>
            </el-table-column>
            <el-table-column label="快照" width="88">
              <template #default="{ row: r }">
                <el-image
                  v-if="r.snapshot_url"
                  :src="r.snapshot_url"
                  :preview-src-list="[r.snapshot_url]"
                  fit="cover"
                  style="width: 56px; height: 56px; border-radius: 4px"
                />
                <span v-else style="color: #999">—</span>
              </template>
            </el-table-column>
          </el-table>
        </template>
      </div>
    </el-dialog>
  </div>
</template>
