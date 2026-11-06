// @vitest-environment node
import { expect, it } from 'vitest'
import { build } from 'esbuild'
import { execFileSync } from 'node:child_process'
import { mkdtemp, writeFile, rm } from 'node:fs/promises'
import { join, resolve } from 'node:path'
import { tmpdir } from 'node:os'

it.skipIf(process.platform === 'win32')('rejects a named pipe without blocking the file reader', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'viewer-pipe-test-'))
  try {
    const fifo = join(dir, 'pipe.json')
    execFileSync('mkfifo', [fifo])
    const runner = join(dir, 'reader.cjs')
    const bundle = await build({ entryPoints: [resolve('electron/files.ts')], bundle: true, platform: 'node', format: 'cjs', write: false })
    await writeFile(runner, bundle.outputFiles[0].text + '\nmodule.exports.readRunFile(process.argv[2]).then(result => console.log(JSON.stringify(result)))\n')
    // A blocking-open regression gets a timeout and its exact child is killed.
    const output = execFileSync(process.execPath, [runner, fifo], { encoding: 'utf8', timeout: 1500, killSignal: 'SIGKILL' })
    expect(JSON.parse(output)).toMatchObject({ kind: 'error', message: expect.any(String) })
  } finally { await rm(dir, { recursive: true, force: true }) }
})
