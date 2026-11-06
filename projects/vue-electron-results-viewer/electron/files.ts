import { constants } from 'node:fs'
import { open } from 'node:fs/promises'
import { basename } from 'node:path'
import type { LoadResult } from '../shared/bridge'
import { parseRun } from '../shared/results'
export const MAX_FILE_BYTES = 2 * 1024 * 1024

export async function readRunFile(filePath: string): Promise<LoadResult> {
  try {
    const handle = await open(filePath, constants.O_RDONLY | (constants.O_NONBLOCK ?? 0))
    let content: string
    try {
      const stat = await handle.stat()
      if (!stat.isFile()) return { kind: 'error', message: 'Choose a regular JSON file, rather than a folder or special file.' }
      if (stat.size > MAX_FILE_BYTES) return { kind: 'error', message: 'File exceeds the 2 MB limit. Split it into smaller runs.' }
      // Read one extra byte so a growing file cannot bypass the size limit.
      const buffer = Buffer.alloc(MAX_FILE_BYTES + 1)
      let used = 0
      while (used < buffer.length) {
        const { bytesRead } = await handle.read(buffer, used, buffer.length - used, null)
        if (!bytesRead) break
        used += bytesRead
      }
      if (used > MAX_FILE_BYTES) return { kind: 'error', message: 'File exceeds the 2 MB limit. Split it into smaller runs.' }
      content = buffer.subarray(0, used).toString('utf8').replace(/^\uFEFF/, '')
    } finally { await handle.close() }
    let json: unknown
    try { json = JSON.parse(content) } catch { return { kind: 'error', message: 'This is not valid JSON. Check the file format in docs/file-format.md.' } }
    try { return { kind: 'loaded', fileName: basename(filePath), run: parseRun(json) } }
    catch (error) { return { kind: 'error', message: error instanceof Error ? error.message : 'Invalid test run.' } }
  } catch { return { kind: 'error', message: 'Could not read this file. Check that it still exists and you have permission to open it.' } }
}
