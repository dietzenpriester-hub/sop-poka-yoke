<script setup lang="ts">
import { ref, onMounted } from "vue";
import { ElMessage } from "element-plus";
import api from "@/api/index";
import { parseErrorMsg } from "@/utils/httpError";

const loading = ref(false);
const testing = ref(false);

const config = ref({
  webhook_url: "",
  enabled: true,
  min_severity: "WARN",
});

async function loadConfig() {
  loading.value = true;
  try {
    const { data } = await api.get("/notification/config");
    config.value = data;
  } catch (e) {
    ElMessage.error(parseErrorMsg(e, "加载配置失败"));
  } finally {
    loading.value = false;
  }
}

async function saveConfig() {
  loading.value = true;
  try {
    await api.put("/notification/config", config.value);
    ElMessage.success("通知配置已保存");
  } catch (e) {
    ElMessage.error(parseErrorMsg(e, "保存失败"));
  } finally {
    loading.value = false;
  }
}

async function testNotification() {
  testing.value = true;
  try {
    const { data } = await api.post("/notification/test");
    if (data.success) {
      ElMessage.success("测试消息发送成功，请在飞书查看");
    } else {
      ElMessage.error(data.error || "发送失败");
    }
  } catch (e) {
    ElMessage.error(parseErrorMsg(e, "测试失败"));
  } finally {
    testing.value = false;
  }
}

onMounted(loadConfig);
</script>

<template>
  <div>
    <div class="page-header">
      <h2>通知配置</h2>
    </div>

    <el-card v-loading="loading">
      <template #header>
        <div style="display: flex; align-items: center; gap: 8px">
          <img
            src="https://sf3-scmcdn-cn.feishucdn.com/ccm/pc/web/resource/bear/src/assets/lark-icon.svg"
            alt="飞书"
            style="width: 24px; height: 24px"
            onerror="this.style.display='none'"
          />
          <span style="font-weight: 600">飞书机器人通知</span>
        </div>
      </template>

      <el-form label-width="120px" style="max-width: 600px">
        <el-form-item label="启用通知">
          <el-switch v-model="config.enabled" />
        </el-form-item>

        <el-form-item label="Webhook URL">
          <el-input
            v-model="config.webhook_url"
            placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
            clearable
          />
          <div style="color: #909399; font-size: 12px; margin-top: 4px; line-height: 1.6">
            在飞书群 → 设置 → 群机器人 → 自定义机器人 → 获取 Webhook URL
          </div>
        </el-form-item>

        <el-form-item label="最低推送级别">
          <el-radio-group v-model="config.min_severity">
            <el-radio value="INFO">全部（含信息）</el-radio>
            <el-radio value="WARN">警告及以上</el-radio>
            <el-radio value="CRITICAL">仅严重</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="saveConfig" :loading="loading">
            保存配置
          </el-button>
          <el-button
            @click="testNotification"
            :loading="testing"
            :disabled="!config.webhook_url"
          >
            发送测试消息
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card style="margin-top: 16px">
      <template #header>
        <span style="font-weight: 600">使用说明</span>
      </template>
      <div style="line-height: 2; color: #606266; font-size: 14px">
        <p><strong>1. 创建飞书机器人</strong></p>
        <p style="padding-left: 16px">打开飞书群 → 设置 → 群机器人 → 添加机器人 → 自定义机器人</p>
        <p><strong>2. 复制 Webhook URL</strong></p>
        <p style="padding-left: 16px">创建后会显示 Webhook 地址，复制粘贴到上方输入框</p>
        <p><strong>3. 配置推送级别</strong></p>
        <p style="padding-left: 16px">
          <el-tag size="small" type="info" style="margin-right: 4px">信息</el-tag>
          所有告警都推送 ·
          <el-tag size="small" type="warning" style="margin-right: 4px">警告</el-tag>
          推送警告和严重 ·
          <el-tag size="small" type="danger">严重</el-tag>
          仅推送严重告警
        </p>
        <p><strong>4. 告警消息示例</strong></p>
        <p style="padding-left: 16px">当系统检测到异常时，飞书群将收到包含告警类型、工位、严重级别等信息的卡片消息</p>
      </div>
    </el-card>
  </div>
</template>
