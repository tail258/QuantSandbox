<template>
  <div class="detail-container">
    <div class="header">
      <el-button @click="goBack" type="info" plain icon="ArrowLeft">返回总览</el-button>
      <h2 class="ticker-title">标的详情: {{ ticker }}</h2>
      <div class="time-controls">
        <span class="progress-text">推演进度: {{ visibleCount }} / {{ totalDays }} 天</span>
        <el-button-group>
          <el-button type="warning" plain icon="RefreshLeft" @click="resetPlayback" :disabled="loading">重置</el-button>
          <el-button type="success" icon="VideoPlay" @click="stepForward" :disabled="loading || isFinished">
            推演 30 天 ⏩
          </el-button>
          <el-button type="primary" plain icon="FastForward" @click="showAll" :disabled="loading || isFinished">揭晓全部</el-button>
        </el-button-group>
      </div>
    </div>

    <div class="stats-panel" v-if="metadata.total_return !== undefined" v-loading="loading">
      <div class="stat-box"><div class="stat-label">期末净值</div><div class="stat-value" :class="metadata.final_equity >= metadata.initial_cash ? 'red' : 'green'">¥{{ metadata.final_equity }}</div></div>
      <div class="stat-box"><div class="stat-label">累计收益率</div><div class="stat-value" :class="metadata.total_return >= 0 ? 'red' : 'green'">{{ metadata.total_return }}%</div></div>
      <div class="stat-box"><div class="stat-label">最大回撤</div><div class="stat-value green">{{ metadata.max_drawdown }}%</div></div>
      <div class="stat-box"><div class="stat-label">夏普比率</div><div class="stat-value">{{ metadata.sharpe_ratio }}</div></div>
      <div class="stat-box"><div class="stat-label">交易胜率</div><div class="stat-value">{{ metadata.win_rate }}%</div></div>
      <div class="stat-box"><div class="stat-label">盈亏比</div><div class="stat-value">{{ metadata.pnl_ratio }}</div></div>
    </div>

    <div class="charts-wrapper" v-loading="loading">
      <div ref="klineChartRef" class="main-chart"></div>
      <div ref="equityChartRef" class="sub-chart"></div>
    </div>

    <div class="logs-wrapper" v-loading="loading">
      <h3 class="logs-title">📝 已触发交易日志 ({{ visibleLogs.length }} 笔操作)</h3>
      <el-table :data="visibleLogs" style="width: 100%" height="250" class="dark-table" size="small">
        <el-table-column prop="timestamp" label="交易时间" width="120" />
        <el-table-column prop="action" label="动作" width="80">
          <template #default="scope">
            <span :class="scope.row.action === '买入' ? 'text-red' : 'text-green'">{{ scope.row.action }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="price" label="成交价" />
        <el-table-column prop="shares" label="股数" />
        <el-table-column prop="fee" label="摩擦成本" />
        <el-table-column prop="reason" label="触发原因" />
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick, computed } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { getStockDetail } from '../api';
import { createChart } from 'lightweight-charts';
import { ElMessage } from 'element-plus';

const props = defineProps(['ticker']);
const router = useRouter();
const route = useRoute();

const loading = ref(true);
const metadata = ref({});

// 🌟 核心引擎内存：存放后端的全量数据
let fullKlineData = [];
let fullEquityData = [];
let fullMarkers = [];
let fullLogs = [];

// 🌟 时空游标：当前展示的数据量
const visibleCount = ref(0);
const totalDays = ref(0);
const visibleLogs = ref([]); // 动态显示的日志
const isFinished = computed(() => visibleCount.value >= totalDays.value);

const klineChartRef = ref(null);
const equityChartRef = ref(null);
let klineChart = null;
let equityChart = null;
let candlestickSeries = null;
let areaSeries = null;

const goBack = () => router.push('/');

const darkThemeOptions = {
  layout: { background: { color: '#131722' }, textColor: '#d1d4dc' },
  grid: { vertLines: { color: '#2B3139' }, horzLines: { color: '#2B3139' } },
  timeScale: { timeVisible: true, borderColor: '#2B3139' },
  rightPriceScale: { borderColor: '#2B3139' }
};

// 🌟 数据切片渲染引擎
const renderSlice = () => {
  if (!candlestickSeries || !areaSeries) return;

  // 1. 切割图表数据
  const currentKlines = fullKlineData.slice(0, visibleCount.value);
  const currentEquity = fullEquityData.slice(0, visibleCount.value);
  
  // 2. 切割 Markers（只显示在当前时间轴内的箭头）
  if (currentKlines.length > 0) {
    const lastVisibleDate = new Date(currentKlines[currentKlines.length - 1].time).getTime();
    const currentMarkers = fullMarkers.filter(m => new Date(m.time).getTime() <= lastVisibleDate);
    candlestickSeries.setMarkers(currentMarkers);
    
    // 3. 动态更新日志表格
    visibleLogs.value = fullLogs.filter(log => new Date(log.timestamp).getTime() <= lastVisibleDate);
  }

  // 4. 将切片推入图表
  candlestickSeries.setData(currentKlines);
  areaSeries.setData(currentEquity);

  // 5. 让时间轴自动跟随最新的一根 K 线
  klineChart.timeScale().fitContent();
};

// 🌟 交互控制器
const stepForward = () => {
  visibleCount.value = Math.min(visibleCount.value + 30, totalDays.value);
  renderSlice();
};

