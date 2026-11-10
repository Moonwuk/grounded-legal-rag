"""Alternate original formats: parse probes, not duplicate benchmark documents.

PDF extraction needs optional pypdf (not required by benchmark or submission).
"""
from pathlib import Path
from datetime import datetime,timezone
import sys
from evaluation.collect_public import fetch
from evaluation.common import EVAL,ROOT,read,write,digest
sys.path.insert(0,str(ROOT/'prototype'))
from psb_corpus import read_docx

def main():
    lock=read(EVAL/'public_documents/sources.lock.json');rows=[]
    for repo,path,license in [
        ('General-Legal/legal-templates','docx-originals/privacy-policy-gdpr-enhanced.docx','CC0-1.0'),
        ('General-Legal/legal-templates','docx-originals/privacy-policy-u-s-only.docx','CC0-1.0'),
        ('mozilla/legal-docs','ru/pdf/mdn_plus_privacy.pdf','CC-BY-SA-3.0'),
        ('mozilla/legal-docs','ru/pdf/mdn_plus_terms.pdf','CC-BY-SA-3.0')]:
        sha=lock[repo]['commit'];url=f'https://raw.githubusercontent.com/{repo}/{sha}/{path}'
        dest=EVAL/'public_documents/alternate_formats'/repo.replace('/','__')/path
        try:
            raw=dest.read_bytes() if dest.exists() else fetch(url)
            dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        except Exception as exc:
            rows.append(dict(source=url,status='not_downloaded',error=type(exc).__name__));continue
        row=dict(source=url,repository=repo,license=license,commit=sha,origin='public',original_format=dest.suffix,
            downloaded_utc=datetime.now(timezone.utc).isoformat(),language='ru' if repo.startswith('mozilla/') else 'en',
            sha256=digest(raw),downloaded=True,indexed=False,reason_not_indexed='alternate format of an existing conceptual document; avoid duplicates')
        try:
            if dest.suffix=='.docx':text=read_docx(raw);row['parser']='production read_docx'
            else:
                from pypdf import PdfReader
                text='\n'.join(p.extract_text() or '' for p in PdfReader(dest).pages);row['parser']='optional pypdf; PDF not supported by production loader'
            row.update(status='parsed',characters=len(text),nonempty=bool(text.strip()))
            dest.with_suffix(dest.suffix+'.extracted.txt').write_text(text,encoding='utf-8')
        except Exception as exc:
            code=str(exc) if isinstance(exc,ValueError) and str(exc).replace('_','').isalnum() else type(exc).__name__
            row.update(status='parse_not_verified',error=code)
        rows.append(row)
    write(EVAL/'reports/alternate-format-probes.json',rows);print(rows)

if __name__=='__main__':main()
