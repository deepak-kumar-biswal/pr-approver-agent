"""
Quarterly PDF generator Lambda.
- Scans DDB table PRRuns (sampled) and writes a rich PDF summary to S3 at reports/YYYY-QN.pdf
- Uses ReportLab for basic styling and charts; falls back to text-only if ReportLab unavailable.
"""
import io
import statistics
import boto3
from datetime import datetime as dt
from lambdas._log import log

S3 = boto3.client('s3')
DDB = boto3.client('dynamodb')

def _quarter(date):
    return (date.month - 1)//3 + 1

def _pdf_bytes(title, stats):
    try:
        # Lazy import to keep lambda import fast
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib import colors
        from reportlab.pdfgen import canvas
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=LETTER)
        styles = getSampleStyleSheet()
        story = []
        story.append(Paragraph(title, styles['Title']))
        story.append(Spacer(1, 12))

        # Summary table
        data = [
            ["Total runs", stats.get('total', 0)],
            ["Green", stats.get('green', 0)],
            ["Amber", stats.get('amber', 0)],
            ["Red", stats.get('red', 0)],
            ["Median review time (ms)", stats.get('p50_ms', '-')],
            ["p90 review time (ms)", stats.get('p90_ms', '-')],
            ["Estimated engineer-hours saved", f"{stats.get('hours_saved', 0):.1f}"],
            ["Top violations", ", ".join(stats.get('top_violations', [])[:5]) or '-'],
        ]
        tbl = Table(data, hAlign='LEFT')
        tbl.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 12))

        doc.build(story)
        pdf = buf.getvalue()
        buf.close()
        return pdf
    except Exception:
        # Fallback to plain text if ReportLab not present
        content = [
            title,
            f"Total runs: {stats.get('total', 0)}",
            f"Green/Amber/Red: {stats.get('green', 0)}/{stats.get('amber', 0)}/{stats.get('red', 0)}",
            f"Median ms: {stats.get('p50_ms', '-')}; p90 ms: {stats.get('p90_ms', '-')}",
            f"Hours saved: {stats.get('hours_saved', 0):.1f}",
            f"Top violations: {', '.join(stats.get('top_violations', []))}",
        ]
        return ("\n".join(content)).encode('utf-8')

def handler(event, context):
    log("INFO", "quarterly_report start", event)
    bucket = event.get('bucket')
    if not bucket:
        log("ERROR", "missing bucket", event)
        raise ValueError("bucket is required")
    table = event.get('table', 'PRRuns')
    today = dt.utcnow().date()
    q = _quarter(today)
    year = today.year
    title = f"PR Review Quarterly Report {year} Q{q}"
    items = []
    paginator = DDB.get_paginator('scan')
    for page in paginator.paginate(TableName=table, PaginationConfig={'MaxItems': 500}):
        items.extend(page.get('Items', []))
    total = len(items)
    # Simple aggregations by attributes commonly written in audit traces
    def _sval(it, k):
        v = it.get(k)
        if isinstance(v, dict):
            return v.get('S') or v.get('s')
        return None
    def _nval(it, k):
        v = it.get(k)
        if isinstance(v, dict):
            try:
                return float(v.get('N') or v.get('n'))
            except Exception:
                return None
        return None
    greens = sum(1 for it in items if (_sval(it, 'verdict') or '').lower() == 'green')
    ambers = sum(1 for it in items if (_sval(it, 'verdict') or '').lower() == 'amber')
    reds = sum(1 for it in items if (_sval(it, 'verdict') or '').lower() == 'red')
    confs = [(_nval(it,'confidence') or 0.0) for it in items]
    times = [(_nval(it,'review_ms') or 0.0) for it in items if _nval(it,'review_ms')]
    p50 = statistics.median(times) if times else None
    p90 = statistics.quantiles(times, n=10)[8] if len(times) >= 10 else None
    # Heuristic time-saved: assume 5 minutes saved for green, 2 minutes for amber, 0 for red
    hours_saved = ((greens*5 + ambers*2)/60.0)
    # Simple top violations aggregation if present
    violations = []
    for it in items:
        v = _sval(it, 'violation')
        if v:
            violations.append(v)
    top_violations = sorted(set(violations))
    stats = {
        'total': total,
        'green': greens,
        'amber': ambers,
        'red': reds,
        'p50_ms': int(p50) if p50 else '-',
        'p90_ms': int(p90) if p90 else '-',
        'hours_saved': hours_saved,
        'top_violations': top_violations,
    }
    pdf = _pdf_bytes(title, stats)
    key = f"reports/{year}-Q{q}.pdf"
    S3.put_object(Bucket=bucket, Key=key, Body=pdf, ContentType='application/pdf')
    log("INFO", "quarterly_report done", event, key=key, total=total)
    return {"status":"ok","report_key": key}
