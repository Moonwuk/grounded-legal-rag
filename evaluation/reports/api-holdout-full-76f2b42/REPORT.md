# Результаты испытаний

Local experiment, not official competition Score. Raw BM25 rank is a separate diagnostic from production grouped context.

```json
{
  "version": "1.0.0",
  "git_commit": "e9c0d473c2b64fec178e62deb8a5747e13b96087",
  "runtime_sha256": "8814a521522a1fd6d21df359db2c5a7a536c316f424936a4c06ab1f3422f2cc0",
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
  "fingerprint": "b28e73140331c81a0e5f09a3504c91d4fe31bfdb77f8680221db0b0e9d6e06d9",
  "started_utc": "2026-11-11T09:29:48.299486+00:00",
  "cases_not_run": 0,
  "elapsed_seconds": 1607.7564172829998,
  "organizer_unchanged": true,
  "budget": {
    "requests": 267,
    "tokens_reserved": 2178248,
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
| fact_accuracy | 135 | 137 | 0.9854014598540146 |
| completeness | 97 | 98 | 0.9897959183673469 |
| citation_integrity | 141 | 141 | 1.0 |
| citation_support_accuracy | 135 | 137 | 0.9854014598540146 |
| false_refusal_rate | 1 | 73 | 0.0136986301369863 |
| unsupported_answer_rate | 2 | 84 | 0.023809523809523808 |
| correct_clarification_rate | 0 | 0 | N/A |
| temporal_accuracy | 12 | 12 | 1.0 |
| end_to_end_success | 81 | 84 | 0.9642857142857143 |
| api_error_rate | 0 | 265 | 0.0 |
| validator_false_acceptance_rate | 0 | 16 | 0.0 |
| validator_false_rejection_rate | 0 | 9 | 0.0 |

Исходы: {'not_evaluated': 11, 'fail': 7, 'pass': 81, 'system_error': 1}

Ошибки: {'generation_failure': 3, 'false_refusal': 1, 'system_error': 1, 'incomplete_answer': 2, 'temporal_failure': 2}

Непроверенные свойства: {'conditional_or_conflict_explanation_requires_manual_review': 11, 'conflict_explanation_requires_manual_review': 6, 'no_accepted_candidate': 1, 'prose_conclusion_not_identified': 3, 'published_prose_semantics': 3}

API requests: 265. Латентность worker (без ожидания очереди): {'median_seconds': 22.558991988000116, 'p95_seconds': 116.33416807000003}

## Разбор

retrieval_failure означает отсутствие полного эталонного набора в фактически выбранном контексте; generation_failure — доказанное расхождение ограниченной грамматики. Причина вне этих данных остаётся гипотезой. Неоценённый свободный текст требует ручного чтения. Технические ошибки не считаются юридическими отказами.

## Примеры и воспроизведение

- `contradiction-0009`: ['generation_failure']. См. cases/contradiction-0009.json, reproduction/contradiction-0009.json.
- `contradiction-0019`: ['false_refusal']. См. cases/contradiction-0019.json, reproduction/contradiction-0019.json.
- `contradiction-0064`: ['system_error']. См. cases/contradiction-0064.json, reproduction/contradiction-0064.json.
- `contradiction-0069`: ['generation_failure']. См. cases/contradiction-0069.json, reproduction/contradiction-0069.json.
- `missing_information-0059`: ['incomplete_answer']. См. cases/missing_information-0059.json, reproduction/missing_information-0059.json.
- `missing_information-0069`: ['generation_failure', 'incomplete_answer']. См. cases/missing_information-0069.json, reproduction/missing_information-0069.json.
- `temporal-0004`: ['temporal_failure']. См. cases/temporal-0004.json, reproduction/temporal-0004.json.
- `temporal-0044`: ['temporal_failure']. См. cases/temporal-0044.json, reproduction/temporal-0044.json.

## Рекомендации

Сначала исправлять подтверждённые потери полного набора оснований. Отдельно измерять изменения TOP_K; не считать расширение контекста улучшением юридической точности. Для неразобранного текста нужна независимая ручная разметка. Прежде чем менять runtime, повторить кейсы с реальным API и бюджетом.
