import { describe, expect, it } from 'vitest'
import { parseRun, measurementStatus } from '../../shared/results'
import { readRunFile, MAX_FILE_BYTES } from '../../electron/files'
import { mkdtemp, writeFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

import { validRun } from '../fixtures'

describe('test-run validation', () => {
  it('keeps real readings and both inclusive boundaries', () => {
    const run = parseRun(validRun())
    expect(run.channels[0].measurements.map(m => measurementStatus(m.value, run.channels[0])))
      .toEqual(['Below range', 'In range', 'In range', 'Above range'])
  })
  it.each([
    ['no channels', (r: any) => { r.channels = [] }],
    ['reversed limits', (r: any) => { r.channels[0].lowerLimit = 5 }],
    ['string reading', (r: any) => { r.channels[0].measurements[0].value = '3' }],
    ['infinite reading', (r: any) => { r.channels[0].measurements[0].value = Infinity }],
    ['invalid date', (r: any) => { r.startedAt = 'tomorrow' }],
    ['impossible date', (r: any) => { r.startedAt = '2026-02-30T12:00:00Z' }],
    ['duplicate time', (r: any) => { r.channels[0].measurements[1].timeSeconds = 0 }],
    ['negative time', (r: any) => { r.channels[0].measurements[0].timeSeconds = -1 }],
    ['empty readings', (r: any) => { r.channels[0].measurements = [] }],
    ['duplicate names', (r: any) => { r.channels.push(r.channels[0]) }],
    ['too many readings', (r: any) => { r.channels[0].measurements = Array.from({length: 2001}, (_, i) => ({timeSeconds: i, value: 3})) }],
  ])('rejects %s instead of silently charting misleading data', (_, change) => {
    const run = validRun(); change(run)
    expect(() => parseRun(run)).toThrow()
  })
  it('rejects null and arrays as documents', () => {
    expect(() => parseRun(null)).toThrow()
    expect(() => parseRun([])).toThrow()
  })
  it('accepts single readings and equal lower/upper limits', () => {
    const run = validRun(); run.channels[0].lowerLimit = 4
    run.channels[0].measurements = [{ timeSeconds: 0, value: 4 }]
    expect(measurementStatus(parseRun(run).channels[0].measurements[0].value, run.channels[0])).toBe('In range')
  })
})

describe('local file reader', () => {
  it('reads JSON from disk, strips private paths, and gives recoverable errors', async () => {
    const dir = await mkdtemp(join(tmpdir(), 'results-test-'))
    try {
      const file = join(dir, 'run.json')
      await writeFile(file, JSON.stringify(validRun()))
      expect(await readRunFile(file)).toMatchObject({ kind: 'loaded', fileName: 'run.json', run: { runId: 'Bench 042' } })
      await writeFile(file, '{bad json')
      expect(await readRunFile(file)).toMatchObject({ kind: 'error', message: expect.stringContaining('JSON') })
      await writeFile(file, ' '.repeat(MAX_FILE_BYTES + 1))
      expect(await readRunFile(file)).toMatchObject({ kind: 'error', message: expect.stringContaining('2 MB') })
      expect(await readRunFile(join(dir, 'missing.json'))).toMatchObject({ kind: 'error' })
      expect(await readRunFile(dir)).toMatchObject({ kind: 'error' })
    } finally { await rm(dir, { recursive: true, force: true }) }
  })
})
