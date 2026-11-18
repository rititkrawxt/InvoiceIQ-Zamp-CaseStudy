"""Generate realistic, self-contained PDF fixtures (including a true raster-only PDF)."""
from pathlib import Path
import io
import fitz
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from PIL import Image
from engine import BASE

OUT = BASE / 'data' / 'samples'
OUT.mkdir(parents=True,exist_ok=True)

samples = [
('01_clean_invoice.pdf',{'vendor':'Northstar Components Pvt Ltd','id':'VEN-101','gstin':'07ABCDE1234F1Z5','no':'NS-2026-041','date':'2026-11-14','po':'PO-1001','bank':'4321','subtotal':'10000.00','tax':'1800.00','total':'11800.00'},False),
('02_scanned_invoice.pdf',{'vendor':'Azure Systems India Pvt Ltd','id':'VEN-202','gstin':'29ABCDE1234F1Z7','no':'AZ-2026-112','date':'2026-11-15','po':'PO-1005','bank':'5478','subtotal':'2000.00','tax':'360.00','total':'2360.00'},True),
('03_exact_duplicate.pdf',{'vendor':'Northstar Components Pvt Ltd','id':'VEN-101','gstin':'07ABCDE1234F1Z5','no':'NS-2026-009','date':'2026-11-10','po':'PO-1001','bank':'4321','subtotal':'10000.00','tax':'1800.00','total':'11800.00'},False),
('04_split_po_overspend.pdf',{'vendor':'Northstar Components Pvt Ltd','id':'VEN-101','gstin':'07ABCDE1234F1Z5','no':'NS-2026-077','date':'2026-11-16','po':'PO-1002','bank':'4321','subtotal':'6000.00','tax':'0.00','total':'6000.00'},False),
('05_bank_change.pdf',{'vendor':'Cloudline Technologies','id':'VEN-404','gstin':'07ABCDE1234F1Z6','no':'CL-2026-052','date':'2026-11-16','po':'PO-1006','bank':'9999','subtotal':'15000.00','tax':'2700.00','total':'17700.00'},False),
('06_ambiguous_po.pdf',{'vendor':'Meridian Industrial Supplies','id':'VEN-303','gstin':'27ABCDE1234F1Z9','no':'ME-2026-014','date':'2026-11-16','po':None,'bank':'1919','subtotal':'4000.00','tax':'720.00','total':'4720.00'},False),
('07_tax_mismatch.pdf',{'vendor':'Northstar Components Pvt Ltd','id':'VEN-101','gstin':'07ABCDE1234F1Z5','no':'NS-2026-055','date':'2026-11-16','po':'PO-1007','bank':'4321','subtotal':'10000.00','tax':'1800.00','total':'12100.00'},False),
]

def draw_pdf(fields, alternate=False):
    buf=io.BytesIO(); c=canvas.Canvas(buf,pagesize=A4)
    W,H=A4
    c.setFillColor(HexColor('#0f1d39' if not alternate else '#164e63'));c.rect(0,H-116,W,116,fill=1,stroke=0)
    c.setFillColor(HexColor('#ffffff'));c.setFont('Helvetica-Bold',24);c.drawString(45,H-54,'TAX INVOICE')
    c.setFont('Helvetica',10);c.setFillColor(HexColor('#bdcbed'));c.drawString(45,H-79,'DEMO / FICTIONAL DATA  |  INVOICEIQ TEST SET')
    c.setFont('Helvetica-Bold',12);c.setFillColor(HexColor('#263650'));c.drawString(45,H-155,'Supplier & invoice details')
    if alternate:
        lines=[('From',fields['vendor']),('Supplier ID',fields['id']),('Tax ID',fields['gstin']),
               ('Inv #',fields['no']),('Date',fields['date'])]
        if fields['po']:lines.append(('Purchase Order',fields['po']))
        lines.extend([('Currency','INR'),('Account Last 4',fields['bank']),('Tax Mode','exclusive')])
    else:
        lines=[('Vendor',fields['vendor']),('Vendor ID',fields['id']),('GSTIN',fields['gstin']),
               ('Invoice Number',fields['no']),('Invoice Date',fields['date'])]
        if fields['po']:lines.append(('PO Number',fields['po']))
        lines.extend([('Currency','INR'),('Bank Last 4',fields['bank']),('Tax Mode','exclusive')])
    y=H-189
    for label,value in lines:
        c.setFont('Helvetica',12);c.setFillColor(HexColor('#172541'))
        c.drawString(53,y,f'{label}: {value}');y-=27
    c.setStrokeColor(HexColor('#e3e8f3'));c.line(45,y-4,W-45,y-4)
    y-=37;c.setFont('Helvetica-Bold',12);c.drawString(45,y,'Billing summary');y-=30
    for label,key in ([('Net Amount','subtotal'),('GST','tax'),('Amount Payable','total')] if alternate
                      else [('Subtotal','subtotal'),('Tax','tax'),('Total','total')]):
        c.setFont('Helvetica-Bold' if label=='Total' else 'Helvetica',12)
        c.drawString(53,y,f'{label}: {fields[key]}');y-=29
    c.setFont('Helvetica',9);c.setFillColor(HexColor('#8490a2'))
    c.drawString(45,68,'Sample created for evaluation only. No real supplier, account or transaction.')
    c.showPage();c.save();return buf.getvalue()

for filename, fields, scanned in samples:
    pdf=draw_pdf(fields,alternate=filename in {'05_bank_change.pdf','06_ambiguous_po.pdf','07_tax_mismatch.pdf'})
    if scanned:
        # Convert to raster and wrap as PDF: embedded text extraction must fail, forcing real OCR.
        doc=fitz.open(stream=pdf,filetype='pdf')
        pix=doc[0].get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
        img=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
        raster_bytes=io.BytesIO();img.save(raster_bytes,format='JPEG',quality=84,optimize=True)
        out=fitz.open();p=out.new_page(width=A4[0],height=A4[1]);p.insert_image(p.rect,stream=raster_bytes.getvalue())
        pdf=out.tobytes();out.close();doc.close()
    (OUT / filename).write_bytes(pdf)
    print(filename,len(pdf),'bytes','raster' if scanned else 'text')
