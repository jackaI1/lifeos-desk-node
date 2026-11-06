import { contextBridge, ipcRenderer } from 'electron'
import { IPC, type ResultsBridge, type LoadResult } from '../shared/bridge'
// One method per capability; raw ipcRenderer and paths never reach the renderer.
const bridge: ResultsBridge = {
  openRun: (): Promise<LoadResult> => ipcRenderer.invoke(IPC.openRun),
  loadExample: (): Promise<LoadResult> => ipcRenderer.invoke(IPC.loadExample),
}
contextBridge.exposeInMainWorld('results', bridge)
