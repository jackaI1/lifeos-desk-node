# How the desktop app fits together

The main process is the part of Electron allowed to read local files. The renderer is the Vue screen. A preload script sits between them and exposes two typed methods, `openRun()` and `loadExample()`. Their shared TypeScript contract is in `shared/bridge.ts`; each returns a loaded run, a cancellation, or a readable error.

`electron/main.ts` owns the native file picker. The renderer cannot supply an arbitrary file path or IPC channel. The main process checks that requests came from its own top-level window and bundled page. `electron/files.ts` opens the selected file without waiting on special files such as named pipes, reads at most the limit plus one byte, closes the handle even on failure, and calls `parseRun()` in `shared/results.ts`. Runtime validation is necessary because TypeScript cannot guarantee the shape of a JSON file supplied by a user.

The window uses a sandbox, context isolation and disabled Node integration. Its content security policy blocks network connections and remote scripts. New windows, navigation and permission requests are denied. These choices follow [Electron's security guidance](https://www.electronjs.org/docs/latest/tutorial/security). Only the file name, rather than the selected private path, is sent to the renderer. No run history or telemetry is stored.

`src/App.vue` owns the loaded run, selected channel and table filters. A canceled or invalid load preserves the last valid run. Loading a new valid run resets channel, filter and pagination. Each channel keeps its own units and limits so the viewer never puts voltage and temperature on the same axis.

`src/components/RunChart.vue` draws a scaled SVG plot, including elapsed-time spacing, a tolerance band, dashed limit lines and larger red markers outside the limits. Values and result labels are also available in a table, so color and hovering are not required to interpret the run. All points stay on the plot while the table shows 100 readings per page. A single reading and equal limits receive a nonzero plot extent.

# Tests and builds

Vitest exercises actual Vue components and the parser and disk reader. The component tests replace the bridge because Electron is not running in that test environment. Playwright launches actual Electron, including in CI after packaging, following [Electron's automated testing approach](https://www.electronjs.org/docs/latest/tutorial/automated-testing). Only `dialog.showOpenDialog` is replaced so the tests can select a temporary file without automating an operating-system dialog. The click, bridge, sender check, file read, validation and rendering are real.

Desktop tests close their owned Electron application after every case, remove temporary files, and record PID, start time, port (none), cleanup method and an exit check in `test-results/resources.jsonl`. One worker avoids concurrent desktop fixtures. CI uploads test evidence and installers as workflow artifacts. The packaged checks launch the extracted app, rather than the installer wizard itself.

The app is unsigned. Linux and Windows CI produce packages, but installer UX, signing, macOS packaging and real instrument integration remain outside this version. This is a viewer: a range flag identifies a reading for review and does not diagnose a hardware fault.
