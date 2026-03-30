<script setup lang="ts">
function handleRetry() {
  window.location.reload();
}
</script>

<template>
  <div class="error-page">
    <div class="error-content">
      <div class="error-icon">⚠️</div>
      <h2 class="error-title">服务连接异常</h2>
      <p class="error-desc">
        无法连接到服务器，请检查网络连接或联系系统管理员。
      </p>
      <div class="error-actions">
        <el-button type="primary" size="large" @click="handleRetry">
          重新连接
        </el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.error-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 80vh;
  text-align: center;
}

.error-icon {
  font-size: 80px;
  margin-bottom: 16px;
}

.error-title {
  font-size: 24px;
  color: #303133;
  margin: 0 0 12px;
}

.error-desc {
  font-size: 15px;
  color: #909399;
  margin: 0 0 32px;
  max-width: 400px;
}

.error-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}
</style>
