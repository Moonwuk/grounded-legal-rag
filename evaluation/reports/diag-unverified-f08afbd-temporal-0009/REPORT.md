# Результаты испытаний

Local experiment, not official competition Score. Raw BM25 rank is a separate diagnostic from production grouped context.

```json
{
  "version": "1.0.0",
  "git_commit": "f08afbd8326cfcc0de72201ca4030581eef327f6",
  "runtime_sha256": "fca5182928d6530167282bfc8a85c06e4df8be533e54479a8c18ffcb0f22dcd2",
  "evaluation_sha256": "075f2349abfb74101fa39de9a4d71d7aaa74482d283e816fa4964ea3164ef36e",
  "validator_sha256": "234a7ec35f269f5a6f94939db791d33894a124a55805ec5128852d066ca0da45",
  "retrieval_adapter_sha256": "2c9691a9d6f6b16fddb156a474c05108401b00ad17a38e3a26dd09c07ea964b2",
  "corpus_id": "synthetic-b148e60beaa44f30",
  "corpus_sha256": "283b6ac186a36c6ca6a10078c9e31f7d41ab65672c3bbe32b8f9ef62c6190fe1",
  "gold_sha256": "99440bd422a366e25c601a1708ba326b2913bdcd1cc76d5fda9d14ae413a164e",
  "gold_version": "1.0.0",
  "questions_sha256": "7e4336e1b6a67c18a8bfae589587c1a035d67d8213455c97d03ac354d9daaf61",
  "selection_sha256": "c7a3617a2a533fda2e9b08d16dd607ebd4375b40ced756d686c36a6aed5d8572",
  "documents": 1000,
  "questions_selected": 1,
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
    "max_requests": 8,
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
  "fingerprint": "ed8682640b4c583d6b9d38dee9451140b1248f7fff3cd8ec6915844f451beffe",
  "started_utc": "2026-11-10T19:21:08.943786+00:00",
  "cases_not_run": 0,
  "elapsed_seconds": 94.99202877399989,
  "organizer_unchanged": true,
  "budget": {
    "requests": 7,
    "tokens_reserved": 155976,
    "cost_reserved": 0.0
  },
  "isolation": "fresh subprocess per case; only copied runtime, corpus and public question; no gold/specs copied",
  "api_status": "executed"
}
```

| Метрика | Числитель | Знаменатель | Значение |
|---|---:|---:|---:|
| raw_bm25_recall@1 | 0.0 | 1 | 0.0 |
| raw_bm25_recall@5 | 0.0 | 1 | 0.0 |
| raw_bm25_recall@10 | 0.0 | 1 | 0.0 |
| production_context_sufficiency | 1 | 1 | 1.0 |
| context_available_and_sufficient | 1 | 1 | 1.0 |
| fact_accuracy | 0 | 0 | N/A |
| completeness | 0 | 1 | 0.0 |
| citation_integrity | 0 | 0 | N/A |
| citation_support_accuracy | 0 | 0 | N/A |
| false_refusal_rate | 1 | 1 | 1.0 |
| unsupported_answer_rate | 0 | 0 | N/A |
| correct_clarification_rate | 0 | 0 | N/A |
| temporal_accuracy | 0 | 0 | N/A |
| end_to_end_success | 0 | 0 | N/A |
| api_error_rate | 0 | 5 | 0.0 |
| validator_false_acceptance_rate | 0 | 16 | 0.0 |
| validator_false_rejection_rate | 0 | 9 | 0.0 |

Исходы: {'fail': 1}

Ошибки: {'false_refusal': 1}

Непроверенные свойства: {'no_accepted_candidate': 1}

API requests: 5. Латентность worker (без ожидания очереди): {'median_seconds': 92.41206146199988, 'p95_seconds': 92.41206146199988}

## Разбор

retrieval_failure означает отсутствие полного эталонного набора в фактически выбранном контексте; generation_failure — доказанное расхождение ограниченной грамматики. Причина вне этих данных остаётся гипотезой. Неоценённый свободный текст требует ручного чтения. Технические ошибки не считаются юридическими отказами.

## Примеры и воспроизведение

- `temporal-0009`: ['false_refusal']. См. cases/temporal-0009.json, reproduction/temporal-0009.json.

## Рекомендации

Сначала исправлять подтверждённые потери полного набора оснований. Отдельно измерять изменения TOP_K; не считать расширение контекста улучшением юридической точности. Для неразобранного текста нужна независимая ручная разметка. Прежде чем менять runtime, повторить кейсы с реальным API и бюджетом.
