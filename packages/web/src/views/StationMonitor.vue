<script setup lang="ts">
import { ref, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { stationApi, type StationItem, type StationStats } from "@/api/station";
import { parseErrorMsg } from "@/utils/httpError";

const stations = ref<StationItem[]>([]);
const loading = ref(false);
const lineFilter = ref("");

const showCreateDialog = ref(false);
const showEditDialog = ref(false);
const showStatsDialog = ref(false);
const editingStation = ref<StationItem | null>(null);
const stationStats = ref<StationStats | null>(null);

const createForm = ref({ name: "", line_id: "", edge_device_id: "", rtsp_url: "", description: "" });
const editForm = ref({ name: "", line_id: "", edge_device_id: "", rtsp_url: "", description: "" });

async function loadStations() {
  loading.value = true;
  try {
    const params: Record<string, unknown> = {};
    if (lineFilter.value) params.line_id = lineFilter.value;
    const { data } = await stationApi.list(params as Parameters<typeof stationApi.list>[0]);
    stations.value = data;
  } catch {
    ElMessage.error("加载工位列表失败");
  } finally {
    loading.value = false;
  }
}

async function handleCreate() {
  if (!createForm.value.name) {
    ElMessage.warning("请填写工位名称");
    return;
  }
  try {
    await stationApi.create(createForm.value);
    ElMessage.success("工位已创建");
    showCreateDialog.value = false;
    createForm.value = { name: "", line_id: "", edge_device_id: "", rtsp_url: "", description: "" };
    loadStations();
  } catch (e: unknown) {
    ElMessage.error(parseErrorMsg(e, "创建失败"));
  }
}

function openEdit(station: StationItem) {
  editingStation.value = station;
  editForm.value = {
    name: station.name,
    line_id: station.line_id,
    edge_device_id: station.edge_device_id,
    rtsp_url: station.rtsp_url,
    description: station.description,
  };
  showEditDialog.value = true;
}

async function handleUpdate() {
  if (!editingStation.value) return;
  try {
    await stationApi.update(editingStation.value.id, editForm.value);
    ElMessage.success("工位信息已更新");
    showEditDialog.value = false;
    loadStations();
  } catch (e: unknown) {
    ElMessage.error(parseErrorMsg(e, "更新失败"));
  }
}

async function handleDelete(station: StationItem) {
  try {
    await ElMessageBox.confirm(`确定删除工位「${station.name}」？`, "确认删除", { type: "warning" });
    await stationApi.delete(station.id);
    ElMessage.success("工位已删除");
    loadStations();
  } catch (e: unknown) {
    if (e !== "cancel") ElMessage.error(parseErrorMsg(e, "删除失败"));
  }
}

async function viewStats(station: StationItem) {
  try {
    const { data } = await stationApi.stats(station.id);
    stationStats.value = data;
    showStatsDialog.value = true;
  } catch {
    ElMessage.error("获取统计失败");
  }
}

function formatTime(ts: string): string {
  return new Date(ts).toLocaleString("zh-CN");
}

onMounted(() => loadStations());
</script>

<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center">
      <h2>工位管理</h2>
      <div>
        <el-input
          v-model="lineFilter"
          placeholder="产线筛选"
          clearable
          style="width: 140px; margin-right: 8px"
          @change="loadStations"
        />
        <el-button type="primary" @click="showCreateDialog = true">新增工位</el-button>
      </div>
    </div>

    <el-table :data="stations" v-loading="loading" style="margin-top: 16px">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="name" label="工位名称" width="120" />
      <el-table-column prop="line_id" label="产线" width="100" />
      <el-table-column prop="edge_device_id" label="边缘设备" width="140" show-overflow-tooltip />
      <el-table-column prop="rtsp_url" label="摄像头 URL" min-width="200" show-overflow-tooltip />
      <el-table-column prop="description" label="描述" min-width="150" show-overflow-tooltip />
      <el-table-column prop="created_at" label="创建时间" width="170">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="240" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="viewStats(row)">统计</el-button>
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 创建对话框 -->
    <el-dialog v-model="showCreateDialog" title="新增工位" width="520px">
      <el-form :model="createForm" label-width="100px">
        <el-form-item label="工位名称"><el-input v-model="createForm.name" placeholder="如 ST-01" /></el-form-item>
        <el-form-item label="所属产线"><el-input v-model="createForm.line_id" placeholder="如 LINE-A" /></el-form-item>
        <el-form-item label="边缘设备 ID"><el-input v-model="createForm.edge_device_id" /></el-form-item>
        <el-form-item label="摄像头 URL"><el-input v-model="createForm.rtsp_url" placeholder="rtsp://..." /></el-form-item>
        <el-form-item label="描述"><el-input v-model="createForm.description" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 编辑对话框 -->
    <el-dialog v-model="showEditDialog" title="编辑工位" width="520px">
      <el-form :model="editForm" label-width="100px">
        <el-form-item label="工位名称"><el-input v-model="editForm.name" /></el-form-item>
        <el-form-item label="所属产线"><el-input v-model="editForm.line_id" /></el-form-item>
        <el-form-item label="边缘设备 ID"><el-input v-model="editForm.edge_device_id" /></el-form-item>
        <el-form-item label="摄像头 URL"><el-input v-model="editForm.rtsp_url" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="editForm.description" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" @click="handleUpdate">保存</el-button>
      </template>
    </el-dialog>

    <!-- 统计对话框 -->
    <el-dialog v-model="showStatsDialog" :title="`工位统计 — ${stationStats?.name}`" width="400px">
      <el-descriptions :column="1" border v-if="stationStats">
        <el-descriptions-item label="工位名称">{{ stationStats.name }}</el-descriptions-item>
        <el-descriptions-item label="关联工单数">{{ stationStats.workorder_count }}</el-descriptions-item>
        <el-descriptions-item label="报警数">{{ stationStats.alert_count }}</el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>
