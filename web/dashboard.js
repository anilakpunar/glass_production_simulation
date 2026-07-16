/* Dashboard tab: KPIs, charts, orders table, histograms, event log,
   run compare, Arena validation */
"use strict";

Chart.defaults.color = "#7d8b9c";
Chart.defaults.borderColor = "#263140";
Chart.defaults.font.family = "ui-monospace, Menlo, Consolas, monospace";
Chart.defaults.font.size = 10;

const ACCENT = "#2dd4bf";

const Dash = {
  charts: {},
  currentRun: null,
  runList: [],
  ordersRows: [],
  liveFollow: false,

  init() {
    const pane = document.getElementById("tab-dash");
    pane.innerHTML = `
      <div class="dash-toolbar">
        <label class="muted">Koşu:</label>
        <select id="dash-run"></select>
        <button class="btn" id="dash-refresh">Yenile</button>
        <label class="muted">Karşılaştır:</label>
        <select id="dash-run2"><option value="">—</option></select>
        <span id="dash-note" class="muted"></span>
      </div>
      <div class="kpi-row" id="kpi-row"></div>
      <div class="dash-grid">
        <div class="dash-card"><h3>Kaynak Kullanımları</h3><canvas id="ch-util"></canvas></div>
        <div class="dash-card"><h3>Kullanım Zaman Serisi</h3><canvas id="ch-utilts"></canvas></div>
        <div class="dash-card"><h3>Tampon Zaman Serileri</h3><canvas id="ch-buf"></canvas>
          <div id="buf-pcts" class="pct-table"></div></div>
        <div class="dash-card"><h3>Throughput (IGU/saat)</h3><canvas id="ch-thr"></canvas></div>
        <div class="dash-card"><h3>Doluluk Histogramları</h3><canvas id="ch-fill"></canvas></div>
        <div class="dash-card"><h3>Çevrim Süresi Dağılımları</h3><canvas id="ch-cycle"></canvas>
          <div id="cycle-stats" class="pct-table"></div></div>
        <div class="dash-card wide"><h3>Sipariş Tablosu
            <button class="btn" id="btn-orders-csv" style="float:right;padding:3px 10px">CSV indir</button></h3>
          <div class="filter-row">
            <input id="ord-filter" placeholder="filtre: sipariş no / durum">
            <select id="ord-status"><option value="">tümü</option>
              <option value="done">tamamlandı</option><option value="in_progress">devam</option>
              <option value="waiting">bekliyor</option></select>
          </div>
          <div id="orders-tablebox"></div></div>
        <div class="dash-card wide"><h3>Olay Günlüğü
            <a class="btn" id="btn-elog-dl" style="float:right;padding:3px 10px" download>JSONL indir</a>
            <label style="float:right;margin-right:12px;font-size:12px">
              <input type="checkbox" id="elog-live"> canlı takip</label></h3>
          <div class="filter-row">
            <input id="elog-station" placeholder="istasyon">
            <input id="elog-event" placeholder="olay (SEIZE, FLUSH…)">
            <input id="elog-t0" type="number" placeholder="dk ≥"><input id="elog-t1" type="number" placeholder="dk ≤">
            <button class="btn" id="btn-elog-apply">Uygula</button>
          </div>
          <div id="eventlog-box"></div></div>
        <div class="dash-card wide" id="compare-card" style="display:none">
          <h3>Koşu Karşılaştırma</h3><div id="compare-box"></div></div>
        <div class="dash-card wide"><h3>Arena Doğrulama (A.4)</h3><div id="valid-box">
          <p class="muted">Koşu seçince A.4 referans tablosuyla karşılaştırılır.</p></div></div>
      </div>`;
    document.getElementById("dash-refresh").addEventListener("click", () => this.refreshRuns(true));
    document.getElementById("dash-run").addEventListener("change",
      e => this.loadRun(e.target.value));
    document.getElementById("dash-run2").addEventListener("change",
      e => this.compare(e.target.value));
    document.getElementById("ord-filter").addEventListener("input", () => this.renderOrders());
    document.getElementById("ord-status").addEventListener("change", () => this.renderOrders());
    document.getElementById("btn-orders-csv").addEventListener("click", () => this.exportOrders());
    document.getElementById("btn-elog-apply").addEventListener("click", () => this.loadEventLog());
    document.getElementById("elog-live").addEventListener("change",
      e => { this.liveFollow = e.target.checked; });
    App.onFrame(d => {
      if (this.liveFollow && d.events_tail) this.renderEventRows(d.events_tail.slice(-200));
    });
  },

  onShow() { if (!this.runList.length) this.refreshRuns(true); },
  onRunFinished(runId) { this.refreshRuns(true, runId); },

  async refreshRuns(load, selectId) {
    const d = await fetch("/api/results").then(r => r.json());
    this.runList = d.runs;
    const opts = d.runs.map(r =>
      `<option value="${r.run_id}">${r.run_id} · ${r.days}g · IGU ${App.fmt(r.igu_done, 0)}</option>`).join("");
    document.getElementById("dash-run").innerHTML = opts;
    document.getElementById("dash-run2").innerHTML = `<option value="">—</option>` + opts;
    const target = selectId || (d.runs[0] && d.runs[0].run_id);
    if (load && target) {
      document.getElementById("dash-run").value = target;
      this.loadRun(target);
    }
  },

  async fetchFile(runId, name) {
    const r = await fetch(`/api/results/${runId}/file/${name}`);
    if (!r.ok) return null;
    if (name.endsWith(".json")) return r.json();
    return r.text();
  },

  async loadRun(runId) {
    if (!runId) return;
    this.currentRun = runId;
    document.getElementById("dash-note").textContent = "yükleniyor…";
    const [summaryRaw, series, dists, ordersCsv] = await Promise.all([
      this.fetchFile(runId, "summary.json"),
      this.fetchFile(runId, "series.json"),
      this.fetchFile(runId, "distributions.json"),
      this.fetchFile(runId, "orders.csv"),
    ]);
    const summary = summaryRaw && summaryRaw.replications && Array.isArray(summaryRaw.replications)
      ? summaryRaw.replications[0] : summaryRaw;
    document.getElementById("dash-note").textContent =
      summaryRaw && summaryRaw.aggregate ? `${summaryRaw.aggregate.replications || ""} replikasyon (ilki gösteriliyor)` : "";
    if (summary) this.renderKPIs(summary);
    if (summary) this.renderUtil(summary);
    if (series) this.renderSeries(series);
    if (dists) this.renderDists(dists);
    if (ordersCsv) { this.parseOrders(ordersCsv); this.renderOrders(); }
    document.getElementById("btn-elog-dl").href = `/api/results/${runId}/file/event_log.jsonl`;
    this.loadEventLog();
    this.loadValidation(runId);
  },

  renderKPIs(s) {
    const util = s.utilization;
    const bottleneck = Object.entries(util).sort((a, b) => b[1] - a[1])[0];
    const wip = s.counters_final ?
      (s.counters_final.order_buffer + s.counters_final.temper_build +
       s.counters_final.igu_gate_q) : "—";
    const items = [
      ["Tamamlanan IGU", App.fmt(s.igu_done, 0), `${s.orders_done}/${s.orders_created} sipariş`],
      ["Zamanında Teslim", s.otd_pct === null ? "—" : s.otd_pct.toFixed(1) + "%", "dueDate bazlı"],
      ["Ort. Akış Kesim→IGU", App.fmt(s.tallies.cycle_kesim_igu_min.mean, 1) + " dk",
        "IGU çevrimi " + App.fmt(s.tallies.cycle_igu_min.mean, 1) + " dk"],
      ["Jumbo Doluluk", (s.tallies.jumbo_fill_combined_mean * 100).toFixed(1) + "%",
        "flush dahil ortalama"],
      ["Temper Doluluk", (s.tallies.temper_fill_combined_mean * 100).toFixed(1) + "%",
        "yatak genişlik doluluğu"],
      ["Darboğaz", bottleneck[0], (bottleneck[1] * 100).toFixed(1) + "% kullanım"],
      ["Throughput", App.fmt(s.throughput_per_h, 1) + "/saat",
        `${App.fmt(s.wall_seconds, 1)} sn duvar saati`],
    ];
    document.getElementById("kpi-row").innerHTML = items.map(([l, v, sub]) =>
      `<div class="kpi"><label>${l}</label><b>${v}</b><br><small>${sub}</small></div>`).join("");
  },

  chart(id, cfg) {
    if (this.charts[id]) this.charts[id].destroy();
    this.charts[id] = new Chart(document.getElementById(id), cfg);
  },

  renderUtil(s) {
    const entries = Object.entries(s.utilization);
    this.chart("ch-util", {
      type: "bar",
      data: { labels: entries.map(e => e[0]),
        datasets: [{ data: entries.map(e => +(e[1] * 100).toFixed(2)),
          backgroundColor: entries.map(e => e[1] > 0.95 ? "#f87171" : ACCENT) }] },
      options: { indexAxis: "y", plugins: { legend: { display: false } },
        scales: { x: { max: 100, title: { display: true, text: "%" } } } }
    });
  },

  renderSeries(series) {
    const t = series.map(p => (p.sim_min / 60).toFixed(1));
    const mk = (label, data, color, fill = false) =>
      ({ label, data, borderColor: color, backgroundColor: color + "33",
         pointRadius: 0, borderWidth: 1.5, fill, tension: .25 });
    this.chart("ch-utilts", {
      type: "line",
      data: { labels: t, datasets: [
        mk("kesim_1", series.map(p => p.util.kesim_1 * 100), "#2dd4bf"),
        mk("igu_1", series.map(p => p.util.igu_1 * 100), "#60a5fa"),
        mk("fırın 1000", series.map(p => p.util.furnace_1000 * 100), "#fb923c"),
        mk("fırın 1600", series.map(p => p.util.furnace_1600 * 100), "#f472b6"),
      ]},
      options: { scales: { x: { title: { display: true, text: "saat" } },
        y: { max: 100 } }, plugins: { legend: { position: "bottom" } } }
    });
    this.chart("ch-buf", {
      type: "line",
      data: { labels: t, datasets: [
        mk("Order Buffer", series.map(p => p.order_buffer), "#2dd4bf", true),
        mk("Token WIP", series.map(p => p.token_wip), "#fbbf24"),
        mk("Match kuyruğu", series.map(p => p.match_q), "#f472b6"),
        mk("IGU sıra kapısı", series.map(p => p.igu_gate_q), "#60a5fa"),
      ]},
      options: { scales: { x: { title: { display: true, text: "saat" } } },
        plugins: { legend: { position: "bottom" } } }
    });
    // P50/P95/P99/max table for buffers
    const stats = (arr) => {
      const s = arr.slice().sort((a, b) => a - b);
      const pc = p => s[Math.min(s.length - 1, Math.floor(p * (s.length - 1)))];
      return [pc(.5), pc(.95), pc(.99), s[s.length - 1]];
    };
    const rows = [["Order Buffer", series.map(p => p.order_buffer)],
      ["Token WIP", series.map(p => p.token_wip)],
      ["Match kuyruğu", series.map(p => p.match_q)],
      ["IGU sıra kapısı", series.map(p => p.igu_gate_q)]];
    document.getElementById("buf-pcts").innerHTML =
      `<table class="data"><tr><th>tampon</th><th>P50</th><th>P95</th><th>P99</th><th>maks</th></tr>` +
      rows.map(([n, a]) => { const [p50, p95, p99, mx] = stats(a);
        return `<tr><td>${n}</td><td>${p50}</td><td>${p95}</td><td>${p99}</td><td>${mx}</td></tr>`;
      }).join("") + "</table>";
    this.chart("ch-thr", {
      type: "line",
      data: { labels: t, datasets: [
        mk("IGU/saat", series.map(p => p.throughput_h), ACCENT, true)] },
      options: { plugins: { legend: { display: false } },
        scales: { x: { title: { display: true, text: "saat" } } } }
    });
  },

  hist(values, bins, min, max) {
    const h = new Array(bins).fill(0);
    const w = (max - min) / bins;
    values.forEach(v => {
      const i = Math.min(bins - 1, Math.max(0, Math.floor((v - min) / w)));
      h[i]++;
    });
    return { h, labels: h.map((_, i) => (min + (i + .5) * w).toFixed(2)) };
  },

  renderDists(d) {
    const jf = this.hist(d.jumbo_fill, 20, 0.3, 1.0);
    const jff = this.hist(d.jumbo_fill_flush, 20, 0.3, 1.0);
    const tf = this.hist(d.temper_fill.concat(d.temper_fill_flush), 20, 0, 1.0);
    this.chart("ch-fill", {
      type: "bar",
      data: { labels: jf.labels, datasets: [
        { label: "jumbo fill", data: jf.h, backgroundColor: ACCENT + "aa" },
        { label: "jumbo fill (flush)", data: jff.h, backgroundColor: "#fb923caa" },
        { label: "temper fill", data: tf.h, backgroundColor: "#60a5fa66" },
      ]},
      options: { plugins: { legend: { position: "bottom" } },
        scales: { x: { ticks: { maxTicksLimit: 10 } } } }
    });
    const ck = d.cycle_kesim_igu, ci = d.cycle_igu, co = d.cycle_order_igu;
    const cmax = Math.min(Math.max(...ck, 1) * 1.02, 300);
    const ckh = this.hist(ck, 24, 0, cmax);
    const cih = this.hist(ci, 24, 0, cmax);
    this.chart("ch-cycle", {
      type: "bar",
      data: { labels: ckh.labels, datasets: [
        { label: "Kesim→IGU (dk)", data: ckh.h, backgroundColor: ACCENT + "aa" },
        { label: "IGU çevrimi (dk)", data: cih.h, backgroundColor: "#f472b6aa" },
      ]},
      options: { plugins: { legend: { position: "bottom" } },
        scales: { x: { ticks: { maxTicksLimit: 10 },
          title: { display: true, text: "dakika" } } } }
    });
    const box = arr => {
      const s = arr.slice().sort((a, b) => a - b);
      const q = p => s[Math.floor(p * (s.length - 1))] || 0;
      return `min ${q(0).toFixed(1)} · Q1 ${q(.25).toFixed(1)} · medyan ${q(.5).toFixed(1)}
        · Q3 ${q(.75).toFixed(1)} · maks ${q(1).toFixed(1)}`;
    };
    document.getElementById("cycle-stats").innerHTML =
      `<table class="data">
        <tr><td>Kesim→IGU</td><td>${box(ck)}</td></tr>
        <tr><td>IGU çevrimi</td><td>${box(ci)}</td></tr>
        <tr><td>Sipariş→IGU</td><td>${box(co)}</td></tr></table>`;
  },

  parseOrders(csv) {
    const lines = csv.trim().split(/\r?\n/);
    const head = lines[0].split(",").map(s => s.trim());
    this.ordersRows = lines.slice(1).map(ln => {
      const cells = ln.split(",").map(s => s.trim());
      return Object.fromEntries(head.map((h, i) => [h, cells[i] ?? ""]));
    });
  },

  renderOrders() {
    const f = document.getElementById("ord-filter").value.toLowerCase();
    const st = document.getElementById("ord-status").value;
    let rows = this.ordersRows;
    if (st) rows = rows.filter(r => r.status === st);
    if (f) rows = rows.filter(r => r.orderNo.includes(f) || r.status.includes(f));
    const stNames = { done: "tamam", in_progress: "devam", waiting: "bekliyor" };
    document.getElementById("orders-tablebox").innerHTML =
      `<table class="data"><thead><tr><th>No</th><th>adet</th><th>pane</th>
        <th>sipariş günü</th><th>termin</th><th>ilk kesim (dk)</th><th>son IGU (dk)</th>
        <th>tamam</th><th>akış (dk)</th><th>gecikme (gün)</th><th>durum</th></tr></thead><tbody>` +
      rows.slice(0, 500).map(r => {
        const late = r.lateness_days !== "" ? Number(r.lateness_days) : null;
        const lateCls = late === null ? "" : late > 0 ? "bad" : "ok";
        return `<tr><td>${r.orderNo}</td><td>${r.qty}</td><td>${r.paneCount}</td>
        <td>${r.orderDate}</td><td>${r.dueDate}</td><td>${r.firstCut_min}</td>
        <td>${r.lastIGU_min}</td><td>${r.done}</td><td>${r.flow_min}</td>
        <td class="${lateCls}">${r.lateness_days}</td>
        <td>${stNames[r.status] || r.status}</td></tr>`;
      }).join("") + "</tbody></table>";
  },

  exportOrders() {
    if (!this.currentRun) return;
    location.href = `/api/results/${this.currentRun}/file/orders.csv`;
  },

  async loadEventLog() {
    if (!this.currentRun) return;
    const box = document.getElementById("eventlog-box");
    box.innerHTML = "<span class='muted'>yükleniyor…</span>";
    const txt = await this.fetchFile(this.currentRun, "event_log.jsonl");
    if (!txt) { box.innerHTML = "<span class='muted'>olay günlüğü yok (event_log=false)</span>"; return; }
    const stF = document.getElementById("elog-station").value.trim();
    const evF = document.getElementById("elog-event").value.trim().toUpperCase();
    const t0 = Number(document.getElementById("elog-t0").value) || 0;
    const t1 = Number(document.getElementById("elog-t1").value) || Infinity;
    const rows = [];
    const lines = txt.split("\n");
    for (let i = 0; i < lines.length && rows.length < 800; i++) {
      if (!lines[i]) continue;
      const e = JSON.parse(lines[i]);
      if (stF && !e.station.includes(stF)) continue;
      if (evF && e.event !== evF) continue;
      if (e.sim_min < t0 || e.sim_min > t1) continue;
      rows.push(e);
    }
    this.renderEventRows(rows);
  },

  renderEventRows(rows) {
    document.getElementById("eventlog-box").innerHTML = rows.map(e =>
      `<div class="row"><span class="muted">${e.sim_min.toFixed(2)} dk</span>
       <b>${e.station}</b> ${e.event} ${e.entity}
       <span class="muted">${JSON.stringify(e.payload)}</span></div>`).join("");
  },

  async compare(otherId) {
    const card = document.getElementById("compare-card");
    if (!otherId || !this.currentRun) { card.style.display = "none"; return; }
    card.style.display = "block";
    const [a, b] = await Promise.all([
      fetch(`/api/results/${this.currentRun}`).then(r => r.json()),
      fetch(`/api/results/${otherId}`).then(r => r.json())]);
    const rows = [
      ["IGU", "igu_done"], ["Sipariş", "orders_created"], ["Adet", "units_ordered"],
      ["Kesim_1 kullanım", "util_kesim_1"], ["IGU kullanım", "util_igu_1"],
      ["Jumbo doluluk", "jumbo_fill"], ["Temper doluluk", "temper_fill"]];
    document.getElementById("compare-box").innerHTML =
      `<table class="data"><tr><th>metrik</th><th>${a.run_id}</th><th>${b.run_id}</th><th>Δ%</th></tr>` +
      rows.map(([l, k]) => {
        const va = a[k], vb = b[k];
        const delta = va ? ((vb - va) / va * 100).toFixed(1) : "—";
        return `<tr><td>${l}</td><td>${App.fmt(va, 3)}</td><td>${App.fmt(vb, 3)}</td>
          <td class="${delta > 0 ? 'ok' : 'bad'}">${delta}%</td></tr>`;
      }).join("") + "</table>";
  },

  async loadValidation(runId) {
    const box = document.getElementById("valid-box");
    try {
      const d = await fetch(`/api/validation/${runId}`).then(r => {
        if (!r.ok) throw new Error(); return r.json(); });
      box.innerHTML =
        `<p class="muted">${d.n} replikasyon ortalaması vs Arena Senaryo 3 referansı</p>
        <table class="data"><tr><th>metrik</th><th>Arena</th><th>bu koşu</th>
        <th>tolerans</th><th>durum</th></tr>` +
        d.rows.map(r => {
          const status = r.ok === null ? "ℹ️" : r.ok ? "✅" : "❌";
          const tol = r.ok === null ? "bilgi" :
            r.kind === "rel" ? `±%${(r.tol * 100).toFixed(0)}` : `±${r.tol}`;
          return `<tr title="${r.root_cause || ''}"><td>${r.label}</td>
            <td>${App.fmt(r.arena, 4)}</td><td>${App.fmt(r.mean, 4)}</td>
            <td>${tol}</td><td>${status}</td></tr>`;
        }).join("") + "</table>" +
        `<p class="muted">❌ satırların üzerine gelince kök neden açıklaması görünür;
         tam rapor: <code>validation_report.md</code></p>`;
    } catch {
      box.innerHTML = "<p class='muted'>summary.json bulunamadı.</p>";
    }
  }
};
