<template>
  <div class="dashboard">
    <el-card class="box-card">
      <template #header>
        <div class="controls">
          <div class="date-picker-group">
            <span class="label">模拟区间:</span>
            <el-date-picker
              v-model="dateRange"
              type="daterange"
              range-separator="至"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              format="YYYY-MM-DD"
              value-format="YYYYMMDD"
              :clearable="false"
            />
          </div>
          <div class="button-group">
            <el-button type="success" @click="advance30Days">前进 30 天 ⏩</el-button>
            <el-button type="primary" :loading="loading" @click="fetchData">执行回测</el-button>
          </div>
        </div>
      </template>

      <el-table :data="tableData" style="width: 100%" v-loading="loading" @row-click="goToDetail" stripe>
        <el-table-column prop="ticker" label="股票代码" width="120" />
        <el-table-column prop="strategy" label="量化策略" />
        <el-table-column prop="final_equity" label="期末净值">
          <template #default="scope">
            <span style="font-weight: bold">{{ scope.row.final_equity }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="return_rate" label="收益率">
          <template #default="scope">
            <span :style="{ color: scope.row.return_rate >= 0 ? '#f56c6c' : '#67c23a' }">
              {{ scope.row.return_rate }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="trade_count" label="交易次数" width="100" />
        <el-table-column label="操作" width="120">
          <template #default>
            <el-button size="small">详情下钻</el-button>
          </template>
        </el-table-column>
      </el-table>
      
      <div class="tip">💡 提示：点击行可进入该股票的详细 K 线回测页面</div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { getSummary } from '../api';
import { ElMessage } from 'element-plus';
import dayjs from 'dayjs';

const router = useRouter();
const dateRange = ref(['20240101', '20240131']); // 默认区间
const loading = ref(false);
const tableData = ref([]);

// 核心逻辑：时间轴一次前进 30 天
const advance30Days = () => {
  const currentEnd = dayjs(dateRange.value[1]);
  // 起始日期变为上次的结束日期 + 1天
  const nextStart = currentEnd.add(1, 'day');
  // 结束日期往后推 30 天
  const nextEnd = nextStart.add(30, 'day');
  
  dateRange.value = [nextStart.format('YYYYMMDD'), nextEnd.format('YYYYMMDD')];
  fetchData(); // 自动触发回测
};

const fetchData = async () => {
  loading.value = true;
  try {
    // 调用 api/index.js 中修改好的方法，并传入日期参数
    const res = await getSummary(dateRange.value[0], dateRange.value[1]);
    
    // 如果该时间段内完全没有符合条件的数据，清空表格
    if (!res.data.data || res.data.data.length === 0) {
      tableData.value = [];
      ElMessage.warning('当前时间区间内数据不足或无交易记录');
    } else {
      tableData.value = res.data.data;
    }
  } catch (error) {
    ElMessage.error('获取后端数据失败，请检查 Python 服务是否运行');
    console.error(error);
  } finally {
    loading.value = false;
  }
};

const goToDetail = (row) => {
  router.push({
    path: `/stock/${row.ticker}`,
    query: { start: dateRange.value[0], end: dateRange.value[1] } // 新增 query 传参
  });
};

onMounted(() => {
  fetchData();
});
</script>

<style scoped>
.dashboard { padding: 20px; max-width: 1000px; margin: 0 auto; }
.controls { display: flex; justify-content: space-between; align-items: center; }
.date-picker-group { display: flex; align-items: center; gap: 10px; }
.label { font-size: 14px; font-weight: bold; color: #606266; }
.button-group { display: flex; gap: 10px; }
.tip { margin-top: 15px; font-size: 13px; color: #909399; text-align: center; }
:deep(.el-table__row) { cursor: pointer; }
</style>