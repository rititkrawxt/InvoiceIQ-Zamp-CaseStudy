"""InvoiceIQ FastAPI service. Start: uvicorn server:app --host 0.0.0.0 --port 8000"""
from __future__ import annotations

import base64
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from engine import BASE, decide, extract_pdf, rows

DB_PATH = Path(os.environ.get('INVOICEIQ_DB', str(BASE / 'data' / 'runs.db')))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def connect():
    con = sqlite3.connect(str(DB_PATH), timeout=10)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA busy_timeout=10000')
    con.execute('PRAGMA journal_mode=WAL')
    return con


def init_db():
    with connect() as con:
        con.execute('''CREATE TABLE IF NOT EXISTS runs (
             id TEXT PRIMARY KEY, filename TEXT NOT NULL, sample_name TEXT,
             created_at TEXT NOT NULL, finished_at TEXT, stage TEXT NOT NULL,
             status TEXT NOT NULL, result_json TEXT, error TEXT)''')
        con.execute('''CREATE TABLE IF NOT EXISTS events (
             seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
             timestamp TEXT NOT NULL, stage TEXT NOT NULL, message TEXT NOT NULL,
             FOREIGN KEY(run_id) REFERENCES runs(id))''')


init_db()
app = FastAPI(title='InvoiceIQ — Zamp ASA Case Study', version='1.0.0')
app.mount('/static', StaticFiles(directory=BASE / 'static'), name='static')


class UploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=160)
    pdf_base64: str = Field(min_length=10)


def event(run_id, stage, message):
    with connect() as con:
        con.execute('INSERT INTO events(run_id, timestamp, stage, message) VALUES (?,?,?,?)',
                    (run_id, utcnow(), stage, message))
        con.execute('UPDATE runs SET stage = ? WHERE id = ?', (stage, run_id))


def worker(run_id, payload):
    try:
        event(run_id, 'VALIDATE_INPUT', f'Validated PDF input ({len(payload):,} bytes).')
        event(run_id, 'EXTRACT_DOCUMENT', 'Reading embedded PDF text; OCR if pages are scanned.')
        extracted = extract_pdf(payload, ai_key=os.getenv('OPENAI_API_KEY', ''))
        event(run_id, 'EXTRACT_DOCUMENT',
              f"Extracted {extracted['text_characters']} characters over {extracted['page_count']} page(s) via {extracted['method']}.")
        event(run_id, 'LOAD_REFERENCES', 'Loading active supplier, purchase-order and payment-history datasets.')
        vendors = rows('vendors.csv')
        pos = rows('purchase_orders.csv')
        history = rows('historical_invoices.csv')
        event(run_id, 'LOAD_REFERENCES', f'Loaded {len(vendors)} vendors, {len(pos)} POs and {len(history)} paid-invoice records.')
        event(run_id, 'EVALUATE_CONTROLS', 'Applying deterministic identity, duplicate, arithmetic and PO-budget controls.')
        # Serialise commitment decisions: prevents two in-flight invoices from
        # both reserving the same remaining PO balance.
        with connect() as con:
            con.execute('BEGIN IMMEDIATE')
            previous = con.execute("SELECT result_json FROM runs WHERE status NOT IN ('IN_PROGRESS','ERROR') AND result_json IS NOT NULL").fetchall()
            old = [json.loads(r['result_json']) for r in previous]
            decision = decide(extracted, old)
            con.execute('UPDATE runs SET status=?,stage=?,finished_at=?,result_json=? WHERE id=?',
                        (decision['status'], 'COMPLETE', utcnow(), json.dumps(decision), run_id))
            con.execute('INSERT INTO events(run_id,timestamp,stage,message) VALUES (?,?,?,?)',
                        (run_id, utcnow(), 'COMPLETE',
                         f"{decision['headline']}; {len(decision['rules'])} policy checks recorded."))
    except Exception as exc:
        with connect() as con:
            con.execute('UPDATE runs SET status=?,stage=?,finished_at=?,error=? WHERE id=?',
                        ('ERROR', 'ERROR', utcnow(), str(exc)[:500], run_id))
            con.execute('INSERT INTO events(run_id,timestamp,stage,message) VALUES (?,?,?,?)',
                        (run_id, utcnow(), 'ERROR', str(exc)[:500]))


def start_run(filename, payload, sample=None):
    if len(payload) > 10 * 1024 * 1024 or not payload.startswith(b'%PDF'):
        raise HTTPException(400, 'Please provide a valid PDF up to 10 MB.')
    run_id = uuid.uuid4().hex[:12]
    with connect() as con:
        con.execute('''INSERT INTO runs(id,filename,sample_name,created_at,stage,status)
                       VALUES (?,?,?,?,?,?)''',
                    (run_id, Path(filename).name, sample, utcnow(), 'QUEUED', 'IN_PROGRESS'))
        con.execute('INSERT INTO events(run_id,timestamp,stage,message) VALUES(?,?,?,?)',
                    (run_id, utcnow(), 'QUEUED', 'Run queued for processing.'))
    threading.Thread(target=worker, args=(run_id, payload), daemon=True).start()
    return {'run_id': run_id, 'status': 'IN_PROGRESS'}


