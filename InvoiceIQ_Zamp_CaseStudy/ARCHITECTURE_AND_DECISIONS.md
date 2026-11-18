# InvoiceIQ — Product Case Study & Design Rationale

**Chosen problem:** Zamp 2026 AI Solutions Analyst Candidate Guide, PS-1 (Invoice Processing — From PDF to Decision).

## 1. Customer pain and user

An Accounts Payable (AP) analyst repeatedly opens invoices, locates the vendor, finds the associated purchase order (PO), compares amounts and tax treatments, and decides whether an invoice can move to posting review. Vendors use different document formats. Bad data, duplicates and PO overspend create financial exposure; too much manual checking slows legitimate invoices.

**Primary user:** AP analyst. **Adjacent users:** AP control owner, procurement owner, finance operations lead. **Job to be done:** “When an invoice arrives, show me what it says, what system data contradicts it, and exactly what action is safe next.”

## 2. Success criteria and decision hierarchy

The prototype demonstrates: (a) a real invoice becomes a validated structured record; (b) ambiguous or risky cases do not quietly become approvals; (c) control rationale can be inspected and exported; (d) processing and historical runs are visible in one UI; and (e) fresh samples are actually executed rather than mocked.

**North-star metric (proposed, not measured):** percentage of eligible invoices that reach AP review with no manual data-entry work and zero observed policy-control bypasses. Guardrails: false-clear rate, reviewer override frequency, duplicate escape rate, OCR exceptions and turnaround time. Do not claim numerical improvements without a measured baseline.

## 3. End-to-end data flow

```text
Invoice PDF (text layer or scanned image)
              |
   Validate: MIME/signature, 10MB, 1-10 pages
              |
   PyMuPDF text extraction; if empty, Tesseract OCR
              |
   Strict field normalization; optional LLM field fallback
              |
   Supplier master      Purchase order master     Paid-invoice history
         \                       |                      /
          --------- deterministic policy engine --------
                                 |
                Risk/duplicate/amount/PO/identity checks
                                 |
             Disposition + evidence + human next action
                                 |
                 SQLite run + timestamped event history
                                 |
           UI dashboard / live view / audit JSON export
```

## 4. Product decisions and why

**Why choose PS-1?** It visibly combines AI document intelligence, operational workflow design, deterministic finance controls, explainable exceptions and measurable outcomes. It makes the split between high-variance document perception and high-integrity authorization especially clear.

**Why not LLM-driven approval?** LLMs can hallucinate fields, depend on prompt changes and fail silently. Invoice acceptance should be reproducible and based on verified supplier/PO data. The language model is optional and constrained to extraction fallback. It is not required to test the prototype or to get a safe decision.

**Why not fuzzy-match a PO?** A missing PO with one plausible match still goes to `REVIEW_PO` for human confirmation; multiple plausible matches are not auto-selected. A wrong PO can incorrectly spend someone else's remaining budget.

**Why not simply check the original PO face value?** Split invoicing requires considering already committed value plus prior clear-for-AP runs. The engine reserves capacity for earlier approved-for-review invoices and serializes concurrent decisions inside an SQLite `BEGIN IMMEDIATE` transaction. `prior_committed` is an **authoritative demo snapshot that already includes externally recorded historic payments**, avoiding double counting them from the duplicate-check historical file.

**Why different hold/review types?** The user should immediately understand whether the action is “stop for risk”, “investigate possible duplicate”, “get an amended PO”, “ask for a correction”, or “confirm the PO”. Labels are deliberately not collapsed into one opaque “failure”.

**Why use simple CSV data rather than a procurement API?** The guide permits realistic synthetic data. CSVs keep the prototype self-contained, easily testable and independent of private ERP credentials. In production these would become audited integrations with reliable transaction isolation.

## 5. Four non-trivial edge cases to lead with

| Edge case | Risk | Behavior | Human response |
|---|---|---|---|
| Historical duplicate | Paying the same invoice twice | `HOLD_DUPLICATE` | Find original AP record and request clarification |
| Split PO overspend | Individually reasonable invoice exceeds remaining aggregate PO budget | `HOLD_BUDGET` | Obtain approved amendment or corrected invoice |
| Vendor bank suffix changed | Invoice could redirect payment | `HOLD_RISK` | Independently reverify account through trusted supplier channel |
| Ambiguous PO reference | Invoice could be attributed to wrong PO | `REVIEW_PO` | Procurement selects and confirms the correct PO |

