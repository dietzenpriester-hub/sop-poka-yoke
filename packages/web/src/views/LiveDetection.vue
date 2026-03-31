<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from "vue";
import { ElMessage } from "element-plus";
import {
  VideoPause,
  VideoPlay,
  Refresh,
  Check,
  Close,
  Warning,
  Loading,
  Connection,
} from "@element-plus/icons-vue";
import { stationApi, type StationItem } from "@/api/station";
import { useStationWebSocket } from "@/composables/useWebSocket";

interface StepInfo {
  index: number;
  name: string;
  status: "pending" | "active" | "ok" | "ng" | "timeout";
}

interface SopStatus {
  type: string;
  station_id: string;
  timestamp: string;
  work_order_sn: string;
  sop_name: string;
  total_steps: number;
  current_step_index: number;
  current_step_name: string;
  status: string;
  event: string;
  vlm_action: string;
  vlm_confidence: number;
  vlm_matches: boolean;
  yolo_objects: string[];
  snapshot: string;
}

const stations = ref<StationItem[]>([]);
const selectedStationId = ref("");
const loading = ref(false);
const monitoring = ref(false);

const snapshotSrc = ref("");
const sopStatus = ref<SopStatus | null>(null);
const detectionCount = ref(0);
const yoloObjects = ref<string[]>([]);
const eventLog = ref<{ time: string; text: string; type: "info" | "success" | "warning" | "danger" }[]>([]);
const lastUpdateTime = ref("");

const steps = ref<StepInfo[]>([]);

function handleWsMessage(data: unknown) {
  const msg = data as Record<string, unknown>;
  if (!msg) return;

  if (msg.type === "sop_status" || (msg.payload && (msg.payload as Record<string, unknown>).type === "sop_status")) {
    const status = (msg.type === "sop_status" ? msg : msg.payload) as SopStatus;
    sopStatus.value = status;
    lastUpdateTime.value = status.timestamp;

    if (status.snapshot) {
      snapshotSrc.value = `data:image/jpeg;base64,${status.snapshot}`;
    }

    if (status.total_steps > 0 && steps.value.length !== status.total_steps) {
      steps.value = Array.from({ length: status.total_steps }, (_, i) => ({
        index: i,
        name: `步骤 ${i + 1}`,
        status: "pending" as const,
      }));
    }
    for (const s of steps.value) {
      if (s.index < status.current_step_index) {
        s.status = "ok";
      } else if (s.index === status.current_step_index) {
        s.status = "active";
      } else {
        s.status = "pending";
      }
    }

    if (status.current_step_name && status.current_step_index < steps.value.length) {
      steps.value[status.current_step_index].name = status.current_step_name;
    }

    if (status.event === "step_ok") {
      const idx = status.current_step_index;
      if (idx > 0 && idx - 1 < steps.value.length) {
        steps.value[idx - 1].status = "ok";
      }
      addEvent("success", `步骤 ${idx} 完成 ✓`);
    } else if (status.event === "step_ng") {
      if (status.current_step_index < steps.value.length) {
        steps.value[status.current_step_index].status = "ng";
      }
      addEvent("danger", `步骤 ${status.current_step_index + 1} NG！`);
    } else if (status.event === "complete") {
      addEvent("success", "所有 SOP 步骤已完成！");
    }

    yoloObjects.value = status.yolo_objects || [];
  }

  const snap = (msg.snapshot as string) || (msg.payload as Record<string, unknown>)?.snapshot as string;
  if (snap && !snapshotSrc.value.includes(snap.slice(0, 20))) {
    snapshotSrc.value = `data:image/jpeg;base64,${snap}`;
  }
  if (typeof msg.detect_count === "number") {
    detectionCount.value = msg.detect_count as number;
  }
  if (Array.isArray(msg.unique_classes)) {
    yoloObjects.value = msg.unique_classes as string[];
  }
}

const { ready: wsReady } = useStationWebSocket(selectedStationId, handleWsMessage);

function addEvent(type: "info" | "success" | "warning" | "danger", text: string) {
  const now = new Date().toLocaleTimeString("zh-CN");
  eventLog.value.unshift({ time: now, text, type });
  if (eventLog.value.length > 50) eventLog.value.length = 50;
}

async function loadStations() {
  loading.value = true;
  try {
    const { data } = await stationApi.list();
    stations.value = data;
  } catch {
    ElMessage.error("加载工位列表失败");
  } finally {
    loading.value = false;
  }
}

