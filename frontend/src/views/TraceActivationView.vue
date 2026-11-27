<template>
  <section class="page trace-activation-page">
    <header class="page-head">
      <div>
        <h2>码段工作台 · 启用总单</h2>
        <p class="page-desc">
          一张总单可登记多套印版，但每套印版逐项受理；包装工位只能领取正式“已受理”的码段。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="reload">刷新总单</button>
        <button class="btn primary" type="button" @click="openCreate">新建启用总单</button>
      </div>
    </header>

    <p v-if="message" class="notice" :class="{ 'error-text': !lastOk }">{{ message }}</p>

    <div class="stat-row">
      <article class="stat-card">
        <span class="stat-label">总单数量</span>
        <strong class="stat-value">{{ orders.length }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">已受理印版</span>
        <strong class="stat-value">{{ plateCount('已受理') }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">整组等核验</span>
        <strong class="stat-value">{{ plateCount('整组等核验') }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">独立错误</span>
        <strong class="stat-value">{{ plateCount('独立错误') }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">已实际使用范围</span>
        <strong class="stat-value">{{ usedRangeCount }}</strong>
      </article>
    </div>

    <div v-if="orders.length" class="order-list">
      <article v-for="order in orders" :key="order.id" class="order-card">
        <header class="order-head">
          <div>
            <h3>{{ order.order_no }} <span class="version-tag">第 {{ order.version }} 次提交</span></h3>
            <p class="page-desc">总单状态：{{ order.status }}；印版：{{ order.plates.length }} 套</p>
          </div>
          <button class="btn ghost" type="button" @click="selectedOrderId = selectedOrderId === order.id ? undefined : order.id">
            {{ selectedOrderId === order.id ? '收起明细' : '查看明细' }}
          </button>
        </header>

        <div class="plate-summary">
          <span v-for="plate in order.plates" :key="String(plate.plate_id)" class="plate-chip" :class="statusClass(plate.status)">
            {{ plate.印版编号 || plate.plate_id }}：{{ plate.status }}
          </span>
        </div>

        <div v-if="selectedOrderId === order.id" class="order-detail">
          <table class="data-table">
            <thead>
              <tr>
                <th>印版</th>
                <th>码段范围</th>
                <th>受理结果</th>
                <th>资料/处理原因</th>
                <th>包装领用</th>
                <th>真实包装批</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="plate in order.plates" :key="String(plate.plate_id)">
                <td>{{ plate.印版编号 || plate.plate_id }}</td>
                <td>{{ plate.起始码号 }} - {{ plate.结束码号 }}</td>
                <td><span class="status-pill" :class="statusClass(plate.status)">{{ plate.status }}</span></td>
                <td>
                  <div>{{ plate.资料上传成功 === false ? '资料上传失败' : '资料已上传' }}</div>
                  <small class="reason-text">{{ plate.处理原因 || '—' }}</small>
                  <div v-if="plate.历史处理原因?.length" class="history-reasons">
                    前序原因：{{ plate.历史处理原因.join('；') }}
                  </div>
                </td>
                <td>{{ plate.领取状态 || '未领取' }}</td>
                <td>{{ plate.packing_no || '—' }}</td>
                <td class="row-actions">
                  <button class="link" type="button" @click="openCorrect(order, plate)">更正印版</button>
                  <button
                    v-if="plate.status === '已受理' && plate.领取状态 !== '已领取'"
                    class="link"
                    type="button"
                    @click="openClaim(order, plate)"
                  >
                    包装领取
                  </button>
                </td>
              </tr>
            </tbody>
          </table>

          <div class="range-panel">
            <h4>总单记录的实际使用范围</h4>
            <p><strong>第一次提交后：</strong>{{ formatRanges(order.首次实际使用范围) }}</p>
            <p><strong>修正后当前：</strong>{{ formatRanges(order.修正后实际使用范围 || order.实际使用范围) }}</p>
          </div>
        </div>
      </article>
    </div>
    <div v-else class="empty-panel">暂无启用总单，请先新建并提交一组印版。</div>

    <div v-if="showCreate" class="modal-backdrop" data-testid="create-order-modal">
      <form class="modal wide-modal" @submit.prevent="submitNewOrder">
        <h3>提交启用总单</h3>
        <label class="create-field">
          <span>总单编号（可留空自动生成）</span>
          <input v-model="newOrderNo" placeholder="例如 TCO-20261127-001" />
        </label>

        <div v-for="(plate, index) in createPlates" :key="index" class="plate-form-card">
          <div class="plate-form-title">
            <strong>印版 {{ index + 1 }}</strong>
            <button class="link danger" type="button" :disabled="createPlates.length === 1" @click="removeCreatePlate(index)">
              删除
            </button>
          </div>
          <div class="form-grid">
            <label class="create-field">
              <span>印版编号</span>
              <input v-model="plate.印版编号" required />
            </label>
            <label class="create-field">
              <span>起始码号</span>
              <input v-model="plate.起始码号" required />
            </label>
            <label class="create-field">
              <span>结束码号</span>
              <input v-model="plate.结束码号" required />
            </label>
            <label class="checkbox-field">
              <input v-model="plate.资料上传成功" type="checkbox" />
              <span>上传资料成功</span>
            </label>
          </div>
        </div>
        <button class="btn" type="button" @click="addCreatePlate">增加一套印版</button>

        <div class="modal-actions">
          <button class="btn" type="button" @click="showCreate = false">取消</button>
          <button class="btn primary" type="submit" :disabled="submitting">
            {{ submitting ? '提交中…' : '提交受理' }}
          </button>
        </div>
      </form>
    </div>

    <div v-if="correctTarget" class="modal-backdrop" data-testid="correct-modal">
      <form class="modal" @submit.prevent="submitCorrection">
        <h3>更正印版 {{ correctTarget.plate.印版编号 || correctTarget.plate.plate_id }}</h3>
        <p class="page-desc">更正会保留该印版上一版处理原因，已领取范围不能改号。</p>
        <label class="create-field">
          <span>起始码号</span>
          <input v-model="correctForm.起始码号" required />
        </label>
        <label class="create-field">
          <span>结束码号</span>
          <input v-model="correctForm.结束码号" required />
        </label>
        <label class="checkbox-field">
          <input v-model="correctForm.资料上传成功" type="checkbox" />
          <span>上传资料成功</span>
        </label>
        <label class="create-field">
          <span>更正原因</span>
          <input v-model="correctReason" required />
        </label>
        <div class="modal-actions">
          <button class="btn" type="button" @click="correctTarget = null">取消</button>
          <button class="btn primary" type="submit" :disabled="submitting">提交更正</button>
        </div>
      </form>
    </div>

    <div v-if="claimTarget" class="modal-backdrop" data-testid="claim-modal">
      <form class="modal" @submit.prevent="submitClaim">
        <h3>包装工位领取码段</h3>
        <p>
          印版 {{ claimTarget.plate.印版编号 || claimTarget.plate.plate_id }}：
          {{ claimTarget.plate.起始码号 }} - {{ claimTarget.plate.结束码号 }}
        </p>
        <label class="create-field">
          <span>真实包装批 ID</span>
          <input v-model.number="claimPackingId" type="number" min="1" required />
        </label>
        <p class="page-desc">每个已受理印版最多对应一次真实使用，提交后不能重复登记。</p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="claimTarget = null">取消</button>
          <button class="btn primary" type="submit" :disabled="submitting">确认领取</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  claimActivationPlate,
  correctActivationPlate,
  listActivationOrders,
  submitActivationOrder,
  type ActivationOrder,
  type ActivationPlate,
} from '@/api/trace-activation'

type PlateForm = ActivationPlate & { 印版编号: string; 起始码号: string; 结束码号: string }

const orders = ref<ActivationOrder[]>([])
const selectedOrderId = ref<number>()
const message = ref('')
const lastOk = ref(true)
const submitting = ref(false)
const showCreate = ref(false)
const newOrderNo = ref('')
const createPlates = ref<PlateForm[]>([])
const correctTarget = ref<{ order: ActivationOrder; plate: ActivationPlate } | null>(null)
const correctForm = ref<PlateForm>(emptyPlateForm())
const correctReason = ref('')
const claimTarget = ref<{ order: ActivationOrder; plate: ActivationPlate } | null>(null)
const claimPackingId = ref<number | null>(null)

const usedRangeCount = computed(() =>
  orders.value.reduce((sum, order) => sum + (order.实际使用范围?.length ?? 0), 0),
)

function emptyPlateForm(): PlateForm {
  return { 印版编号: '', 起始码号: '', 结束码号: '', 资料上传成功: true }
}

function addCreatePlate() {
  createPlates.value.push(emptyPlateForm())
}

function removeCreatePlate(index: number) {
  createPlates.value.splice(index, 1)
}

function openCreate() {
  newOrderNo.value = ''
  createPlates.value = [emptyPlateForm(), emptyPlateForm(), emptyPlateForm()]
  showCreate.value = true
}

function setMessage(ok: boolean, text: string) {
  lastOk.value = ok
  message.value = text
}

async function reload() {
  try {
    orders.value = await listActivationOrders()
  } catch (error) {
    setMessage(false, error instanceof Error ? error.message : '启用总单读取失败')
  }
}

async function submitNewOrder() {
  submitting.value = true
  try {
    const order = await submitActivationOrder({
      order_no: newOrderNo.value || undefined,
      plates: createPlates.value.map((plate) => ({ ...plate })),
    })
    setMessage(true, `启用总单 ${order.order_no} 已提交，系统已逐项判定印版受理状态`)
    showCreate.value = false
    selectedOrderId.value = order.id
    await reload()
  } catch (error) {
    setMessage(false, error instanceof Error ? error.message : '提交失败')
  } finally {
    submitting.value = false
  }
}

function openCorrect(order: ActivationOrder, plate: ActivationPlate) {
  correctTarget.value = { order, plate }
  correctForm.value = {
    ...emptyPlateForm(),
    ...plate,
    印版编号: String(plate.印版编号 || plate.plate_id || ''),
    起始码号: String(plate.起始码号 || ''),
    结束码号: String(plate.结束码号 || ''),
  }
  correctReason.value = ''
}

async function submitCorrection() {
  if (!correctTarget.value) return
  submitting.value = true
  try {
    const order = await correctActivationPlate({
      orderId: correctTarget.value.order.id,
      plateKey: String(correctTarget.value.plate.plate_id || correctTarget.value.plate.印版编号),
      reason: correctReason.value,
      plate: { ...correctForm.value },
    })
    setMessage(true, `印版更正已提交，当前总单版本为第 ${order.version} 次`)
    correctTarget.value = null
    selectedOrderId.value = order.id
    await reload()
  } catch (error) {
    setMessage(false, error instanceof Error ? error.message : '更正失败')
  } finally {
    submitting.value = false
  }
}

function openClaim(order: ActivationOrder, plate: ActivationPlate) {
  claimTarget.value = { order, plate }
  claimPackingId.value = null
}

async function submitClaim() {
  if (!claimTarget.value || claimPackingId.value === null) return
  submitting.value = true
  try {
    const target = claimTarget.value
    await claimActivationPlate({
      orderId: target.order.id,
      plateKey: String(target.plate.plate_id || target.plate.印版编号),
      packingId: claimPackingId.value,
    })
    setMessage(true, '包装工位领取成功，该范围已登记为一次真实使用')
    claimTarget.value = null
    selectedOrderId.value = target.order.id
    await reload()
  } catch (error) {
    setMessage(false, error instanceof Error ? error.message : '领取失败')
  } finally {
    submitting.value = false
  }
}

function plateCount(status: string): number {
  return orders.value.reduce(
    (sum, order) => sum + order.plates.filter((plate) => plate.status === status).length,
    0,
  )
}

function statusClass(status?: string) {
  return {
    'status-accepted': status === '已受理',
    'status-pending': status === '整组等核验',
    'status-error': status === '独立错误',
  }
}

function formatRanges(ranges?: Array<Record<string, unknown>>): string {
  if (!ranges || !ranges.length) return '暂无'
  return ranges
    .map((item) => `${String(item.印版编号 || item.plate_id)}：${String(item.码段范围 || `${item.起始码号}-${item.结束码号}`)}`)
    .join('；')
}

onMounted(() => {
  void reload()
})
</script>
