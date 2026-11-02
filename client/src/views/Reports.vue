<template>
  <div class="reports">
    <div class="page-header">
      <h2>{{ t('reports.title') }}</h2>
      <p>{{ t('reports.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('reports.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else-if="quarterlyData.length === 0 && monthlyData.length === 0" class="loading">{{ t('reports.empty') }}</div>
    <div v-else>
      <!-- Quarterly Performance -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('reports.quarterly.title') }}</h3>
        </div>
        <div class="table-container">
          <table class="reports-table">
            <thead>
              <tr>
                <th>{{ t('reports.quarterly.quarter') }}</th>
                <th>{{ t('reports.quarterly.totalOrders') }}</th>
                <th>{{ t('reports.quarterly.totalRevenue') }}</th>
                <th>{{ t('reports.quarterly.avgOrderValue') }}</th>
                <th>{{ t('reports.quarterly.fulfillmentRate') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="q in quarterlyData" :key="q.quarter">
                <td><strong>{{ q.quarter }}</strong></td>
                <td>{{ q.total_orders }}</td>
                <td>{{ money(q.total_revenue) }}</td>
                <td>{{ money(q.avg_order_value) }}</td>
                <td>
                  <span :class="getFulfillmentClass(q.fulfillment_rate)">
                    {{ q.fulfillment_rate }}%
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Monthly Trends Chart -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('reports.trend.title') }}</h3>
        </div>
        <div class="chart-container">
          <div class="bar-chart">
            <div v-for="month in monthlyData" :key="month.month" class="bar-wrapper">
              <div class="bar-container">
                <div
                  class="bar"
                  :style="{ height: getBarHeight(month.revenue) + 'px' }"
                  :title="money(month.revenue)"
                ></div>
              </div>
              <div class="bar-label">{{ formatMonth(month.month) }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Month-over-Month Comparison -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('reports.mom.title') }}</h3>
        </div>
        <div class="table-container">
          <table class="reports-table">
            <thead>
              <tr>
                <th>{{ t('reports.mom.month') }}</th>
                <th>{{ t('reports.mom.orders') }}</th>
                <th>{{ t('reports.mom.revenue') }}</th>
                <th>{{ t('reports.mom.change') }}</th>
                <th>{{ t('reports.mom.growthRate') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in monthRows" :key="row.month">
                <td><strong>{{ formatMonth(row.month) }}</strong></td>
                <td>{{ row.order_count }}</td>
                <td>{{ money(row.revenue) }}</td>
                <td>
                  <span v-if="row.change !== null" :class="row.changeClass">{{ row.changeLabel }}</span>
                  <span v-else>-</span>
                </td>
                <td>
                  <span v-if="row.change !== null" :class="row.changeClass">{{ row.growthLabel }}</span>
                  <span v-else>-</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Summary Stats -->
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-label">{{ t('reports.summary.totalRevenue') }}</div>
          <div class="stat-value">{{ money(totalRevenue) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('reports.summary.avgMonthlyRevenue') }}</div>
          <div class="stat-value">{{ money(avgMonthlyRevenue) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('reports.summary.totalOrders') }}</div>
          <div class="stat-value">{{ totalOrders }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('reports.summary.bestQuarter') }}</div>
          <div class="stat-value">{{ bestQuarter || '-' }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { api } from '../api'
import { useFilters } from '../composables/useFilters'
import { useI18n } from '../composables/useI18n'
import { formatCurrency } from '../utils/currency'

const { t, currentLocale, currentCurrency } = useI18n()
const { selectedPeriod, selectedLocation, selectedCategory, selectedStatus, getCurrentFilters } = useFilters()

const loading = ref(true)
const error = ref(null)
const quarterlyData = ref([])
const monthlyData = ref([])

// Guards against an older, slower response overwriting a newer one when filters change quickly
let requestId = 0

const loadData = async () => {
  const currentRequest = ++requestId
  loading.value = true
  error.value = null
  try {
    // Both report endpoints are built from orders, so all four filters apply
    const filters = getCurrentFilters()
    const [quarterly, monthly] = await Promise.all([
      api.getQuarterlyReports(filters),
      api.getMonthlyTrends(filters)
    ])
    if (currentRequest !== requestId) return
    quarterlyData.value = quarterly
    monthlyData.value = monthly
  } catch (err) {
    if (currentRequest !== requestId) return
    error.value = t('reports.loadFailed') + ': ' + err.message
  } finally {
    if (currentRequest === requestId) loading.value = false
  }
}

watch([selectedPeriod, selectedLocation, selectedCategory, selectedStatus], loadData)
onMounted(loadData)

const money = (amount) => formatCurrency(amount, currentCurrency.value)

const totalRevenue = computed(() => monthlyData.value.reduce((sum, m) => sum + m.revenue, 0))
const totalOrders = computed(() => monthlyData.value.reduce((sum, m) => sum + m.order_count, 0))
const avgMonthlyRevenue = computed(() =>
  monthlyData.value.length > 0 ? totalRevenue.value / monthlyData.value.length : 0
)

const bestQuarter = computed(() => {
  let best = null
  for (const q of quarterlyData.value) {
    if (!best || q.total_revenue > best.total_revenue) best = q
  }
  return best ? best.quarter : ''
})

const maxRevenue = computed(() => Math.max(0, ...monthlyData.value.map(m => m.revenue)))

// Max bar height is 200px, matching .bar-container
const getBarHeight = (revenue) => (maxRevenue.value === 0 ? 0 : (revenue / maxRevenue.value) * 200)

// "YYYY-MM" -> localized "Jan 2025" / "2025年1月"; returns the raw string if it is malformed
const formatMonth = (monthStr) => {
  const [year, month] = String(monthStr).split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1, 1))
  if (!year || !month || isNaN(date.getTime())) return monthStr
  return date.toLocaleDateString(currentLocale.value === 'ja' ? 'ja-JP' : 'en-US', {
    year: 'numeric',
    month: 'short',
    timeZone: 'UTC'
  })
}

