# InvoiceIQ | Zamp AI Solutions Analyst Case Study (PS-1)

**An executable PDF-to-decision Accounts Payable workflow.**  Upload an actual PDF invoice (or select one of seven example PDFs); the backend reads embedded text or performs real OCR on scanned pages, checks the invoice against vendor/PO/payment-history reference data, and records an explained financial control decision. A web interface shows live workflow stages, policy evidence, cumulative history, and downloadable JSON audit records.

> **Safety boundary:** `CLEAR_FOR_AP` means **eligible for an AP posting review**, never that a payment has been made or authorized. The prototype does not initiate any payment, modify the reference procurement records, or independently verify bank ownership.

## Quick start (local)

Prerequisites: Python 3.10+ and **Tesseract OCR** installed on the OS (`tesseract --version` should work). On Ubuntu/Debian: `sudo apt-get install tesseract-ocr`. On Windows, install Tesseract OCR and make `tesseract.exe` available on your PATH. macOS: `brew install tesseract`.

```bash
cd InvoiceIQ_Zamp_CaseStudy
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. Start with **Clean invoice**, then run **Scanned invoice**, **Exact duplicate**, and **Split-PO overspend**. Select any history row to inspect the result and step-by-step trace. To upload a document, click **Browse PDF files**.

For a clean, reproducible interview demo, stop the server and delete `data/runs.db` (and its `-wal`/`-shm` siblings if present while the server is stopped), then start the service again. **Do not clear production audit logs**; this is for this local demo fixture only. When using the examples, prefer the demo sequence suggested in `DEMO_SCRIPT.md` because approved runs reserve the remaining PO capacity.

## Alternative: Docker (recommended for reliable OCR installation)

```bash
docker build -t invoiceiq .
docker run --rm -p 8000:8000 -e PORT=8000 invoiceiq
```

For a persistent database across container restarts, set `INVOICEIQ_DB=/app/persistent/runs.db` and mount a writable persistent directory or volume to `/app/persistent`. If hosting on a platform with an ephemeral filesystem, run history will disappear after rebuild/restart unless persistent storage is configured. Use a persistent volume or external database for a durable public demo. Deploying to a public HTTPS URL requires your own hosting account; the zip contains the source but is not itself a hosted app.

## Optional AI enhancement

The core end-to-end demo **does not need a paid API**. PDF embedded-text extraction and OCR are real executable functions. If `OPENAI_API_KEY` is supplied, the backend can call an LLM to fill **missing explicitly visible fields** after text/OCR extraction. The model does *not* determine approval, replace evidence, bypass validation or authorize payments. If no key is present, the product still processes all seven provided scenarios. If the LLM API fails, the deterministic workflow continues with the extracted data. This intentionally illustrates the difference between AI document understanding and financial policy logic.

## Real input → real output

`Upload PDF` → `Validate file` → `Extract text / OCR` → `Identify vendor and invoice` → `Read vendor + PO + history CSVs` → `Check policies` → `Recommend disposition` → `Persist the run and event log` → `Render reviewable decision and export audit JSON`.

**Policy checks**: required identity/date/positive amount; invoice date sanity; explicitly stated currency; strict vendor-master identity and status; bank-suffix consistency; subtotal + tax reconciliation (inclusive/exclusive tax); exact duplicates across historic paid invoices and previous clear-for-AP runs; PO existence/vendor/status/currency/ambiguity; remaining PO commitment **including prior committed value and preceding clear-for-AP runs**.

Decision categories: `CLEAR_FOR_AP`, `HOLD_DUPLICATE`, `HOLD_RISK`, `HOLD_BUDGET`, `REVIEW_PO`, `REVIEW_AMOUNT`, `REQUEST_INFO`. Errors are logged with an `ERROR` status. Risk holds take precedence over lower-risk exceptions. Financial calculations use Python `Decimal` rather than floating point.

## Seven executable demo scenarios

| File | What it proves | Expected disposition |
|---|---|---|
| `01_clean_invoice.pdf` | Structured, valid invoice → AP processing recommendation | `CLEAR_FOR_AP` |
| `02_scanned_invoice.pdf` | Actual image-only PDF → Tesseract OCR → decision | `CLEAR_FOR_AP` |
| `03_exact_duplicate.pdf` | Same vendor + invoice number already in paid-invoice CSV | `HOLD_DUPLICATE` |
| `04_split_po_overspend.pdf` | Invoice would cross PO limit after existing commitments | `HOLD_BUDGET` |
| `05_bank_change.pdf` | Supplier bank digits differ from vetted master | `HOLD_RISK` |
| `06_ambiguous_po.pdf` | Missing PO reference with two plausible open POs | `REVIEW_PO` |
| `07_tax_mismatch.pdf` | Total inconsistent with subtotal and tax | `REVIEW_AMOUNT` |

These are **fictional, clearly labeled data**, not real vendor financial documents. The PDF fixtures were generated by `generate_samples.py`. The sample set tests specific extraction formats; arbitrary invoice formats will not all parse without extending extraction and verification logic.

## Run tests

```bash
python -m pytest -q
python smoke_test.py
```

`pytest` covers rule behavior and hard-fail safety properties. `smoke_test.py` executes seven real PDF requests through the HTTP application (via FastAPI test client), waits for background processing, verifies expected status, event trace and dashboard metrics, and uses an isolated temporary SQLite database. It will not alter your normal demo history.

## Files

- `server.py` — FastAPI endpoints, asynchronous run execution, SQLite history + stage event logging, guarded critical section for PO reservation
- `engine.py` — PDF parsing/OCR, optional LLM extraction fallback, deterministic matching + controls
- `static/index.html` — self-contained interactive UI with live updates, dashboard, history and audit exports
- `data/vendors.csv`, `data/purchase_orders.csv`, `data/historical_invoices.csv` — realistic but fictional procurement dataset
- `data/samples/*.pdf` — seven sample invoices, including image-only PDF
- `tests/test_engine.py` — 18 decision-engine tests
- `smoke_test.py` — full application smoke test, including persistent audit verification
- `ARCHITECTURE_AND_DECISIONS.md` — product design, alternatives, caveats, metrics, roadmap and interview defenses
- `DEMO_SCRIPT.md` — timed five-minute walkthrough and expected outcomes
- `SUBMISSION_EMAIL.md` — message to the hiring coordinator; replace both placeholders with actual URLs

## Submission status and limitations

- ✅ Real app source, real PDF processing, OCR, policy engine, demo inputs, tests, UI and audit logs included.
- ✅ Runs locally and is Docker-packaged for deployment.
- ⬜ **Publicly accessible URL:** not included; deploy from your account and paste the HTTPS address in the submission email.
- ⬜ **Five-minute recording URL:** not included; record a genuine screen demonstration and paste the Loom/Drive recording URL.
- Not a production ERP connector, e-invoice authentication solution, bank-ownership verification service, AP ledger or general-purpose invoice parser. For production use: add identity/access controls, encryption/redaction, reference master sync, receipt/three-way matching, proper payment-approval integration, idempotent queues, comprehensive anomaly scoring, and retention policies.

## Example API

- `GET /api/health` — basic health
- `GET /api/samples` — seven sample choices
- `POST /api/runs/sample/{filename}` — queue actual sample PDF processing
- `POST /api/runs/upload` — `{"filename":"invoice.pdf","pdf_base64":"..."}`
- `GET /api/runs` — persisted run history
- `GET /api/runs/{run_id}` — decision, controls and each stage event
- `GET /api/runs/{run_id}/export` — audit JSON download
- `GET /api/overview` — run counts and disposition overview
- `GET /api/references` — sanitized supplier/PO reference summary

## Interview-ready one-liner

> “InvoiceIQ turns messy vendor PDFs into an auditable AP disposition. I used OCR and optional AI only to read documents, while verifiable business rules handle duplicate detection, cumulative PO checks, bank-change flags and human escalation. The application executes in real time, retains every decision, and deliberately stops before moving money.”
