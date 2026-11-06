<script setup lang="ts">
import { computed } from 'vue'
import { measurementStatus, type Channel } from '../../shared/results'
const props = defineProps<{ channel: Channel }>()
const geometry = computed(() => {
  const c = props.channel
  const values = c.measurements.map(m => m.value)
  const lo = Math.min(c.lowerLimit, ...values)
  const hi = Math.max(c.upperLimit, ...values)
  const padding = (hi - lo || Math.max(Math.abs(lo) * 0.1, 1)) * 0.15
  const min = lo - padding, max = hi + padding
  const first = c.measurements[0].timeSeconds
  const last = c.measurements.at(-1)!.timeSeconds
  const x = (t: number) => last === first ? 470 : 90 + (t - first) / (last - first) * 760
  const y = (value: number) => 240 - (value - min) / (max - min) * 205
  return {
    x, y, points: c.measurements.map(m => `${x(m.timeSeconds)},${y(m.value)}`).join(' '),
    yTicks: Array.from({length: 5}, (_, i) => min + i * (max - min) / 4),
    xTicks: last === first ? [first] : Array.from({length: 5}, (_, i) => first + i * (last - first) / 4),
  }
})
const tick = (n: number) => Number(n.toPrecision(4)).toString()
</script>

<template>
  <figure>
    <svg viewBox="0 0 900 295" role="img" :aria-label="`${channel.name} over elapsed seconds; limits ${channel.lowerLimit} to ${channel.upperLimit} ${channel.unit}. Exact values in the table below.`">
      <rect x="90" :y="geometry.y(channel.upperLimit)" width="760" :height="Math.max(0, geometry.y(channel.lowerLimit) - geometry.y(channel.upperLimit))" fill="#e3efe7" />
      <g v-for="value in geometry.yTicks" :key="value">
        <line x1="90" x2="850" :y1="geometry.y(value)" :y2="geometry.y(value)" stroke="#dbe2ea" />
        <text x="78" :y="geometry.y(value) + 4" text-anchor="end">{{ tick(value) }}</text>
      </g>
      <line v-for="(limit, index) in [channel.lowerLimit, channel.upperLimit]" :key="index" x1="90" x2="850" :y1="geometry.y(limit)" :y2="geometry.y(limit)" stroke="#216144" stroke-dasharray="5 4" />
      <polyline :points="geometry.points" fill="none" stroke="#1760a5" stroke-width="2" />
      <circle v-for="point in channel.measurements" :key="point.timeSeconds" :cx="geometry.x(point.timeSeconds)" :cy="geometry.y(point.value)" :r="measurementStatus(point.value, channel) === 'In range' ? 3 : 5" :data-status="measurementStatus(point.value, channel)" :fill="measurementStatus(point.value, channel) === 'In range' ? '#1760a5' : '#b42318'" stroke="white" stroke-width="1">
        <title>{{ point.timeSeconds }} s: {{ point.value }} {{ channel.unit }}, {{ measurementStatus(point.value, channel) }}</title>
      </circle>
      <text v-for="time in geometry.xTicks" :key="time" :x="geometry.x(time)" y="261" text-anchor="middle">{{ tick(time) }}</text>
      <text x="470" y="286" text-anchor="middle">Elapsed time (s)</text>
      <text x="90" y="20">{{ channel.name }} ({{ channel.unit }})</text>
    </svg>
    <figcaption><span class="reading-key">Readings</span><span class="limit-key">Dashed lines: inclusive limits</span><span class="flag-key">Large red points: outside limits</span></figcaption>
  </figure>
</template>
