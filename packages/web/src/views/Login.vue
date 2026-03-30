<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { User, Lock } from "@element-plus/icons-vue";
import axios from "axios";
import api from "@/api/index";
import { useAuthStore } from "@/stores/auth";
import { parseErrorMsg } from "@/utils/httpError";

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
  } catch (e) {
    if (axios.isAxiosError(e) && !e.response) {
      ElMessage.error("网络连接失败，请检查后端服务");
    } else {
      ElMessage.error(parseErrorMsg(e, "用户名或密码错误"));
    }
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-bg-pattern" />

    <div class="login-container">
      <div class="login-brand">
        <div class="login-logo-text">
          <span class="logo-thunder">Thunder</span><span class="logo-comm">comm</span>
        </div>
        <h1 class="login-title">SOP 防呆系统</h1>
        <p class="login-subtitle">智能作业防错 · AI 视觉引导</p>
      </div>

      <el-card class="login-card" shadow="never">
        <h2 class="login-card-title">欢迎登录</h2>
        <el-form :model="form" @submit.prevent="handleLogin" size="large">
          <el-form-item>
            <el-input
              v-model="form.username"
              placeholder="用户名"
              :prefix-icon="User"
              clearable
            />
          </el-form-item>
          <el-form-item>
            <el-input
              v-model="form.password"
              type="password"
              placeholder="密码"
              :prefix-icon="Lock"
              show-password
            />
          </el-form-item>
          <el-form-item style="margin-bottom: 0">
            <el-button
              type="primary"
              class="login-btn"
              :loading="loading"
              native-type="submit"
            >
              {{ loading ? "登录中..." : "登 录" }}
            </el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <p class="login-footer">Thundercomm SOP Poka-Yoke v1.0.0</p>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0c2135 0%, #143a5c 40%, #1a5276 70%, #1e6f9f 100%);
  position: relative;
  overflow: hidden;
}

.login-bg-pattern {
  position: absolute;
  inset: 0;
  background-image:
    radial-gradient(circle at 20% 80%, rgba(64, 158, 255, 0.12) 0%, transparent 50%),
    radial-gradient(circle at 80% 20%, rgba(103, 194, 58, 0.08) 0%, transparent 50%),
    radial-gradient(circle at 50% 50%, rgba(255, 255, 255, 0.02) 0%, transparent 70%);
  animation: bgShift 20s ease-in-out infinite alternate;
}

@keyframes bgShift {
  0% { opacity: 0.6; }
  100% { opacity: 1; }
}

.login-container {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  animation: fadeUp 0.6s ease-out;
}

@keyframes fadeUp {
  from {
    opacity: 0;
    transform: translateY(24px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.login-brand {
  text-align: center;
  margin-bottom: 32px;
}

.login-logo-text {
  font-size: 38px;
  letter-spacing: 1px;
  margin-bottom: 16px;
  filter: drop-shadow(0 2px 8px rgba(227, 27, 35, 0.25));
}

.logo-thunder {
  font-weight: 700;
  color: #e31b23;
  font-style: italic;
}

.logo-comm {
  font-weight: 400;
  color: #e31b23;
}

.login-title {
  font-size: 28px;
  font-weight: 700;
  color: #ffffff;
  margin: 0;
  letter-spacing: 2px;
}

.login-subtitle {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.55);
  margin: 8px 0 0;
  letter-spacing: 1px;
}

.login-card {
  width: 400px;
  max-width: 92vw;
  border-radius: 16px !important;
  border: 1px solid rgba(255, 255, 255, 0.08) !important;
  background: rgba(255, 255, 255, 0.95) !important;
  backdrop-filter: blur(12px);
  box-shadow:
    0 8px 32px rgba(0, 0, 0, 0.2),
    0 0 0 1px rgba(255, 255, 255, 0.05);
}

.login-card :deep(.el-card__body) {
  padding: 36px 32px;
}

.login-card-title {
  font-size: 20px;
  font-weight: 600;
  color: #1d2129;
  text-align: center;
  margin: 0 0 28px;
}

.login-card :deep(.el-input__wrapper) {
  border-radius: 10px;
  padding: 4px 12px;
  box-shadow: 0 0 0 1px #dcdfe6 inset;
  transition: box-shadow 0.25s;
}

.login-card :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px #c0c4cc inset;
}

.login-card :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 2px var(--sop-primary) inset;
}

.login-btn {
  width: 100%;
  height: 44px;
  border-radius: 10px;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 4px;
  background: linear-gradient(135deg, var(--sop-primary) 0%, var(--sop-primary-dark) 100%);
  border: none;
  transition: transform 0.2s, box-shadow 0.2s;
}

.login-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 16px rgba(64, 158, 255, 0.4);
}

.login-btn:active {
  transform: translateY(0);
}

.login-footer {
  margin-top: 24px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.3);
  letter-spacing: 0.5px;
}

@media (max-width: 480px) {
  .login-title { font-size: 22px; }
  .login-card :deep(.el-card__body) { padding: 28px 20px; }
}
</style>
