# Результаты испытаний

Local experiment, not official competition Score. Raw BM25 rank is a separate diagnostic from production grouped context.

```json
{
  "version": "1.0.0",
  "git_commit": "436ae8f654071b9d91d14c3451390f67f66de4e1",
  "runtime_sha256": "b41a441e00854ce99070221e2f1174f00e0ba0601d9978cf979965107f671edb",
  "evaluation_sha256": "9d17e59485f31ba4d99888ac9a9755018c8d3f2582a4aca40b1bac4ee14ca0f9",
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
    "note": "timeout/max_tokens/temperature/reasoning_effort null = runtime defaults (no override), as on the platform. No prices guessed. Set both unit prices to enforce monetary cap. Token bound reserves UTF-8 request bytes plus max_tokens per HTTP attempt, then settles to provider-reported total_tokens; not billing.",
    "reasoning_effort": null,
    "engine": "deepseek"
  },
  "fingerprint": "8b8e7cc0fb92b77fd33b60448061e6bdacd2e094d4170629cbd13109b55da42a",
  "started_utc": "2026-11-12T09:25:45.864909+00:00",
  "cases_not_run": 0,
  "elapsed_seconds": 604.5681423440001,
  "organizer_unchanged": true,
  "budget": {
    "requests": 181,
    "tokens_reserved": 2827489,
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
| fact_accuracy | 65 | 65 | 1.0 |
| completeness | 49 | 49 | 1.0 |
| citation_integrity | 67 | 67 | 1.0 |
| citation_support_accuracy | 65 | 65 | 1.0 |
| false_refusal_rate | 0 | 37 | 0.0 |
| unsupported_answer_rate | 0 | 46 | 0.0 |
| correct_clarification_rate | 0 | 0 | N/A |
| temporal_accuracy | 7 | 7 | 1.0 |
| end_to_end_success | 46 | 46 | 1.0 |
| api_error_rate | 47 | 179 | 0.26256983240223464 |
| validator_false_acceptance_rate | 0 | 16 | 0.0 |
| validator_false_rejection_rate | 0 | 9 | 0.0 |

Исходы: {'not_evaluated': 7, 'pass': 46, 'system_error': 47}

Ошибки: {'system_error': 47}

Непроверенные свойства: {'conditional_or_conflict_explanation_requires_manual_review': 7, 'conflict_explanation_requires_manual_review': 4}

API requests: 179. Латентность worker (без ожидания очереди): {'median_seconds': 6.007731266000519, 'p95_seconds': 49.03798178800025}

## Разбор

retrieval_failure означает отсутствие полного эталонного набора в фактически выбранном контексте; generation_failure — доказанное расхождение ограниченной грамматики. Причина вне этих данных остаётся гипотезой. Неоценённый свободный текст требует ручного чтения. Технические ошибки не считаются юридическими отказами.

## Примеры и воспроизведение

- `contradiction-0049`: ['system_error']. См. cases/contradiction-0049.json, reproduction/contradiction-0049.json.
- `contradiction-0054`: ['system_error']. См. cases/contradiction-0054.json, reproduction/contradiction-0054.json.
- `contradiction-0059`: ['system_error']. См. cases/contradiction-0059.json, reproduction/contradiction-0059.json.
- `contradiction-0064`: ['system_error']. См. cases/contradiction-0064.json, reproduction/contradiction-0064.json.
- `contradiction-0069`: ['system_error']. См. cases/contradiction-0069.json, reproduction/contradiction-0069.json.
- `contradiction-0074`: ['system_error']. См. cases/contradiction-0074.json, reproduction/contradiction-0074.json.
- `fact-0049`: ['system_error']. См. cases/fact-0049.json, reproduction/fact-0049.json.
- `fact-0054`: ['system_error']. См. cases/fact-0054.json, reproduction/fact-0054.json.

## Рекомендации

Сначала исправлять подтверждённые потери полного набора оснований. Отдельно измерять изменения TOP_K; не считать расширение контекста улучшением юридической точности. Для неразобранного текста нужна независимая ручная разметка. Прежде чем менять runtime, повторить кейсы с реальным API и бюджетом.
