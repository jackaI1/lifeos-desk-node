import { app, BrowserWindow, dialog, ipcMain, session, type IpcMainInvokeEvent } from 'electron'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { IPC, type LoadResult, type ResultsBridge } from '../shared/bridge'
import { readRunFile } from './files'

let mainWindow: BrowserWindow | null = null
let opening = false
const rendererPath = join(__dirname, '../dist/index.html')
const rendererUrl = pathToFileURL(rendererPath).href

function trusted(event: IpcMainInvokeEvent): boolean {
  return !!mainWindow && event.sender === mainWindow.webContents &&
    event.senderFrame === mainWindow.webContents.mainFrame && event.senderFrame.url === rendererUrl
}
function handle(channel: typeof IPC[keyof typeof IPC], action: ResultsBridge[keyof ResultsBridge]) {
  ipcMain.handle(channel, async (event): Promise<LoadResult> => {
    if (!trusted(event)) return { kind: 'error', message: 'This window is not allowed to open runs.' }
    return action()
  })
}
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1180, height: 900, minWidth: 650, minHeight: 600,
    title: 'Results viewer', backgroundColor: '#f5f7fa', autoHideMenuBar: true,
    webPreferences: { preload: join(__dirname, 'preload.cjs'), sandbox: true, contextIsolation: true, nodeIntegration: false, webSecurity: true },
  })
  mainWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }))
  mainWindow.webContents.on('will-navigate', event => event.preventDefault())
  mainWindow.on('closed', () => { mainWindow = null })
  void mainWindow.loadFile(rendererPath)
}
app.whenReady().then(() => {
  session.defaultSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false))
  session.defaultSession.setPermissionCheckHandler(() => false)
  handle(IPC.openRun, async () => {
    if (!mainWindow || opening) return { kind: 'canceled' }
    opening = true
    try {
      const selection = await dialog.showOpenDialog(mainWindow, { title: 'Open a test-run JSON file', properties: ['openFile'], filters: [{ name: 'Test runs', extensions: ['json'] }] })
      if (selection.canceled || !selection.filePaths[0]) return { kind: 'canceled' }
      return await readRunFile(selection.filePaths[0])
    } catch { return { kind: 'error', message: 'Could not open the file picker. Try again.' } }
    finally { opening = false }
  })
  handle(IPC.loadExample, () => readRunFile(join(app.getAppPath(), 'samples/bench-run.json')))
  createWindow()
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow() })
})
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit() })
