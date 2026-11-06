import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';

type Result = {wavelength_nm:number; launch_dbm:number; loss_db?:number; osnr_db?:number; status:string; model_label?:string; reason?:string};
function App() {
  const [rows, setRows] = useState<Result[]>([]);
  const [message, setMessage] = useState('Run the default plan to see measurements.');
  const [busy, setBusy] = useState(false);
  async function run() {
    setBusy(true); setMessage('Running the wavelength and power sweep...');
    try {
      const response = await fetch('/api/run', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
      const data = await response.json(); if (!response.ok) throw new Error(data.error);
      setRows(data.results); setMessage(`Finished ${data.results.length} settings. Classifier accuracy on ${data.evaluation.test_count} held-out simulated examples: ${(data.evaluation.accuracy * 100).toFixed(1)}%.`);
    } catch (error) { setMessage(String(error)); } finally { setBusy(false); }
  }
  async function triage(row:Result) {
    try { const response = await fetch('/api/triage', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(row)}); const data = await response.json(); setMessage(`${data.source}: ${data.advice}`); } catch (error) { setMessage(String(error)); }
  }
  async function report() {
    const response = await fetch('/api/report', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({results:rows})});
    const blob = await response.blob(); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href=url; a.download='report.html'; a.click(); URL.revokeObjectURL(url);
  }
  return <main><h1>Optical test station</h1><p>Run a simulated fibre link through a repeatable test plan. Loss is signal power lost along the link; OSNR compares the signal with background noise.</p><button onClick={run} disabled={busy}>{busy?'Running…':'Run test plan'}</button> {rows.length>0 && <button onClick={report}>Download report</button>}<section aria-live="polite">{message}</section>{rows.length>0 && <table><thead><tr><th>Wavelength (nm)</th><th>Launch (dBm)</th><th>Loss (dB)</th><th>OSNR (dB)</th><th>Limits</th><th>Model</th><th>Next step</th></tr></thead><tbody>{rows.map((r,i)=><tr key={i}><td>{r.wavelength_nm}</td><td>{r.launch_dbm}</td><td>{r.loss_db?.toFixed(2) ?? 'N/A'}</td><td>{r.osnr_db?.toFixed(2) ?? 'N/A'}</td><td>{r.status}</td><td>{r.model_label ?? 'N/A'}</td><td><button onClick={()=>triage(r)}>Triage</button></td></tr>)}</tbody></table>}</main>;
}
createRoot(document.getElementById('root')!).render(<App/>);
