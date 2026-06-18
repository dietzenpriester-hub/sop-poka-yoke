<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { learningApi, type LearningTask, type LearningStep } from "@/api/learning";
import { parseErrorMsg } from "@/utils/httpError";
import { formatDateTime } from "@/utils/date";

function isAnalysisRunning(status: string): boolean {
  return !["completed", "failed", "confirmed", "needs_review"].includes(status);
}

function phaseProgress(status: string): string {
  const map: Record<string, string> = {
    phase_1: "运动分析 → 动作段自动分割",
    phase_2: "YOLO 检测每段中的物体",
    phase_3: "VLM 逐段识别操作动作",
    phase_4: "组装步骤 + 生成判定标准",
    phase_5: "绑定参考帧截图",
  };
  return map[status] || "";
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    queued: "排队中",
    analyzing: "分析中",
    phase_1: "阶段1·动作分割",
    phase_2: "阶段2·目标检测",
    phase_3: "阶段3·逐段识别",
    phase_4: "阶段4·步骤组装",
    phase_5: "阶段5·参考帧绑定",
    completed: "已完成",
    needs_review: "待复核",
    failed: "失败",
    confirmed: "已确认",
  };
  return map[status] || status;
}

function statusTagType(status: string): "info" | "success" | "warning" | "danger" {
  if (status === "failed") return "danger";
  if (status === "completed") return "success";
  if (status === "confirmed") return "success";
  if (status === "needs_review") return "warning";
  if (isAnalysisRunning(status)) return "warning";
  return "info";
}

interface QualityIssue {
  code: string;
  message: string;
  severity: string;
}

type ReviewStatus = LearningStep["review_status"];
type EvidenceStatus = LearningStep["evidence_status"];

function qualityReport(task: LearningTask | null): Record<string, unknown> | null {
  const quality = task?.analysis_detail?.quality;
  if (!quality || typeof quality !== "object" || Array.isArray(quality)) return null;
  return quality as Record<string, unknown>;
}

function qualityIssues(task: LearningTask | null): QualityIssue[] {
  const issues = qualityReport(task)?.issues;
  if (!Array.isArray(issues)) return [];
  return issues.map((item) => {
    const issue = item as Record<string, unknown>;
    return {
      code: String(issue.code || ""),
      message: String(issue.message || ""),
      severity: String(issue.severity || "warning"),
    };
  });
}

function qualityAlertType(task: LearningTask | null): "success" | "warning" {
  return qualityReport(task)?.passed === true ? "success" : "warning";
}

function qualityAlertTitle(task: LearningTask | null): string {
  const report = qualityReport(task);
  if (!report) return "";
  const score = typeof report.score === "number" ? `，评分 ${Math.round(report.score * 100)}%` : "";
  if (report.passed === true && report.manual_reviewed === true) return `人工复核通过${score}`;
  return report.passed === true ? `质量评估通过${score}` : `学习结果需要人工复核${score}`;
}

function inferEvidenceStatus(raw: Record<string, unknown>): EvidenceStatus {
  if (raw.grounding_supported === false || raw.name === "无法确认动作") return "missing";
  const confidence = typeof raw.grounding_confidence === "number" ? raw.grounding_confidence : null;
  if (confidence !== null && confidence < 0.65) return "weak";
  if (!raw.reference_frame_b64 && !raw.reference_frame_url) return "weak";
  return "supported";
}

function reviewStatusLabel(status: ReviewStatus): string {
  const map: Record<ReviewStatus, string> = {
    pending: "待确认",
    confirmed: "已确认",
    ignored: "已忽略",
    needs_rework: "需重分析",
  };
  return map[status] || status;
}

function reviewStatusTagType(status: ReviewStatus): "info" | "success" | "warning" | "danger" {
  if (status === "confirmed") return "success";
  if (status === "ignored") return "info";
  if (status === "needs_rework") return "danger";
  return "warning";
}

function evidenceStatusLabel(status: EvidenceStatus): string {
  const map: Record<string, string> = {
    supported: "证据充分",
    weak: "证据偏弱",
    missing: "证据不足",
    "": "未评估",
  };
  return map[status] || status;
}

