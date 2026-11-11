from __future__ import annotations
import argparse
from collections import Counter,defaultdict
from statistics import median
from pathlib import Path
from evaluation.common import read,write

def ratio(n,d):return dict(numerator=n,denominator=d,value=n/d if d else None)

def summarize(rows):
    metrics={}
    for k in (1,5,10):
        eligible=[r for r in rows if r.get('recall',{}).get(str(k)) is not None]
        metrics[f'raw_bm25_recall@{k}']=ratio(sum(r['recall'][str(k)] for r in eligible),len(eligible))
    eligible=[r for r in rows if r.get('sufficient') is not None]
    metrics['production_context_sufficiency']=ratio(sum(r['sufficient'] for r in eligible),len(eligible))
    attempted=[r for r in rows if r.get('has_required_evidence')]
    metrics['context_available_and_sufficient']=ratio(sum(r.get('sufficient') is True for r in attempted),len(attempted))
    evaluated=[r for r in rows if r['validation']['outcome'] not in {'system_error','not_evaluated'} and not r['validation']['not_evaluated']]
    counts=Counter()
    for r in rows:
        if r['validation']['outcome']!='system_error':counts.update(r['validation'].get('counts',{}))
    metrics['fact_accuracy']=ratio(counts['correct_claims'],counts['claims'])
    # Required facts in unrun generation are NOT incomplete answers.
    metrics['completeness']=ratio(counts['covered'],counts['required'])
    metrics['citation_integrity']=ratio(counts['valid_citations'],counts['citations'])
    metrics['citation_support_accuracy']=ratio(counts['supported_citations'],counts['support_evaluated'])
    positive=[r for r in rows if r.get('answerable') and r['engine']!='retrieval' and r['validation']['outcome']!='system_error']
    metrics['false_refusal_rate']=ratio(sum('false_refusal' in r['validation']['failures'] for r in positive),len(positive))
    metrics['unsupported_answer_rate']=ratio(sum('generation_failure' in r['validation']['failures'] and r.get('status') in {'answer','partial'} for r in evaluated),len(evaluated))
    clarification=[r for r in evaluated if r.get('expects_clarification')]
    metrics['correct_clarification_rate']=ratio(sum(r['validation']['checks'].get('refusal',False) and r['validation']['checks'].get('gap',True) for r in clarification),len(clarification))
    temporal=[r for r in evaluated if r['category']=='temporal' and r['validation']['checks'].get('temporal') is not None]
    metrics['temporal_accuracy']=ratio(sum(r['validation']['checks']['temporal'] for r in temporal),len(temporal))
    metrics['end_to_end_success']=ratio(sum(r['validation']['outcome']=='pass' for r in evaluated),len(evaluated))
    metrics['api_error_rate']=ratio(sum(len(r.get('api_errors',[])) for r in rows),sum(r.get('requests',0) for r in rows if r['engine']=='deepseek'))
    metrics['validator_false_acceptance_rate']=ratio(0,0)
    metrics['validator_false_rejection_rate']=ratio(0,0)
    # Calibration comes only from labelled mutation tests, not assistant outputs.
    categories=defaultdict(Counter)
    for r in rows:categories[r['category']].update([r['validation']['outcome']])
    latencies=sorted(r.get('seconds',0) for r in rows)
    return dict(metrics=metrics,outcomes=dict(Counter(r['validation']['outcome'] for r in rows)),
                categories={k:dict(v) for k,v in categories.items()},
                failures=dict(Counter(f for r in rows for f in r['validation']['failures'])),
                not_evaluated_reasons=dict(Counter(x for r in rows for x in r['validation']['not_evaluated'])),
                latency=dict(median_seconds=median(latencies) if latencies else None,p95_seconds=latencies[min(len(latencies)-1,int(len(latencies)*.95))] if latencies else None),
                requests=sum(r.get('requests',0) for r in rows),
                usage=dict(sum_counter(r.get('usage',[]) for r in rows)))

def sum_counter(items):
    c=Counter()
    for values in items:
        for value in values:c.update(value)
    return c

def report(out,manifest,rows):
    out=Path(out);summary=summarize(rows)
    # Calibrate the validator of this very commit; an older calibration file
    # describes another validator and must not be reported as current.
    from evaluation.validators.calibration import calibration
    c=calibration()
    for name in ('validator_false_acceptance_rate','validator_false_rejection_rate'):summary['metrics'][name]=c[name]
    summary['validator_calibration']=dict(bad_outcomes=c['bad_outcomes'],good_outcomes=c['good_outcomes'],
                                          permitted_not_evaluated=c['permitted_not_evaluated'],scope=c['scope'])
    value={**manifest,**summary,'cases_completed':len(rows),'scope':'Local experiment, not official competition Score. Raw BM25 rank is a separate diagnostic from production grouped context.'}
    write(out/'summary.json',value)
    lines=['# Результаты испытаний','',value['scope'],'','```json',__import__('json').dumps(manifest,ensure_ascii=False,indent=2),'```','',
           '| Метрика | Числитель | Знаменатель | Значение |','|---|---:|---:|---:|']
    for name,m in summary['metrics'].items():lines.append(f'| {name} | {m["numerator"]} | {m["denominator"]} | {m["value"] if m["value"] is not None else "N/A"} |')
    lines+=['','Исходы: '+str(summary['outcomes']),'','Ошибки: '+str(summary['failures']),'','Непроверенные свойства: '+str(summary['not_evaluated_reasons']),
            '', 'API requests: '+str(summary['requests'])+'. Латентность worker (без ожидания очереди): '+str(summary['latency']),
            '', '## Разбор', '', 'retrieval_failure означает отсутствие полного эталонного набора в фактически выбранном контексте; generation_failure — доказанное расхождение ограниченной грамматики. Причина вне этих данных остаётся гипотезой. Неоценённый свободный текст требует ручного чтения. Технические ошибки не считаются юридическими отказами.',
            '', '## Примеры и воспроизведение','']
    for r in [r for r in rows if r['validation']['failures']][:8]:
        lines.extend([f"- `{r['case_id']}`: {r['validation']['failures']}. См. cases/{r['case_id']}.json, reproduction/{r['case_id']}.json."])
    lines+=['','## Рекомендации','', 'Сначала исправлять подтверждённые потери полного набора оснований. Отдельно измерять изменения TOP_K; не считать расширение контекста улучшением юридической точности. Для неразобранного текста нужна независимая ручная разметка. Прежде чем менять runtime, повторить кейсы с реальным API и бюджетом.']
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return value

def main():
    p=argparse.ArgumentParser();p.add_argument('reports',nargs='+',type=Path);p.add_argument('--out',type=Path,default=Path('evaluation/reports/comparison.json'));a=p.parse_args()
    values=[read(x/'summary.json' if x.is_dir() else x) for x in a.reports]
    keys=('corpus_sha256','gold_sha256','questions_sha256','selection_sha256','runtime_sha256','validator_sha256','retrieval_adapter_sha256')
    if any(any(v.get(k)!=values[0].get(k) for k in keys) for v in values):raise ValueError('incomparable corpora/gold/questions/selection/runtime')
    if any(v.get('validator_sha256') is None for v in values) and len({v['evaluation_sha256'] for v in values})>1:
        raise ValueError('legacy reports have different evaluator code; rerun comparison')
    write(a.out,dict(comparable=True,runs=values))

if __name__=='__main__':main()
