<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { learningApi, type LearningTask, type LearningStep } from "@/api/learning";
import { parseErrorMsg } from "@/utils/httpError";
import { formatDateTime } from "@/utils/date";

function isAnalysisRunning(status: string): boolean {
  return !["completed", "failed", "confirmed"].includes(status);
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    queued: "排队中",
    analyzing: "分析中",
    phase_1: "阶段1·分帧",
    phase_2: "阶段2·识别",
    phase_3: "阶段3·分析",
    phase_4: "阶段4·优化",
    completed: "已完成",
    failed: "失败",
    confirmed: "已确认",
  };
  return map[status] || status;
}

function statusTagType(status: string): "info" | "success" | "warning" | "danger" {
  if (status === "failed") return "danger";
  if (status === "completed") return "success";
  if (status === "confirmed") return "success";
  if (isAnalysisRunning(status)) return "warning";
  return "info";
}

function normalizeStep(raw: Record<string, unknown>, index: number): LearningStep {
  const req = raw.required_objects;
  const required_objects = Array.isArray(req) ? req.map(String) : [];
  return {
    index: typeof raw.index === "number" ? raw.index : index,
    name: typeof raw.name === "string" ? raw.name : "",
    description: typeof raw.description === "string" ? raw.description : "",
    required_objects,
    action_type: typeof raw.action_type === "string" ? raw.action_type : "",
    timeout_seconds:
      typeof raw.timeout_seconds === "number" && !Number.isNaN(raw.timeout_seconds)
        ? raw.timeout_seconds
        : 30,
    is_optional: Boolean(raw.is_optional),
    reference_frame_url: typeof raw.reference_frame_url === "string" ? raw.reference_frame_url : "",
    ok_criteria: typeof raw.ok_criteria === "string" ? raw.ok_criteria : "",
    ng_criteria: typeof raw.ng_criteria === "string" ? raw.ng_criteria : "",
  };
}

const listLoading = ref(false);
const tasks = ref<LearningTask[]>([]);
const total = ref(0);

const productModel = ref("");
const processName = ref("");
const uploadLoading = ref(false);
const fileInputRef = ref<HTMLInputElement>();
const selectedFile = ref<File | null>(null);

const detailVisible = ref(false);
const detailLoading = ref(false);
const currentTask = ref<LearningTask | null>(null);
const editingSteps = ref<LearningStep[]>([]);
const stepsSaving = ref(false);
const confirmLoading = ref(false);

let pollTimer: ReturnType<typeof setInterval> | null = null;
let detailReqId = 0;

const shouldPoll = computed(() => {
  const listHasActive = tasks.value.some((t) => isAnalysisRunning(t.status));
  const dialogActive =
    detailVisible.value && currentTask.value && isAnalysisRunning(currentTask.value.status);
  return listHasActive || dialogActive;
});

async function loadTasks(showError = true) {
  listLoading.value = true;
  try {
    const { data } = await learningApi.listTasks({ skip: 0, limit: 100 });
    tasks.value = data.items;
    total.value = data.total;
  } catch (e) {
    if (showError) ElMessage.error(parseErrorMsg(e, "加载任务列表失败"));
  } finally {
    listLoading.value = false;
  }
}

async function loadTaskDetail(taskId: string) {
  const reqId = ++detailReqId;
  detailLoading.value = true;
  try {
    const { data } = await learningApi.getTask(taskId);
    if (reqId !== detailReqId) return;
    currentTask.value = data;
    editingSteps.value = (data.steps || []).map((s, i) =>
      normalizeStep(s as unknown as Record<string, unknown>, i)
    );
  } catch (e) {
    if (reqId !== detailReqId) return;
    ElMessage.error(parseErrorMsg(e, "加载任务详情失败"));
    currentTask.value = null;
  } finally {
    if (reqId === detailReqId) {
      detailLoading.value = false;
    }
  }
}

function openDetail(row: LearningTask) {
  detailVisible.value = true;
  void loadTaskDetail(row.task_id);
}