function startMonitoring() {
  if (!selectedStationId.value) {
    ElMessage.warning("请先选择工位");
    return;
  }
  monitoring.value = true;
  eventLog.value = [];
  steps.value = [];
  sopStatus.value = null;
  snapshotSrc.value = "";
  addEvent("info", `开始监控工位 ${selectedStationId.value}`);
}

function stopMonitoring() {
  monitoring.value = false;
  selectedStationId.value = "";
  addEvent("info", "停止监控");
}

const progressPercent = computed(() => {
  if (!sopStatus.value || sopStatus.value.total_steps === 0) return 0;
  return Math.round((sopStatus.value.current_step_index / sopStatus.value.total_steps) * 100);
});

const statusColor = computed(() => {
  if (!sopStatus.value) return "#909399";
  switch (sopStatus.value.status) {
    case "running": return "#409eff";
    case "completed": return "#67c23a";
    case "timeout": return "#e6a23c";
    case "error": return "#f56c6c";
    default: return "#909399";
  }
});

const statusText = computed(() => {
  if (!sopStatus.value) return "等待连接...";
  switch (sopStatus.value.status) {
    case "running": return "检测中";
    case "completed": return "已完成";
    case "timeout": return "超时";
    case "error": return "异常";
    default: return sopStatus.value.status;
  }
});

const confidenceColor = computed(() => {
  if (!sopStatus.value) return "";
  const c = sopStatus.value.vlm_confidence;
  if (c >= 0.8) return "#67c23a";
  if (c >= 0.5) return "#e6a23c";
  return "#f56c6c";
});

onMounted(() => {
  loadStations();
});

onUnmounted(() => {
  monitoring.value = false;
});
</script>

