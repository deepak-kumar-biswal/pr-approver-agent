"""
Quarterly PDF generator Lambda.
- Scans DDB table PRRuns (sampled) and writes a simple PDF summary to S3 at reports/YYYY-QN.pdf
- Replace the naive _pdf_bytes with ReportLab for production styling if desired.
"""
import boto3
from datetime import datetime as dt

S3 = boto3.client('s3')
DDB = boto3.client('dynamodb')

def _quarter(date):
    return (date.month - 1)//3 + 1

def _pdf_bytes(title, lines):
    # Minimal single-page PDF placeholder; for rich formatting, use ReportLab.
    content = f"{title}\n\n" + "\n".join(lines)
    return content.encode('utf-8')

def handler(event, context):
    bucket = event.get('bucket')
    if not bucket:
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
    lines = [
        f"Total runs (sampled): {total}",
        "Verdict mix: TBD",
        "Failures: TBD",
        "Median time saved: TBD",
    ]
    pdf = _pdf_bytes(title, lines)
    key = f"reports/{year}-Q{q}.pdf"
    S3.put_object(Bucket=bucket, Key=key, Body=pdf, ContentType='application/pdf')
    return {"status":"ok","report_key": key}