function closeDetail() {
  detailVisible.value = false;
  currentTask.value = null;
  editingSteps.value = [];
}

async function refreshDetailIfOpen() {
  if (!detailVisible.value || !currentTask.value) return;
  await loadTaskDetail(currentTask.value.task_id);
}

let _pollInFlight = false;
function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(() => {
    if (_pollInFlight) return;
    _pollInFlight = true;
    void (async () => {
      try {
        await loadTasks(false);
        await refreshDetailIfOpen();
      } finally {
        _pollInFlight = false;
      }
    })();
  }, 5000);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

watch(
  shouldPoll,
  (v) => {
    if (v) startPolling();
    else stopPolling();
  },
  { immediate: true }
);

onMounted(() => {
  void loadTasks();
});

onUnmounted(() => {
  stopPolling();
});

function onFileSelected(event: Event) {
  const input = event.target as HTMLInputElement;
  if (input.files && input.files.length > 0) {
    selectedFile.value = input.files[0];
  }
}

async function submitUpload() {
  if (!productModel.value.trim() || !processName.value.trim()) {
    ElMessage.warning("请填写产品型号和工序名称");
    return;
  }
  if (!selectedFile.value) {
    ElMessage.warning("请选择视频文件");
    return;
  }
  uploadLoading.value = true;
  const formData = new FormData();
  formData.append("video", selectedFile.value);
  try {
    await learningApi.uploadVideo(formData, productModel.value.trim(), processName.value.trim());
    ElMessage.success("视频已上传，分析任务已排队");
    selectedFile.value = null;
    if (fileInputRef.value) fileInputRef.value.value = "";
    await loadTasks();
  } catch (e) {
    ElMessage.error(parseErrorMsg(e, "上传失败"));
  } finally {
    uploadLoading.value = false;
  }
}

async function handleDelete(row: LearningTask) {
  try {
    await ElMessageBox.confirm(`确定删除任务 ${row.task_id.slice(0, 8)}… 吗？`, "删除确认", {
      type: "warning",
    });
  } catch (e) {
    if (e !== "cancel") ElMessage.error(parseErrorMsg(e, "操作失败"));
    return;
  }
  try {
    await learningApi.deleteTask(row.task_id);
    ElMessage.success("已删除");
    if (currentTask.value?.task_id === row.task_id) closeDetail();
    await loadTasks();
  } catch (e) {
    ElMessage.error(parseErrorMsg(e, "删除失败"));
  }
}

const canEditSteps = computed(() => {
  const t = currentTask.value;
  return t && (t.status === "completed" || t.status === "confirmed");
});

async function saveSteps() {
  if (!currentTask.value) return;
  stepsSaving.value = true;
  try {
    await learningApi.updateSteps(currentTask.value.task_id, editingSteps.value);
    ElMessage.success("步骤已保存");
    await loadTaskDetail(currentTask.value.task_id);
    await loadTasks(false);
  } catch (e) {
    ElMessage.error(parseErrorMsg(e, "保存失败"));
  } finally {
    stepsSaving.value = false;
  }
}

async function confirmGenerate() {
  if (!currentTask.value) return;
  try {
    await ElMessageBox.confirm(
      "确认后将根据当前步骤生成 SOP 草稿模板，是否继续？",
      "确认并生成模板",
      { type: "warning" }
    );
  } catch (e) {
    if (e !== "cancel") ElMessage.error(parseErrorMsg(e, "操作失败"));
    return;
  }
  confirmLoading.value = true;
  try {
    const { data } = await learningApi.confirmTask(currentTask.value.task_id);
    ElMessage.success(`模板已生成，ID: ${data.template_id}`);
    await loadTaskDetail(currentTask.value.task_id);
    await loadTasks(false);
  } catch (e) {
    ElMessage.error(parseErrorMsg(e, "生成失败"));
  } finally {
    confirmLoading.value = false;
  }
}

