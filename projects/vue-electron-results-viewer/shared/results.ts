export interface Measurement { timeSeconds: number; value: number }
export interface Channel { name: string; unit: string; lowerLimit: number; upperLimit: number; measurements: Measurement[] }
export interface TestRun { runId: string; startedAt: string; channels: Channel[] }
export type MeasurementStatus = 'Below range' | 'In range' | 'Above range'

function object(value: unknown, path: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`${path} must be an object.`)
  return value as Record<string, unknown>
}
function text(value: unknown, path: string): string {
  if (typeof value !== 'string' || !value.trim() || value.length > 120) throw new Error(`${path} must be text between 1 and 120 characters.`)
  return value.trim()
}
function number(value: unknown, path: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || Math.abs(value) > 1e12) throw new Error(`${path} must be a finite number between -1e12 and 1e12.`)
  return value
}
export function parseRun(input: unknown): TestRun {
  const root = object(input, 'Run')
  const runId = text(root.runId, 'runId')
  const startedAt = text(root.startedAt, 'startedAt')
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3})?Z$/.test(startedAt) ||
      !Number.isFinite(Date.parse(startedAt)) || new Date(startedAt).toISOString().slice(0, 19) !== startedAt.slice(0, 19)) {
    throw new Error('startedAt must be a valid UTC date, for example 2026-01-10T12:00:00Z.')
  }
  if (!Array.isArray(root.channels) || !root.channels.length || root.channels.length > 16) throw new Error('Run must contain 1 to 16 channels.')
  const names = new Set<string>()
  let total = 0
  const channels = root.channels.map((raw, i): Channel => {
    const path = `Channel ${i + 1}`
    const channel = object(raw, path)
    const name = text(channel.name, `${path} name`)
    if (names.has(name)) throw new Error(`Channel names must be unique: ${name}.`)
    names.add(name)
    const unit = text(channel.unit, `${path} unit`)
    const lowerLimit = number(channel.lowerLimit, `${path} lowerLimit`)
    const upperLimit = number(channel.upperLimit, `${path} upperLimit`)
    if (lowerLimit > upperLimit) throw new Error(`${path} lowerLimit must not exceed upperLimit.`)
    if (!Array.isArray(channel.measurements) || !channel.measurements.length || channel.measurements.length > 2000) throw new Error(`${path} must contain 1 to 2000 measurements.`)
    total += channel.measurements.length
    if (total > 20000) throw new Error('Run must contain at most 20000 measurements in total.')
    let previous = -1
    const measurements = channel.measurements.map((rawPoint, j): Measurement => {
      const point = object(rawPoint, `${path}, reading ${j + 1}`)
      const timeSeconds = number(point.timeSeconds, `${path}, reading ${j + 1} timeSeconds`)
      if (timeSeconds < 0 || timeSeconds <= previous) throw new Error(`${path} times must be nonnegative and strictly increasing.`)
      previous = timeSeconds
      return { timeSeconds, value: number(point.value, `${path}, reading ${j + 1} value`) }
    })
    return { name, unit, lowerLimit, upperLimit, measurements }
  })
  return { runId, startedAt, channels }
}
export function measurementStatus(value: number, channel: Pick<Channel, 'lowerLimit' | 'upperLimit'>): MeasurementStatus {
  if (value < channel.lowerLimit) return 'Below range'
  if (value > channel.upperLimit) return 'Above range'
  return 'In range'
}
