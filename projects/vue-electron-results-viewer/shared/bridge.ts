import type { TestRun } from './results'
export type LoadResult = { kind: 'loaded'; fileName: string; run: TestRun } | { kind: 'canceled' } | { kind: 'error'; message: string }
export const IPC = { openRun: 'results:open-run', loadExample: 'results:load-example' } as const
export interface ResultsBridge { openRun(): Promise<LoadResult>; loadExample(): Promise<LoadResult> }