function evidenceStatusTagType(status: EvidenceStatus): "info" | "success" | "warning" | "danger" {
  if (status === "supported") return "success";
  if (status === "missing") return "danger";
  if (status === "weak") return "warning";
  return "info";
}

function groundingConfidenceText(step: LearningStep): string {
  if (typeof step.grounding_confidence !== "number") return "";
  return `${Math.round(step.grounding_confidence * 100)}%`;
}

function reviewProgressText(steps: LearningStep[] | undefined): string {
  const list = steps || [];
  const active = list.filter((s) => s.review_status !== "ignored");
  if (!active.length) return "0/0";
  const confirmed = active.filter((s) => s.review_status === "confirmed").length;
  return `${confirmed}/${active.length}`;
}

function normalizeStep(raw: Record<string, unknown>, index: number): LearningStep {
  const req = raw.required_objects;
  const required_objects = Array.isArray(req) ? req.map(String) : [];
  const seg_ids = raw.segment_ids;
  const segment_ids = Array.isArray(seg_ids) ? seg_ids.map(Number) : [];
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
    reference_frame_b64: typeof raw.reference_frame_b64 === "string" ? raw.reference_frame_b64 : "",
    reference_frame_timestamp: typeof raw.reference_frame_timestamp === "number" ? raw.reference_frame_timestamp : 0,
    ok_criteria: typeof raw.ok_criteria === "string" ? raw.ok_criteria : "",
    ng_criteria: typeof raw.ng_criteria === "string" ? raw.ng_criteria : "",
    start_sec: typeof raw.start_sec === "number" ? raw.start_sec : 0,
    end_sec: typeof raw.end_sec === "number" ? raw.end_sec : 0,
    segment_ids,
    review_status: ["pending", "confirmed", "ignored", "needs_rework"].includes(String(raw.review_status))
      ? (raw.review_status as ReviewStatus)
      : "pending",
    evidence_status: ["supported", "weak", "missing"].includes(String(raw.evidence_status))
      ? (raw.evidence_status as EvidenceStatus)
      : inferEvidenceStatus(raw),
    confirmation_note: typeof raw.confirmation_note === "string" ? raw.confirmation_note : "",
    human_reviewed: Boolean(raw.human_reviewed),
    reviewed_at: typeof raw.reviewed_at === "string" ? raw.reviewed_at : "",
    grounding_supported: typeof raw.grounding_supported === "boolean" ? raw.grounding_supported : null,
    grounding_confidence: typeof raw.grounding_confidence === "number" ? raw.grounding_confidence : null,
    grounding_issue: typeof raw.grounding_issue === "string" ? raw.grounding_issue : "",
    source_confidence: typeof raw.source_confidence === "number" ? raw.source_confidence : null,
  };
}

function formatTimeSec(sec: number): string {
  if (!sec) return "0:00";
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
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
const retryLoading = ref(false);

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
  return Boolean(t && (t.status === "completed" || t.status === "needs_review"));
});

const activeSteps = computed(() => editingSteps.value.filter((s) => s.review_status !== "ignored"));

const confirmedStepCount = computed(() =>
  activeSteps.value.filter((s) => s.review_status === "confirmed").length
);

const weakEvidenceCount = computed(() =>
  activeSteps.value.filter((s) => s.evidence_status !== "supported").length
);

const allActiveStepsConfirmed = computed(() =>
  activeSteps.value.length > 0 && confirmedStepCount.value === activeSteps.value.length
);

const canConfirmSteps = computed(() => {
  const t = currentTask.value;
  return Boolean(t && t.status === "completed" && allActiveStepsConfirmed.value);
});

