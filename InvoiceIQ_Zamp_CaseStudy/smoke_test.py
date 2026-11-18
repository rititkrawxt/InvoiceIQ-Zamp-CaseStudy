"""Runs the seven actual sample PDFs through the HTTP API in an isolated database.

Usage: python smoke_test.py
The test drives application endpoints and validates persistent event and result records.
"""
import importlib
import os
import tempfile
import time
from pathlib import Path

expected = {
 '01_clean_invoice.pdf': 'CLEAR_FOR_AP',
 '02_scanned_invoice.pdf': 'CLEAR_FOR_AP',
 '03_exact_duplicate.pdf': 'HOLD_DUPLICATE',
 '04_split_po_overspend.pdf': 'HOLD_BUDGET',
 '05_bank_change.pdf': 'HOLD_RISK',
 '06_ambiguous_po.pdf': 'REVIEW_PO',
 '07_tax_mismatch.pdf': 'REVIEW_AMOUNT',
}

with tempfile.TemporaryDirectory() as d:
    os.environ['INVOICEIQ_DB'] = str(Path(d) / 'runs.db')
    from fastapi.testclient import TestClient
    from server import app

    with TestClient(app) as client:
        assert client.get('/api/health').json()['status'] == 'ok'
        for filename, correct in expected.items():
            r = client.post('/api/runs/sample/' + filename)
            assert r.status_code == 200, r.text
            run_id = r.json()['run_id']
            for _ in range(300):
                detail = client.get(f'/api/runs/{run_id}').json()
                if detail['run']['status'] != 'IN_PROGRESS':
                    break
                time.sleep(.05)
            result = detail['result']
            actual = detail['run']['status']
            assert actual == correct, f'{filename}: expected {correct}, got {actual}; {detail}'
            assert len(detail['events']) >= 5
            assert result and len(result['rules']) >= 7
            if 'scanned' in filename:
                assert result['ocr_used'] is True
            assert client.get(f'/api/runs/{run_id}/export').status_code == 200
            print(f'PASS {filename:32} -> {actual:18} ({len(detail["events"])} events)')
        metric = client.get('/api/overview').json()
        assert metric['total'] == 7
        assert metric['clear'] == 2
        assert metric['hold'] == 3
        assert metric['review'] == 2
        assert metric['errors'] == 0
        assert len(client.get('/api/runs').json()) == 7
        print('PASS persisted dashboard:', metric)
