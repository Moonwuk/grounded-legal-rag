"""Download an allowlisted set of licensed public templates/policies, no crawling
of signed contracts or personal records. Store original bytes and attribution.
"""
from __future__ import annotations
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
import json
import re
import time
from urllib.error import URLError,HTTPError
from urllib.parse import quote
from urllib.request import Request,urlopen
from evaluation.common import EVAL,VERSION,archive,canonical,digest,read,write

SOURCES=[
    dict(repo='capysta2016/samozanyaty-docs-templates',license='CC0-1.0',license_file='LICENSE',markers=['CC0','Public Domain'],language='ru',pattern=r'^(contracts|acts)/.*\.md$',kind='contract_or_act'),
    dict(repo='dshushin/nvim.bilingual',license='MIT',license_file='LICENSE',markers=['Permission is hereby granted'],language='ru-en',pattern=r'^templates/contracts/en-ru\.md$',kind='bilingual_contract'),
    dict(repo='General-Legal/legal-templates',license='CC0-1.0',license_file='LICENSE',markers=['CC0'],language='en',pattern=r'^templates/[^/]+/template\.md$',kind='corporate_template'),
    dict(repo='mozilla/legal-docs',license='CC-BY-SA-3.0',license_file='LICENSE.md',markers=['Attribution-ShareAlike 3.0'],language='path',pattern=r'^(ru|en|de|fr|es|it|pl|tr|pt-BR)/[^/]+\.md$',kind='public_policy')]

def fetch(url):
    for attempt in range(3):
        try:return fetch_once(url)
        except (URLError,TimeoutError):
            if attempt==2:raise
            time.sleep(attempt+1)

def fetch_once(url):
    with urlopen(Request(url,headers={'User-Agent':'PSB-corpus-evaluation/1.0 (public research corpus)','Accept':'application/vnd.github+json'}),timeout=30) as r:
        raw=r.read(8*1024*1024+1)
        if len(raw)>8*1024*1024:raise ValueError('source_size_limit')
        return raw

def words(text):return set(re.findall(r'\w+',text.casefold()))

