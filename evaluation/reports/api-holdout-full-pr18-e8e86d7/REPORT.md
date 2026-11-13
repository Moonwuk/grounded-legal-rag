# Результаты испытаний

Local experiment, not official competition Score. Raw BM25 rank is a separate diagnostic from production grouped context.

```json
{
  "version": "1.0.0",
  "git_commit": "e8e86d774cba3afe45bc9be374aa67ceebb9c51e",
  "runtime_sha256": "feaac9cd3ea8da4e197ef4262ce7bc2700b7c265f6410614be8b82007eb3cde5",
  "evaluation_sha256": "d7c79970784e2abab796c90de667e706de0c441049051fd572b2994261f1ba8f",
  "validator_sha256": "e833da8a064cc9dabaa97e20bfc2756f3232e582d4c1af7ea0ec3fa4d7514305",
  "retrieval_adapter_sha256": "17a03efaa958ee5f1ff64a6154f3feef07c685611e3fbef753291cd02afbfd43",
  "corpus_id": "synthetic-b148e60beaa44f30",
  "corpus_sha256": "283b6ac186a36c6ca6a10078c9e31f7d41ab65672c3bbe32b8f9ef62c6190fe1",
  "gold_sha256": "99440bd422a366e25c601a1708ba326b2913bdcd1cc76d5fda9d14ae413a164e",
  "gold_version": "1.0.0",
  "questions_sha256": "7e4336e1b6a67c18a8bfae589587c1a035d67d8213455c97d03ac354d9daaf61",
  "selection_sha256": "0eb3203a0eae4d5e6d8df429afc1d1adfbc9c96dac3a1bb2014d5aff259625fd",
  "documents": 1000,
  "questions_selected": 100,
  "mode": "holdout",
  "engine": "deepseek",
  "model": "deepseek-flash",
  "provider_base_url": "https://api.deepseek.com/v1",
  "config": {
    "top_k": 6,
    "workers": 2,
    "timeout": null,
    "case_seconds": 240,
    "max_tokens": null,
    "temperature": null,
    "max_requests": 650,
    "max_token_bound": 40000000,
    "max_cost": null,
    "input_price_per_million": 0,
    "output_price_per_million": 0,
    "save_responses": true,
    "bm25_k1": 1.5,
    "bm25_b": 0.75,
    "note": "Full holdout run: limits raised for 100 cases; same generation settings (runtime defaults).",
    "engine": "deepseek"
  },
  "fingerprint": "3e84eff0c6708c0c01e62f73f75d05d65ded8dc4f5f43547e82d040d0bed1ac2",
  "started_utc": "2026-11-11T14:13:09.831689+00:00",
  "cases_not_run": 0,
  "elapsed_seconds": 1499.388725257,
  "organizer_unchanged": true,
  "budget": {
    "requests": 254,
    "tokens_reserved": 1924198,
    "cost_reserved": 0.0
  },
  "isolation": "fresh subprocess per case; only copied runtime, corpus and public question; no gold/specs copied",
  "api_status": "executed"
}
```

| Метрика | Числитель | Знаменатель | Значение |
|---|---:|---:|---:|
| raw_bm25_recall@1 | 43.5 | 78 | 0.5576923076923077 |
| raw_bm25_recall@5 | 50.5 | 78 | 0.6474358974358975 |
| raw_bm25_recall@10 | 51.0 | 78 | 0.6538461538461539 |
| production_context_sufficiency | 78 | 78 | 1.0 |
| context_available_and_sufficient | 78 | 78 | 1.0 |
| fact_accuracy | 135 | 135 | 1.0 |
| completeness | 97 | 98 | 0.9897959183673469 |
| citation_integrity | 141 | 141 | 1.0 |
| citation_support_accuracy | 135 | 135 | 1.0 |
| false_refusal_rate | 1 | 73 | 0.0136986301369863 |
| unsupported_answer_rate | 3 | 86 | 0.03488372093023256 |
| correct_clarification_rate | 0 | 0 | N/A |
| temporal_accuracy | 11 | 11 | 1.0 |
| end_to_end_success | 83 | 86 | 0.9651162790697675 |
| api_error_rate | 0 | 252 | 0.0 |
| validator_false_acceptance_rate | 0 | 16 | 0.0 |
| validator_false_rejection_rate | 0 | 9 | 0.0 |

Исходы: {'not_evaluated': 13, 'pass': 83, 'fail': 4}

Ошибки: {'generation_failure': 3, 'false_refusal': 1}

Непроверенные свойства: {'conditional_or_conflict_explanation_requires_manual_review': 12, 'conflict_explanation_requires_manual_review': 7, 'prose_conclusion_not_identified': 1, 'published_prose_semantics': 1, 'no_accepted_candidate': 1}

API requests: 252. Латентность worker (без ожидания очереди): {'median_seconds': 20.115463271000067, 'p95_seconds': 89.0780763790001}

## Разбор

retrieval_failure означает отсутствие полного эталонного набора в фактически выбранном контексте; generation_failure — доказанное расхождение ограниченной грамматики. Причина вне этих данных остаётся гипотезой. Неоценённый свободный текст требует ручного чтения. Технические ошибки не считаются юридическими отказами.

## Примеры и воспроизведение

- `contradiction-0049`: ['generation_failure']. См. cases/contradiction-0049.json, reproduction/contradiction-0049.json.
- `contradiction-0069`: ['generation_failure']. См. cases/contradiction-0069.json, reproduction/contradiction-0069.json.
- `security-0024`: ['generation_failure']. См. cases/security-0024.json, reproduction/security-0024.json.
- `temporal-0039`: ['false_refusal']. См. cases/temporal-0039.json, reproduction/temporal-0039.json.

## Рекомендации

Сначала исправлять подтверждённые потери полного набора оснований. Отдельно измерять изменения TOP_K; не считать расширение контекста улучшением юридической точности. Для неразобранного текста нужна независимая ручная разметка. Прежде чем менять runtime, повторить кейсы с реальным API и бюджетом.
