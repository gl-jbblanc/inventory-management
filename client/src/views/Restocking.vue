<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div class="card budget-card">
      <div class="budget-row">
        <label for="budget-slider" class="budget-label">{{ t('restocking.budget') }}</label>
        <span class="budget-value">{{ formatMoney(budget) }}</span>
      </div>
      <input
        id="budget-slider"
        v-model.number="budget"
        type="range"
        class="budget-slider"
        min="0"
        :max="MAX_BUDGET"
        :step="BUDGET_STEP"
      />
    </div>

    <div v-if="confirmation" class="confirmation">
      <span>{{ t('restocking.confirmation', { orderNumber: confirmation.order_number }) }}</span>
      <router-link to="/orders" class="confirmation-link">{{ t('restocking.viewOrders') }}</router-link>
    </div>
    <div v-if="submitError" class="error">{{ submitError }}</div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div v-if="items.length === 0" class="card empty-state">{{ t('restocking.empty') }}</div>
      <div v-else class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendedItems') }} ({{ items.length }})</h3>
        </div>
        <div class="table-container">
          <table>
            <thead>
              <tr>
                <th class="col-check"></th>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.name') }}</th>
                <th>{{ t('restocking.table.quantity') }}</th>
                <th>{{ t('restocking.table.unitCost') }}</th>
                <th>{{ t('restocking.table.lineCost') }}</th>
                <th>{{ t('restocking.table.leadTime') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in items" :key="item.sku">
                <td class="col-check">
                  <input
                    type="checkbox"
                    :checked="selectedSkus.has(item.sku)"
                    :aria-label="t('restocking.selectItem', { sku: item.sku })"
                    @change="toggleItem(item.sku)"
                  />
                </td>
                <td><strong>{{ item.sku }}</strong></td>
                <td>{{ translateProductName(item.name) }}</td>
                <td>{{ item.quantity.toLocaleString() }}</td>
                <td>{{ formatMoney(item.unit_cost) }}</td>
                <td><strong>{{ formatMoney(item.quantity * item.unit_cost) }}</strong></td>
                <td>{{ item.lead_time_days }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="stats-grid summary-grid">
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.summary.selectedItems') }}</div>
          <div class="stat-value">{{ selectedItems.length }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.summary.selectedTotal') }}</div>
          <div class="stat-value">{{ formatMoney(selectedTotal) }}</div>
          <div class="stat-sub">/ {{ formatMoney(loadedBudget) }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restocking.summary.remaining') }}</div>
          <div class="stat-value">{{ formatMoney(remainingBudget) }}</div>
        </div>
        <div class="stat-card warning">
          <div class="stat-label">{{ t('restocking.summary.leadTime') }}</div>
          <div class="stat-value">{{ t('restocking.days', { days: orderLeadTime }) }}</div>
        </div>
      </div>

      <div class="actions">
        <button
          type="button"
          class="place-order-btn"
          :disabled="selectedItems.length === 0 || submitting"
          @click="placeOrder"
        >
          {{ submitting ? t('restocking.submitting') : t('restocking.placeOrder') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'

const MAX_BUDGET = 60000
const BUDGET_STEP = 500
const DEFAULT_BUDGET = 10000
const DEBOUNCE_MS = 300

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, translateProductName } = useI18n()

    const currencySymbol = computed(() => {
      return currentCurrency.value === 'JPY' ? '¥' : '$'
    })
    const formatMoney = (value) => {
      return `${currencySymbol.value}${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    }

    const budget = ref(DEFAULT_BUDGET)
    // Budget the displayed recommendations were computed for (slider may be ahead of it while debouncing)
    const loadedBudget = ref(DEFAULT_BUDGET)
    const items = ref([])
    const selectedSkus = ref(new Set())
    const loading = ref(true)
    const error = ref(null)
    const submitting = ref(false)
    const submitError = ref(null)
    const confirmation = ref(null)

    const selectedItems = computed(() => items.value.filter(i => selectedSkus.value.has(i.sku)))
    const selectedTotal = computed(() => {
      return selectedItems.value.reduce((sum, i) => sum + i.quantity * i.unit_cost, 0)
    })
    const remainingBudget = computed(() => loadedBudget.value - selectedTotal.value)
    // An order arrives when its slowest item does
    const orderLeadTime = computed(() => {
      return selectedItems.value.reduce((max, i) => Math.max(max, i.lead_time_days), 0)
    })

    // Each request gets an id; only the latest one may update state, so slow older responses are dropped
    let requestId = 0
    let debounceTimer = null

    const loadRecommendations = async () => {
      const myId = ++requestId
      const requestedBudget = budget.value
      try {
        loading.value = true
        error.value = null
        const data = await api.getRestockRecommendations(requestedBudget)
        if (myId !== requestId) return
        items.value = data.items
        loadedBudget.value = requestedBudget
        // Everything recommended starts out selected
        selectedSkus.value = new Set(data.items.map(i => i.sku))
      } catch (err) {
        if (myId !== requestId) return
        error.value = 'Failed to load recommendations: ' + err.message
      } finally {
        if (myId === requestId) loading.value = false
      }
    }

    watch(budget, () => {
      confirmation.value = null
      submitError.value = null
      clearTimeout(debounceTimer)
      debounceTimer = setTimeout(loadRecommendations, DEBOUNCE_MS)
    })

    const toggleItem = (sku) => {
      // Replace the Set so Vue picks up the change
      const next = new Set(selectedSkus.value)
      if (next.has(sku)) next.delete(sku)
      else next.add(sku)
      selectedSkus.value = next
    }

    const placeOrder = async () => {
      if (selectedItems.value.length === 0 || submitting.value) return
      submitting.value = true
      submitError.value = null
      confirmation.value = null
      try {
        // Send the budget the list was built for so the backend total check matches what the user saw
        const order = await api.createRestockOrder({
          budget: loadedBudget.value,
          items: selectedItems.value
        })
        confirmation.value = order
        // Cancel any pending debounce and refresh now
        clearTimeout(debounceTimer)
        await loadRecommendations()
      } catch (err) {
        submitError.value = err.response?.data?.detail
          ? (typeof err.response.data.detail === 'string'
            ? err.response.data.detail
            : JSON.stringify(err.response.data.detail))
          : t('restocking.submitFailed') + ': ' + err.message
      } finally {
        submitting.value = false
      }
    }

    onMounted(loadRecommendations)
    onBeforeUnmount(() => clearTimeout(debounceTimer))

    return {
      t,
      MAX_BUDGET,
      BUDGET_STEP,
      budget,
      loadedBudget,
      items,
      selectedSkus,
      selectedItems,
      selectedTotal,
      remainingBudget,
      orderLeadTime,
      loading,
      error,
      submitting,
      submitError,
      confirmation,
      formatMoney,
      toggleItem,
      placeOrder,
      translateProductName
    }
  }
}
</script>

<style scoped>
.budget-card {
  padding: 1.25rem 1.5rem;
  margin-bottom: 1.5rem;
}

.budget-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 0.75rem;
}

.budget-label {
  font-size: 0.875rem;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.budget-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
}

.budget-slider {
  width: 100%;
  accent-color: #0f172a;
}

.col-check {
  width: 40px;
}

.confirmation {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  padding: 0.875rem 1.25rem;
  margin-bottom: 1.5rem;
  background: #d1fae5;
  border: 1px solid #10b981;
  border-radius: 8px;
  color: #065f46;
  font-weight: 500;
}

.confirmation-link {
  color: #065f46;
  font-weight: 600;
  text-decoration: underline;
}

.empty-state {
  padding: 2rem;
  text-align: center;
  color: #64748b;
}

.summary-grid {
  margin-top: 1.5rem;
}

.stat-sub {
  font-size: 0.813rem;
  color: #64748b;
  margin-top: 0.25rem;
}

.actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 1.5rem;
}

.place-order-btn {
  background: #0f172a;
  color: white;
  border: none;
  border-radius: 8px;
  padding: 0.75rem 1.5rem;
  font-size: 0.938rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.place-order-btn:hover:not(:disabled) {
  background: #1e293b;
}

.place-order-btn:disabled {
  background: #cbd5e1;
  color: #64748b;
  cursor: not-allowed;
}
</style>