<template>
  <div class="live-detection">
    <div class="page-header">
      <h2>实时作业检测</h2>
      <div class="page-header-actions">
        <el-tag
          :type="wsReady ? 'success' : 'danger'"
          effect="dark"
          round
          size="small"
        >
          <span class="ws-dot" :class="{ online: wsReady }" />
          {{ wsReady ? "已连接" : "未连接" }}
        </el-tag>
      </div>
    </div>

    <!-- 工位选择与控制 -->
    <el-card class="control-bar" shadow="never">
      <div class="control-row">
        <div class="control-left">
          <el-select
            v-model="selectedStationId"
            placeholder="选择工位"
            :disabled="monitoring"
            style="width: 240px"
          >
            <el-option
              v-for="s in stations"
              :key="s.id"
              :label="`${s.name} (${s.line_id || '—'})`"
              :value="s.edge_device_id || String(s.id)"
            />
          </el-select>
          <el-button
            v-if="!monitoring"
            type="primary"
            :icon="VideoPlay"
            :disabled="!selectedStationId"
            @click="startMonitoring"
          >
            开始监控
          </el-button>
          <el-button
            v-else
            type="danger"
            :icon="VideoPause"
            @click="stopMonitoring"
          >
            停止监控
          </el-button>
          <el-button :icon="Refresh" @click="loadStations" :loading="loading">
            刷新工位
          </el-button>
        </div>
        <div class="control-right">
          <span v-if="lastUpdateTime" class="last-update">
            最后更新: {{ lastUpdateTime }}
          </span>
        </div>
      </div>
    </el-card>

    <template v-if="monitoring">
      <el-row :gutter="16" style="margin-top: 16px">
        <!-- 左：摄像头画面 + VLM 结果 -->
        <el-col :xs="24" :lg="14">
          <el-card class="video-card" shadow="never">
            <template #header>
              <div class="card-header-row">
                <span class="card-title">摄像头实时画面</span>
                <el-tag size="small" :type="monitoring ? 'success' : 'info'">
                  {{ monitoring ? "实时画面" : "等待画面..." }}
                </el-tag>
              </div>
            </template>
            <div class="video-container">
              <img
                v-if="monitoring"
                :src="'/mjpeg/stream'"
                class="snapshot-img"
                style="transform: scaleX(-1)"
                alt="MJPEG 实时视频"
              />
              <div v-else class="video-placeholder">
                <el-icon :size="48" color="#c0c4cc"><Connection /></el-icon>
                <p>等待摄像头数据...</p>
              </div>
            </div>

            <!-- VLM 识别结果叠加 -->
            <div v-if="sopStatus" class="vlm-overlay">
              <div class="vlm-result-row">
                <span class="vlm-label">VLM 识别:</span>
                <span class="vlm-action">{{ sopStatus.vlm_action || "等待推理..." }}</span>
              </div>
              <div class="vlm-result-row">
                <span class="vlm-label">置信度:</span>
                <el-progress
                  :percentage="Math.round(sopStatus.vlm_confidence * 100)"
                  :color="confidenceColor"
                  :stroke-width="14"
                  style="flex: 1"
                />
              </div>
              <div class="vlm-result-row">
                <span class="vlm-label">匹配:</span>
                <el-tag
                  :type="sopStatus.vlm_matches ? 'success' : 'danger'"
                  size="small"
                  effect="dark"
                >
                  <el-icon style="margin-right: 2px">
                    <component :is="sopStatus.vlm_matches ? Check : Close" />
                  </el-icon>
                  {{ sopStatus.vlm_matches ? "匹配" : "不匹配" }}
                </el-tag>
              </div>
            </div>
          </el-card>

          <!-- YOLO 检测物体 -->
          <el-card class="objects-card" shadow="never" style="margin-top: 16px">
            <template #header>
              <span class="card-title">YOLO 目标检测</span>
            </template>
            <div v-if="yoloObjects.length > 0" class="object-tags">
              <el-tag
                v-for="obj in yoloObjects"
                :key="obj"
                type="info"
                effect="plain"
                size="large"
                class="object-tag"
              >
                {{ obj }}
              </el-tag>
            </div>
            <el-empty v-else description="暂无检测到物体" :image-size="40" />
            <div class="detect-count">
              累计检测: <strong>{{ detectionCount }}</strong> 次
            </div>
          </el-card>
        </el-col>

        <!-- 右：SOP 步骤进度 + 事件日志 -->
        <el-col :xs="24" :lg="10">
          <!-- SOP 总体状态 -->
          <el-card class="status-card" shadow="never">
            <template #header>
              <div class="card-header-row">
                <span class="card-title">SOP 执行状态</span>
                <el-tag :color="statusColor" effect="dark" size="small" style="color:#fff; border:none">
                  {{ statusText }}
                </el-tag>
              </div>
            </template>

            <div v-if="sopStatus" class="status-info">
              <div class="info-row">
                <span class="info-label">工单:</span>
                <span>{{ sopStatus.work_order_sn || "—" }}</span>
              </div>
              <div class="info-row">
                <span class="info-label">当前步骤:</span>
                <span class="current-step-text">
                  {{ sopStatus.current_step_index + 1 }} / {{ sopStatus.total_steps }}
                  — {{ sopStatus.current_step_name || "—" }}
                </span>
              </div>
              <el-progress
                :percentage="progressPercent"
                :stroke-width="18"
                :color="[
                  { color: '#f56c6c', percentage: 20 },
                  { color: '#e6a23c', percentage: 40 },
                  { color: '#409eff', percentage: 70 },
                  { color: '#67c23a', percentage: 100 },
                ]"
                style="margin-top: 12px"
              />
            </div>
            <el-empty v-else description="等待 SOP 状态..." :image-size="50" />
          </el-card>

          <!-- 步骤列表 -->
          <el-card class="steps-card" shadow="never" style="margin-top: 16px">
            <template #header>
              <span class="card-title">步骤明细</span>
            </template>
            <el-scrollbar max-height="280px">
              <div v-if="steps.length > 0" class="step-list">
                <div
                  v-for="s in steps"
                  :key="s.index"
                  class="step-item"
                  :class="`step-${s.status}`"
                >
                  <div class="step-icon">
                    <el-icon v-if="s.status === 'ok'" color="#67c23a"><Check /></el-icon>
                    <el-icon v-else-if="s.status === 'ng'" color="#f56c6c"><Close /></el-icon>
                    <el-icon v-else-if="s.status === 'active'" color="#409eff" class="spin"><Loading /></el-icon>
                    <el-icon v-else-if="s.status === 'timeout'" color="#e6a23c"><Warning /></el-icon>
                    <span v-else class="step-num">{{ s.index + 1 }}</span>
                  </div>
                  <div class="step-text">
                    <span class="step-name">{{ s.name }}</span>
                    <el-tag
                      v-if="s.status !== 'pending'"
                      :type="s.status === 'ok' ? 'success' : s.status === 'ng' ? 'danger' : s.status === 'active' ? '' : 'warning'"
                      size="small"
                      style="margin-left: 8px"
                    >
                      {{ s.status === 'ok' ? '完成' : s.status === 'ng' ? 'NG' : s.status === 'active' ? '执行中' : '超时' }}
                    </el-tag>
                  </div>
                </div>
              </div>
              <el-empty v-else description="等待步骤数据..." :image-size="40" />
            </el-scrollbar>
          </el-card>

          <!-- 事件日志 -->
          <el-card class="log-card" shadow="never" style="margin-top: 16px">
            <template #header>
              <span class="card-title">事件日志</span>
            </template>
            <el-scrollbar max-height="200px">
              <div v-if="eventLog.length > 0" class="event-log">
                <div v-for="(e, i) in eventLog" :key="i" class="log-entry">
                  <span class="log-time">{{ e.time }}</span>
                  <el-tag :type="e.type" size="small" effect="plain">
                    {{ e.text }}
                  </el-tag>
                </div>
              </div>
              <el-empty v-else description="暂无事件" :image-size="30" />
            </el-scrollbar>
          </el-card>
        </el-col>
      </el-row>
    </template>

    <!-- 未开始监控 -->
    <div v-else class="idle-hint">
      <el-empty description="请选择工位并点击「开始监控」">
        <template #image>
          <el-icon :size="80" color="#c0c4cc"><Monitor /></el-icon>
        </template>
      </el-empty>
    </div>
  </div>
