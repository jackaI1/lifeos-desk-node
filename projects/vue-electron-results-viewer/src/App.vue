<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import RunChart from './components/RunChart.vue'
import { measurementStatus, type TestRun } from '../shared/results'
const run = ref<TestRun | null>(null)
const fileName = ref('')
const error = ref('')
const busy = ref(false)
const selected = ref(0)
const flaggedOnly = ref(false)
const page = ref(0)
const pageSize = 100
const channel = computed(() => run.value?.channels[selected.value])
const flags = computed(() => channel.value?.measurements.filter(m => measurementStatus(m.value, channel.value!) !== 'In range').length ?? 0)
const totalFlags = computed(() => run.value?.channels.reduce((sum, c) => sum + c.measurements.filter(m => measurementStatus(m.value, c) !== 'In range').length, 0) ?? 0)
const rows = computed(() => channel.value?.measurements.filter(m => !flaggedOnly.value || measurementStatus(m.value, channel.value!) !== 'In range') ?? [])
const visibleRows = computed(() => rows.value.slice(page.value * pageSize, (page.value + 1) * pageSize))
const pageCount = computed(() => Math.max(1, Math.ceil(rows.value.length / pageSize)))
watch([selected, flaggedOnly], () => { page.value = 0 })
async function load(source: 'openRun' | 'loadExample') {
  if (busy.value) return
  busy.value = true; error.value = ''
  try {
    const result = await window.results[source]()
    if (result.kind === 'loaded') {
      run.value = result.run; fileName.value = result.fileName
      selected.value = 0; flaggedOnly.value = false; page.value = 0
    } else if (result.kind === 'error') error.value = result.message
  } catch { error.value = 'Could not open the run. Try opening the file again.' }
  finally { busy.value = false }
}
</script>

<template>
  <main :aria-busy="busy">
    <header class="app-header">
      <div><p class="app-name">Results viewer</p><p class="local-note">Local files. No uploads.</p></div>
      <div class="actions"><button class="primary" :disabled="busy" @click="load('openRun')">Open JSON file</button><button :disabled="busy" @click="load('loadExample')">Load example</button></div>
    </header>
    <p v-if="busy" role="status">Opening run…</p>
    <div v-if="error" role="alert" class="error"><strong>File could not be loaded.</strong> {{ error }} <span v-if="run">Your previous run is still displayed.</span></div>
    <section v-if="!run" class="empty">
      <p class="empty-mark" aria-hidden="true">∿</p><h1>See where a test run went out of range.</h1>
      <p>Open a test-run JSON file to plot measurements against their limits. Choose a channel, then inspect the readings that need attention.</p>
      <p>Start with <strong>Load example</strong> for a synthetic two-channel bench run. Nothing is uploaded or changed on disk.</p>
    </section>
    <template v-else-if="channel">
      <section class="run-heading">
        <div><h1>{{ run.runId }}</h1><p>{{ fileName }} <span class="separator">/</span> Started {{ new Date(run.startedAt).toLocaleString() }}</p></div>
        <p class="run-summary" role="status">{{ totalFlags }} outside limits across {{ run.channels.length }} {{ run.channels.length === 1 ? 'channel' : 'channels' }}</p>
      </section>
      <section class="plot-panel" aria-label="Channel plot">
        <div class="plot-controls"><label>Channel <select v-model.number="selected"><option v-for="(c, i) in run.channels" :key="c.name" :value="i">{{ c.name }} ({{ c.unit }})</option></select></label>
          <p>Limits <strong>{{ channel.lowerLimit }} to {{ channel.upperLimit }} {{ channel.unit }}</strong></p></div>
        <RunChart :channel="channel" />
      </section>
      <section class="readings" aria-labelledby="readings-title">
        <div class="table-heading"><div><h2 id="readings-title">Measurements</h2><p :class="{ 'flag-count': flags > 0 }">{{ flags }} of {{ channel.measurements.length }} readings outside limits</p></div>
          <label class="checkbox"><input v-model="flaggedOnly" type="checkbox" /> Only outside limits</label></div>
        <p v-if="!rows.length" class="no-results">No readings outside limits in this channel.</p>
        <div v-else class="table-scroll"><table><caption class="sr-only">{{ channel.name }} readings, page {{ page + 1 }} of {{ pageCount }}</caption><thead><tr><th scope="col">Elapsed time (s)</th><th scope="col">Value ({{ channel.unit }})</th><th scope="col">Result</th></tr></thead>
          <tbody><tr v-for="point in visibleRows" :key="point.timeSeconds" :class="{ flagged: measurementStatus(point.value, channel) !== 'In range' }"><td>{{ point.timeSeconds }}</td><td>{{ point.value }}</td><td>{{ measurementStatus(point.value, channel) }}</td></tr></tbody></table></div>
        <nav v-if="rows.length > pageSize" aria-label="Measurement pages" class="pagination"><button :disabled="page === 0" @click="page--">Previous</button><span>Page {{ page + 1 }} of {{ pageCount }}</span><button :disabled="page + 1 >= pageCount" @click="page++">Next</button></nav>
      </section>
      <footer>Limits include both endpoints. A flag means a reading needs review; it does not explain the cause.</footer>
    </template>
  </main>
</template>
