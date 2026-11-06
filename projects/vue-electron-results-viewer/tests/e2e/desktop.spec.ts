import { test, expect, _electron as electron, type ElectronApplication } from '@playwright/test'
import { mkdtemp, writeFile, rm, appendFile, mkdir } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { resolve, join } from 'node:path'
import { validRun } from '../fixtures'

let desktop: ElectronApplication
let directory: string
let pid: number | undefined

test.beforeEach(async () => {
  desktop = undefined as unknown as ElectronApplication
  pid = undefined
  directory = await mkdtemp(join(tmpdir(), 'viewer-e2e-'))
  const env = Object.fromEntries(Object.entries(process.env).filter((pair): pair is [string, string] => typeof pair[1] === 'string'))
  delete env.ELECTRON_RUN_AS_NODE
  desktop = await electron.launch({
    ...(process.env.ELECTRON_APP_PATH ? { executablePath: process.env.ELECTRON_APP_PATH, args: [] } : { args: [resolve('.')] }),
    env,
  })
  pid = desktop.process().pid
  const creationTime = await desktop.evaluate(() => process.getCreationTime())
  await mkdir('test-results', { recursive: true })
  await appendFile('test-results/resources.jsonl', JSON.stringify({ owner: test.info().title, pid, startedAt: creationTime === null ? null : new Date(creationTime).toISOString(), port: null, cleanup: 'await desktop.close()' }) + '\n')
})
test.afterEach(async () => {
  try { if (desktop) await desktop.close() }
  finally {
    await rm(directory, { recursive: true, force: true })
    if (pid) {
      let alive = true
      for (let i = 0; i < 30 && alive; i++) {
        try { process.kill(pid, 0); await new Promise(r => setTimeout(r, 100)) } catch { alive = false }
      }
      await appendFile('test-results/resources.jsonl', JSON.stringify({ pid, stopped: !alive, checkedAt: new Date().toISOString() }) + '\n')
      expect(alive, 'owned Electron process must exit').toBe(false)
    }
  }
})

// Stub only the OS picker. The real click, typed bridge, IPC handler, disk reader,
// runtime validation, chart and table still run in the actual Electron process.
async function chooseFile(path: string | null) {
  await desktop.evaluate(({ dialog }, selected) => {
    dialog.showOpenDialog = async () => ({ canceled: selected === null, filePaths: selected ? [selected] : [] })
  }, path)
}

test('opens real JSON through the native dialog bridge and recovers from invalid files', async () => {
  const page = await desktop.firstWindow()
  const file = join(directory, 'bench.json')
  await writeFile(file, JSON.stringify(validRun()))
  await chooseFile(file)
  await page.getByRole('button', { name: 'Open JSON file' }).click()
  await expect(page.getByRole('heading', { name: 'Bench 042' })).toBeVisible()
  await expect(page.locator('circle[data-status="In range"]')).toHaveCount(2)
  await expect(page.locator('circle[data-status="Above range"]')).toHaveCount(1)
  await expect(page.locator('tbody tr')).toHaveCount(4)
  await page.getByLabel('Only outside limits').check()
  await expect(page.locator('tbody tr')).toHaveCount(2)
  await chooseFile(null)
  await page.getByRole('button', { name: 'Open JSON file' }).click()
  await expect(page.getByRole('heading', { name: 'Bench 042' })).toBeVisible()
  await writeFile(file, '{bad')
  await chooseFile(file)
  await page.getByRole('button', { name: 'Open JSON file' }).click()
  await expect(page.getByRole('alert')).toContainText('not valid JSON')
  await expect(page.locator('tbody tr')).toHaveCount(2)
  const invalid = validRun(); invalid.channels[0].lowerLimit = 10
  await writeFile(file, JSON.stringify(invalid))
  await page.getByRole('button', { name: 'Open JSON file' }).click()
  await expect(page.getByRole('alert')).toContainText('lowerLimit')
  await writeFile(file, JSON.stringify(validRun()))
  await page.getByRole('button', { name: 'Open JSON file' }).click()
  await expect(page.getByRole('alert')).toHaveCount(0)
  await expect(page.locator('tbody tr')).toHaveCount(4)
})

test('bundled two-channel run works offline in a sandbox with no Node access', async () => {
  const page = await desktop.firstWindow()
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.getByRole('button', { name: 'Load example' }).click()
  await expect(page.getByRole('heading', { name: 'Bench supply warm-up' })).toBeVisible()
  await expect(page.locator('tbody tr')).toHaveCount(12)
  await page.getByRole('combobox', { name: 'Channel', exact: true }).selectOption('1')
  await expect(page.getByRole('img')).toHaveAttribute('aria-label', /Temperature/)
  await expect(page.locator('tbody tr')).toHaveCount(12)
  expect(await page.evaluate(() => ({ node: typeof (window as any).require, process: typeof (window as any).process, bridge: Object.keys(window.results) })))
    .toEqual({ node: 'undefined', process: 'undefined', bridge: ['openRun', 'loadExample'] })
  const preferences = await desktop.evaluate(({ BrowserWindow }) => {
    const p = (BrowserWindow.getAllWindows()[0].webContents as unknown as { getLastWebPreferences(): Electron.WebPreferences }).getLastWebPreferences()
    return { sandbox: p.sandbox, contextIsolation: p.contextIsolation, nodeIntegration: p.nodeIntegration }
  })
  expect(preferences).toEqual({ sandbox: true, contextIsolation: true, nodeIntegration: false })
  await page.evaluate(() => window.open('https://example.com'))
  expect(desktop.windows()).toHaveLength(1)
  await page.getByRole('combobox', { name: 'Channel', exact: true }).selectOption('0')
  await page.screenshot({ path: 'test-results/viewer.png', fullPage: true })
  expect(errors).toEqual([])
})