</template>

<script lang="ts">
import { Monitor } from "@element-plus/icons-vue";
export default { components: { Monitor } };
</script>

<style scoped>
.live-detection {
  max-width: 1440px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.page-header h2 {
  margin: 0;
  font-size: 18px;
}

.control-bar {
  border-radius: var(--sop-radius-lg, 12px);
}

.control-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.control-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.last-update {
  font-size: 12px;
  color: #909399;
}

.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-weight: 600;
  font-size: 14px;
}

.video-card,
.objects-card,
.status-card,
.steps-card,
.log-card {
  border-radius: var(--sop-radius-lg, 12px);
}

.video-container {
  background: #000;
  border-radius: 8px;
  overflow: hidden;
  aspect-ratio: 16 / 10;
  display: flex;
  align-items: center;
  justify-content: center;
}

.snapshot-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.video-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: #c0c4cc;
}

.video-placeholder p {
  margin: 0;
  font-size: 14px;
}

.vlm-overlay {
  margin-top: 12px;
  background: #f5f7fa;
  border-radius: 8px;
  padding: 12px 16px;
}

.vlm-result-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.vlm-result-row:last-child {
  margin-bottom: 0;
}

.vlm-label {
  font-size: 13px;
  color: #606266;
  white-space: nowrap;
  min-width: 64px;
}

.vlm-action {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.object-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.object-tag {
  font-size: 14px !important;
}

.detect-count {
  margin-top: 12px;
  font-size: 13px;
  color: #909399;
  text-align: right;
}

.status-info {
  padding: 4px 0;
}

.info-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 14px;
}

.info-label {
  color: #909399;
  min-width: 64px;
  flex-shrink: 0;
}

.current-step-text {
  font-weight: 600;
  color: #409eff;
}

.step-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.step-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  transition: background 0.2s;
}

.step-item.step-active {
  background: rgba(64, 158, 255, 0.08);
}

.step-item.step-ok {
  background: rgba(103, 194, 58, 0.06);
}

.step-item.step-ng {
  background: rgba(245, 108, 108, 0.08);
}

.step-icon {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #f5f7fa;
  flex-shrink: 0;
}

.step-active .step-icon {
  background: rgba(64, 158, 255, 0.12);
}

.step-ok .step-icon {
  background: rgba(103, 194, 58, 0.12);
}

.step-ng .step-icon {
  background: rgba(245, 108, 108, 0.12);
}

.step-num {
  font-size: 12px;
  color: #c0c4cc;
  font-weight: 600;
}

.step-text {
  display: flex;
  align-items: center;
}

.step-name {
  font-size: 14px;
  color: #303133;
}

.spin {
  animation: spin 1.5s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.event-log {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.log-entry {
  display: flex;
  align-items: center;
  gap: 8px;
}

.log-time {
  font-size: 12px;
  color: #c0c4cc;
  font-family: monospace;
  white-space: nowrap;
}

.idle-hint {
  margin-top: 60px;
}

.ws-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #f56c6c;
  margin-right: 4px;
  vertical-align: middle;
}

.ws-dot.online {
  background: #67c23a;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
</style>
