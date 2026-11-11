from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / 'evaluation'
VERSION = '1.0.0'

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)

def commit():
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()

def archive(path, files):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, body in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, body.encode('utf-8') if isinstance(body, str) else body)
    return digest(path.read_bytes())

def apportion(n, weights):
    counts = [n * w // sum(weights) for w in weights]
    order = sorted(range(len(weights)), key=lambda i: (-(n * weights[i] % sum(weights)), i))
    for i in order[:n - sum(counts)]:
        counts[i] += 1
    return counts

def question_text(question, history=()):
    if not history:
        return question
    labels = {'user': 'Пользователь', 'assistant': 'Ассистент'}
    return '\n'.join(f'{labels[item["role"]]}: {item["content"]}' for item in history) + '\nПользователь: ' + question
