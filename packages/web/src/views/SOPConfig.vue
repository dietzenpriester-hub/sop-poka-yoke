<script setup lang="ts">
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import { sopApi, type SOPTemplate } from "@/api/sop";

const templates = ref<SOPTemplate[]>([]);
const loading = ref(false);
const dialogVisible = ref(false);
const form = ref({
  name: "",
  version: "1.0",
  product_model: "",
  description: "",
  steps: [] as Record<string, unknown>[],
});

async function loadTemplates() {
  loading.value = true;
  try {
    const { data } = await sopApi.list();
    templates.value = data;
  } catch {
    ElMessage.error("加载失败");
  } finally {
    loading.value = false;
  }
}

async function handleCreate() {
  try {
    await sopApi.create(form.value);
    ElMessage.success("创建成功");
    dialogVisible.value = false;
    loadTemplates();
  } catch {
    ElMessage.error("创建失败");
  }
}

async function handleDelete(id: number) {
  await sopApi.delete(id);
  ElMessage.success("已删除");
  loadTemplates();
}

onMounted(loadTemplates);
</script>

<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center">
      <h2>SOP 模板管理</h2>
      <el-button type="primary" @click="dialogVisible = true">新建模板</el-button>
    </div>

    <el-table :data="templates" v-loading="loading" style="margin-top: 20px">
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="version" label="版本" width="100" />
      <el-table-column prop="product_model" label="产品型号" />
      <el-table-column prop="steps" label="步骤数" width="100">
        <template #default="{ row }">{{ row.steps?.length || 0 }}</template>
      </el-table-column>
      <el-table-column label="操作" width="150">
        <template #default="{ row }">
          <el-button size="small" type="danger" @click="handleDelete(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="新建 SOP 模板" width="500px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="版本"><el-input v-model="form.version" /></el-form-item>
        <el-form-item label="产品型号"><el-input v-model="form.product_model" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="form.description" type="textarea" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>
