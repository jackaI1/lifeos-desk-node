import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import App from '../../src/App.vue'
import { validRun } from '../fixtures'
import type { LoadResult } from '../../shared/bridge'

const loaded = (): LoadResult => ({ kind: 'loaded', fileName: 'bench.json', run: validRun() })
const wrappers: ReturnType<typeof mount>[] = []
function setup(results: LoadResult[] = [loaded()]) {
  window.results = { openRun: vi.fn(async (): Promise<LoadResult> => results.shift() ?? { kind: 'canceled' }), loadExample: vi.fn(async () => loaded()) }
  const wrapper = mount(App); wrappers.push(wrapper); return wrapper
}
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()) })
const click = async (wrapper: ReturnType<typeof mount>, text: string) => {
  const button = wrapper.findAll('button').find(b => b.text() === text)
  expect(button, `button ${text}`).toBeDefined()
  await button!.trigger('click'); await flushPromises()
}

describe('results workflow', () => {
  it('opens a run and charts all points with inclusive boundary flags', async () => {
    const w = setup()
    await click(w, 'Open JSON file')
    expect(w.text()).toContain('Bench 042')
    expect(w.findAll('tbody tr')).toHaveLength(4)
    expect(w.findAll('circle[data-status="In range"]')).toHaveLength(2)
    expect(w.findAll('circle[data-status="Below range"]')).toHaveLength(1)
    expect(w.findAll('circle[data-status="Above range"]')).toHaveLength(1)
    expect(w.get('[role="img"]').attributes('aria-label')).toContain('Voltage')
    await w.get('input[type="checkbox"]').setValue(true)
    expect(w.findAll('tbody tr')).toHaveLength(2)
    expect(w.text()).toContain('2 of 4 readings outside limits')
  })
  it('loads the bundled example from the empty state', async () => {
    const w = setup(); await click(w, 'Load example')
    expect(w.text()).toContain('Bench 042')
  })
  it('preserves a good run after cancellation and reports bad files', async () => {
    const w = setup([loaded(), { kind: 'canceled' }, { kind: 'error', message: 'Bad measurement format.' }])
    await click(w, 'Open JSON file'); await click(w, 'Open JSON file')
    expect(w.text()).toContain('Bench 042'); expect(w.find('[role="alert"]').exists()).toBe(false)
    await click(w, 'Open JSON file')
    expect(w.get('[role="alert"]').text()).toContain('Bad measurement format.')
    expect(w.findAll('tbody tr')).toHaveLength(4)
  })
  it('recovers from a rejected bridge and re-enables opening', async () => {
    const w = setup(); window.results.openRun = vi.fn(async () => { throw new Error('disconnected') })
    await click(w, 'Open JSON file')
    expect(w.get('[role="alert"]').text()).toContain('Could not open')
    expect(w.findAll('button')[0].attributes('disabled')).toBeUndefined()
  })
  it('switches channels without mixing units and clears a stale filter on a new run', async () => {
    const result = loaded(); if (result.kind !== 'loaded') throw new Error('fixture')
    result.run.channels.push({ name: 'Temperature', unit: '°C', lowerLimit: 20, upperLimit: 25, measurements: [{ timeSeconds: 0, value: 23 }] })
    const w = setup([result, loaded()]); await click(w, 'Open JSON file')
    await w.get('select').setValue('1')
    expect(w.get('[role="img"]').attributes('aria-label')).toContain('Temperature')
    expect(w.findAll('tbody tr')).toHaveLength(1)
    await w.get('input[type="checkbox"]').setValue(true)
    expect(w.text()).toContain('No readings outside limits')
    await click(w, 'Open JSON file')
    expect(w.get('select').element.value).toBe('0')
    expect(w.findAll('tbody tr')).toHaveLength(4)
  })
  it('paginates large tables without dropping chart points', async () => {
    const result = loaded(); if (result.kind !== 'loaded') throw new Error('fixture')
    result.run.channels[0].measurements = Array.from({ length: 101 }, (_, i) => ({ timeSeconds: i, value: 3.5 }))
    const w = setup([result]); await click(w, 'Open JSON file')
    expect(w.findAll('tbody tr')).toHaveLength(100)
    expect(w.findAll('circle')).toHaveLength(101)
    await click(w, 'Next')
    expect(w.findAll('tbody tr')).toHaveLength(1)
    expect(w.find('tbody tr').text()).toContain('100')
    await click(w, 'Previous'); expect(w.findAll('tbody tr')).toHaveLength(100)
  })
  it('draws a finite chart for a single constant reading and equal limits', async () => {
    const result = loaded(); if (result.kind !== 'loaded') throw new Error('fixture')
    result.run.channels[0] = { name: 'Zero', unit: 'V', lowerLimit: 0, upperLimit: 0, measurements: [{ timeSeconds: 0, value: 0 }] }
    const w = setup([result]); await click(w, 'Open JSON file')
    expect(w.get('svg').html()).not.toMatch(/NaN|Infinity/)
    expect(w.findAll('circle[data-status="In range"]')).toHaveLength(1)
  })
})
