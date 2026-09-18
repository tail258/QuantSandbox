<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  AreaSeries,
  CandlestickSeries,
  ColorType,
  LineSeries,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type Time,
} from 'lightweight-charts'
import type { Bar, EquityPoint, Trade } from '../types'
import { number } from '../utils/format'
const props = defineProps<{
  bars: Bar[]
  series: EquityPoint[]
  trades: Trade[]
  initialCash: number
  fastPeriod: number
  slowPeriod: number
  selectedDate?: string
}>()
const emit = defineEmits<{ select: [date: string] }>()
const priceElement = ref<HTMLElement>(),
  equityElement = ref<HTMLElement>()
let priceChart: IChartApi,
  equityChart: IChartApi,
  candle: ISeriesApi<'Candlestick'>,
  fast: ISeriesApi<'Line'>,
  slow: ISeriesApi<'Line'>,
  net: ISeriesApi<'Area'>,
  markers: ISeriesMarkersPluginApi<Time>
let observer: ResizeObserver,
  syncing = false
let compactViewport: boolean | null = null
let selectionFrame = 0
const indicator = (key: 'fast_ma' | 'slow_ma') =>
  props.bars
    .filter((bar) => bar[key] != null && Number.isFinite(bar[key]))
    .map((bar) => ({ time: bar.date, value: bar[key]! }))
const fastData = computed(() => indicator('fast_ma')),
  slowData = computed(() => indicator('slow_ma'))
