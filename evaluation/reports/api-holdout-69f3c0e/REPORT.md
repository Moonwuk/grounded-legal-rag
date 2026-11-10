# Результаты испытаний

Local experiment, not official competition Score. Raw BM25 rank is a separate diagnostic from production grouped context.

```json
{
  "version": "1.0.0",
  "git_commit": "69f3c0ecd71df51f1818f5bfb3816e61716a0322",
  "runtime_sha256": "fca5182928d6530167282bfc8a85c06e4df8be533e54479a8c18ffcb0f22dcd2",
  "evaluation_sha256": "0cf35b12d0fdd1444e971655e70d6f708682a921e6b93ffd71ff3285f62b3711",
  "validator_sha256": "234a7ec35f269f5a6f94939db791d33894a124a55805ec5128852d066ca0da45",
  "retrieval_adapter_sha256": "40dfa08fc867efbe77b2b77b4ab165048828276fc70faf27d421c2332e93647c",
  "corpus_id": "synthetic-b148e60beaa44f30",
  "corpus_sha256": "283b6ac186a36c6ca6a10078c9e31f7d41ab65672c3bbe32b8f9ef62c6190fe1",
  "gold_sha256": "99440bd422a366e25c601a1708ba326b2913bdcd1cc76d5fda9d14ae413a164e",
  "gold_version": "1.0.0",
  "questions_sha256": "7e4336e1b6a67c18a8bfae589587c1a035d67d8213455c97d03ac354d9daaf61",
  "selection_sha256": "12cc4e6eb330b88cb87de0732dc36ab23037be56d800b2e4f30d176308851994",
  "documents": 1000,
  "questions_selected": 12,
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
    "max_requests": 60,
    "max_token_bound": 3000000,
    "max_cost": null,
    "input_price_per_million": 0,
    "output_price_per_million": 0,
    "save_responses": true,
    "bm25_k1": 1.5,
    "bm25_b": 0.75,
    "note": "timeout/max_tokens/temperature null = runtime defaults (no override), as on the platform. No prices guessed. Set both unit prices to enforce monetary cap. Token bound reserves UTF-8 request bytes plus max_tokens per HTTP attempt, then settles to provider-reported total_tokens; not billing.",
    "engine": "deepseek"
  },
  "fingerprint": "9d3378c857357dd3752df77724688754b6e4a2c109ffd4805cc5788c9fb99951",
  "started_utc": "2026-11-10T19:12:39.593580+00:00",
  "cases_not_run": 0,
  "elapsed_seconds": 356.79128589100003,
  "organizer_unchanged": true,
  "budget": {
    "requests": 41,
    "tokens_reserved": 1430699,
    "cost_reserved": 0.0
  },
  "isolation": "fresh subprocess per case; only copied runtime, corpus and public question; no gold/specs copied",
  "api_status": "executed"
}
```

| Метрика | Числитель | Знаменатель | Значение |
|---|---:|---:|---:|
| raw_bm25_recall@1 | 3.5 | 8 | 0.4375 |
| raw_bm25_recall@5 | 3.5 | 8 | 0.4375 |
| raw_bm25_recall@10 | 3.5 | 8 | 0.4375 |
| production_context_sufficiency | 8 | 8 | 1.0 |
| context_available_and_sufficient | 8 | 8 | 1.0 |
| fact_accuracy | 7 | 7 | 1.0 |
| completeness | 7 | 8 | 0.875 |
| citation_integrity | 7 | 7 | 1.0 |
| citation_support_accuracy | 7 | 7 | 1.0 |
| false_refusal_rate | 1 | 7 | 0.14285714285714285 |
| unsupported_answer_rate | 0 | 7 | 0.0 |
| correct_clarification_rate | 0 | 0 | N/A |
| temporal_accuracy | 0 | 0 | N/A |
| end_to_end_success | 7 | 7 | 1.0 |
| api_error_rate | 0 | 39 | 0.0 |
| validator_false_acceptance_rate | 0 | 16 | 0.0 |
| validator_false_rejection_rate | 0 | 9 | 0.0 |

Исходы: {'fail': 3, 'pass': 7, 'system_error': 2}

Ошибки: {'generation_failure': 2, 'system_error': 2, 'false_refusal': 1}

Непроверенные свойства: {'no_accepted_candidate': 3}

API requests: 39. Латентность worker (без ожидания очереди): {'median_seconds': 27.57573110100003, 'p95_seconds': 183.53902149099986}

## Разбор

retrieval_failure означает отсутствие полного эталонного набора в фактически выбранном контексте; generation_failure — доказанное расхождение ограниченной грамматики. Причина вне этих данных остаётся гипотезой. Неоценённый свободный текст требует ручного чтения. Технические ошибки не считаются юридическими отказами.

## Примеры и воспроизведение

- `contradiction-0004`: ['generation_failure']. См. cases/contradiction-0004.json, reproduction/contradiction-0004.json.
- `missing_information-0009`: ['system_error']. См. cases/missing_information-0009.json, reproduction/missing_information-0009.json.
- `multi_document-0009`: ['system_error']. См. cases/multi_document-0009.json, reproduction/multi_document-0009.json.
- `temporal-0004`: ['generation_failure']. См. cases/temporal-0004.json, reproduction/temporal-0004.json.
- `temporal-0009`: ['false_refusal']. См. cases/temporal-0009.json, reproduction/temporal-0009.json.

## Рекомендации

Сначала исправлять подтверждённые потери полного набора оснований. Отдельно измерять изменения TOP_K; не считать расширение контекста улучшением юридической точности. Для неразобранного текста нужна независимая ручная разметка. Прежде чем менять runtime, повторить кейсы с реальным API и бюджетом.
