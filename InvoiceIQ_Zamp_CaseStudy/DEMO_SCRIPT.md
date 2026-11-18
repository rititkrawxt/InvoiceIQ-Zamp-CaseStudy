# InvoiceIQ — five-minute live demo script

**What to record:** genuine full-screen or browser screen capture with narration (Loom, OBS, Windows screen recorder, etc.). **No slides.** Run the program while the recording is made. Use the normal interactive web interface and keep the cursor visible. Ideally start with a clean `data/runs.db` file (stop app first to remove it), so the result history tells the story from zero.

## 0:00–0:35 — Introduce the user pain and design

“Hi, I’m presenting **InvoiceIQ**, my solution for Zamp’s invoice-processing challenge, PS-1. The user is an AP analyst handling hundreds of inconsistent invoice PDFs. The goal is not to summarize a PDF; it is to turn an unstructured invoice into a **traceable financial disposition**. I separated AI-style document understanding from deterministic financial policies, because inaccurate numbers and PO guesses must never auto-release money.”

**Screen:** show the Command Center header and four empty metrics. Point to the PDF upload and to the seven samples.

## 0:35–1:45 — Happy path with actual file processing

“I’ll start with a real PDF. This is a fictional supplier invoice, but the backend processes its bytes, not a mocked response. It extracts the invoice number, supplier identity, PO, subtotal, tax and total, then checks them against the vendor master, PO reference and invoice history.”

**Action:** click **Clean invoice**. Watch the six real stages and wait for `CLEAR FOR AP`. Scroll through the control evidence and show the next action.

“Notice the engine doesn’t say ‘paid’. It says **ready for AP posting review** and retains every control. The audit JSON can be downloaded here, and the run immediately appears in history.”

## 1:45–2:25 — Prove OCR is real

“Not every invoice contains selectable text. This second sample is a raster-only scanned PDF. The process detects that, invokes Tesseract OCR, and executes the same policy engine. I can verify the extraction method in the run result.”

**Action:** click **Scanned invoice**. Wait for `CLEAR FOR AP`; point to **OCR (Tesseract)** in the extraction footer.

## 2:25–3:55 — Two meaningful exceptions (not trivial)

**Action:** click **Exact duplicate**.

“First: duplicates. The invoice has valid supplier details and amounts, but its number already exists for this vendor in historical paid invoices. It is placed on a **duplicate hold**, not quietly processed twice. The exact rule and action are displayed.”

**Action:** click **Split-PO overspend**.

“Second: split POs. The invoice amount alone looks fine, but the PO already has prior commitments. My logic checks **remaining committed budget**, not just whether one invoice is under the original PO total. This invoice gets a **budget hold**, with the limit, previously committed amount and remaining available value explained.”

## 3:55–4:35 — High-risk exception and human judgment

**Action:** click **Bank-account change**, then optionally **Ambiguous purchase order** if there is time.

“A difference in the bank details triggers a hard risk hold with a requirement to verify through a trusted vendor channel. Missing or ambiguous PO references go to human review; the automation does not guess the PO. This is where business judgment and controls matter more than maximizing an auto-approval number.”

## 4:35–5:00 — Dashboard and close

**Action:** show dashboard counters, recent runs, click a history row, and show export.

“Every run is stored with timestamps, decision, complete rule evidence, and a visible stage trace. This prototype uses synthetic datasets and two-way matching, with no actual payment execution. Production next steps are ERP integration, line-level/three-way matching, and human workflow ownership. The demo proves the real end-to-end process and the deliberate edge-case behavior.”

## Back-up demo plan

- If OCR is unexpectedly slow, demonstrate **Clean invoice**, **Exact duplicate**, and **Split-PO overspend** before OCR.
- If you do not have an optional LLM API key, that is **not** a blocker. The PDF/OCR and deterministic financial decisioning pipeline still executes.
- If the app is not yet deployed, **do not submit a localhost URL**. Host it under your own HTTPS domain/hosting account, test it from a different device, and only then add the URL to the email.
- If you run the exact same previously cleared invoice again, it will correctly show a duplicate hold. Restarting the service does not reset data: delete the local demo-only database with the server stopped if you need a clean baseline.
- Actual video recording is required; this script is not a substitute.
