# Результаты испытаний

Local experiment, not official competition Score. Raw BM25 rank is a separate diagnostic from production grouped context.

```json
{
  "version": "1.0.0",
  "git_commit": "b5ecfdc130c8f10aacd75a2d813b124f01e923c3",
  "runtime_sha256": "e74860d250de51d8b0e0b43d2eb5ac11513ea9bf090d593ed07613650302cea5",
  "evaluation_sha256": "e1c908d3de082e029bd497f4535c41bb2ae50cb880c47b216375697941ac7cd9",
  "corpus_id": "synthetic-080b083c21e00acd",
  "corpus_sha256": "4992f489770051e3502af664eda5adc90ca776c24ba74245c0079d69d6e7963f",
  "gold_sha256": "06ca02da278771714d8f95ff369928b8a20195cf04fbe1616a9441d7ed7153a0",
  "gold_version": "1.0.0",
  "questions_sha256": "e923efab2d5b9466d5f6e366247febed78e2fcda6e3879af25ef180470b4da15",
  "selection_sha256": "a540b7aa7ff47e5679bb5e1c09d5ea285c97827ac83ee0ce256ea33b89fbe278",
  "documents": 1000,
  "questions_selected": 60,
  "mode": "full",
  "engine": "retrieval",
  "model": null,
  "provider_base_url": null,
  "config": {
    "top_k": 10,
    "workers": 4,
    "timeout": 30,
    "case_seconds": 240,
    "max_tokens": 2048,
    "temperature": 0,
    "max_requests": 60,
    "max_token_bound": 3000000,
    "max_cost": null,
    "input_price_per_million": 0,
    "output_price_per_million": 0,
    "save_responses": true,
    "bm25_k1": 1.5,
    "bm25_b": 0.75,
    "note": "No prices guessed. Set both unit prices to enforce monetary cap. Token bound reserves UTF-8 request bytes plus max_tokens per HTTP attempt; conservative, not billing.",
    "engine": "retrieval"
  },
  "fingerprint": "a7abd1caeb4c77cbfb0363311ffe2b778222c4b61b8b6fc771a2b7f0174c1f1e",
  "started_utc": "2026-11-10T10:19:26.598158+00:00",
  "cases_not_run": 0,
  "elapsed_seconds": 14.093292699999893,
  "organizer_unchanged": true,
  "budget": {
    "requests": 0,
    "tokens_reserved": 0,
    "cost_reserved": 0.0
  },
  "isolation": "fresh subprocess per case; only copied runtime, corpus and public question; no gold/specs copied",
  "api_status": "not_requested"
}
```

| Метрика | Числитель | Знаменатель | Значение |
|---|---:|---:|---:|
| raw_bm25_recall@1 | 20.0 | 47 | 0.425531914893617 |
| raw_bm25_recall@5 | 28.5 | 47 | 0.6063829787234043 |
| raw_bm25_recall@10 | 31.0 | 47 | 0.6595744680851063 |
| production_context_sufficiency | 25 | 25 | 1.0 |
| context_available_and_sufficient | 25 | 47 | 0.5319148936170213 |
| fact_accuracy | 0 | 0 | N/A |
| completeness | 0 | 0 | N/A |
| citation_integrity | 0 | 0 | N/A |
| citation_support_accuracy | 0 | 0 | N/A |
| false_refusal_rate | 0 | 0 | N/A |
| unsupported_answer_rate | 0 | 0 | N/A |
| correct_clarification_rate | 0 | 0 | N/A |
| temporal_accuracy | 0 | 0 | N/A |
| end_to_end_success | 0 | 0 | N/A |
| api_error_rate | 0 | 0 | N/A |
| validator_false_acceptance_rate | 0 | 7 | 0.0 |
| validator_false_rejection_rate | 0 | 4 | 0.0 |

Исходы: {'system_error': 27, 'not_evaluated': 33}

Ошибки: {'system_error': 27}

Непроверенные свойства: {'generation_not_run': 33}

API requests: 0. Латентность worker (без ожидания очереди): {'median_seconds': 0.6653292500000134, 'p95_seconds': 0.7809086999995998}

## Разбор

retrieval_failure означает отсутствие полного эталонного набора в фактически выбранном контексте; generation_failure — доказанное расхождение ограниченной грамматики. Причина вне этих данных остаётся гипотезой. Неоценённый свободный текст требует ручного чтения. Технические ошибки не считаются юридическими отказами.

## Примеры и воспроизведение

- `contradiction-0000`: ['system_error']. См. cases/contradiction-0000.json, reproduction/contradiction-0000.json.
- `contradiction-0006`: ['system_error']. См. cases/contradiction-0006.json, reproduction/contradiction-0006.json.
- `fact-0000`: ['system_error']. См. cases/fact-0000.json, reproduction/fact-0000.json.
- `fact-0001`: ['system_error']. См. cases/fact-0001.json, reproduction/fact-0001.json.
- `fact-0002`: ['system_error']. См. cases/fact-0002.json, reproduction/fact-0002.json.
- `fact-0003`: ['system_error']. См. cases/fact-0003.json, reproduction/fact-0003.json.
- `fact-0005`: ['system_error']. См. cases/fact-0005.json, reproduction/fact-0005.json.
- `fact-0006`: ['system_error']. См. cases/fact-0006.json, reproduction/fact-0006.json.

## Рекомендации

Сначала исправлять подтверждённые потери полного набора оснований. Отдельно измерять изменения TOP_K; не считать расширение контекста улучшением юридической точности. Для неразобранного текста нужна независимая ручная разметка. Прежде чем менять runtime, повторить кейсы с реальным API и бюджетом.