@app.get('/')
def home():
    return FileResponse(BASE / 'static' / 'index.html')


@app.get('/api/health')
def health():
    return {'status': 'ok', 'service': 'InvoiceIQ', 'runtime': 'real PDF processing + deterministic policy engine'}


@app.get('/api/samples')
def samples():
    names = [
        ('01_clean_invoice.pdf', 'Clean invoice', 'Happy path: matches approved supplier and open PO.'),
        ('02_scanned_invoice.pdf', 'Scanned invoice', 'Real raster PDF requiring OCR.'),
        ('03_exact_duplicate.pdf', 'Exact duplicate', 'Matches an existing paid invoice.'),
        ('04_split_po_overspend.pdf', 'Split-PO overspend', 'New invoice pushes cumulative PO commitment over limit.'),
        ('05_bank_change.pdf', 'Bank-account change', 'Invoice bank suffix disagrees with vendor master.'),
        ('06_ambiguous_po.pdf', 'Ambiguous purchase order', 'Missing PO reference with two valid candidates.'),
        ('07_tax_mismatch.pdf', 'Tax reconciliation error', 'Subtotal + tax does not equal invoice total.'),
    ]
    return [{'name': n, 'label': label, 'description': desc} for n, label, desc in names]


@app.get('/api/samples/{name}/download')
def sample_file(name: str):
    safe = Path(name).name
    if safe != name or not safe.endswith('.pdf'):
        raise HTTPException(400, 'Invalid file name')
    path = BASE / 'data' / 'samples' / safe
    if not path.is_file():
        raise HTTPException(404, 'Sample not found')
    return FileResponse(path, media_type='application/pdf', filename=safe)


@app.post('/api/runs/sample/{name}')
def create_sample(name: str):
    if Path(name).name != name or not name.endswith('.pdf'):
        raise HTTPException(400, 'Invalid sample name')
    path = BASE / 'data' / 'samples' / name
    if not path.is_file():
        raise HTTPException(404, 'Sample not found')
    return start_run(path.name, path.read_bytes(), name)


@app.post('/api/runs/upload')
def create_upload(data: UploadRequest):
    if not data.filename.lower().endswith('.pdf'):
        raise HTTPException(400, 'Only PDF files are supported.')
    try:
        payload = base64.b64decode(data.pdf_base64, validate=True)
    except Exception:
        raise HTTPException(400, 'Invalid base64 document.')
    return start_run(data.filename, payload)


def compact(r):
    item = dict(r)
    detail = json.loads(item['result_json']) if item.get('result_json') else {}
    return {k: item[k] for k in ('id', 'filename', 'sample_name', 'created_at', 'finished_at', 'stage', 'status', 'error')} | {
        'invoice_number': detail.get('invoice_number'), 'vendor_name': detail.get('vendor_name'),
        'po_number': detail.get('po_number'), 'total': detail.get('total'),
        'headline': detail.get('headline'), 'method': detail.get('method')}


@app.get('/api/runs')
def list_runs():
    with connect() as con:
        found = con.execute('SELECT * FROM runs ORDER BY created_at DESC LIMIT 100').fetchall()
    return [compact(r) for r in found]


@app.get('/api/runs/{run_id}')
def detail(run_id: str):
    with connect() as con:
        r = con.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
        if not r:
            raise HTTPException(404, 'Run not found')
        ev = con.execute('SELECT timestamp,stage,message FROM events WHERE run_id=? ORDER BY seq', (run_id,)).fetchall()
    return {'run': compact(r), 'result': json.loads(r['result_json']) if r['result_json'] else None,
            'events': [dict(e) for e in ev]}


@app.get('/api/runs/{run_id}/export')
def export(run_id: str):
    data = detail(run_id)
    return JSONResponse(data, headers={'Content-Disposition': f'attachment; filename="invoiceiq-{run_id}.json"'})


@app.get('/api/overview')
def overview():
    recent = list_runs()
    completed = [r for r in recent if r['status'] != 'IN_PROGRESS']
    clear = [r for r in completed if r['status'] == 'CLEAR_FOR_AP']
    review = [r for r in completed if r['status'].startswith(('REVIEW', 'REQUEST'))]
    hold = [r for r in completed if r['status'].startswith('HOLD')]
    errors = [r for r in completed if r['status'] == 'ERROR']
    return {'total': len(recent), 'clear': len(clear), 'review': len(review), 'hold': len(hold),
            'errors': len(errors), 'in_progress': len(recent) - len(completed),
            'clear_value': str(sum(float(r['total'] or 0) for r in clear))}


@app.get('/api/references')
def references():
    pos = rows('purchase_orders.csv')
    return {'purchase_orders': pos, 'vendors': [
        {'vendor_id': v['vendor_id'], 'legal_name': v['legal_name'], 'status': v['status']}
        for v in rows('vendors.csv')]}
