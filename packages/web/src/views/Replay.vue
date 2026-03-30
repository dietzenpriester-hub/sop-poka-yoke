<script setup lang="ts">
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { replayApi, type VideoClip } from "@/api/replay";
import VideoPlayer from "@/components/VideoPlayer.vue";
import { parseErrorMsg } from "@/utils/httpError";
import { formatDateTime } from "@/utils/date";

const clips = ref<VideoClip[]>([]);
const loading = ref(false);
const selectedClip = ref<VideoClip | null>(null);
const showPlayer = ref(false);

const filters = ref({
  sn: "",
  station_code: "",
  event_type: "",
  dateRange: null as [string, string] | null,
});
const pagination = ref({ skip: 0, limit: 20 });

async function loadClips() {
  loading.value = true;
  try {
    const params: Record<string, unknown> = { ...pagination.value };
    if (filters.value.sn) params.sn = filters.value.sn;
    if (filters.value.station_code) params.station_code = filters.value.station_code;
    if (filters.value.event_type) params.event_type = filters.value.event_type;
    if (filters.value.dateRange?.length === 2) {
      params.date_from = filters.value.dateRange[0];
      params.date_to = filters.value.dateRange[1];
    }
    const { data } = await replayApi.listClips(params as Parameters<typeof replayApi.listClips>[0]);
    clips.value = data.items;
  } catch (e: unknown) {
    ElMessage.error(parseErrorMsg(e, "加载视频列表失败"));
  } finally {
    loading.value = false;
  }
}

function playClip(clip: VideoClip) {
  if (!clip.video_url) {
    ElMessage.warning("该记录无视频文件");
    return;
  }
  selectedClip.value = clip;
  showPlayer.value = true;
}

function clipTypeLabel(clip: VideoClip): string {
  if (clip.type === "step") return `步骤 ${clip.step_index}: ${clip.step_name || ""}`;
  return `报警 ${clip.alert_type}: ${clip.message || ""}`;
}

function resultTagType(result: string | undefined): "" | "success" | "warning" | "danger" | "info" {
  switch (result) {
    case "OK": return "success";
    case "NG": return "danger";
    case "SKIP": return "warning";
    case "OVERRIDE": return "info";
    default: return "";
  }
}

function handleSearch() {
  pagination.value.skip = 0;
  loadClips();
}

function handleReset() {
  filters.value = { sn: "", station_code: "", event_type: "", dateRange: null };
  pagination.value = { skip: 0, limit: 20 };
  loadClips();
}

onMounted(() => loadClips());
</script>

<template>
  <div>
    <h2>视频回放</h2>

    <!-- 搜索筛选 -->
    <el-card style="margin-top: 16px">
      <el-form inline>
        <el-form-item label="工单 SN">
          <el-input v-model="filters.sn" placeholder="模糊搜索" clearable style="width: 160px" />
        </el-form-item>
        <el-form-item label="工位">
          <el-input v-model="filters.station_code" placeholder="工位编号" clearable style="width: 120px" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="filters.event_type" clearable placeholder="全部" style="width: 120px">
            <el-option label="步骤视频" value="step" />
            <el-option label="报警视频" value="alert" />
          </el-select>
        </el-form-item>
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="filters.dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始"
            end-placeholder="结束"
            value-format="YYYY-MM-DDTHH:mm:ss"
            style="width: 280px"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch" :loading="loading">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 视频列表 -->
    <el-row :gutter="16" style="margin-top: 16px" v-loading="loading">
      <el-col v-for="clip in clips" :key="clip.id" :xs="24" :sm="12" :md="8" :lg="6" style="margin-bottom: 16px">
        <el-card shadow="hover" :body-style="{ padding: '0' }" @click="playClip(clip)" style="cursor: pointer">
          <div style="height: 160px; background: #1a1a2e; display: flex; align-items: center; justify-content: center; color: #fff; position: relative">
            <img v-if="clip.snapshot_url" :src="clip.snapshot_url" style="width: 100%; height: 100%; object-fit: cover" />
            <div v-else style="font-size: 48px; opacity: 0.3">&#9654;</div>
            <el-tag
              :type="clip.type === 'alert' ? 'danger' : 'primary'"
              size="small"
              style="position: absolute; top: 8px; left: 8px"
            >
              {{ clip.type === "step" ? "步骤" : "报警" }}
            </el-tag>
            <el-tag
              v-if="clip.result"
              :type="resultTagType(clip.result)"
              size="small"
              style="position: absolute; top: 8px; right: 8px"
            >
              {{ clip.result }}
            </el-tag>
          </div>
          <div style="padding: 12px">
            <div style="font-size: 14px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap">
              {{ clipTypeLabel(clip) }}
            </div>
            <div style="font-size: 12px; color: #999; margin-top: 4px">
              <span v-if="clip.sn">SN: {{ clip.sn }}</span>
              <span v-if="clip.station_code"> | {{ clip.station_code }}</span>
            </div>
            <div style="font-size: 12px; color: #bbb; margin-top: 4px">
              {{ formatDateTime(clip.created_at) }}
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-empty v-if="!loading && clips.length === 0" description="暂无视频记录" />

    <!-- 分页 -->
    <div v-if="clips.length > 0" style="margin-top: 16px; display: flex; justify-content: flex-end">
      <el-button :disabled="pagination.skip === 0" @click="pagination.skip = Math.max(0, pagination.skip - pagination.limit); loadClips()">
        上一页
      </el-button>
      <span style="line-height: 32px; margin: 0 12px; color: #666">
        第 {{ Math.floor(pagination.skip / pagination.limit) + 1 }} 页
      </span>
      <el-button :disabled="clips.length < pagination.limit" @click="pagination.skip += pagination.limit; loadClips()">
        下一页
      </el-button>
    </div>

    <!-- 视频播放对话框 -->
    <el-dialog v-model="showPlayer" :title="selectedClip ? clipTypeLabel(selectedClip) : '视频回放'" width="720px" destroy-on-close>
      <VideoPlayer v-if="selectedClip?.video_url" :src="selectedClip.video_url" />
      <div style="margin-top: 12px; color: #666; font-size: 13px">
        <p v-if="selectedClip?.sn"><strong>工单:</strong> {{ selectedClip.sn }}</p>
        <p v-if="selectedClip?.station_code"><strong>工位:</strong> {{ selectedClip.station_code }}</p>
        <p><strong>时间:</strong> {{ formatDateTime(selectedClip?.created_at) }}</p>
        <p v-if="selectedClip?.type === 'alert'">
          <strong>报警:</strong> {{ selectedClip.alert_type }} / {{ selectedClip.severity }} — {{ selectedClip.message }}
        </p>
      </div>
    </el-dialog>
  </div>
</template>
