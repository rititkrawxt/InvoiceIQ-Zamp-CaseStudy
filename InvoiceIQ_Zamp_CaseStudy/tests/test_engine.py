"""Candidate test suite: run `pytest -q`."""
import copy
from pathlib import Path

import pytest

from engine import decide, extract_pdf, parse_fields

SAMPLES = Path(__file__).resolve().parents[1] / 'data' / 'samples'


def perform(name, previous=None):
    return decide(extract_pdf((SAMPLES / name).read_bytes()), previous or [])


def mod(name, changes, previous=None):
    extraction = extract_pdf((SAMPLES / name).read_bytes())
    extraction['fields'].update(changes)
    return decide(extraction, previous or [])


def fail_codes(result):
    return {r['code'] for r in result['rules'] if r['result'] != 'PASS'}


def test_clean_pdf_is_ready_for_ap_not_payment():
    r=perform('01_clean_invoice.pdf')
    assert r['status']=='CLEAR_FOR_AP'
    assert 'not a payment instruction' in ' '.join(r['assumptions'])
    assert not r['failed_controls']


def test_scanned_pdf_is_really_ocr_not_embedded_text():
    b=(SAMPLES/'02_scanned_invoice.pdf').read_bytes()
    import fitz
    doc=fitz.open(stream=b,filetype='pdf')
    assert not doc[0].get_text('text').strip()
    r=decide(extract_pdf(b),[])
    assert r['status']=='CLEAR_FOR_AP'
    assert r['ocr_used'] is True


def test_paid_duplicate_hard_hold():
    r=perform('03_exact_duplicate.pdf')
    assert r['status']=='HOLD_DUPLICATE'
    assert 'EXACT_DUPLICATE' in fail_codes(r)


def test_overspend_including_previous_po_commitments():
    r=perform('04_split_po_overspend.pdf')
    assert r['status']=='HOLD_BUDGET'
    assert r['po_remaining_before']=='5000.00'


def test_suspicious_bank_change_takes_priority():
    r=perform('05_bank_change.pdf')
    assert r['status']=='HOLD_RISK'
    assert 'BANK_CHANGE' in fail_codes(r)
    assert r['fields']['bank_last4']=='••••9999'


def test_ambiguous_missing_po_not_guessed():
    r=perform('06_ambiguous_po.pdf')
    assert r['status']=='REVIEW_PO'
    assert r['po_number'] is None


def test_tax_mismatch_not_auto_accepted():
    assert perform('07_tax_mismatch.pdf')['status']=='REVIEW_AMOUNT'


def test_internal_duplicate_across_separate_runs():
    previous=[perform('01_clean_invoice.pdf')]
    r=perform('01_clean_invoice.pdf',previous)
    assert r['status']=='HOLD_DUPLICATE'


def test_two_invoices_which_sum_above_remaining_po_budget():
    previous=[perform('01_clean_invoice.pdf')]
    r=mod('01_clean_invoice.pdf',{'invoice_number':'NS-2026-046','subtotal':'20000.00','tax':'0.00','total':'20000.00'},previous)
    assert r['status']=='CLEAR_FOR_AP'
    previous.append(r)
    r2=mod('01_clean_invoice.pdf',{'invoice_number':'NS-2026-047','subtotal':'7000.00','tax':'0.00','total':'7000.00'},previous)
    assert r2['status']=='HOLD_BUDGET'
    assert r2['po_remaining_before']=='6400.00'


def test_missing_total_requires_corrected_invoice():
    assert mod('01_clean_invoice.pdf',{'total':None})['status']=='REQUEST_INFO'


def test_missing_currency_cannot_be_guessed():
    r=mod('01_clean_invoice.pdf',{'currency':None})
    assert r['status']=='REQUEST_INFO'
    assert 'CURRENCY_PRESENT' in fail_codes(r)


def test_unknown_vendor_is_never_clear():
    r=mod('01_clean_invoice.pdf',{'vendor_id':'VEN-999','vendor_name':'Fake Vendor','gstin':'09NOTREAL0001Z9'})
    assert r['status']=='HOLD_RISK'


def test_future_date_requires_vendor_correction():
    assert mod('01_clean_invoice.pdf',{'invoice_date':'2099-12-31'})['status']=='REQUEST_INFO'


def test_corrupt_pdf_fails_safely():
    with pytest.raises(ValueError):extract_pdf(b'not pdf')


def test_tax_inclusive_is_mathematically_supported():
    r=mod('01_clean_invoice.pdf',{'tax_mode':'inclusive','subtotal':'11800.00','total':'11800.00'})
    assert r['status']=='CLEAR_FOR_AP'


def test_no_po_but_single_open_po_is_not_auto_cleared(tmp_path):
    # Restrict a new fixture to one PO while leaving other reference data intact.
    import shutil
    for f in ('vendors.csv','historical_invoices.csv'):
        shutil.copyfile(SAMPLES.parent/f,tmp_path/f)
    (tmp_path/'purchase_orders.csv').write_text(
      'po_number,vendor_id,currency,po_limit,prior_committed,status\nPO-1005,VEN-202,INR,50000.00,0.00,OPEN\n')
    a=extract_pdf((SAMPLES/'02_scanned_invoice.pdf').read_bytes())
    a['fields']['po_number']=None
    r=decide(a,[],data_dir=tmp_path)
    assert r['status']=='REVIEW_PO'
    assert r['po_number']=='PO-1005'


def test_corrected_previous_review_is_not_falsely_blocked_as_paid_duplicate():
    earlier=mod('01_clean_invoice.pdf',{'tax':'1700.00'})
    assert earlier['status']=='REVIEW_AMOUNT'
    assert perform('01_clean_invoice.pdf',[earlier])['status']=='CLEAR_FOR_AP'

def test_negative_tax_never_auto_clears():
    r=mod('01_clean_invoice.pdf',{'subtotal':'13000.00','tax':'-1200.00','total':'11800.00'})
    assert r['status']=='REVIEW_AMOUNT'
