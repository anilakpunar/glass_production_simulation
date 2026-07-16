/* Parameters tab: schema-driven accordion form, profiles, product mix, run start */
"use strict";

const PARAM_META = {
  run: { title: "Koşu", fields: {
    start_datetime: { l: "Başlangıç tarihi/saati", a: "REPLICATE", u: "—", type: "text" },
    days: { l: "Gün sayısı", a: "Replication Length", u: "gün", min: 1, max: 260 },
    hours_per_day: { l: "Vardiya süresi/gün", a: "Hours Per Day", u: "saat", min: 1, max: 24 },
    seed: { l: "RNG tohumu", a: "SEEDS", u: "—", min: 0, max: 1e9 },
    replications: { l: "Replikasyon sayısı", a: "NREPS", u: "—", min: 1, max: 25 },
    snapshot_interval_min: { l: "Anlık görüntü aralığı", a: "—", u: "sim-dk", min: 0.1, max: 10, step: 0.1 },
    event_log: { l: "Olay günlüğü yaz", a: "—", u: "—", type: "bool" }
  }},
  orders: { title: "Sipariş Üretimi", fields: {
    daily_target: { l: "Günlük hedef adet", a: "vDailyTarget", u: "adet", min: 100, max: 200000 },
    batch_interval_s: { l: "Parti aralığı", a: "CREATE interval", u: "sn", min: 3600, max: 1e6 },
    first_batch_s: { l: "İlk parti zamanı", a: "First Creation", u: "sn", min: 0, max: 1e5 },
    qty_mean: { l: "Adet dağılımı ortalama", a: "LOGN m", u: "adet", min: 1, max: 10000 },
    qty_sd: { l: "Adet dağılımı std", a: "LOGN s", u: "adet", min: 0, max: 20000 },
    qty_cap: { l: "Adet üst sınırı", a: "MN(..,2500)", u: "adet", min: 1, max: 50000 },
    due_gamma_shape: { l: "Termin Gamma shape", a: "GAMM α", u: "—", min: 0.1, max: 20, step: 0.01 },
    due_gamma_scale: { l: "Termin Gamma scale", a: "GAMM β", u: "gün", min: 0.1, max: 365, step: 0.1 },
    product_mix_file: { l: "Ürün karması dosyası", a: "DISC", u: "csv", type: "text" }
  }},
  nesting: { title: "Nesting / Jumbo", fields: {
    jumbo_w_mm: { l: "Jumbo genişlik", a: "vJumboW", u: "mm", min: 1000, max: 12000 },
    jumbo_h_mm: { l: "Jumbo yükseklik", a: "vJumboH", u: "mm", min: 1000, max: 6000 },
    kerf_mm: { l: "Kerf (kesim payı)", a: "vKerf", u: "mm", min: 0, max: 50 },
    rotation_ok: { l: "Rotasyon serbest", a: "vRotOK", u: "—", type: "bool" },
    due_window_days: { l: "Termin penceresi", a: "vDDwin", u: "gün", min: 0, max: 60 },
    max_token_wip: { l: "Maks. token WIP", a: "vMaxTok", u: "jumbo", min: 1, max: 64 },
    flush_grace_s: { l: "Flush yaşı", a: "vJGrace", u: "sn", min: 0, max: 36000 },
    flush_fill_threshold: { l: "Flush doluluk eşiği", a: "—", u: "0–1", min: 0, max: 1, step: 0.01 },
    flush_period_min: { l: "Flush tarama periyodu", a: "—", u: "dk", min: 0.5, max: 120, step: 0.5 }
  }},
  cutting: { title: "Kesim", fields: {
    machines: { l: "Makine sayısı", a: "Kesim_1..2", u: "—", min: 1, max: 2 },
    trim_tria_s: { l: "Trim süresi (min/mod/maks)", a: "TRIA", u: "sn", type: "tria" },
    break_tria_s: { l: "Kırım süresi (min/mod/maks)", a: "TRIA", u: "sn", type: "tria" },
    lookahead_orders: { l: "Lookahead penceresi", a: "vLookahead", u: "sipariş", min: 0, max: 1000 },
    dispatch_period_min: { l: "Dispatch periyodu", a: "EXPO(1)", u: "dk", min: 0.1, max: 10, step: 0.1 },
    dispatch_expo: { l: "Dispatch EXPO dağılımlı", a: "EXPO", u: "—", type: "bool" }
  }},
  sequencer: { title: "Sequencer / Sıralama", fields: {
    igu_window_orders: { l: "IGU penceresi", a: "vIGUWindow", u: "sipariş", min: 1, max: 100 },
    strict_pane_feed: { l: "Katı pane besleme", a: "(yeni)", u: "—", type: "bool",
      tip: "False = Arena aynısı (2× eşik); True = paneCount × adet" }
  }},
  edging: { title: "Rodaj", fields: {
    lines: { l: "Hat sayısı", a: "Rodaj_1..2", u: "—", min: 1, max: 2 },
    feed_mm_s: { l: "İlerleme hızı", a: "vfeed", u: "mm/sn", min: 10, max: 100000 }
  }},
  temper: { title: "Temper / Fırın", fields: {
    furnace_width_mm: { l: "Fırın genişlikleri [1000,1600]", a: "vFurnaceWidth", u: "mm", type: "arr2" },
    heat_zone_len_mm: { l: "Isıtma bölgesi boyu", a: "vL_heat", u: "mm", type: "arr2" },
    tunnel_len_mm: { l: "Tünel boyu", a: "vFurnLen", u: "mm", type: "arr2" },
    row_gap_mm: { l: "Sıra aralığı", a: "vRowGap", u: "mm", min: 0, max: 5000 },
    glass_gap_mm: { l: "Cam arası boşluk", a: "vGap", u: "mm", min: 0, max: 1000 },
    bed_timeout_s: { l: "Yatak zaman aşımı", a: "vTmax", u: "sn", min: 1, max: 36000 },
    divert_threshold: { l: "Sapma eşiği", a: "vDivN", u: "kuyruk", min: 0, max: 50 },
    furnace_of: { l: "Tip→fırın tablosu", a: "vFurnaceOf", u: "0/1/2", type: "arr12", min: 0, max: 2 },
    heat_time_s: { l: "Tip→ısıtma süresi", a: "vHeatT", u: "sn", type: "arr12", min: 0, max: 3600 }
  }},
  igu: { title: "IGU Montaj", fields: {
    stations: { l: "İstasyon sayısı", a: "IGU_1 capacity", u: "—", min: 1, max: 12 },
    process_tria_s: { l: "Süreç süresi (min/mod/maks)", a: "TRIA", u: "sn", type: "tria" },
    setup_s: { l: "Sipariş değişim setup", a: "tSetupIGU", u: "sn", min: 0, max: 3600 }
  }}
};