def collect(limit=140,refresh=False):
    base=EVAL/'public_documents';base.mkdir(exist_ok=True)
    lock_path=base/'sources.lock.json';lock=read(lock_path) if lock_path.exists() and not refresh else {}
    items=[];licences=[]
    for source in SOURCES:
        repo=source['repo'];repo_dir=base/'licenses'/repo.replace('/','__');repo_dir.mkdir(parents=True,exist_ok=True)
        if repo not in lock:
            info=json.loads(fetch('https://api.github.com/repos/'+repo))
            sha=json.loads(fetch(f'https://api.github.com/repos/{repo}/commits/{info["default_branch"]}'))['sha']
            tree=json.loads(fetch(f'https://api.github.com/repos/{repo}/git/trees/{sha}?recursive=1'))
            if tree.get('truncated'):raise ValueError('truncated_source_tree')
            paths=[x['path'] for x in tree['tree'] if x['type']=='blob' and re.match(source['pattern'],x['path'])]
            # RU first; don't inflate count with generated preview duplicates.
            paths=[p for p in paths if 'preview' not in p and 'preamble' not in p]
            paths=sorted(paths,key=lambda p:(not p.startswith('ru/'),p))
            lock[repo]=dict(commit=sha,paths=paths)
            write(lock_path,lock)
        record=lock[repo];sha=record['commit']
        licence_url=f'https://raw.githubusercontent.com/{repo}/{sha}/{source["license_file"]}'
        licence=fetch(licence_url).decode('utf-8-sig')
        if not all(m.casefold() in licence.casefold() for m in source['markers']):raise ValueError('license_verification_failed')
        (repo_dir/'LICENSE.txt').write_text(licence,encoding='utf-8')
        licences.append(dict(repository=repo,commit=sha,license=source['license'],license_url=licence_url))
        paths=record['paths'][:max(0,limit-len(items))]
        def download(path):
            url=f'https://raw.githubusercontent.com/{repo}/{sha}/'+quote(path)
            dest=base/'originals'/repo.replace('/','__')/path
            raw=dest.read_bytes() if dest.exists() else fetch(url)
            text=raw.decode('utf-8-sig')
            if not text.strip() or '\ufffd' in text:raise ValueError('invalid_source_text')
            # Reject likely private contact/secret data; template placeholders and
            # official generic corporate contacts may remain. No signed documents.
            if re.search(r'\b\d{10,12}\b',text):return None
            dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
            name=repo.replace('/','__')+'/'+path
            lang=path.split('/')[0] if source['language']=='path' else source['language']
            return dict(name=name,source_url=f'https://github.com/{repo}/blob/{sha}/'+quote(path),download_url=url,
                repository=repo,license=source['license'],license_url=licence_url,downloaded_utc=datetime.now(timezone.utc).isoformat(),
                original_format=Path(path).suffix,sha256=digest(raw),document_type=source['kind'],language=lang,origin='public',
                authority='unverified_public_template_or_policy; not independent legal truth',text=text,
                original_relative_path=str(dest.relative_to(EVAL)),modified=False)
        with ThreadPoolExecutor(max_workers=4) as pool:
            for item in pool.map(download,paths):
                if item:items.append(item)
        print(f'collected={len(items)} repository={repo}',flush=True)
    accepted=[];duplicates=[];seen=set();token_sets=[]
    for item in items:
        t=item['text'];normalized=' '.join(t.split()).casefold();h=digest(normalized.encode());w=words(t)
        near=next((x['name'] for x,s in zip(accepted,token_sets) if len(w|s) and len(w&s)/len(w|s)>.94),None)
        if h in seen or near:
            duplicates.append(dict(name=item['name'],near=near,sha256=item['sha256']));continue
        seen.add(h);accepted.append(item);token_sets.append(w)
    files={x['name']:x['text'] for x in accepted};sha=archive(EVAL/'generated_corpora/public/knowledge-base.zip',files)
    corpus_id='public-'+sha[:16]
    manifest=dict(version=VERSION,corpus_id=corpus_id,archive_sha256=sha,documents=len(files),origin='public',
                  languages=dict(Counter(x['language'] for x in accepted)),sources=licences,files=[{k:v for k,v in x.items() if k!='text'} for x in accepted])
    write(EVAL/'generated_corpora/public/manifest.json',manifest)
    write(base/'registry.json',manifest);write(base/'duplicates.json',duplicates)
    # Structural retrieval questions: expected span is copied from source, not
    # a model-generated legal conclusion. No automatic public legal accuracy gold.
    sources={};cases=[];questions=[]
    for item in [x for x in accepted if x['language'] in {'ru','ru-en'}][:20]:
        t=item['text'];matches=list(re.finditer(r'[^\n]+',t))
        candidates=[m for m in matches if 100<len(m.group())<700 and not m.group().startswith(('#','---','<','|'))]
        if not candidates:continue
        m=candidates[len(candidates)//2];sid=f'{item["name"]}:anchor';cid=f'public-{len(cases):03}'
        sources[sid]=dict(id=sid,document=item['name'],start=m.start(),end=m.end(),quote=m.group(),document_sha256=item['sha256'],revision='downloaded',fact={})
        question=f'Найдите в документе {Path(item["name"]).name} положение, начинающееся словами «{m.group()[:90]}», и приведите его дословно. Не давайте правовой оценки.'
        cases.append(dict(case_id=cid,corpus_id=corpus_id,scenario_id=cid,question=question,history=[],category='public_span_retrieval',difficulty=1,split='development',event_date=None,
            expected=dict(allowed_statuses=['answer'],required_claims=[dict(fact={},acceptable_evidence_sets=[[sid]])],forbidden_claims=[],missing=[],issue='')))
        questions.append(dict(case_id=cid,corpus_id=corpus_id,question=question,history=[],split='development'))
    write(EVAL/'gold/public.json',dict(version=VERSION,corpus_id=corpus_id,sources=sources,cases=cases,scope='Structural span retrieval only. Not annotated legal accuracy.'))
    write(EVAL/'questions/public.json',questions)
    lines=['# Реестр публичных источников','',f'Фактически включено {len(accepted)} документов. Отклонено дубликатов/near-duplicates: {len(duplicates)}. Источники зафиксированы commit SHA в public_documents/sources.lock.json.',
           '', '| Источник | Лицензия | Фактически включено |','|---|---|---:|']
    for s in licences:lines.append(f'| [{s["repository"]}](https://github.com/{s["repository"]}) | [{s["license"]}]({s["license_url"]}) | {sum(x["repository"]==s["repository"] for x in accepted)} |')
    lines+=['','Оригинальные байты и отдельные LICENSE сохранены в public_documents/. Mozilla: CC BY-SA 3.0, автор Mozilla, source URL и SHA каждого файла в registry.json; тексты не изменены. Они сохраняют свою лицензию, не перелицензируются вместе со стендом. General Legal и capysta2016: CC0; nvim.bilingual: MIT с сохранением notice.',
            '', 'Это опубликованные шаблоны и корпоративные политики, не подписанные сделки. Большая часть Mozilla — переводы одних семейств; число файлов не равно числу независимых правовых ситуаций. Языки указаны отдельно. Документы не объявляются действующим правом и не превращаются в эталоны ответа модели.',
            '', 'Исследованы, но не включены: wpcraft-ru/kb-wordpress (README заявляет MIT, явный LICENSE не найден); irlcode/RusLawOD (CC BY-NC 4.0, не переносим в банковский/коммерческий контур); неизвестные договоры с неясной лицензией и банковские формы без явного разрешения на распространение. Их содержимое не копировалось в корпус.',
            '', 'Публичный набор оценивается отдельно: вопросы проверяют поиск буквального диапазона, а не юридическую правильность. Вручную размеченной реальной базы организаторов пока нет. Для mixed используются только синтетические юридические эталоны; публичные тексты служат отвлекающими источниками.',
            '', 'Повторная загрузка: python -m evaluation.collect_public. Уже сохранённый lock фиксирует ревизии; --refresh явно обновляет источники. Сетевой сбой даёт ошибку, не выдуманный документ.']
    (EVAL/'DATA_SOURCES.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return manifest

def mixed():
    import zipfile
    files={}
    for name in ('synthetic','public'):
        with zipfile.ZipFile(EVAL/'generated_corpora'/name/'knowledge-base.zip') as z:
            for n in z.namelist():
                if n in files:raise ValueError('mixed name collision')
                files[n]=z.read(n)
    sha=archive(EVAL/'generated_corpora/mixed/knowledge-base.zip',files)
    gold=read(EVAL/'gold/synthetic.json');cid='mixed-'+sha[:16];gold['corpus_id']=cid
    for c in gold['cases']:c['corpus_id']=cid
    questions=read(EVAL/'questions/synthetic.json')
    for q in questions:q['corpus_id']=cid
    write(EVAL/'gold/mixed.json',gold);write(EVAL/'questions/mixed.json',questions)
    write(EVAL/'generated_corpora/mixed/manifest.json',dict(version=VERSION,corpus_id=cid,archive_sha256=sha,documents=len(files),origin='mixed',
        parents=[read(EVAL/f'generated_corpora/{n}/manifest.json')['corpus_id'] for n in ('synthetic','public')]))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--limit',type=int,default=140);p.add_argument('--refresh',action='store_true');p.add_argument('--mixed',action='store_true');a=p.parse_args()
    m=collect(a.limit,a.refresh);print(dict(documents=m['documents'],languages=m['languages']))
    if a.mixed:mixed()