function analysisDetailEntries(task: LearningTask): { key: string; value: string }[] {
  const d = task.analysis_detail || {};
  return Object.entries(d).map(([k, v]) => ({
    key: k,
    value: typeof v === "object" ? JSON.stringify(v) : String(v),
  }));
}
</script>

<template>
  <div class="sop-learning-page">
    <div class="page-header">
      <h2>SOP 标准作业学习</h2>
    </div>
    <p class="page-desc">
      三阶段流程：标准作业视频录入 → AI 自动分析与模板生成 → 步骤审核与确认
    </p>

    <el-card class="section-card" shadow="never">
      <template #header>
        <span>学习任务列表</span>
        <span class="header-meta">共 {{ total }} 条</span>
      </template>
      <el-table v-loading="listLoading" :data="tasks" stripe style="width: 100%" empty-text="暂无任务">
        <el-table-column label="任务 ID" min-width="120">
          <template #default="{ row }">
            <el-tooltip :content="row.task_id" placement="top">
              <span class="mono">{{ row.task_id.slice(0, 8) }}…</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column prop="product_model" label="产品型号" min-width="110" />
        <el-table-column prop="process_name" label="工序名称" min-width="110" />
        <el-table-column label="状态" width="130">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进度" min-width="160">
          <template #default="{ row }">
            <el-progress
              :percentage="Math.round((row.progress ?? 0) * 100)"
              :status="row.status === 'failed' ? 'exception' : undefined"
              :stroke-width="10"
            />
          </template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="170">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link @click="openDetail(row)">查看详情</el-button>
            <el-button type="danger" link @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="section-card" shadow="never">
      <template #header>新建学习任务</template>
      <el-form label-width="100px" class="upload-form" @submit.prevent>
        <el-form-item label="产品型号">
          <el-input v-model="productModel" placeholder="如 PCB-A100" clearable />
        </el-form-item>
        <el-form-item label="工序名称">
          <el-input v-model="processName" placeholder="如 螺丝装配" clearable />
        </el-form-item>
        <el-form-item label="标准视频">
          <div>
            <input
              ref="fileInputRef"
              type="file"
              accept="video/*"
              style="display: none"
              @change="onFileSelected"
            />
            <el-button type="primary" :loading="uploadLoading" @click="fileInputRef?.click()">
              选择视频文件
            </el-button>
            <span v-if="selectedFile" style="margin-left: 12px">{{ selectedFile.name }}</span>
            <div class="el-upload__tip" style="margin-top: 4px">支持常见视频格式，上传后自动进入 AI 分析队列</div>
          </div>
        </el-form-item>
        <el-form-item>
          <el-button type="success" :loading="uploadLoading" @click="submitUpload">上传并开始分析</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-dialog
      v-model="detailVisible"
      title="任务详情"
      width="min(920px, 96vw)"
      destroy-on-close
      class="detail-dialog"
      @closed="closeDetail"
    >
      <div v-loading="detailLoading">
        <template v-if="currentTask">
          <el-descriptions :column="2" border class="task-desc">
            <el-descriptions-item label="产品型号">{{ currentTask.product_model }}</el-descriptions-item>
            <el-descriptions-item label="工序名称">{{ currentTask.process_name }}</el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag :type="statusTagType(currentTask.status)" size="small">
                {{ statusLabel(currentTask.status) }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="进度">
              <el-progress
                :percentage="Math.round((currentTask.progress ?? 0) * 100)"
                :status="currentTask.status === 'failed' ? 'exception' : undefined"
              />
            </el-descriptions-item>
            <el-descriptions-item label="视频路径" :span="2">
              <span class="mono small-path">{{ currentTask.video_path || "—" }}</span>
            </el-descriptions-item>
            <el-descriptions-item v-if="currentTask.error_message" label="错误信息" :span="2">
              <el-alert type="error" :closable="false" show-icon>{{ currentTask.error_message }}</el-alert>
            </el-descriptions-item>
            <el-descriptions-item label="模板 ID">
              {{ currentTask.template_id ?? "—" }}
            </el-descriptions-item>
            <el-descriptions-item label="完成时间">
              {{ formatDateTime(currentTask.completed_at) }}
            </el-descriptions-item>
          </el-descriptions>

          <el-collapse class="detail-collapse">
            <el-collapse-item title="分析详情" name="analysis">
              <el-descriptions v-if="analysisDetailEntries(currentTask).length" :column="1" border size="small">
                <el-descriptions-item
                  v-for="item in analysisDetailEntries(currentTask)"
                  :key="item.key"
                  :label="item.key"
                >
                  {{ item.value }}
                </el-descriptions-item>
              </el-descriptions>
              <el-empty v-else description="暂无分析详情" />
            </el-collapse-item>
          </el-collapse>

          <h4 class="steps-heading">识别步骤</h4>
          <el-timeline v-if="editingSteps.length">
            <el-timeline-item v-for="(step, idx) in editingSteps" :key="idx" :timestamp="`#${idx + 1}`" placement="top">
              <el-card shadow="hover" class="step-card">
                <el-form label-width="120px" size="small" :disabled="!canEditSteps">
                  <el-form-item label="名称">
                    <el-input v-model="step.name" />
                  </el-form-item>
                  <el-form-item label="描述">
                    <el-input v-model="step.description" type="textarea" :rows="2" />
                  </el-form-item>
                  <el-form-item label="动作类型">
                    <el-input v-model="step.action_type" />
                  </el-form-item>
                  <el-form-item label="超时 (秒)">
                    <el-input-number v-model="step.timeout_seconds" :min="1" :max="600" />
                  </el-form-item>
                  <el-form-item label="必选对象">
                    <el-select
                      v-model="step.required_objects"
                      multiple
                      filterable
                      allow-create
                      default-first-option
                      placeholder="输入后回车添加"
                      style="width: 100%"
                    />
                  </el-form-item>
                  <el-form-item label="可选步骤">
                    <el-switch v-model="step.is_optional" />
                  </el-form-item>
                  <el-form-item label="OK 判定">
                    <el-input v-model="step.ok_criteria" type="textarea" :rows="2" />
                  </el-form-item>
                  <el-form-item label="NG 判定">
                    <el-input v-model="step.ng_criteria" type="textarea" :rows="2" />
                  </el-form-item>
                </el-form>
              </el-card>
            </el-timeline-item>
          </el-timeline>
          <el-empty v-else description="暂无步骤（分析完成后将显示）" />

          <div class="detail-actions">
            <el-button
              type="primary"
              :loading="stepsSaving"
              :disabled="!canEditSteps || !editingSteps.length"
              @click="saveSteps"
            >
              保存步骤修改
            </el-button>
            <el-button
              type="success"
              :loading="confirmLoading"
              :disabled="!canEditSteps || !editingSteps.length"
              @click="confirmGenerate"
            >
              确认并生成模板
            </el-button>
          </div>
        </template>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.sop-learning-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 16px;
}

.page-title {
  margin: 0 0 8px;
  font-size: 22px;
  font-weight: 600;
}

.page-desc {
  margin: 0 0 20px;
  color: var(--el-text-color-secondary);
  font-size: 14px;
}

.section-card {
  margin-bottom: 20px;
}

.section-card :deep(.el-card__header) {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-meta {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.mono {
  font-family: ui-monospace, monospace;
  font-size: 12px;
}

.small-path {
  word-break: break-all;
  font-size: 12px;
}

.upload-form {
  max-width: 560px;
}

.task-desc {
  margin-bottom: 16px;
}

.detail-collapse {
  margin-bottom: 16px;
}

.steps-heading {
  margin: 16px 0 12px;
  font-size: 16px;
}

.step-card {
  margin-bottom: 8px;
}

.detail-actions {
  margin-top: 20px;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

@media (max-width: 768px) {
  .sop-learning-page {
    padding: 12px;
  }
}
</style>
