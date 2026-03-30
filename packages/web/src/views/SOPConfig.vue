<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { ArrowDown, ArrowUp } from "@element-plus/icons-vue";
import { sopApi, type SOPTemplate } from "@/api/sop";
import { parseErrorMsg } from "@/utils/httpError";
import { formatDateTime } from "@/utils/date";

interface SOPStep {
  /** 仅用于列表渲染，不提交到 API */
  clientKey: string;
  name: string;
  description: string;
  required_objects: string[];
  action_type: string;
  timeout_seconds: number;
  is_optional: boolean;
}

const ACTION_TYPE_OPTIONS = [
  "目视检查",
  "扫码验证",
  "工具操作",
  "装配",
  "测量",
  "其他",
] as const;

function normalizeStep(raw: Record<string, unknown>): SOPStep {
  const name = typeof raw.name === "string" ? raw.name : "";
  const description = typeof raw.description === "string" ? raw.description : "";
  const action_type = typeof raw.action_type === "string" ? raw.action_type : "";
  const timeout_seconds =
    typeof raw.timeout_seconds === "number" && !Number.isNaN(raw.timeout_seconds)
      ? raw.timeout_seconds
      : 60;
  const is_optional = typeof raw.is_optional === "boolean" ? raw.is_optional : false;
  const ro = raw.required_objects;
  const required_objects = Array.isArray(ro)
    ? ro.filter((x): x is string => typeof x === "string")
    : [];
  return {
    clientKey: crypto.randomUUID(),
    name,
    description,
    required_objects,
    action_type,
    timeout_seconds,
    is_optional,
  };
}

function emptyStep(): SOPStep {
  return {
    clientKey: crypto.randomUUID(),
    name: "",
    description: "",
    required_objects: [],
    action_type: "",
    timeout_seconds: 60,
    is_optional: false,
  };
}

const templates = ref<SOPTemplate[]>([]);
const loading = ref(false);

const dialogVisible = ref(false);
const previewVisible = ref(false);
const editingId = ref<number | null>(null);
const previewTemplate = ref<SOPTemplate | null>(null);

const form = ref({
  name: "",
  version: "1.0",
  product_model: "",
  description: "",
  steps: [] as SOPStep[],
});

const previewSteps = computed(() => {
  const t = previewTemplate.value;
  if (!t) return [];
  return t.steps.map((s) => normalizeStep(s as Record<string, unknown>));
});

function requiredObjectsInputValue(step: SOPStep): string {
  return step.required_objects.join(", ");
}