const showAll = () => {
  visibleCount.value = totalDays.value;
  renderSlice();
};

const resetPlayback = () => {
  visibleCount.value = Math.min(60, totalDays.value); // 重置时默认显示前 60 天建仓期
  renderSlice();
};

const initChartAndData = async () => {
  try {
    const start = route.query.start || '20240101';
    const end = route.query.end || '20240131';
    
    const res = await getStockDetail(props.ticker, start, end);
    const data = res.data;
    metadata.value = data.metadata;
    fullLogs = data.logs;

    const seenDates = new Set();
    data.klines.forEach(item => {
      if (item.date && !seenDates.has(item.date)) {
        seenDates.add(item.date);
        fullKlineData.push({ time: item.date, open: Number(item.open), high: Number(item.high), low: Number(item.low), close: Number(item.close) });
        fullEquityData.push({ time: item.date, value: Number(item.total_equity) });
      }
    });

    data.logs.forEach(log => {
      if (seenDates.has(log.timestamp)) {
        fullMarkers.push({
          time: log.timestamp, position: log.action === '买入' ? 'belowBar' : 'aboveBar',
          color: log.action === '买入' ? '#F6465D' : '#0ECB81', shape: log.action === '买入' ? 'arrowUp' : 'arrowDown',
          text: log.action === '买入' ? '买入' : '卖出',
        });
      }
    });

    fullKlineData.sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime());
    fullEquityData.sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime());
    fullMarkers.sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime());

    totalDays.value = fullKlineData.length;
    visibleCount.value = Math.min(60, totalDays.value); // 初始加载前 60 天的数据

    await nextTick();
    
    klineChart = createChart(klineChartRef.value, { ...darkThemeOptions, width: klineChartRef.value.clientWidth, height: 400 });
    candlestickSeries = klineChart.addCandlestickSeries({ upColor: '#F6465D', downColor: '#0ECB81', borderVisible: false, wickUpColor: '#F6465D', wickDownColor: '#0ECB81' });

    equityChart = createChart(equityChartRef.value, { ...darkThemeOptions, width: equityChartRef.value.clientWidth, height: 200 });
    areaSeries = equityChart.addAreaSeries({ topColor: 'rgba(245, 158, 11, 0.4)', bottomColor: 'rgba(245, 158, 11, 0.0)', lineColor: '#f59e0b', lineWidth: 2 });

    klineChart.timeScale().subscribeVisibleLogicalRangeChange(timeRange => {
      if (timeRange) equityChart.timeScale().setVisibleLogicalRange(timeRange);
    });
    equityChart.timeScale().subscribeVisibleLogicalRangeChange(timeRange => {
      if (timeRange) klineChart.timeScale().setVisibleLogicalRange(timeRange);
    });

    // 首次渲染切片
    renderSlice();

  } catch (error) {
    ElMessage.error('图表渲染失败，请检查控制台报错');
    console.error(error);
  } finally {
    loading.value = false;
  }
};

onMounted(() => initChartAndData());

onUnmounted(() => {
  if (klineChart) klineChart.remove();
  if (equityChart) equityChart.remove();
});
</script>

<style scoped>
/* 样式新增了时空控制台的排版，其余保持不变 */
.detail-container { background-color: #0b0e14; min-height: 100vh; padding: 20px; color: #d1d4dc; }
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; flex-wrap: wrap; gap: 15px;}
.ticker-title { margin: 0; color: #fff; font-size: 24px;}
.time-controls { display: flex; align-items: center; gap: 15px; background: #131722; padding: 5px 15px; border-radius: 8px; border: 1px solid #2B3139;}
.progress-text { font-size: 14px; font-weight: bold; color: #f59e0b; }
.stats-panel { display: flex; flex-wrap: wrap; gap: 15px; background-color: #131722; padding: 15px; border-radius: 8px; margin-bottom: 20px; border: 1px solid #2B3139; }
.stat-box { flex: 1; min-width: 120px; display: flex; flex-direction: column; align-items: center; justify-content: center;}
.stat-label { font-size: 12px; color: #8a919e; margin-bottom: 5px; }
.stat-value { font-size: 18px; font-weight: bold; color: #fff; }
.charts-wrapper { background-color: #131722; border: 1px solid #2B3139; border-radius: 8px; padding: 10px; margin-bottom: 20px; }
.main-chart { width: 100%; border-bottom: 1px solid #2B3139; margin-bottom: 10px; padding-bottom: 10px;}
.sub-chart { width: 100%; }
.logs-wrapper { background-color: #131722; border-radius: 8px; padding: 15px; border: 1px solid #2B3139;}
.logs-title { margin-top: 0; margin-bottom: 15px; font-size: 16px; color: #fff; }
.red { color: #F6465D !important; }
.green { color: #0ECB81 !important; }
.text-red { color: #F6465D; font-weight: bold; }
.text-green { color: #0ECB81; font-weight: bold; }
:deep(.el-table) { background-color: transparent !important; --el-table-border-color: #2B3139; --el-table-header-bg-color: #1a1e29; --el-table-tr-bg-color: #131722; --el-table-text-color: #d1d4dc; --el-table-header-text-color: #8a919e;}
:deep(.el-table th.el-table__cell), :deep(.el-table td.el-table__cell) { border-bottom: 1px solid #2B3139; }
:deep(.el-table--striped .el-table__body tr.el-table__row--striped td.el-table__cell) { background-color: #1a1e29; }
</style>