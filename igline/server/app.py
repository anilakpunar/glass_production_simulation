"""FastAPI app: REST control + WebSocket state stream + static UI."""
from __future__ import annotations

import asyncio
import csv
import io
import json
import pathlib
import re

import yaml
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from igline.io.params import (DEFAULT_PARAMS_FILE, ROOT, load_params,
                              load_product_mix)
from igline.io.rundb import get_run, list_runs
from igline.server.manager import manager
from igline.validation import REFERENCE, evaluate

WEB_DIR = ROOT / "web"
PROFILE_DIR = ROOT / "config" / "profiles"
RUNS_DIR = ROOT / "runs"

app = FastAPI(title="IGLINE-PySim")

SAFE_NAME = re.compile(r"^[\w.\-]+$")
ALLOWED_FILES = {"summary.json", "orders.csv", "series.json",
                 "distributions.json", "igu_results.csv", "jumbo_results.csv",
                 "jumbo_detail.csv", "temp_results.csv", "event_log.jsonl",
                 "params.yaml", "validation_report.md"}


class RunRequest(BaseModel):
    params: dict = {}
    mode: str = "live"            # live | headless
    speed: float | str = 60


class SpeedRequest(BaseModel):
    speed: float | str


class ProfileRequest(BaseModel):
    name: str
    params: dict


class MixUpload(BaseModel):
    csv_text: str
    filename: str = "custom_mix.csv"


# ------------------------------------------------------------------ params
@app.get("/api/params/defaults")
def get_defaults():
    with open(DEFAULT_PARAMS_FILE) as f:
        params = yaml.safe_load(f)
    return {"params": params}


@app.get("/api/params/mix_preview")
def mix_preview(path: str = "data/product_mix.csv"):
    if not SAFE_NAME.match(path.replace("/", "_")) and ".." in path:
        raise HTTPException(400, "invalid path")
    try:
        cum, codes = load_product_mix(path)
    except Exception as exc:
        raise HTTPException(400, str(exc))
    from igline.io.params import decode_product
    rows = []
    prev = 0.0
    for c, code in zip(cum, codes):
        d = decode_product(code)
        rows.append({"cum_prob": c, "prob": round(c - prev, 5), "code": code, **d})
        prev = c
    return {"rows": rows, "count": len(rows)}


@app.post("/api/params/mix_upload")
def mix_upload(req: MixUpload):
    if not SAFE_NAME.match(req.filename) or not req.filename.endswith(".csv"):
        raise HTTPException(400, "invalid filename")
    reader = csv.DictReader(io.StringIO(req.csv_text))
    if reader.fieldnames != ["cum_prob", "code"]:
        raise HTTPException(400, "CSV başlığı 'cum_prob,code' olmalı")
    rows = [(float(r["cum_prob"]), int(r["code"])) for r in reader]
    if not rows:
        raise HTTPException(400, "boş dosya")
    if any(b[0] < a[0] for a, b in zip(rows, rows[1:])):
        raise HTTPException(400, "cum_prob monoton artmalı")
    if abs(rows[-1][0] - 1.0) > 1e-6:
        raise HTTPException(400, "son cum_prob 1.0 olmalı")
    path = ROOT / "data" / req.filename
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cum_prob", "code"])
        w.writerows(rows)
    return {"path": f"data/{req.filename}", "rows": len(rows)}


# ---------------------------------------------------------------- profiles
@app.get("/api/profiles")
def profiles_list():
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    return {"profiles": sorted(p.stem for p in PROFILE_DIR.glob("*.yaml"))}


@app.post("/api/profiles")
def profile_save(req: ProfileRequest):
    if not SAFE_NAME.match(req.name):
        raise HTTPException(400, "invalid profile name")
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        merged = load_params(overrides=req.params)   # validate
    except Exception as exc:
        raise HTTPException(400, f"parametre doğrulama hatası: {exc}")
    with open(PROFILE_DIR / f"{req.name}.yaml", "w") as f:
        yaml.safe_dump(req.params, f, sort_keys=False, allow_unicode=True)
    return {"saved": req.name}


