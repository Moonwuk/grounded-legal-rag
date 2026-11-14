# Результаты испытаний

Local experiment, not official competition Score. Raw BM25 rank is a separate diagnostic from production grouped context.

```json
{
  "version": "1.0.0",
  "git_commit": "9dd8e3c6d5ecead325edad7a99ebec6ba7731ffa",
  "runtime_sha256": "369bf987092cb95399a369dce9d28dbd12a07fe213f0286d75b3417cc6247643",
  "evaluation_sha256": "d5e6a8c48fdaeab84851a1722216c2e6d13566dccb6cb47b45864f02d3659503",
  "validator_sha256": "3120d9c32fcd1dab1c4b78fac36cce15e9098e440987f403ae6ee39aef645ab6",
  "retrieval_adapter_sha256": "17a03efaa958ee5f1ff64a6154f3feef07c685611e3fbef753291cd02afbfd43",
  "corpus_id": "synthetic-b148e60beaa44f30",
  "corpus_sha256": "283b6ac186a36c6ca6a10078c9e31f7d41ab65672c3bbe32b8f9ef62c6190fe1",
  "gold_sha256": "99440bd422a366e25c601a1708ba326b2913bdcd1cc76d5fda9d14ae413a164e",
  "gold_version": "1.0.0",
  "questions_sha256": "7e4336e1b6a67c18a8bfae589587c1a035d67d8213455c97d03ac354d9daaf61",
  "selection_sha256": "a3bc171f08e7116f74c00b2c7492cbaceb1d7b169a9021aa18a6e93c126e94f9",
  "documents": 1000,
  "questions_selected": 12,
  "mode": "smoke",
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
    "note": "timeout/max_tokens/temperature/reasoning_effort null = runtime defaults (no override), as on the platform. No prices guessed. Set both unit prices to enforce monetary cap. Token bound reserves UTF-8 request bytes plus max_tokens per HTTP attempt, then settles to provider-reported total_tokens; not billing.",
    "reasoning_effort": null,
    "engine": "deepseek"
  },
  "fingerprint": "1345b50b206c219d2ddb2a9cda1c4cbe9f2b471f982c655082de0ce17efb3208",
  "started_utc": "2026-11-12T05:52:43.237964+00:00",
  "cases_not_run": 0,
  "elapsed_seconds": 153.69282328600002,
  "organizer_unchanged": true,
  "budget": {
    "requests": 30,
    "tokens_reserved": 299680,
    "cost_reserved": 0.0
  },
  "isolation": "fresh subprocess per case; only copied runtime, corpus and public question; no gold/specs copied",
  "api_status": "executed"
}
```

| Метрика | Числитель | Знаменатель | Значение |
|---|---:|---:|---:|
| raw_bm25_recall@1 | 3.5 | 9 | 0.3888888888888889 |
| raw_bm25_recall@5 | 5.0 | 9 | 0.5555555555555556 |
| raw_bm25_recall@10 | 6.0 | 9 | 0.6666666666666666 |
| production_context_sufficiency | 9 | 9 | 1.0 |
| context_available_and_sufficient | 9 | 9 | 1.0 |
| fact_accuracy | 18 | 18 | 1.0 |
| completeness | 11 | 11 | 1.0 |
| citation_integrity | 19 | 19 | 1.0 |
| citation_support_accuracy | 18 | 18 | 1.0 |
| false_refusal_rate | 0 | 9 | 0.0 |
| unsupported_answer_rate | 1 | 10 | 0.1 |
| correct_clarification_rate | 0 | 0 | N/A |
| temporal_accuracy | 2 | 2 | 1.0 |
| end_to_end_success | 8 | 10 | 0.8 |
| api_error_rate | 0 | 28 | 0.0 |
| validator_false_acceptance_rate | 0 | 16 | 0.0 |
| validator_false_rejection_rate | 0 | 9 | 0.0 |

Исходы: {'not_evaluated': 2, 'pass': 8, 'fail': 2}

Ошибки: {'generation_failure': 1, 'incomplete_answer': 1}

Непроверенные свойства: {'conditional_or_conflict_explanation_requires_manual_review': 2, 'conflict_explanation_requires_manual_review': 1}

API requests: 28. Латентность worker (без ожидания очереди): {'median_seconds': 17.8206290065001, 'p95_seconds': 67.27146411900003}

## Разбор

retrieval_failure означает отсутствие полного эталонного набора в фактически выбранном контексте; generation_failure — доказанное расхождение ограниченной грамматики. Причина вне этих данных остаётся гипотезой. Неоценённый свободный текст требует ручного чтения. Технические ошибки не считаются юридическими отказами.

## Примеры и воспроизведение

- `fact-0000`: ['generation_failure']. См. cases/fact-0000.json, reproduction/fact-0000.json.
- `missing_information-0001`: ['incomplete_answer']. См. cases/missing_information-0001.json, reproduction/missing_information-0001.json.

## Рекомендации

Сначала исправлять подтверждённые потери полного набора оснований. Отдельно измерять изменения TOP_K; не считать расширение контекста улучшением юридической точности. Для неразобранного текста нужна независимая ручная разметка. Прежде чем менять runtime, повторить кейсы с реальным API и бюджетом.
