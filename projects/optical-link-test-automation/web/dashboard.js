// web/dashboard.tsx
import React, { useState } from "react";
import { createRoot } from "react-dom/client";
function App() {
  const [rows, setRows] = useState([]);
  const [message, setMessage] = useState("Run the default plan to see measurements.");
  const [busy, setBusy] = useState(false);
  async function run() {
    setBusy(true);
    setMessage("Running the wavelength and power sweep...");
    try {
      const response = await fetch("/api/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error);
      setRows(data.results);
      setMessage(`Finished ${data.results.length} settings. Classifier accuracy on ${data.evaluation.test_count} held-out simulated examples: ${(data.evaluation.accuracy * 100).toFixed(1)}%.`);
    } catch (error) {
      setMessage(String(error));
    } finally {
      setBusy(false);
    }
  }
  async function triage(row) {
    try {
      const response = await fetch("/api/triage", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(row) });
      const data = await response.json();
      setMessage(`${data.source}: ${data.advice}`);
    } catch (error) {
      setMessage(String(error));
    }
  }
  async function report() {
    const response = await fetch("/api/report", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ results: rows }) });
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "report.html";
    a.click();
    URL.revokeObjectURL(url);
  }
  return /* @__PURE__ */ React.createElement("main", null, /* @__PURE__ */ React.createElement("h1", null, "Optical test station"), /* @__PURE__ */ React.createElement("p", null, "Run a simulated fibre link through a repeatable test plan. Loss is signal power lost along the link; OSNR compares the signal with background noise."), /* @__PURE__ */ React.createElement("button", { onClick: run, disabled: busy }, busy ? "Running\u2026" : "Run test plan"), " ", rows.length > 0 && /* @__PURE__ */ React.createElement("button", { onClick: report }, "Download report"), /* @__PURE__ */ React.createElement("section", { "aria-live": "polite" }, message), rows.length > 0 && /* @__PURE__ */ React.createElement("table", null, /* @__PURE__ */ React.createElement("thead", null, /* @__PURE__ */ React.createElement("tr", null, /* @__PURE__ */ React.createElement("th", null, "Wavelength (nm)"), /* @__PURE__ */ React.createElement("th", null, "Launch (dBm)"), /* @__PURE__ */ React.createElement("th", null, "Loss (dB)"), /* @__PURE__ */ React.createElement("th", null, "OSNR (dB)"), /* @__PURE__ */ React.createElement("th", null, "Limits"), /* @__PURE__ */ React.createElement("th", null, "Model"), /* @__PURE__ */ React.createElement("th", null, "Next step"))), /* @__PURE__ */ React.createElement("tbody", null, rows.map((r, i) => /* @__PURE__ */ React.createElement("tr", { key: i }, /* @__PURE__ */ React.createElement("td", null, r.wavelength_nm), /* @__PURE__ */ React.createElement("td", null, r.launch_dbm), /* @__PURE__ */ React.createElement("td", null, r.loss_db?.toFixed(2) ?? "N/A"), /* @__PURE__ */ React.createElement("td", null, r.osnr_db?.toFixed(2) ?? "N/A"), /* @__PURE__ */ React.createElement("td", null, r.status), /* @__PURE__ */ React.createElement("td", null, r.model_label ?? "N/A"), /* @__PURE__ */ React.createElement("td", null, /* @__PURE__ */ React.createElement("button", { onClick: () => triage(r) }, "Triage")))))));
}
createRoot(document.getElementById("root")).render(/* @__PURE__ */ React.createElement(App, null));
