<script setup lang="ts">
import { ref } from "vue";
import { ElMessage } from "element-plus";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE || "";

const productModel = ref("");
const processName = ref("");
const taskId = ref("");
const taskStatus = ref("");
const templateResult = ref<Record<string, unknown> | null>(null);

async function handleUpload(file: { raw: File }) {
  if (!productModel.value || !processName.value) {
    ElMessage.warning("请填写产品型号和工序名称");
    return;
  }
  const formData = new FormData();
  formData.append("video", file.raw);
  const resp = await axios.post(
    `${API_BASE}/api/learning/upload-video?product_model=${productModel.value}&process_name=${processName.value}`,
    formData
  );
  taskId.value = resp.data.task_id;
  taskStatus.value = resp.data.status;
  ElMessage.success("视频已上传，开始 AI 分析");
  pollStatus();
}

async function pollStatus() {
  const interval = setInterval(async () => {
    const resp = await axios.get(`${API_BASE}/api/learning/task/${taskId.value}`);
    taskStatus.value = resp.data.status;
    if (resp.data.status === "completed") {
      clearInterval(interval);
      ElMessage.success(`分析完成，识别到 ${resp.data.step_count} 个步骤`);
    }
  }, 2000);
}

async function generateTemplate() {
  const resp = await axios.post(`${API_BASE}/api/learning/generate-template/${taskId.value}`);
  templateResult.value = resp.data;
  ElMessage.success("草稿模板已生成");
}
</script>

<template>
  <div style="max-width: 800px">
    <h2>SOP 标准作业学习</h2>
    <el-form label-width="100px" style="margin-top: 24px">
      <el-form-item label="产品型号">
        <el-input v-model="productModel" placeholder="如 PCB-A100" />
      </el-form-item>
      <el-form-item label="工序名称">
        <el-input v-model="processName" placeholder="如 螺丝装配" />
      </el-form-item>
      <el-form-item label="标准视频">
        <el-upload :auto-upload="false" accept="video/*" :on-change="(f: any) => handleUpload(f)" :show-file-list="false">
          <el-button type="primary">选择视频文件</el-button>
        </el-upload>
      </el-form-item>
    </el-form>
    <div v-if="taskId" style="margin-top: 24px">
      <p>任务 ID：{{ taskId }}</p>
      <p>状态：{{ taskStatus }}</p>
      <el-button v-if="taskStatus === 'completed'" type="success" @click="generateTemplate">生成 SOP 模板</el-button>
    </div>
    <div v-if="templateResult" style="margin-top: 24px">
      <h3>生成结果</h3>
      <pre style="background: #f5f5f5; padding: 16px; border-radius: 8px; overflow-x: auto">{{ JSON.stringify(templateResult, null, 2) }}</pre>
    </div>
  </div>
</template>