const canRetryAnalysis = computed(() => {
  const t = currentTask.value;
  return Boolean(
    t
      && !t.template_id
      && ["failed", "needs_review", "completed"].includes(t.status)
  );
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

async function retryAnalysis() {
  if (!currentTask.value) return;
  try {
    const message = currentTask.value.status === "completed"
      ? "重新分析会覆盖当前识别步骤，适合当前结果与视频明显不匹配的情况。是否继续？"
      : "将使用原视频重新排队分析，是否继续？";
    await ElMessageBox.confirm(message, "重新分析", { type: "warning" });
  } catch (e) {
    if (e !== "cancel") ElMessage.error(parseErrorMsg(e, "操作失败"));
    return;
  }
  retryLoading.value = true;
  try {
    const { data } = await learningApi.retryTask(currentTask.value.task_id);
    currentTask.value = data;
    editingSteps.value = [];
    ElMessage.success("分析任务已重新排队");
    await loadTasks(false);
  } catch (e) {
    ElMessage.error(parseErrorMsg(e, "重试失败"));
  } finally {
    retryLoading.value = false;
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
      上传标准作业视频 → AI 自动分割动作段 → 逐段识别并生成 SOP → 人工审核与确认
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
        <el-table-column label="复核" width="100">
          <template #default="{ row }">
            <span class="review-progress">{{ reviewProgressText(row.steps) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="进度" min-width="200">
          <template #default="{ row }">
            <el-progress
              :percentage="Math.round((row.progress ?? 0) * 100)"
              :status="row.status === 'failed' ? 'exception' : undefined"
              :stroke-width="10"
            />
            <span v-if="phaseProgress(row.status)" class="phase-hint">{{ phaseProgress(row.status) }}</span>
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
            <el-descriptions-item v-if="qualityReport(currentTask)" label="质量评估" :span="2">
              <el-alert
                :type="qualityAlertType(currentTask)"
                :title="qualityAlertTitle(currentTask)"
                :closable="false"
                show-icon
                class="quality-alert"
              >
                <ul v-if="qualityIssues(currentTask).length" class="quality-issues">
                  <li v-for="issue in qualityIssues(currentTask)" :key="issue.code + issue.message">
                    {{ issue.message }}
                  </li>
                </ul>
              </el-alert>
            </el-descriptions-item>
            <el-descriptions-item label="复核进度">
              {{ confirmedStepCount }} / {{ activeSteps.length }}
            </el-descriptions-item>
            <el-descriptions-item label="弱证据步骤">
              {{ weakEvidenceCount }}
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

          <h4 class="steps-heading">识别步骤（{{ editingSteps.length }} 步）</h4>
          <el-alert
            v-if="canEditSteps && !allActiveStepsConfirmed"
            type="warning"
            :closable="false"
            show-icon
            class="review-alert"
            title="候选步骤需逐步复核后才能生成模板"
          />
          <el-timeline v-if="editingSteps.length">
            <el-timeline-item v-for="(step, idx) in editingSteps" :key="idx" :timestamp="`#${idx + 1}`" placement="top">
              <el-card shadow="hover" class="step-card">
                <div class="step-card-body">
                  <div v-if="step.reference_frame_b64" class="step-ref-frame">
                    <img :src="'data:image/jpeg;base64,' + step.reference_frame_b64" alt="参考帧" />
                    <span class="ref-frame-time">{{ formatTimeSec(step.reference_frame_timestamp) }}</span>
                  </div>
                  <div class="step-form-area">
                    <div v-if="step.start_sec || step.end_sec" class="step-time-badge">
                      {{ formatTimeSec(step.start_sec) }} ~ {{ formatTimeSec(step.end_sec) }}
                    </div>
                    <div class="step-review-row">
                      <el-tag :type="evidenceStatusTagType(step.evidence_status)" size="small">
                        {{ evidenceStatusLabel(step.evidence_status) }}
                      </el-tag>
                      <el-tag :type="reviewStatusTagType(step.review_status)" size="small">
                        {{ reviewStatusLabel(step.review_status) }}
                      </el-tag>
                      <span v-if="groundingConfidenceText(step)" class="confidence-text">
                        视觉证据 {{ groundingConfidenceText(step) }}
                      </span>
                    </div>
                    <el-alert
                      v-if="step.grounding_issue"
                      type="warning"
                      :closable="false"
                      class="step-grounding-alert"
                      :title="step.grounding_issue"
                    />
                    <el-form label-width="120px" size="small" :disabled="!canEditSteps">
                      <el-form-item label="复核结论">
                        <el-radio-group v-model="step.review_status">
                          <el-radio-button label="pending">待确认</el-radio-button>
                          <el-radio-button label="confirmed">已确认</el-radio-button>
                          <el-radio-button label="needs_rework">需重分析</el-radio-button>
                          <el-radio-button label="ignored">忽略</el-radio-button>
                        </el-radio-group>
                      </el-form-item>
                      <el-form-item label="名称">
                        <el-input v-model="step.name" />
                      </el-form-item>
                      <el-form-item label="描述">
                        <el-input v-model="step.description" type="textarea" :rows="2" />
                      </el-form-item>
                      <el-form-item label="动作类型">
                        <el-select v-model="step.action_type" placeholder="选择类型" style="width: 100%">
                          <el-option label="装配 (assemble)" value="assemble" />
                          <el-option label="检查 (inspect)" value="inspect" />
                          <el-option label="取料 (pick)" value="pick" />
                          <el-option label="放置 (place)" value="place" />
                          <el-option label="拧螺丝 (screw)" value="screw" />
                          <el-option label="其他 (other)" value="other" />
                        </el-select>
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
                        <el-input v-model="step.ok_criteria" type="textarea" :rows="2" placeholder="合格判定标准（如：螺丝完全拧入，与表面齐平）" />
                      </el-form-item>
                      <el-form-item label="NG 判定">
                        <el-input v-model="step.ng_criteria" type="textarea" :rows="2" placeholder="不合格判定标准（如：螺丝凸出、歪斜或未拧紧）" />
                      </el-form-item>
                      <el-form-item label="复核备注">
                        <el-input v-model="step.confirmation_note" type="textarea" :rows="2" />
                      </el-form-item>
                    </el-form>
                  </div>
                </div>
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
              保存复核结果
            </el-button>
            <el-button
              type="success"
              :loading="confirmLoading"
              :disabled="!canConfirmSteps"
              @click="confirmGenerate"
            >
              确认并生成模板
            </el-button>
            <span v-if="canEditSteps && !allActiveStepsConfirmed" class="confirm-disabled-tip">
              {{ activeSteps.length - confirmedStepCount }} 个有效步骤待确认
            </span>
            <el-button
              v-if="canRetryAnalysis"
              type="warning"
              :loading="retryLoading"
              @click="retryAnalysis"
            >
              {{ currentTask.status === "completed" ? "重新分析" : "重试分析" }}
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

.phase-hint {
  display: block;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
}

.review-progress {
  color: var(--el-text-color-regular);
  font-variant-numeric: tabular-nums;
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

.review-alert {
  margin-bottom: 14px;
}

.step-card {
  margin-bottom: 8px;
}

.detail-actions {
  margin-top: 20px;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}

.confirm-disabled-tip {
  color: var(--el-color-warning);
  font-size: 13px;
}

.quality-alert {
  width: 100%;
}

.quality-issues {
  margin: 8px 0 0;
  padding-left: 18px;
  line-height: 1.8;
}

.step-card-body {
  display: flex;
  gap: 16px;
}

.step-ref-frame {
  flex-shrink: 0;
  width: 160px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.step-ref-frame img {
  width: 160px;
  border-radius: 6px;
  border: 1px solid var(--el-border-color-lighter);
  object-fit: cover;
}

.ref-frame-time {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  font-family: ui-monospace, monospace;
}

.step-form-area {
  flex: 1;
  min-width: 0;
}

.step-review-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.confidence-text {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.step-grounding-alert {
  margin-bottom: 10px;
}

.step-time-badge {
  display: inline-block;
  margin-bottom: 8px;
  padding: 2px 10px;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  border-radius: 10px;
  font-size: 12px;
  font-family: ui-monospace, monospace;
}

@media (max-width: 768px) {
  .sop-learning-page {
    padding: 12px;
  }
  .step-card-body {
    flex-direction: column;
  }
  .step-ref-frame {
    width: 100%;
  }
  .step-ref-frame img {
    width: 100%;
    max-height: 200px;
  }
}
</style>