const Params = {
  defaults: null,
  current: null,

  async init() {
    const d = await fetch("/api/params/defaults").then(r => r.json());
    this.defaults = d.params;
    this.current = structuredClone(d.params);
    this.render();
    this.loadMixPreview();
    this.refreshProfiles();
  },

  render() {
    const pane = document.getElementById("tab-params");
    pane.innerHTML = `
      <div class="pgrid">
        <div>
          <div class="accordion" id="acc"></div>
        </div>
        <div>
          <div class="side-card">
            <h3>Koşu Başlat</h3>
            <div class="formline">
              <label>Mod</label>
              <select id="run-mode">
                <option value="live">Canlı (SCADA)</option>
                <option value="headless">Headless (MAX hız)</option>
              </select>
              <label>Hız</label>
              <select id="run-speed">
                <option>1</option><option>10</option><option selected>60</option>
                <option>300</option><option value="max">MAX</option>
              </select>
            </div>
            <div class="formline">
              <label>Gün</label><input id="run-days" type="number" min="1" max="260">
              <label>Tohum</label><input id="run-seed" type="number">
              <label>Replikasyon</label><input id="run-reps" type="number" min="1" max="25">
            </div>
            <div class="btnrow">
              <button class="btn primary" id="btn-start">KOŞUYU BAŞLAT</button>
              <button class="btn" id="btn-stopper">Durdur</button>
            </div>
            <div id="start-note" class="muted"></div>
          </div>
          <div class="side-card">
            <h3>Profiller</h3>
            <div class="formline">
              <input id="profile-name" type="text" placeholder="profil adı" style="width:160px">
              <button class="btn" id="btn-save-profile">Kaydet</button>
            </div>
            <div class="formline">
              <select id="profile-list" style="width:160px"></select>
              <button class="btn" id="btn-load-profile">Yükle</button>
              <button class="btn" id="btn-reset">Varsayılanlara dön</button>
            </div>
          </div>
          <div class="side-card">
            <h3>Ürün Karması (DISC 66 satır)</h3>
            <div class="formline">
              <input type="file" id="mix-file" accept=".csv">
              <button class="btn" id="btn-mix-upload">Yükle & Doğrula</button>
            </div>
            <div id="mix-info" class="muted"></div>
            <div id="mix-preview"></div>
          </div>
        </div>
      </div>`;
    this.renderAccordion();
    this.bindSideActions();
  },

  renderAccordion() {
    const acc = document.getElementById("acc");
    acc.innerHTML = "";
    for (const [group, meta] of Object.entries(PARAM_META)) {
      const g = document.createElement("div");
      g.className = "acc-group" + (group === "run" ? " open" : "");
      const nf = Object.keys(meta.fields).length;
      g.innerHTML = `<div class="acc-head"><b>${meta.title}</b><span class="cnt">${nf} parametre</span></div>
                     <div class="acc-body"></div>`;
      g.querySelector(".acc-head").addEventListener("click", () => g.classList.toggle("open"));
      const body = g.querySelector(".acc-body");
      for (const [key, f] of Object.entries(meta.fields)) {
        body.appendChild(this.renderField(group, key, f));
      }
      acc.appendChild(g);
    }
  },

  renderField(group, key, f) {
    const row = document.createElement("div");
    row.className = "prow";
    const val = this.current[group][key];
    const tip = f.tip ? ` title="${f.tip}"` : "";
    let ctrl;
    if (f.type === "bool") {
      ctrl = `<input type="checkbox" data-p="${group}.${key}" ${val ? "checked" : ""}>`;
    } else if (f.type === "tria" || f.type === "arr2" || f.type === "arr12") {
      const n = f.type === "arr12" ? 12 : f.type === "arr2" ? 2 : 3;
      const cls = f.type === "arr12" ? "" : (f.type === "arr2" ? "n2" : "n3");
      const hds = f.type === "tria" ? ["min", "mod", "maks"]
        : f.type === "arr2" ? ["1000", "1600"]
        : Array.from({ length: 12 }, (_, i) => `T${i + 1}`);
      let cells = hds.map(h => `<div class="hd">${h}</div>`).join("");
      cells += val.map((v, i) =>
        `<input type="number" data-p="${group}.${key}" data-i="${i}" value="${v}"
          ${f.min !== undefined ? `min="${f.min}"` : ""} ${f.max !== undefined ? `max="${f.max}"` : ""}>`
      ).join("");
      ctrl = `<div class="arrtable ${cls}" style="grid-template-rows: auto auto">${cells}</div>`;
    } else if (f.type === "text") {
      ctrl = `<input type="text" data-p="${group}.${key}" value="${val}">`;
    } else {
      ctrl = `<input type="number" data-p="${group}.${key}" value="${val}"
        ${f.min !== undefined ? `min="${f.min}"` : ""} ${f.max !== undefined ? `max="${f.max}"` : ""}
        ${f.step ? `step="${f.step}"` : ""}>`;
    }
    row.innerHTML = `<label${tip}>${f.l}<span class="arena">${f.a}</span></label>
                     <div>${ctrl}</div><div class="unit">${f.u}</div>`;
    row.querySelectorAll("[data-p]").forEach(inp => {
      inp.addEventListener("change", () => this.onInput(inp, f));
    });
    return row;
  },

  onInput(inp, f) {
    const [group, key] = inp.dataset.p.split(".");
    let v;
    if (inp.type === "checkbox") v = inp.checked;
    else if (inp.type === "number") {
      v = Number(inp.value);
      if (Number.isNaN(v) || (f.min !== undefined && v < f.min) ||
          (f.max !== undefined && v > f.max)) {
        inp.classList.add("invalid");
        return;
      }
      inp.classList.remove("invalid");
    } else v = inp.value;
    if (inp.dataset.i !== undefined) {
      this.current[group][key][Number(inp.dataset.i)] = v;
      if (f.type === "tria") {
        const a = this.current[group][key];
        const bad = !(a[0] <= a[1] && a[1] <= a[2]);
        inp.classList.toggle("invalid", bad);
      }
    } else {
      this.current[group][key] = v;
    }
    if (key === "product_mix_file") this.loadMixPreview();
  },

  bindSideActions() {
    const q = id => document.getElementById(id);
    q("run-days").value = this.current.run.days;
    q("run-seed").value = this.current.run.seed;
    q("run-reps").value = this.current.run.replications;

    q("btn-start").addEventListener("click", async () => {
      this.current.run.days = Number(q("run-days").value);
      this.current.run.seed = Number(q("run-seed").value);
      this.current.run.replications = Number(q("run-reps").value);
      const mode = q("run-mode").value;
      const speed = q("run-speed").value;
      const note = q("start-note");
      note.textContent = "başlatılıyor…";
      const res = await fetch("/api/run", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ params: this.current, mode,
                               speed: speed === "max" ? "max" : Number(speed) })
      });
      const d = await res.json();
      if (!res.ok) { note.innerHTML = `<span class="bad">${d.detail}</span>`; return; }
      note.innerHTML = `<span class="ok">koşu başladı: ${d.run_id}</span> — parametreler runs/${d.run_id}/params.yaml olarak donduruldu`;
      document.querySelectorAll("#speedbox .spd").forEach(b =>
        b.classList.toggle("active", b.dataset.sp === String(speed)));
      if (mode === "live")
        document.querySelector('[data-tab="scada"]').click();
    });

    q("btn-stopper").addEventListener("click", () => fetch("/api/stop", { method: "POST" }));

    q("btn-reset").addEventListener("click", () => {
      this.current = structuredClone(this.defaults);
      this.renderAccordion();
      this.bindSideActions();
    });

    q("btn-save-profile").addEventListener("click", async () => {
      const name = q("profile-name").value.trim();
      if (!name) return alert("profil adı girin");
      const res = await fetch("/api/profiles", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ name, params: this.current })
      });
      if (res.ok) { this.refreshProfiles(); alert(`profil kaydedildi: ${name}`); }
      else alert((await res.json()).detail);
    });

    q("btn-load-profile").addEventListener("click", async () => {
      const name = q("profile-list").value;
      if (!name) return;
      const d = await fetch(`/api/profiles/${name}`).then(r => r.json());
      this.current = structuredClone(this.defaults);
      this.deepMerge(this.current, d.params);
      this.renderAccordion();
      this.bindSideActions();
    });

    q("btn-mix-upload").addEventListener("click", async () => {
      const file = q("mix-file").files[0];
      if (!file) return alert("CSV dosyası seçin");
      const text = await file.text();
      const res = await fetch("/api/params/mix_upload", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ csv_text: text, filename: file.name.replace(/[^\w.\-]/g, "_") })
      });
      const d = await res.json();
      if (!res.ok) { q("mix-info").innerHTML = `<span class="bad">${d.detail}</span>`; return; }
      this.current.orders.product_mix_file = d.path;
      this.renderAccordion();
      this.bindSideActions();
      this.loadMixPreview();
      q("mix-info").innerHTML = `<span class="ok">${d.path} yüklendi (${d.rows} satır)</span>`;
    });
  },

  deepMerge(base, over) {
    for (const [k, v] of Object.entries(over)) {
      if (v && typeof v === "object" && !Array.isArray(v) && base[k]) this.deepMerge(base[k], v);
      else base[k] = v;
    }
  },

  async refreshProfiles() {
    const d = await fetch("/api/profiles").then(r => r.json());
    const sel = document.getElementById("profile-list");
    sel.innerHTML = d.profiles.map(p => `<option>${p}</option>`).join("");
  },

  async loadMixPreview() {
    const path = this.current.orders.product_mix_file;
    const box = document.getElementById("mix-preview");
    try {
      const d = await fetch(`/api/params/mix_preview?path=${encodeURIComponent(path)}`)
        .then(r => { if (!r.ok) throw new Error("okunamadı"); return r.json(); });
      document.getElementById("mix-info").textContent =
        `${d.count} satır · kümülatif olasılık monoton ✓`;
      box.innerHTML = `<table class="data"><thead><tr>
        <th>kod</th><th>p</th><th>G1</th><th>G2</th><th>G3</th><th>en×boy</th><th>m²</th>
        </tr></thead><tbody>` +
        d.rows.map(r => `<tr><td>${r.code}</td><td>${r.prob.toFixed(4)}</td>
          <td>${r.glass1}</td><td>${r.glass2}</td><td>${r.glass3}</td>
          <td>${r.width}×${r.height}</td><td>${r.area.toFixed(3)}</td></tr>`).join("") +
        "</tbody></table>";
    } catch (e) {
      document.getElementById("mix-info").innerHTML =
        `<span class="bad">karma dosyası okunamadı: ${path}</span>`;
      box.innerHTML = "";
    }
  }
};