@app.get("/api/profiles/{name}")
def profile_get(name: str):
    if not SAFE_NAME.match(name):
        raise HTTPException(400, "invalid profile name")
    path = PROFILE_DIR / f"{name}.yaml"
    if not path.exists():
        raise HTTPException(404, "profile not found")
    with open(path) as f:
        return {"name": name, "params": yaml.safe_load(f)}


# --------------------------------------------------------------- run ctrl
@app.post("/api/run")
def run_start(req: RunRequest):
    try:
        params = load_params(overrides=req.params)
    except Exception as exc:
        raise HTTPException(400, f"parametre hatası: {exc}")
    if req.mode not in ("live", "headless"):
        raise HTTPException(400, "mode: live | headless")
    try:
        run_id = manager.start(params, mode=req.mode, speed=req.speed)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))
    return {"run_id": run_id, "status": manager.status()}


@app.post("/api/pause")
def run_pause():
    manager.pause()
    return manager.status()


@app.post("/api/resume")
def run_resume():
    manager.resume()
    return manager.status()


@app.post("/api/step")
def run_step():
    manager.step()
    return manager.status()


@app.post("/api/stop")
def run_stop():
    manager.stop()
    return manager.status()


@app.post("/api/speed")
def run_speed(req: SpeedRequest):
    if req.speed != "max":
        try:
            s = float(req.speed)
            if not (0.1 <= s <= 10000):
                raise ValueError
        except (TypeError, ValueError):
            raise HTTPException(400, "speed: 0.1..10000 | 'max'")
    manager.set_speed(req.speed)
    return manager.status()


@app.get("/api/state")
def get_state():
    return {"status": manager.status(), "snapshot": manager.snapshot}


@app.get("/api/summary")
def get_summary():
    if manager.summary is None:
        raise HTTPException(404, "no finished run in this session")
    return manager.summary


# ----------------------------------------------------------------- results
@app.get("/api/results")
def results_list():
    return {"runs": list_runs()}


@app.get("/api/results/{run_id}")
def results_get(run_id: str):
    if not SAFE_NAME.match(run_id):
        raise HTTPException(400, "invalid run id")
    run = get_run(run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    return run


@app.get("/api/results/{run_id}/file/{name}")
def results_file(run_id: str, name: str, rep: str | None = None):
    if not SAFE_NAME.match(run_id) or name not in ALLOWED_FILES:
        raise HTTPException(400, "invalid request")
    base = RUNS_DIR / run_id
    if rep:
        if not SAFE_NAME.match(rep):
            raise HTTPException(400, "invalid rep")
        base = base / rep
    path = base / name
    if not path.exists():
        # single-rep runs store files at top level; multi-rep under rep01
        alt = RUNS_DIR / run_id / "rep01" / name
        if not rep and alt.exists():
            path = alt
        else:
            raise HTTPException(404, f"{name} not found")
    return FileResponse(path)


@app.get("/api/validation/{run_id}")
def validation_compare(run_id: str):
    if not SAFE_NAME.match(run_id):
        raise HTTPException(400, "invalid run id")
    base = RUNS_DIR / run_id
    summaries = []
    if (base / "summary.json").exists():
        with open(base / "summary.json") as f:
            data = json.load(f)
        if "replications" in data and isinstance(data["replications"], list):
            summaries = data["replications"]
        else:
            summaries = [data]
    else:
        for rep in sorted(base.glob("rep*/summary.json")):
            with open(rep) as f:
                summaries.append(json.load(f))
    if not summaries:
        raise HTTPException(404, "summary not found")
    rows = evaluate(summaries)
    return {"rows": rows, "n": len(summaries)}


# --------------------------------------------------------------- websocket
@app.websocket("/ws/state")
async def ws_state(ws: WebSocket):
    await ws.accept()
    last_seq = -1
    try:
        while True:
            await asyncio.sleep(0.25)
            if manager.snapshot_seq != last_seq and manager.snapshot is not None:
                last_seq = manager.snapshot_seq
                await ws.send_json(manager.snapshot)
            elif manager.state in ("idle", "finished", "error"):
                await ws.send_json({"run": manager.status(), "idle": True})
                await asyncio.sleep(0.75)
    except (WebSocketDisconnect, RuntimeError):
        return


# ------------------------------------------------------------------ static
@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")
