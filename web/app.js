/* IGLINE-PySim — shell: tabs, websocket, top bar, run control */
"use strict";

const App = {
  snapshot: null,
  prevSnapshot: null,
  snapTime: 0,          // wall ms of last frame
  prevSnapTime: 0,
  status: { state: "idle" },
  i18n: null,
  listeners: [],        // fn(snapshot) on every frame
  utilHistory: {},      // station -> [{t, util}]
  lastFinishedRun: null,

  t(group, key) {
    return (this.i18n && this.i18n[group] && this.i18n[group][key]) || key;
  },

  onFrame(fn) { this.listeners.push(fn); },

  async init() {
    this.i18n = await fetch("/static/i18n_tr.json").then(r => r.json());
    this.initTabs();
    this.initSpeedBox();
    this.connectWS();
    await Params.init();
    Scada.init();
    Dash.init();
  },

  initTabs() {
    document.querySelectorAll(".tab").forEach(btn => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".tab").forEach(b => b.classList.remove("active"));
        document.querySelectorAll(".tabpane").forEach(p => p.classList.remove("active"));
        btn.classList.add("active");
        document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
        if (btn.dataset.tab === "dash") Dash.onShow();
      });
    });
  },

  initSpeedBox() {
    document.querySelectorAll("#speedbox .sp").forEach(btn => {
      btn.addEventListener("click", async () => {
        const sp = btn.dataset.sp;
        if (sp === "pause") await fetch("/api/pause", { method: "POST" });
        else if (sp === "resume") await fetch("/api/resume", { method: "POST" });
        else if (sp === "step") await fetch("/api/step", { method: "POST" });
        else {
          await fetch("/api/speed", {
            method: "POST", headers: { "content-type": "application/json" },
            body: JSON.stringify({ speed: sp === "max" ? "max" : Number(sp) })
          });
          document.querySelectorAll("#speedbox .spd").forEach(b => b.classList.remove("active"));
          btn.classList.add("active");
        }
      });
    });
  },

  connectWS() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/state`);
    ws.onmessage = ev => {
      const d = JSON.parse(ev.data);
      if (d.run) this.setStatus(d.run);
      if (d.idle) return;
      this.prevSnapshot = this.snapshot;
      this.prevSnapTime = this.snapTime;
      this.snapshot = d;
      this.snapTime = performance.now();
      this.trackUtil(d);
      this.updateTopbar(d);
      this.listeners.forEach(fn => fn(d));
      if (d.final && d.run && d.run.run_id) {
        if (this.lastFinishedRun !== d.run.run_id) {
          this.lastFinishedRun = d.run.run_id;
          Dash.onRunFinished(d.run.run_id);
        }
      }
    };
    ws.onclose = () => setTimeout(() => this.connectWS(), 1500);
  },

  setStatus(st) {
    this.status = st;
    const chip = document.getElementById("runstate");
    const names = { idle: "boşta", running: "çalışıyor", paused: "duraklatıldı",
                    finished: "tamamlandı", error: "hata" };
    chip.className = "chip " + st.state;
    let txt = names[st.state] || st.state;
    if (st.replication && st.replication.total > 1)
      txt += ` (${st.replication.current}/${st.replication.total})`;
    chip.textContent = txt;
    if (st.error) chip.title = st.error;
  },

  trackUtil(d) {
    if (!d.stations) return;
    for (const [name, s] of Object.entries(d.stations)) {
      if (s.util === undefined) continue;
      const h = this.utilHistory[name] || (this.utilHistory[name] = []);
      h.push({ t: d.sim_min, u: s.util });
      if (h.length > 400) h.splice(0, h.length - 400);
    }
  },

  updateTopbar(d) {
    document.getElementById("simclock").textContent = d.sim_clock || "—";
    document.getElementById("simday").textContent =
      `gün ${Math.floor(d.sim_min / 540) + 1}/10 · ${d.sim_min.toFixed(1)} dk`;
    document.getElementById("k-thr").textContent =
      d.kpis ? d.kpis.throughput_per_h.toFixed(0) : "—";
    document.getElementById("k-cur").textContent = d.counters.cur_order;
    document.getElementById("k-igucur").textContent = d.counters.igu_cur_order;
    document.getElementById("k-igu").textContent = d.counters.igu_done.toLocaleString("tr");
    document.getElementById("k-starve").classList.toggle("on", d.counters.starve === 1);
    document.getElementById("progressfill").style.width =
      ((d.progress || 0) * 100).toFixed(1) + "%";
  },

  fmt(x, d = 1) {
    if (x === null || x === undefined) return "—";
    return Number(x).toLocaleString("tr", { maximumFractionDigits: d });
  }
};

window.addEventListener("DOMContentLoaded", () => App.init());