function setRequiredObjectsFromInput(step: SOPStep, value: string): void {
  step.required_objects = value
    .split(/[,，]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

async function loadTemplates() {
  loading.value = true;
  try {
    const { data } = await sopApi.list();
    templates.value = data;
  } catch (e) {
    ElMessage.error(parseErrorMsg(e, "加载失败"));
  } finally {
    loading.value = false;
  }
}

function openCreateDialog(): void {
  editingId.value = null;
  form.value = {
    name: "",
    version: "1.0",
    product_model: "",
    description: "",
    steps: [],
  };
  dialogVisible.value = true;
}

async function openEditDialog(template: SOPTemplate): Promise<void> {
  editingId.value = template.id;
  dialogVisible.value = true;
  try {
    const { data } = await sopApi.get(template.id);
    form.value = {
      name: data.name,
      version: data.version,
      product_model: data.product_model ?? "",
      description: data.description,
      steps: data.steps.map((s) => normalizeStep(s as Record<string, unknown>)),
    };
  } catch (e) {
    ElMessage.error(parseErrorMsg(e, "加载模板失败"));
    dialogVisible.value = false;
    editingId.value = null;
  }
}

function openPreviewDialog(template: SOPTemplate): void {
  previewTemplate.value = template;
  previewVisible.value = true;
}

function addStep(): void {
  form.value.steps.push(emptyStep());
}

function removeStep(index: number): void {
  form.value.steps.splice(index, 1);
}

function moveStepUp(index: number): void {
  if (index <= 0) return;
  const arr = form.value.steps;
  const prev = arr[index - 1];
  const cur = arr[index];
  if (prev === undefined || cur === undefined) return;
  arr[index - 1] = cur;
  arr[index] = prev;
}

function moveStepDown(index: number): void {
  const arr = form.value.steps;
  if (index >= arr.length - 1) return;
  const cur = arr[index];
  const next = arr[index + 1];
  if (cur === undefined || next === undefined) return;
  arr[index] = next;
  arr[index + 1] = cur;
}

function buildSavePayload() {
  return {
    name: form.value.name,
    version: form.value.version,
    description: form.value.description,
    product_model: form.value.product_model.trim() || null,
    steps: form.value.steps.map((s) => ({
      name: s.name,
      description: s.description,
      required_objects: s.required_objects,
      action_type: s.action_type,
      timeout_seconds: s.timeout_seconds,
      is_optional: s.is_optional,
    })),
  };
}

async function handleSave(): Promise<void> {
  const nameTrim = form.value.name.trim();
  if (!nameTrim) {
    ElMessage.warning("请填写模板名称");
    return;
  }
  form.value.name = nameTrim;

  if (form.value.steps.length === 0) {
    ElMessage.warning("请至少添加一个步骤");
    return;
  }

  for (let i = 0; i < form.value.steps.length; i++) {
    const s = form.value.steps[i];
    if (!s) continue;
    if (!s.name.trim()) {
      ElMessage.warning(`请填写步骤 ${i + 1} 的名称`);
      return;
    }
    s.name = s.name.trim();
  }

  try {
    if (editingId.value === null) {
      await sopApi.create(buildSavePayload());
      ElMessage.success("创建成功");
    } else {
      await sopApi.update(editingId.value, buildSavePayload());
      ElMessage.success("保存成功");
    }
    dialogVisible.value = false;
    editingId.value = null;
    await loadTemplates();
  } catch (e) {
    ElMessage.error(parseErrorMsg(e, editingId.value === null ? "创建失败" : "保存失败"));
  }
}

async function handleDelete(id: number): Promise<void> {
  try {
    await ElMessageBox.confirm("确定要删除此模板吗？", "确认删除", { type: "warning" });
    await sopApi.delete(id);
    ElMessage.success("已删除");
    await loadTemplates();
  } catch (e) {
    if (e !== "cancel") ElMessage.error(parseErrorMsg(e, "删除失败"));
  }
}

function onEditDialogClosed(): void {
  editingId.value = null;
}

onMounted(loadTemplates);
</script>

<template>
  <div>
    <div style="display: flex; justify-content: space-between; align-items: center">
      <h2>SOP 模板管理</h2>
      <el-button type="primary" @click="openCreateDialog">新建模板</el-button>
    </div>

    <el-table :data="templates" v-loading="loading" style="margin-top: 20px">
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="name" label="名称" min-width="120" />
      <el-table-column prop="version" label="版本" width="100" />
      <el-table-column prop="product_model" label="产品型号" min-width="120" />
      <el-table-column prop="steps" label="步骤数" width="100">
        <template #default="{ row }">{{ row.steps?.length || 0 }}</template>
      </el-table-column>
      <el-table-column label="更新时间" width="180">
        <template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="260" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openPreviewDialog(row)">预览</el-button>
          <el-button size="small" type="primary" @click="openEditDialog(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="handleDelete(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId === null ? '新建 SOP 模板' : '编辑 SOP 模板'"
      width="700px"
      destroy-on-close
      @closed="onEditDialogClosed"
    >
      <el-form :model="form" label-width="100px">
        <el-divider content-position="left">基本信息</el-divider>
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="模板名称" maxlength="100" show-word-limit />
        </el-form-item>
        <el-form-item label="版本">
          <el-input v-model="form.version" placeholder="如 1.0" />
        </el-form-item>
        <el-form-item label="产品型号">
          <el-input v-model="form.product_model" placeholder="可选" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="模板说明" />
        </el-form-item>

        <el-divider content-position="left">步骤</el-divider>
        <div v-if="form.steps.length === 0" class="steps-empty">暂无步骤，请点击下方「添加步骤」</div>

        <el-card
          v-for="(step, index) in form.steps"
          :key="step.clientKey"
          shadow="never"
          class="step-card"
        >
          <template #header>
            <div class="step-card-header">
              <span class="step-index">步骤 {{ index + 1 }}</span>
              <div class="step-card-actions">
                <el-button
                  :disabled="index === 0"
                  size="small"
                  :icon="ArrowUp"
                  circle
                  title="上移"
                  @click="moveStepUp(index)"
                />
                <el-button
                  :disabled="index === form.steps.length - 1"
                  size="small"
                  :icon="ArrowDown"
                  circle
                  title="下移"
                  @click="moveStepDown(index)"
                />
                <el-button size="small" type="danger" text @click="removeStep(index)">删除</el-button>
              </div>
            </div>
          </template>

          <el-form-item label="名称" :label-width="90">
            <el-input v-model="step.name" placeholder="步骤名称" maxlength="200" show-word-limit />
          </el-form-item>
          <el-form-item label="描述" :label-width="90">
            <el-input v-model="step.description" type="textarea" :rows="2" placeholder="步骤说明" />
          </el-form-item>
          <el-form-item label="动作类型" :label-width="90">
            <el-select v-model="step.action_type" placeholder="选择类型" clearable style="width: 100%">
              <el-option
                v-for="opt in ACTION_TYPE_OPTIONS"
                :key="opt"
                :label="opt"
                :value="opt"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="超时(秒)" :label-width="90">
            <el-input-number v-model="step.timeout_seconds" :min="0" :step="1" style="width: 100%" />
          </el-form-item>
          <el-form-item label="可选" :label-width="90">
            <el-checkbox v-model="step.is_optional">此步骤可跳过</el-checkbox>
          </el-form-item>
          <el-form-item label="必需对象" :label-width="90">
            <el-input
              :model-value="requiredObjectsInputValue(step)"
              placeholder="逗号分隔，如：螺丝, 螺母"
              @update:model-value="(v: string) => setRequiredObjectsFromInput(step, v ?? '')"
            />
          </el-form-item>
        </el-card>

        <el-button class="add-step-btn" type="primary" plain @click="addStep">添加步骤</el-button>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave">{{ editingId === null ? "创建" : "保存" }}</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="previewVisible" title="模板预览" width="700px" destroy-on-close>
      <template v-if="previewTemplate">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="名称">{{ previewTemplate.name }}</el-descriptions-item>
          <el-descriptions-item label="版本">{{ previewTemplate.version }}</el-descriptions-item>
          <el-descriptions-item label="产品型号">
            {{ previewTemplate.product_model || "—" }}
          </el-descriptions-item>
          <el-descriptions-item label="描述">{{ previewTemplate.description || "—" }}</el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">步骤</el-divider>
        <el-timeline v-if="previewSteps.length > 0">
          <el-timeline-item
            v-for="(step, idx) in previewSteps"
            :key="idx"
            :timestamp="`步骤 ${idx + 1}`"
            placement="top"
          >
            <el-card shadow="never" class="preview-step-card">
              <div class="preview-step-title">
                {{ step.name || "（未命名）" }}
                <el-tag v-if="step.is_optional" size="small" type="info">可选</el-tag>
              </div>
              <p v-if="step.description" class="preview-desc">{{ step.description }}</p>
              <el-descriptions :column="1" size="small" class="preview-meta">
                <el-descriptions-item v-if="step.action_type" label="动作类型">
                  {{ step.action_type }}
                </el-descriptions-item>
                <el-descriptions-item label="超时">
                  {{ step.timeout_seconds }} 秒
                </el-descriptions-item>
              </el-descriptions>
              <div v-if="step.required_objects.length > 0" class="preview-tags">
                <span class="preview-tags-label">必需对象：</span>
                <el-tag
                  v-for="(tag, tidx) in step.required_objects"
                  :key="tidx"
                  size="small"
                  class="preview-tag"
                >
                  {{ tag }}
                </el-tag>
              </div>
            </el-card>
          </el-timeline-item>
        </el-timeline>
        <el-empty v-else description="暂无步骤" />
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.steps-empty {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin-bottom: 12px;
}

.step-card {
  margin-bottom: 12px;
  border: 1px solid var(--el-border-color-lighter);
}

.step-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.step-index {
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.step-card-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.add-step-btn {
  width: 100%;
  margin-top: 4px;
}

.preview-step-card {
  border: 1px solid var(--el-border-color-lighter);
}

.preview-step-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  margin-bottom: 8px;
}

.preview-desc {
  margin: 0 0 8px;
  color: var(--el-text-color-regular);
  font-size: 13px;
  line-height: 1.5;
}

.preview-meta {
  margin-top: 4px;
}

.preview-tags {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.preview-tags-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.preview-tag {
  margin-right: 0;
}
</style>
