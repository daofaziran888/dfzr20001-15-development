import { request } from './client'

export type ActivationPlate = {
  plate_id?: string
  印版编号?: string
  起始码号?: string
  结束码号?: string
  资料上传成功?: boolean
  处理原因?: string
  status?: string
  受理状态?: string
  领取状态?: string
  处理原因_?: string
  历史处理原因?: string[]
  trace_code_id?: number | null
  packing_id?: number | null
  packing_no?: string | null
  usage?: Record<string, unknown> | null
  [key: string]: unknown
}

export type ActivationOrder = {
  id: number
  order_no: string
  登记编号?: string
  status: string
  version: number
  plates: ActivationPlate[]
  首次实际使用范围?: Array<Record<string, unknown>>
  修正后实际使用范围?: Array<Record<string, unknown>>
  实际使用范围?: Array<Record<string, unknown>>
  submission_history?: Array<Record<string, unknown>>
  [key: string]: unknown
}

type ApiResult<T> = {
  ok: boolean
  message: string
  item?: T
  items?: T[]
  total?: number
}

async function parseResponse<T>(response: Response): Promise<ApiResult<T>> {
  const payload = (await response.json()) as ApiResult<T>
  if (!response.ok || !payload.ok) {
    throw new Error(payload.message || `接口返回 ${response.status}`)
  }
  return payload
}

export async function listActivationOrders(): Promise<ActivationOrder[]> {
  const response = await request('/api/trace-activation/orders')
  const payload = await parseResponse<ActivationOrder>(response)
  return payload.items ?? []
}

export async function submitActivationOrder(input: {
  order_id?: number
  order_no?: string
  plates: ActivationPlate[]
  note?: string
  correction_reason?: string
}): Promise<ActivationOrder> {
  const response = await request('/api/trace-activation/orders', {
    method: 'POST',
    body: JSON.stringify(input),
  })
  const payload = await parseResponse<ActivationOrder>(response)
  if (!payload.item) throw new Error('启用总单未返回')
  return payload.item
}

export async function correctActivationPlate(input: {
  orderId: number
  plateKey: string
  reason: string
  plate: ActivationPlate
}): Promise<ActivationOrder> {
  const response = await request(
    `/api/trace-activation/orders/${input.orderId}/plates/${encodeURIComponent(input.plateKey)}/correct`,
    {
      method: 'POST',
      body: JSON.stringify({ reason: input.reason, plate: input.plate }),
    },
  )
  const payload = await parseResponse<ActivationOrder>(response)
  if (!payload.item) throw new Error('更正结果未返回')
  return payload.item
}

export async function claimActivationPlate(input: {
  orderId: number
  plateKey: string
  packingId: number
}): Promise<Record<string, unknown>> {
  const response = await request(
    `/api/trace-activation/orders/${input.orderId}/plates/${encodeURIComponent(input.plateKey)}/claim`,
    {
      method: 'POST',
      body: JSON.stringify({ packing_id: input.packingId }),
    },
  )
  const payload = await parseResponse<Record<string, unknown>>(response)
  if (!payload.item) throw new Error('领用结果未返回')
  return payload.item
}
