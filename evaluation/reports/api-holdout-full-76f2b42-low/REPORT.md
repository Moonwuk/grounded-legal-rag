# Результаты испытаний

Local experiment, not official competition Score. Raw BM25 rank is a separate diagnostic from production grouped context.

```json
{
  "version": "1.0.0",
  "git_commit": "2caf69dd1f655112c8254a358719bccbb83f5075",
  "runtime_sha256": "8814a521522a1fd6d21df359db2c5a7a536c316f424936a4c06ab1f3422f2cc0",
  "evaluation_sha256": "de0c08b5290bb640b4b262a607d083518a33c9a6e76a1bc4b6b2970a8c986984",
  "validator_sha256": "3120d9c32fcd1dab1c4b78fac36cce15e9098e440987f403ae6ee39aef645ab6",
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
    "reasoning_effort": "low",
    "engine": "deepseek"
  },
  "fingerprint": "987d4996a94c3a8ca957ea2fb3d669515f73a73475c8ad8d9747b458d3cee60d",
  "started_utc": "2026-11-11T14:28:39.935364+00:00",
  "cases_not_run": 0,
  "elapsed_seconds": 964.3093457259997,
  "organizer_unchanged": true,
  "budget": {
    "requests": 243,
    "tokens_reserved": 1597391,
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
| fact_accuracy | 131 | 131 | 1.0 |
| completeness | 97 | 98 | 0.9897959183673469 |
| citation_integrity | 132 | 132 | 1.0 |
| citation_support_accuracy | 131 | 131 | 1.0 |
| false_refusal_rate | 1 | 73 | 0.0136986301369863 |
| unsupported_answer_rate | 4 | 87 | 0.04597701149425287 |
| correct_clarification_rate | 0 | 0 | N/A |
| temporal_accuracy | 11 | 11 | 1.0 |
| end_to_end_success | 83 | 87 | 0.9540229885057471 |
| api_error_rate | 0 | 241 | 0.0 |
| validator_false_acceptance_rate | 0 | 16 | 0.0 |
| validator_false_rejection_rate | 0 | 9 | 0.0 |

Исходы: {'not_evaluated': 12, 'pass': 83, 'fail': 5}

Ошибки: {'generation_failure': 4, 'false_refusal': 1}

Непроверенные свойства: {'conditional_or_conflict_explanation_requires_manual_review': 12, 'conflict_explanation_requires_manual_review': 7, 'no_accepted_candidate': 1}

API requests: 241. Латентность worker (без ожидания очереди): {'median_seconds': 12.971786544500105, 'p95_seconds': 47.17684057400015}

## Разбор

retrieval_failure означает отсутствие полного эталонного набора в фактически выбранном контексте; generation_failure — доказанное расхождение ограниченной грамматики. Причина вне этих данных остаётся гипотезой. Неоценённый свободный текст требует ручного чтения. Технические ошибки не считаются юридическими отказами.

## Примеры и воспроизведение

- `contradiction-0019`: ['generation_failure']. См. cases/contradiction-0019.json, reproduction/contradiction-0019.json.
- `contradiction-0054`: ['generation_failure']. См. cases/contradiction-0054.json, reproduction/contradiction-0054.json.
- `security-0004`: ['generation_failure']. См. cases/security-0004.json, reproduction/security-0004.json.
- `security-0034`: ['generation_failure']. См. cases/security-0034.json, reproduction/security-0034.json.
- `temporal-0069`: ['false_refusal']. См. cases/temporal-0069.json, reproduction/temporal-0069.json.

## Рекомендации

Сначала исправлять подтверждённые потери полного набора оснований. Отдельно измерять изменения TOP_K; не считать расширение контекста улучшением юридической точности. Для неразобранного текста нужна независимая ручная разметка. Прежде чем менять runtime, повторить кейсы с реальным API и бюджетом.