const getFulfillmentClass = (rate) => {
  if (rate >= 90) return 'badge success'
  if (rate >= 75) return 'badge warning'
  return 'badge danger'
}

// Month-over-month rows; the first month has no previous month so change is null
const monthRows = computed(() =>
  monthlyData.value.map((m, i) => {
    if (i === 0) return { ...m, change: null }
    const previous = monthlyData.value[i - 1].revenue
    const change = m.revenue - previous
    const sign = change > 0 ? '+' : change < 0 ? '-' : ''
    const rate = previous === 0 ? null : (change / previous) * 100
    return {
      ...m,
      change,
      changeClass: change > 0 ? 'positive-change' : change < 0 ? 'negative-change' : '',
      changeLabel: sign + money(Math.abs(change)),
      growthLabel: rate === null ? t('reports.mom.notAvailable') : `${sign}${Math.abs(rate).toFixed(1)}%`
    }
  })
)
</script>

<style scoped>
.chart-container {
  padding: 2rem 1rem;
  min-height: 300px;
}

.bar-chart {
  display: flex;
  align-items: flex-end;
  justify-content: space-around;
  height: 250px;
  gap: 0.5rem;
}

.bar-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  max-width: 80px;
}

.bar-container {
  height: 200px;
  display: flex;
  align-items: flex-end;
  width: 100%;
}

.bar {
  width: 100%;
  background: #3b82f6;
  border-radius: 4px 4px 0 0;
  transition: background-color 0.2s;
}

.bar:hover {
  background: #2563eb;
}

.bar-label {
  font-size: 0.75rem;
  color: #64748b;
  text-align: center;
  transform: rotate(-45deg);
  white-space: nowrap;
  margin-top: 1.5rem;
}

.positive-change {
  color: #059669;
  font-weight: 600;
}

.negative-change {
  color: #dc2626;
  font-weight: 600;
}
</style>
