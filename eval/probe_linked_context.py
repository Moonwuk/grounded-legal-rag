"""Reproduce connected-document context growth without a model or organizer data.

This is a new constructed probe, not the report's original 500-case benchmark.
"""
from pathlib import Path
import json
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'prototype'))
from psb_corpus import load_corpus
from psb_retrieval import Retriever


def main():
    results = []
    for count in (1, 20, 60):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'knowledge-base.zip'
            with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
                for document in range(count):
                    lines = ['ДОГОВОР Ш-91/2038']
                    for clause in range(1, 14):
                        lines.append(f'{clause}. Размер оплаты по договору составляет {1000 + document} рублей. ' +
                            'Условие расчётов сохраняется для поставки оборудования и проверяется по документам сторон. ' * 2)
                    archive.writestr(f'Документ_{document:03}.txt', '\n'.join(lines))
            docs, fragments = load_corpus(path)
            row = {'documents': count, 'input_characters': sum(len(d.text) for d in docs),
                   'indexed_fragments': len(fragments), 'top_k': 6}
            try:
                evidence = Retriever(docs, fragments).search('Какой размер оплаты по договору Ш-91/2038?', top_k=6)
                row.update(status='context', context_fragments=len(evidence),
                           context_characters=sum(len(f.text) for f in evidence))
            except ValueError as error:
                row.update(status='guard_exception', error_code=str(error))
            results.append(row)
    report = {'purpose':'new deterministic linked-context probe; no API calls',
              'source_base':'main d67c837dcba83439f594623aa506d8550ebd0f6a; retrieval unchanged in PR12',
              'construction':'All files share one contract identifier; 13 full clauses per file.',
              'not_original_benchmark':True, 'not_minimal_reproducer':True, 'results':results}
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
