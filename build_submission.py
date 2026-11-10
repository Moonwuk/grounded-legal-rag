"""Build the platform ZIP with root-level modules only."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT=Path(__file__).resolve().parent
NAMES=['solution.py','psb_corpus.py','psb_retrieval.py','psb_policy.py','psb_llm.py','requirements.txt']


def main():
    out=ROOT/'dist';out.mkdir(exist_ok=True)
    path=out/'PSB_baseline_submission.zip'
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name in NAMES:
            info=zipfile.ZipInfo(name,date_time=(2026,11,10,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,(ROOT/'prototype'/name).read_bytes())
    with zipfile.ZipFile(path) as archive:
        if archive.namelist()!=NAMES or archive.testzip() is not None:
            raise ValueError('invalid_submission_zip')
    manifest={'file':path.name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'entries':NAMES,
              'platform_execution':'NOT RUN; proxy credentials unavailable in this session'}
    (ROOT/'results/submission_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    print(json.dumps(manifest,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
