"""Run the actual submission ZIP against the environment-configured API."""
from pathlib import Path
from datetime import datetime, timezone
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]

def main():
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = ROOT / os.environ.get('PSB_AUDIT_OUT', 'results/live_submission_' + run_id)
    out.mkdir(parents=True, exist_ok=False)
    path=ROOT/'dist/PSB_baseline_submission.zip'
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory() as temp:
        p=Path(temp)
        with zipfile.ZipFile(path) as archive:
            archive.extractall(p)
        data=p/'data';data.mkdir()
        shutil.copyfile(ROOT/'organizer/knowledge-base.zip',data/'knowledge-base.zip')
        shutil.copyfile(ROOT/'organizer/demo_questions.csv',data/'questions.csv')
        start=time.monotonic()
        result=subprocess.run([sys.executable,'-S',str(p/'solution.py')],cwd=p,
            env={**os.environ,'DATA_DIR':str(data),'MAX_WORKERS':'2','TOP_K':'6',
                 'MAX_TOKENS':'8192','PSB_RUN_SECONDS':'800'},capture_output=True,text=True,timeout=850)
        elapsed=time.monotonic()-start
        rows=list(csv.DictReader((p/'submission.csv').open(encoding='utf-8-sig',newline='')))
        shutil.copyfile(p/'submission.csv',out/'submission.csv')
        (out/'submission_run.txt').write_text(result.stderr)
        expected=list(csv.DictReader((data/'questions.csv').open(encoding='utf-8-sig',newline='')))
        report={'archive_sha256':digest,'model':os.environ.get('LLM_MODEL'),
                'seconds':round(elapsed,3),'exit_code':result.returncode,'rows':len(rows),
                'unique_ids':len({r['id'] for r in rows}),
                'all_ids_match':[r['id'] for r in expected]==[r['id'] for r in rows],
                'all_answers_valid':all(r['answer'].strip() and len(r['answer'])<=10000 for r in rows),
                'technical_answers':sum('технической ошибки' in r['answer'] for r in rows),
                'unverified_answers':sum('достаточно проверенных оснований' in r['answer'] for r in rows),
                'platform_submission':False, 'output_directory':str(out.relative_to(ROOT)) if out.is_relative_to(ROOT) else str(out)}
        (out/'submission_summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