const latest = computed(() => props.bars.at(-1))
function focusSelection() {
  if (!priceChart || !props.selectedDate) return
  const bar = props.bars.find((item) => item.date === props.selectedDate)
  const point = props.series.find((item) => item.date === props.selectedDate)
  if (bar) priceChart.setCrosshairPosition(bar.close, bar.date, candle)
  if (point) equityChart.setCrosshairPosition(point.equity / props.initialCash, point.date, net)
}
function scheduleSelection() {
  window.cancelAnimationFrame(selectionFrame)
  // Chart dimensions and time ranges settle during the library's next paint.
  selectionFrame = window.requestAnimationFrame(() => {
    selectionFrame = window.requestAnimationFrame(focusSelection)
  })
}
function updateMarkers() {
  markers?.setMarkers(
    props.trades.map((trade) => ({
      time: trade.date,
      position: trade.action === 'buy' ? ('belowBar' as const) : ('aboveBar' as const),
      color: trade.action === 'buy' ? '#8ea9ff' : '#ba99ec',
      shape: 'circle' as const,
      text: trade.date === props.selectedDate ? (trade.action === 'buy' ? 'B' : 'S') : '',
      size: trade.date === props.selectedDate ? 1.2 : 0.5,
    })),
  )
}
function render() {
  if (!priceChart) return
  syncing = true
  try {
    candle.setData(
      props.bars.map((bar) => ({
        time: bar.date,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
      })),
    )
    fast.setData(fastData.value)
    slow.setData(slowData.value)
    net.setData(
      props.series.map((point) => ({ time: point.date, value: point.equity / props.initialCash })),
    )
    updateMarkers()
    priceChart.timeScale().fitContent()
    equityChart.timeScale().fitContent()
  } finally {
    syncing = false
  }
  scheduleSelection()
}
onMounted(() => {
  const shared = {
    layout: {
      background: { type: ColorType.Solid, color: '#191d25' },
      textColor: '#8893a7',
      fontSize: 11,
      fontFamily: 'Inter, "Segoe UI", sans-serif',
    },
    grid: { vertLines: { color: '#242a3455' }, horzLines: { color: '#242a34' } },
    rightPriceScale: { borderColor: '#323947', minimumWidth: 64 },
    timeScale: { borderColor: '#323947', rightOffset: 2, fixLeftEdge: true, barSpacing: 6 },
    crosshair: {
      vertLine: { color: '#8ea9ff88', labelBackgroundColor: '#4c629e' },
      horzLine: { color: '#8ea9ff66', labelBackgroundColor: '#4c629e' },
    },
  }
  priceChart = createChart(priceElement.value!, {
    ...shared,
    height: 240,
    timeScale: { ...shared.timeScale, visible: false },
  })
  equityChart = createChart(equityElement.value!, { ...shared, height: 110 })
  candle = priceChart.addSeries(CandlestickSeries, {
    upColor: '#ec7682',
    downColor: '#60c4a4',
    wickUpColor: '#ec7682',
    wickDownColor: '#60c4a4',
    borderVisible: false,
    priceLineVisible: true,
  })
  fast = priceChart.addSeries(LineSeries, {
    color: '#8ea9ff',
    lineWidth: 1,
    priceLineVisible: false,
    lastValueVisible: false,
    crosshairMarkerVisible: false,
  })
  slow = priceChart.addSeries(LineSeries, {
    color: '#d8b869',
    lineWidth: 1,
    priceLineVisible: false,
    lastValueVisible: false,
    crosshairMarkerVisible: false,
  })
  net = equityChart.addSeries(AreaSeries, {
    lineColor: '#8ea9ff',
    topColor: '#8ea9ff29',
    bottomColor: '#8ea9ff00',
    lineWidth: 2,
    priceLineVisible: false,
    priceFormat: { type: 'price', precision: 3, minMove: 0.001 },
  })
  markers = createSeriesMarkers(candle, [])
  const synchronize = (from: IChartApi, to: IChartApi) =>
    from.timeScale().subscribeVisibleTimeRangeChange((range) => {
      if (!range || syncing || !candle?.data().length || !net?.data().length) return
      syncing = true
      try {
        to.timeScale().setVisibleRange(range)
      } finally {
        syncing = false
      }
    })
  synchronize(priceChart, equityChart)
  synchronize(equityChart, priceChart)
  priceChart.subscribeClick((event) => {
    if (!event.time) return
    const time = event.time
    const date =
      typeof time === 'string'
        ? time
        : typeof time === 'number'
          ? new Date(time * 1000).toISOString().slice(0, 10)
          : `${time.year}-${String(time.month).padStart(2, '0')}-${String(time.day).padStart(2, '0')}`
    emit('select', date)
  })
  observer = new ResizeObserver(() => {
    const compact = window.matchMedia('(max-width: 600px)').matches
    const shouldFit = compactViewport === null || compactViewport !== compact
    compactViewport = compact
    syncing = true
    try {
      if (priceElement.value) priceChart.applyOptions({ width: priceElement.value.clientWidth })
      if (equityElement.value) equityChart.applyOptions({ width: equityElement.value.clientWidth })
      if (shouldFit) {
        priceChart.timeScale().fitContent()
        equityChart.timeScale().fitContent()
      }
    } finally {
      syncing = false
    }
    scheduleSelection()
  })
  observer.observe(priceElement.value!)
  observer.observe(equityElement.value!)
  render()
})
watch(() => [props.bars, props.series, props.trades, props.fastPeriod, props.slowPeriod], render)
watch(
  () => props.selectedDate,
  () => {
    updateMarkers()
    scheduleSelection()
  },
)
onUnmounted(() => {
  window.cancelAnimationFrame(selectionFrame)
  observer?.disconnect()
  priceChart?.remove()
  equityChart?.remove()
})
</script>

<template>
  <div class="market-charts">
    <div class="chart-legend">
      <span v-if="fastData.length"
        ><i class="legend-line blue" />MA{{ fastPeriod }}
        <b>{{ number(fastData.at(-1)?.value) }}</b></span
      ><span v-if="slowData.length"
        ><i class="legend-line gold" />MA{{ slowPeriod }}
        <b>{{ number(slowData.at(-1)?.value) }}</b></span
      ><span class="ohlc">收 {{ number(latest?.close) }}</span>
    </div>
    <div
      ref="priceElement"
      class="price-chart"
      role="img"
      :aria-label="`价格图，共 ${bars.length} 个交易日`"
    />
    <div class="equity-caption">
      策略净值 <b>{{ number((series.at(-1)?.equity || initialCash) / initialCash, 4) }}</b>
    </div>
    <div ref="equityElement" class="equity-chart" role="img" aria-label="策略净值走势" />
  </div>
</template>