**Extra:** actual image-only scanned PDF that invokes OCR; mismatched tax math; invalid invoice date/currency; inactive/unrecognized vendor; repeated clear-for-AP invoices.

## 6. Assumptions and deliberately unimplemented behavior

- This is a **two-way** invoice-to-PO check: no goods receipt, service acceptance, quantity-by-line 3-way matching, or actual payment authorization.
- The purchase-order dataset's `prior_committed` includes amounts already present in the external historical-invoices reference. History is read **separately** for duplicate detection, and not added again to budget commitments.
- Exact supplier-name/GSTIN/ID agreement is required when those fields are provided. A parse that yields conflicting identifiers fails closed, rather than silently fuzzy-joining a different supplier.
- Amounts are assumed to be denominated in the stated currency. Currency absence requires clarification; non-INR currency would need matching supplier/PO data and UI currency formatting adjustments.
- Demo invoices use ISO invoice dates and a subset of realistic text labels. Universal OCR/layout extraction is beyond this one-week build.
- The bank-last-four check is **not bank ownership verification**. A match only establishes consistency against a separately maintained supplier master.
- No claim of Indian GST compliance validation or government GSTIN verification. The supplied GSTIN is checked for correspondence to the demo supplier master, not validity against an official registry.
- Files are not stored long term: run results and sanitized extraction fields are retained in SQLite; the original uploaded PDF is processed in memory.
- SQLite supports a robust single-instance prototype, not distributed high-scale coordination; production would use durable queues, a stronger transactional datastore, access control and infrastructure observability.

## 7. Implementation and measurable evaluation

**Functional coverage:** all seven scenario PDFs invoke the same file-processing pipeline, including a true raster-only OCR case. Run `python -m pytest -q` and `python smoke_test.py` to verify. Recorded samples are fictional; do not represent measured accuracy on a representative production corpus.

**Evaluations to track before production:** field accuracy (per-field exact-match against hand-labeled ground truth), invoice-level disposition accuracy, false clear rate, reviewer effort, rate of “request info” decisions, duplicate detection sensitivity/precision, monetary difference detection, latency p50/p95, and percentage of audit trails with complete inputs/controls. Segment by vendor, scan quality, tax treatment, PDF layout and OCR language.

**Possible pilot target hypotheses, not observed outcomes:** 40–60% reduction in manual entry time on common invoice formats, over 95% correct vendor/PO identification on a controlled pilot corpus, and zero incorrect automatic payment releases (none are supported here). Baseline, corpus and gates must be defined before performance claims.

## 8. Productionization roadmap

**Week 1 — candidate prototype:** shipped executable PDF/OCR + rule engine + step trace + example dataset + dashboard + edge cases.

**Next phase — controlled pilot:** retrieve invoices from a dedicated email queue; connect ERP vendor/PO APIs; review workflow with assignment and resolution; idempotency keys; validation of signed reference data; line-item extraction with evidence spans; stronger privacy/auth controls.

**Later phase — wider rollout:** receipt-based 3-way matching, user/role permissions, tax/currency localization, distributed job queue, versioned rule policies, monitoring and feedback loop, invoice-image evidence viewer, retry/dead-letter system, data retention and compliance review.

## 9. High-value interview questions and responses

**“Why isn’t AI making the decision?”** Because an AI can help transcribe a document but should not decide whether money is spent; transparent deterministic rules prevent a fabricated number or ungrounded PO guess from causing a financial loss.

**“What if OCR reads the wrong total?”** Reconcile subtotal + tax and PO remaining budget, flag missing/unreconciled values, and require review. OCR has residual risk; a more complete system would attach document-level confidence and visually linked evidence.

**“What if the vendor has multiple invoices on one PO?”** The policy engine accounts for cumulative commitments. An invoice that fits on its own can still receive a budget hold once preceding commitments are considered.

**“What if a salesperson asks you to auto-approve everything?”** Define automation boundaries and acceptable false-clear costs with the finance control owner. Offer fast processing for consistent invoices; keep unsafe or ambiguous cases as human checkpoints.

**“What is the weakest part?”** Supporting arbitrary layouts, supplier-master verification, and three-way matching are not production-ready. The candidate build intentionally prioritizes a demonstrated happy path, high-value exceptions, and an honest audit trail over an unsupported claim of universal accuracy.

**“What if two invoices race to use the same PO amount?”** The same-instance SQLite transaction serializes `CLEAR_FOR_AP` reservation decisions so both cannot evaluate against an unchanged balance. A multi-instance deployment would require durable database locks and idempotency.
