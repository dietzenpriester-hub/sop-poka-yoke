<script setup lang="ts">
import { ref, onMounted, watch, nextTick } from "vue";
import { ElMessage } from "element-plus";
import { useECharts } from "@/composables/useECharts";
import { overrideLogApi, type OverrideLogItem, type OverrideStats } from "@/api/overrideLog";
import { parseErrorMsg } from "@/utils/httpError";
import { formatDateTime } from "@/utils/date";

const stats = ref<OverrideStats | null>(null);
const statsLoading = ref(false);
const rows = ref<OverrideLogItem[]>([]);
const total = ref(0);
const listLoading = ref(false);

const filters = ref({
  workorder_id: null as number | null,
  operator_badge: "",
  dateRange: null as [string, string] | null,
});

const page = ref(1);
const pageSize = ref(20);

const { chartRef: trendChartRef, setOption: setTrendOption, resize } = useECharts();

function applyTrendChart() {
  const s = stats.value;
  if (!s?.daily_counts?.length) return;
  setTrendOption({
    title: { text: "近 30 日每日放行次数", left: "center" },
    tooltip: { trigger: "axis" },
    grid: { left: 50, right: 24, bottom: 48, top: 48 },
    xAxis: {
      type: "category",
      data: s.daily_counts.map((d) => d.date),
      axisLabel: { rotate: 35, fontSize: 11 },
    },
    yAxis: { type: "value", name: "次数" },
    series: [
      {
        name: "放行次数",
        type: "bar",
        data: s.daily_counts.map((d) => d.count),
        itemStyle: { color: "#e6a23c" },
      },
    ],
  });
  nextTick(() => resize());
}

async function loadStats() {
  statsLoading.value = true;
  try {
    const { data } = await overrideLogApi.stats();
    stats.value = data;
    nextTick(() => applyTrendChart());
  } catch (e) {
    ElMessage.error(parseErrorMsg(e, "加载统计数据失败"));
    stats.value = null;
  } finally {
    statsLoading.value = false;
  }
}

async function loadList() {
  listLoading.value = true;
  try {
    const skip = (page.value - 1) * pageSize.value;
    const params: Record<string, unknown> = { skip, limit: pageSize.value };
    if (filters.value.workorder_id != null) params.workorder_id = filters.value.workorder_id;
    if (filters.value.operator_badge) params.operator_badge = filters.value.operator_badge.trim();
    if (filters.value.dateRange?.length === 2) {
      params.start_date = filters.value.dateRange[0];
      params.end_date = filters.value.dateRange[1];
    }
    const { data } = await overrideLogApi.list(
      params as Parameters<typeof overrideLogApi.list>[0]
    );
    rows.value = data.items;
    total.value = data.total;
  } catch (e) {
    ElMessage.error(parseErrorMsg(e, "加载放行记录失败"));
  } finally {
    listLoading.value = false;
  }
}

function handleSearch() {
  page.value = 1;
  loadList();
}

function handleReset() {
  filters.value = { workorder_id: null, operator_badge: "", dateRange: null };
  page.value = 1;
  loadList();
}

function handlePageSizeChange() {
  page.value = 1;
  loadList();
}

watch(stats, () => nextTick(() => applyTrendChart()));

onMounted(() => {
  loadStats();
  loadList();
});
</script>

<template>
  <div>
    <el-alert
      type="warning"
      show-icon
      :closable="false"
      title="强制放行审计"
      description="本页记录工牌强制放行操作，含敏感审计数据，仅管理员可访问。"
      style="margin-bottom: 16px"
    />

    <div style="display: flex; justify-content: space-between; align-items: center">
      <h2 style="margin: 0">强制放行审计</h2>
      <el-button type="primary" :loading="statsLoading || listLoading" @click="loadStats(); loadList()">
        刷新
      </el-button>
    </div>

    <!-- 统计 -->
    <el-row :gutter="16" style="margin-top: 16px" v-loading="statsLoading">
      <el-col :xs="24" :md="6">
        <el-card shadow="hover">
          <template #header>总放行次数</template>
          <div style="font-size: 32px; font-weight: bold; color: #e6a23c">
            {{ stats?.total ?? 0 }}
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :md="12">
        <el-card shadow="hover">
          <template #header>趋势（近 30 天）</template>
          <div ref="trendChartRef" style="height: 320px; width: 100%" />
        </el-card>
      </el-col>
      <el-col :xs="24" :md="6">
        <el-card shadow="hover">
          <template #header>高频放行操作员</template>
          <el-table :data="stats?.top_operators ?? []" size="small" max-height="260">
            <el-table-column prop="badge" label="工牌" show-overflow-tooltip />
            <el-table-column prop="count" label="次数" width="70" />
          </el-table>
          <div v-if="!(stats?.top_operators?.length)" style="color: #909399; padding: 8px 0">
            暂无数据
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 筛选 -->
    <el-card shadow="never" style="margin-top: 16px">
      <el-form :inline="true" @submit.prevent="handleSearch">
        <el-form-item label="工单 ID">
          <el-input-number v-model="filters.workorder_id" :min="1" :controls="false" placeholder="工单 ID" clearable style="width: 140px" />
        </el-form-item>
        <el-form-item label="操作员工牌">
          <el-input v-model="filters.operator_badge" clearable placeholder="工牌号" style="width: 160px" />
        </el-form-item>
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="filters.dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="YYYY-MM-DD"
            clearable
            style="width: 280px"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 表格 -->
    <el-table :data="rows" v-loading="listLoading" style="margin-top: 16px" border>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="workorder_id" label="工单 ID" width="100" />
      <el-table-column prop="step_index" label="步骤序号" width="100" />
      <el-table-column prop="operator_badge" label="操作员工牌" width="120" />
      <el-table-column prop="reason" label="放行原因" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          <el-tooltip v-if="row.reason" :content="row.reason" placement="top">
            <span>{{ row.reason }}</span>
          </el-tooltip>
          <span v-else style="color: #c0c4cc">—</span>
        </template>
      </el-table-column>
      <el-table-column label="视频" width="100">
        <template #default="{ row }">
          <el-link
            v-if="row.video_url && (row.video_url.startsWith('http://') || row.video_url.startsWith('https://'))"
            :href="row.video_url"
            target="_blank"
            type="primary"
          >查看</el-link>
          <span v-else style="color: #c0c4cc">—</span>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="时间" width="180">
        <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
      </el-table-column>
    </el-table>

    <div style="margin-top: 16px; display: flex; justify-content: flex-end">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        background
        @current-change="loadList"
        @size-change="handlePageSizeChange"
      />
    </div>
  </div>
</template>
