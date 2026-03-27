<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import api from "@/api/index";
import { useAuthStore } from "@/stores/auth";

const router = useRouter();
const authStore = useAuthStore();
const form = ref({ username: "", password: "" });
const loading = ref(false);

async function handleLogin() {
  if (!form.value.username || !form.value.password) {
    ElMessage.warning("请输入用户名和密码");
    return;
  }
  loading.value = true;
  try {
    const { data } = await api.post("/auth/login", form.value);
    if (!data?.access_token) {
      ElMessage.error("登录响应异常");
      return;
    }
    authStore.setToken(data.access_token);
    ElMessage.success("登录成功");
    router.push("/");
  } catch {
    ElMessage.error("用户名或密码错误");
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div style="display: flex; justify-content: center; align-items: center; height: 100vh; background: #f0f2f5">
    <el-card style="width: 400px; padding: 20px">
      <h2 style="text-align: center; margin-bottom: 24px; color: #409eff">SOP 防呆系统</h2>
      <el-form :model="form" @submit.prevent="handleLogin">
        <el-form-item>
          <el-input v-model="form.username" placeholder="用户名" size="large" prefix-icon="User" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="form.password" type="password" placeholder="密码" size="large" prefix-icon="Lock" show-password />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" style="width: 100%" size="large" :loading="loading" native-type="submit">
            登录
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>
