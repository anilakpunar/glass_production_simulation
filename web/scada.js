/* SCADA tab: SVG line mimic, live animation, detail panel, alarm strip */
"use strict";

const TYPE_PALETTE = ["#2dd4bf", "#60a5fa", "#f472b6", "#fbbf24", "#a78bfa",
  "#34d399", "#fb923c", "#38bdf8", "#f87171", "#c084fc", "#facc15", "#4ade80"];

const NS = "http://www.w3.org/2000/svg";

const Scada = {
  svg: null,
  refs: {},
  paths: [],
  particles: [],
  selected: null,
  raf: null,

  init() {
    this.build();
    App.onFrame(d => this.update(d));
    const loop = () => { this.animate(); this.raf = requestAnimationFrame(loop); };
    loop();
  },

  el(tag, attrs, parent, text) {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v);
    if (text !== undefined) e.textContent = text;
    (parent || this.svg).appendChild(e);
    return e;
  },

  build() {
    const box = document.getElementById("scada-svgbox");
    box.innerHTML = "";
    this.svg = document.createElementNS(NS, "svg");
    this.svg.setAttribute("viewBox", "0 0 1560 640");
    box.appendChild(this.svg);

    // ---------------- conveyor paths (drawn first, under cards) ----------
    const conv = [
      ["p_pool_nest", "M 190 105 H 240"],
      ["p_nest_tok", "M 390 105 H 428"],
      ["p_tok_k1", "M 472 90 C 495 90 495 65 518 65"],
      ["p_tok_k2", "M 472 120 C 495 120 495 155 518 155"],
      ["p_k1_buf", "M 708 65 C 735 65 735 105 758 105"],
      ["p_k2_buf", "M 708 155 C 735 155 735 105 758 105"],
      ["p_buf_seq", "M 804 105 H 852"],
      ["p_seq_rodaj", "M 900 130 C 900 230 60 190 108 296"],
      ["p_rodaj_dia", "M 212 366 C 250 366 240 366 272 366"],
      ["p_dia_bed", "M 332 366 H 380"],
      ["p_bed_f1", "M 550 340 C 575 330 575 307 598 307"],
      ["p_bed_f2", "M 550 390 C 575 390 575 387 598 387"],
      ["p_f1_match", "M 900 307 C 930 307 930 366 948 366"],
      ["p_f2_match", "M 900 387 C 930 387 930 366 948 366"],
      ["p_bypass", "M 302 396 C 302 480 900 480 948 396"],
      ["p_match_gate", "M 1118 366 H 1148"],
      ["p_gate_igu", "M 1192 366 H 1228"],
      ["p_igu_ship", "M 1448 366 H 1472"]
    ];
    for (const [id, d] of conv) {
      this.el("path", { d, class: "conv", id });
      const flow = this.el("path", { d, class: "conv-flow", id: id + "_f" });
      this.paths.push(flow);
    }
    this.el("text", { x: 585, y: 475, class: "lane-label" }, null, "BYPASS HATTI (temper yok)");

    // ---------------- station cards --------------------------------------
    this.card("pool", 40, 60, 150, 90, "SİPARİŞ HAVUZU", ["hold_glass", "orders"]);
    this.card("nesting", 240, 60, 150, 90, "NESTING", ["tok", "jinfo"], "nesting");
    this.vbar("tokbar", 430, 50, 42, 112, "TOKEN RAFI", 8);
    this.card("kesim_1", 518, 30, 190, 70, "KESİM 1", ["job", "left"], "kesim_1");
    this.card("kesim_2", 518, 120, 190, 70, "KESİM 2", ["job", "left"], "kesim_2");
    this.vbar("bufbar", 758, 40, 46, 130, "ORDER BUFFER", 2500);
    this.card("seq", 852, 60, 96, 90, "SEQUENCER", ["cur", "win"], "sequencer");
    this.card("rodaj_1", 42, 296, 170, 62, "RODAJ 1", ["dim"], "rodaj_1");
    this.card("rodaj_2", 42, 382, 170, 62, "RODAJ 2", ["dim"], "rodaj_2");
    // temper decision diamond
    const dia = this.el("g", { class: "clickable" });
    this.el("polygon", { points: "302,336 332,366 302,396 272,366", class: "diamond" }, dia);
    this.el("text", { x: 302, y: 362, class: "st-info", "text-anchor": "middle" }, dia, "temper?");
    this.el("text", { x: 302, y: 375, class: "st-info", "text-anchor": "middle" }, dia, "vFurnaceOf");
    this.card("temper_build", 380, 316, 170, 100, "YATAK OLUŞTURMA", ["beds", "cnt"], "temper_build");
    this.tunnel("furnace_1000", 598, 280, 302, 54, "FIRIN 1000 (1050 mm)");
    this.tunnel("furnace_1600", 598, 360, 302, 54, "FIRIN 1600");
    this.card("match", 948, 316, 170, 100, "SORTING 2 / MATCH", ["q1", "q2"], "match");
    this.vbar("gatebar", 1148, 316, 44, 100, "IGU SIRA", 800);
    this.iguCard(1228, 300, 220, 132);
    this.card("ship", 1472, 330, 76, 72, "SEVKİYAT", ["done"]);

    // labels under gate
    this.refs.gate_cur = this.el("text", { x: 1170, y: 440, class: "buf-val" }, null, "—");
    this.el("text", { x: 1170, y: 452, class: "buf-label" }, null, "vIGUCurOrder");
  },

  card(id, x, y, w, h, title, infoKeys, station) {
    const g = this.el("g", {});
    const rect = this.el("rect", {
      x, y, width: w, height: h, rx: 10,
      class: "st-card" + (station ? " clickable" : "")
    }, g);
    this.el("circle", { cx: x + 14, cy: y + 15, r: 5, class: "led", fill: "#39434f", id: `led_${id}` }, g);
    this.el("text", { x: x + 26, y: y + 19, class: "st-name" }, g, title);
    const infos = infoKeys.map((k, i) =>
      this.el("text", { x: x + 12, y: y + 38 + i * 15, class: "st-info", id: `inf_${id}_${k}` }, g, ""));
    const utilTxt = this.el("text", {
      x: x + w - 10, y: y + 19, class: "st-info hi", "text-anchor": "end", id: `util_${id}`
    }, g, "");
    this.refs[id] = { rect, infos: Object.fromEntries(infoKeys.map((k, i) => [k, infos[i]])), utilTxt };
    if (station) {
      rect.addEventListener("click", () => this.select(station, id));
    }
    return g;
  },

  vbar(id, x, y, w, h, label, cap) {
    const g = this.el("g", {});
    this.el("rect", { x, y, width: w, height: h, rx: 5, class: "buf-bg" }, g);
    const fill = this.el("rect", { x: x + 3, y: y + h - 3, width: w - 6, height: 0, rx: 3, class: "buf-fill" }, g);
    const val = this.el("text", { x: x + w / 2, y: y - 8, class: "buf-val" }, g, "0");
    this.el("text", { x: x + w / 2, y: y + h + 13, class: "buf-label" }, g, label);
    this.refs[id] = { fill, val, cap, h, y };
  },

  tunnel(id, x, y, w, h, title) {
    const g = this.el("g", {});
    const rect = this.el("rect", { x, y, width: w, height: h, class: "tunnel st-card clickable", rx: 8 }, g);
    this.el("circle", { cx: x + 13, cy: y + 14, r: 5, class: "led", fill: "#39434f", id: `led_${id}` }, g);
    this.el("text", { x: x + 24, y: y + 17, class: "st-name" }, g, title);
    const qtext = this.el("text", { x: x - 6, y: y + h / 2 + 4, class: "buf-val", "text-anchor": "end" }, g, "");
    const util = this.el("text", { x: x + w - 8, y: y + 17, class: "st-info hi", "text-anchor": "end" }, g, "");
    const loadsG = this.el("g", {}, g);
    const cur = this.el("text", { x: x + 8, y: y + h - 8, class: "st-info" }, g, "");
    this.refs[id] = { rect, qtext, util, loadsG, cur, x, y, w, h };
    rect.addEventListener("click", () => this.select(id.replace("furnace", "furnace"), id));
  },

  iguCard(x, y, w, h) {
    const g = this.el("g", {});
    const rect = this.el("rect", { x, y, width: w, height: h, rx: 10, class: "st-card clickable" }, g);
    this.el("circle", { cx: x + 14, cy: y + 15, r: 5, class: "led", fill: "#39434f", id: "led_igu" }, g);
    this.el("text", { x: x + 26, y: y + 19, class: "st-name" }, g, "IGU MONTAJ (3 istasyon)");
    const util = this.el("text", { x: x + w - 10, y: y + 19, class: "st-info hi", "text-anchor": "end" }, g, "");
    const slots = [];
    for (let i = 0; i < 3; i++) {
      const sx = x + 14 + i * 66;
      this.el("rect", { x: sx, y: y + 34, width: 58, height: 54, rx: 6, class: "buf-bg" }, g);
      const led = this.el("circle", { cx: sx + 10, cy: y + 46, r: 4, class: "led", fill: "#39434f" }, g);
      this.el("text", { x: sx + 29, y: y + 50, class: "buf-label" }, g, `İST ${i + 1}`);
      const ord = this.el("text", { x: sx + 29, y: y + 74, class: "buf-val" }, g, "—");
      slots.push({ led, ord });
    }
    const done = this.el("text", { x: x + 14, y: y + h - 10, class: "st-info" }, g, "");
    this.refs.igu = { rect, util, slots, done };
    rect.addEventListener("click", () => this.select("igu_1", "igu"));
  },

  ledColor(state) {
    return { BUSY: "#34d399", RUNNING: "#34d399", IDLE: "#4b5563",
             STARVED: "#fbbf24", BLOCKED: "#f87171", SETUP: "#60a5fa" }[state] || "#4b5563";
  },

  setLed(id, state) {
    const led = document.getElementById(`led_${id}`);
    if (led) led.setAttribute("fill", this.ledColor(state));
  },

  setBar(id, value) {
    const r = this.refs[id];
    if (!r) return;
    const frac = Math.min(1, value / r.cap);
    const hh = Math.max(0, (r.h - 6) * frac);
    r.fill.setAttribute("height", hh);
    r.fill.setAttribute("y", r.y + r.h - 3 - hh);
    r.fill.setAttribute("class", "buf-fill" + (frac > 0.9 ? " crit" : frac > 0.7 ? " warn" : ""));
    r.val.textContent = App.fmt(value, 0);
  },

  update(d) {
    if (!d.stations) return;
    const st = d.stations, c = d.counters, b = d.buffers;
    // pool / nesting
    this.refs.pool.infos.hold_glass.textContent = `havuz: ${App.fmt(b.hold_glass, 0)} cam`;
    this.refs.pool.infos.orders.textContent = `sipariş: ${c.orders_created} (parti ${d.day})`;
    this.setLed("pool", b.hold_glass > 0 ? "BUSY" : "IDLE");
    this.refs.nesting.infos.tok.textContent = `token WIP: ${c.tok_wip}/8`;
    this.refs.nesting.infos.jinfo.textContent = `rafta: ${b.token_buffer} token`;
    this.setLed("nesting", c.tok_wip >= 8 ? "BLOCKED" : "BUSY");
    this.setBar("tokbar", b.token_buffer);
    // cutting machines
    for (const m of ["kesim_1", "kesim_2"]) {
      const s = st[m]; if (!s) continue;
      const r = this.refs[m];
      this.setLed(m, s.state);
      r.utilTxt.textContent = (s.util * 100).toFixed(1) + "%";
      if (s.job) {
        r.infos.job.textContent = `jumbo ${s.job.jumboID} · sip ${s.job.orderRange[0]}–${s.job.orderRange[1]}`;
        r.infos.left.textContent = `kalan parça: ${s.job.tokN_left}`;
      } else {
        r.infos.job.textContent = "—";
        r.infos.left.textContent = "";
      }
    }
    this.setBar("bufbar", b.order_buffer);
    // sequencer
    this.refs.seq.infos.cur.textContent = `vCurOrder: ${c.cur_order}`;
    this.refs.seq.infos.win.textContent = `pencere: ≤ ${c.igu_cur_order + 8}`;
    this.setLed("seq", c.starve ? "STARVED" : "BUSY");
    // rodaj
    for (const m of ["rodaj_1", "rodaj_2"]) {
      const s = st[m]; if (!s) continue;
      this.setLed(m, s.state);
      this.refs[m].utilTxt.textContent = (s.util * 100).toFixed(2) + "%";
      this.refs[m].infos.dim.textContent = s.state === "BUSY" ? "işleniyor…" : "—";
    }
    // temper build
    this.refs.temper_build.infos.beds.textContent = `açık yatak camı: ${b.temper_build}`;
    this.refs.temper_build.infos.cnt.textContent = `FT zaman aşımı: 300 sn`;
    this.setLed("temper_build", b.temper_build > 0 ? "BUSY" : "IDLE");
    // furnaces
    for (const f of ["furnace_1000", "furnace_1600"]) {
      const s = st[f]; if (!s) continue;
      const r = this.refs[f];
      this.setLed(f, s.state);
      r.util.textContent = (s.util * 100).toFixed(1) + "%";
      r.qtext.textContent = s.entry_queue > 0 ? `${s.entry_queue}▶` : "";
      r.cur.textContent = s.current
        ? `yatak ${s.current.tempID} · ${s.current.pieces} cam · çıkış ${s.current.exit_eta_min.toFixed(1)} dk`
        : `tünelde ${s.loads_in_tunnel} yük`;
      // loads drawn in animate() with interpolation
    }
    // match
    this.refs.match.infos.q1.textContent = `kuyruklar: [${b.match_q.join(", ")}]`;
    this.refs.match.infos.q2.textContent = `eşleşen bekleyen: ${b.igu_order_q}`;
    this.setLed("match", b.match_q.some(x => x > 0) ? "BUSY" : "IDLE");
    this.setBar("gatebar", b.igu_order_q);
    this.refs.gate_cur.textContent = c.igu_cur_order;
    // IGU
    const igu = st.igu_1;
    if (igu) {
      this.setLed("igu", igu.state);
      this.refs.igu.util.textContent = (igu.util * 100).toFixed(1) + "%";
      igu.stations.forEach((slot, i) => {
        const s = this.refs.igu.slots[i];
        s.led.setAttribute("fill", slot.busy ? "#34d399" : "#4b5563");
        s.ord.textContent = slot.busy ? `#${slot.orderNo}` : "—";
      });
      this.refs.igu.done.textContent =
        `tamam: ${App.fmt(c.igu_done, 0)} IGU · ${App.fmt(d.kpis.throughput_per_h, 0)}/saat`;
    }
    this.refs.ship.infos.done.textContent = App.fmt(c.igu_done, 0);
    this.setLed("ship", "IDLE");
    // alarms
    this.renderAlarms(d.alarms || []);
    // detail panel refresh
    if (this.selected) this.renderDetail(d);
  },

  renderAlarms(alarms) {
    const ul = document.getElementById("alarm-list");
    ul.innerHTML = alarms.slice().reverse().map(a => {
      const cls = a.event === "FLUSH" ? "flush" : a.event === "STARVE" ? "starve" : "";
      return `<li><span class="t">${a.sim_min.toFixed(1)} dk</span>
        <span class="${cls}">${a.event}</span> ${a.station} ${a.entity}</li>`;
    }).join("");
  },

  select(station, refId) {
    this.selected = { station, refId };
    document.getElementById("detail-title").textContent =
      App.t("stations", station) || station;
    if (App.snapshot) this.renderDetail(App.snapshot);
  },

  renderDetail(d) {
    const { station } = this.selected;
    const body = document.getElementById("detail-body");
    const evs = (d.events_tail || []).filter(e => e.station === station).slice(-20).reverse();
    const hist = App.utilHistory[station] || [];
    let html = "";
    const s = d.stations[station];
    if (s && s.util !== undefined)
      html += `<p>kullanım: <b class="ok">${(s.util * 100).toFixed(2)}%</b></p>`;
    html += `<ul>` + (evs.length ? evs.map(e =>
      `<li>${e.sim_min.toFixed(1)} dk — ${App.t("events", e.event)} · ${e.entity}</li>`).join("")
      : "<li class='muted'>bu istasyon için olay yok</li>") + "</ul>";
    html += `<canvas id="detail-util" width="290" height="70"></canvas>`;
    body.innerHTML = html;
    // mini utilization sparkline
    const cv = document.getElementById("detail-util");
    if (cv && hist.length > 1) {
      const ctx = cv.getContext("2d");
      ctx.clearRect(0, 0, cv.width, cv.height);
      ctx.strokeStyle = "#2dd4bf"; ctx.lineWidth = 1.5;
      ctx.beginPath();
      const t0 = hist[0].t, t1 = hist[hist.length - 1].t || 1;
      hist.forEach((p, i) => {
        const x = 5 + (cv.width - 10) * (p.t - t0) / Math.max(t1 - t0, 1e-9);
        const y = cv.height - 5 - (cv.height - 15) * p.u;
        i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
      });
      ctx.stroke();
      ctx.fillStyle = "#7d8b9c"; ctx.font = "9px monospace";
      ctx.fillText("kullanım zaman serisi", 8, 10);
    }
  },

  // ------------------------------------------------------------ animation
  animate() {
    const d = App.snapshot;
    if (!d || !document.getElementById("tab-scada").classList.contains("active")) return;
    const speedMax = App.status.speed === "max";
    // flow dash animation speed by throughput
    const running = App.status.state === "running";
    const off = (performance.now() / 40) % 20;
    this.paths.forEach(p => {
      p.setAttribute("stroke-dashoffset", running && !speedMax ? -off : 0);
      p.style.opacity = running ? 0.55 : 0.15;
    });
    // furnace tunnel loads with interpolation between frames
    for (const f of ["furnace_1000", "furnace_1600"]) {
      const r = this.refs[f]; if (!r) continue;
      const s = d.stations[f]; if (!s) continue;
      r.loadsG.innerHTML = "";
      const prev = App.prevSnapshot && App.prevSnapshot.stations[f];
      const alpha = speedMax ? 1 : Math.min(1,
        (performance.now() - App.snapTime) / Math.max(App.snapTime - App.prevSnapTime, 1));
      for (const load of s.loads || []) {
        let pos = load.pos;
        if (prev) {
          const pl = (prev.loads || []).find(x => x.tempID === load.tempID);
          if (pl) pos = pl.pos + (load.pos - pl.pos) * alpha;
        }
        const lx = r.x + 26 + (r.w - 60) * pos;
        const el = document.createElementNS(NS, "rect");
        el.setAttribute("x", lx); el.setAttribute("y", r.y + 24);
        el.setAttribute("width", Math.max(8, Math.min(26, load.pieces * 4)));
        el.setAttribute("height", 14);
        el.setAttribute("class", "tunnel-load");
        el.setAttribute("rx", 2);
        r.loadsG.appendChild(el);
      }
    }
    if (!speedMax && running) this.spawnParticles(d);
    this.moveParticles();
  },

  spawnParticles(d) {
    // particle rate proportional to throughput; capped
    if (this.particles.length > 90) return;
    if (Math.random() > Math.min(0.5, (d.kpis.throughput_per_h || 0) / 900)) return;
    const flows = ["p_pool_nest", "p_tok_k1", "p_tok_k2", "p_k1_buf", "p_k2_buf",
      "p_seq_rodaj", "p_dia_bed", "p_bed_f1", "p_bypass", "p_f1_match",
      "p_match_gate", "p_gate_igu", "p_igu_ship"];
    const pathId = flows[Math.floor(Math.random() * flows.length)];
    const path = document.getElementById(pathId);
    if (!path) return;
    const el = document.createElementNS(NS, "rect");
    el.setAttribute("width", 7); el.setAttribute("height", 4);
    el.setAttribute("class", "particle");
    el.setAttribute("fill", TYPE_PALETTE[Math.floor(Math.random() * 12)]);
    this.svg.appendChild(el);
    this.particles.push({ el, path, len: path.getTotalLength(), s: 0,
      v: 1.2 + Math.random() * 1.4 });
  },

  moveParticles() {
    for (let i = this.particles.length - 1; i >= 0; i--) {
      const p = this.particles[i];
      p.s += p.v;
      if (p.s >= p.len) { p.el.remove(); this.particles.splice(i, 1); continue; }
      const pt = p.path.getPointAtLength(p.s);
      p.el.setAttribute("x", pt.x - 3.5);
      p.el.setAttribute("y", pt.y - 2);
    }
  }
};
