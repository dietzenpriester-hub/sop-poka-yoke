<script setup lang="ts">
import { ref, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { userApi, type UserItem } from "@/api/user";
import { parseErrorMsg } from "@/utils/httpError";
import { formatDateTime } from "@/utils/date";

const users = ref<UserItem[]>([]);
const loading = ref(false);
const roleFilter = ref("");

const showCreateDialog = ref(false);
const showEditDialog = ref(false);
const showPasswordDialog = ref(false);
const editingUser = ref<UserItem | null>(null);

const createForm = ref({ username: "", display_name: "", role: "operator", badge_id: "", password: "" });
const editForm = ref({ display_name: "", role: "", badge_id: "" });
const passwordForm = ref({ new_password: "" });

async function loadUsers() {
  loading.value = true;
  try {
    const params: Record<string, unknown> = {};
    if (roleFilter.value) params.role = roleFilter.value;
    const { data } = await userApi.list(params as Parameters<typeof userApi.list>[0]);
    users.value = data;
  } catch (e: unknown) {
    ElMessage.error(parseErrorMsg(e, "加载用户列表失败"));
  } finally {
    loading.value = false;
  }
}

async function handleCreate() {
  if (!createForm.value.username || !createForm.value.password) {
    ElMessage.warning("请填写用户名和密码");
    return;
  }
  try {
    await userApi.create(createForm.value);
    ElMessage.success("用户已创建");
    showCreateDialog.value = false;
    createForm.value = { username: "", display_name: "", role: "operator", badge_id: "", password: "" };
    loadUsers();
  } catch (e: unknown) {
    ElMessage.error(parseErrorMsg(e, "创建失败"));
  }
}

function openEdit(user: UserItem) {
  editingUser.value = user;
  editForm.value = { display_name: user.display_name, role: user.role, badge_id: user.badge_id };
  showEditDialog.value = true;
}

async function handleUpdate() {
  if (!editingUser.value) return;
  try {
    await userApi.update(editingUser.value.id, editForm.value);
    ElMessage.success("用户信息已更新");
    showEditDialog.value = false;
    loadUsers();
  } catch (e: unknown) {
    ElMessage.error(parseErrorMsg(e, "更新失败"));
  }
}

function openPasswordChange(user: UserItem) {
  editingUser.value = user;
  passwordForm.value = { new_password: "" };
  showPasswordDialog.value = true;
}

async function handleChangePassword() {
  if (!editingUser.value || !passwordForm.value.new_password) {
    ElMessage.warning("请输入新密码");
    return;
  }
  try {
    await userApi.changePassword(editingUser.value.id, passwordForm.value.new_password);
    ElMessage.success("密码已更新");
    showPasswordDialog.value = false;
  } catch (e: unknown) {
    ElMessage.error(parseErrorMsg(e, "修改密码失败"));
  }
}

async function handleDelete(user: UserItem) {
  try {
    await ElMessageBox.confirm(`确定删除用户「${user.display_name || user.username}」？`, "确认删除", { type: "warning" });
    await userApi.delete(user.id);
    ElMessage.success("用户已删除");
    loadUsers();
  } catch (e: unknown) {
    if (e !== "cancel") ElMessage.error(parseErrorMsg(e, "删除失败"));
  }
}

function roleTagType(role: string): "" | "success" | "warning" | "danger" | "info" {
  switch (role) {
    case "admin": return "danger";
    case "supervisor": return "warning";
    default: return "info";
  }
}

onMounted(() => loadUsers());
</script>

<template>
  <div>
    <div class="page-header">
      <h2>用户管理</h2>
      <div class="page-header-actions">
        <el-select v-model="roleFilter" clearable placeholder="角色筛选" style="width: 120px; margin-right: 8px" @change="loadUsers">
          <el-option label="管理员" value="admin" />
          <el-option label="主管" value="supervisor" />
          <el-option label="操作员" value="operator" />
        </el-select>
        <el-button type="primary" @click="showCreateDialog = true">新增用户</el-button>
      </div>
    </div>

    <div class="data-table">
      <el-table :data="users" v-loading="loading" style="margin-top: 16px">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="username" label="用户名" width="120" />
      <el-table-column prop="display_name" label="姓名" width="120" />
      <el-table-column prop="role" label="角色" width="100">
        <template #default="{ row }">
          <el-tag :type="roleTagType(row.role)" size="small">{{ row.role }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="badge_id" label="工牌号" width="100" />
      <el-table-column prop="created_at" label="创建时间" width="170">
        <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="warning" @click="openPasswordChange(row)">改密</el-button>
          <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    </div>

    <!-- 创建对话框 -->
    <el-dialog v-model="showCreateDialog" title="新增用户" width="480px">
      <el-form :model="createForm" label-width="80px">
        <el-form-item label="用户名"><el-input v-model="createForm.username" /></el-form-item>
        <el-form-item label="姓名"><el-input v-model="createForm.display_name" /></el-form-item>
        <el-form-item label="角色">
          <el-select v-model="createForm.role" style="width: 100%">
            <el-option label="管理员" value="admin" />
            <el-option label="主管" value="supervisor" />
            <el-option label="操作员" value="operator" />
          </el-select>
        </el-form-item>
        <el-form-item label="工牌号"><el-input v-model="createForm.badge_id" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="createForm.password" type="password" show-password /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 编辑对话框 -->
    <el-dialog v-model="showEditDialog" title="编辑用户" width="480px">
      <el-form :model="editForm" label-width="80px">
        <el-form-item label="姓名"><el-input v-model="editForm.display_name" /></el-form-item>
        <el-form-item label="角色">
          <el-select v-model="editForm.role" style="width: 100%">
            <el-option label="管理员" value="admin" />
            <el-option label="主管" value="supervisor" />
            <el-option label="操作员" value="operator" />
          </el-select>
        </el-form-item>
        <el-form-item label="工牌号"><el-input v-model="editForm.badge_id" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" @click="handleUpdate">保存</el-button>
      </template>
    </el-dialog>

    <!-- 修改密码对话框 -->
    <el-dialog v-model="showPasswordDialog" :title="`修改密码 — ${editingUser?.display_name || editingUser?.username}`" width="400px">
      <el-form :model="passwordForm" label-width="80px">
        <el-form-item label="新密码"><el-input v-model="passwordForm.new_password" type="password" show-password /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showPasswordDialog = false">取消</el-button>
        <el-button type="primary" @click="handleChangePassword">确认修改</el-button>
      </template>
    </el-dialog>
  </div>
</template>
