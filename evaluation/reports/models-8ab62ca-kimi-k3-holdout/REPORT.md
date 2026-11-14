# Результаты испытаний

Local experiment, not official competition Score. Raw BM25 rank is a separate diagnostic from production grouped context.

```json
{
  "version": "1.0.0",
  "git_commit": "8ab62ca82607137c7ede6682c42f340766f0613d",
  "runtime_sha256": "7861ee91ed828403014aa91eeeb620ac4dd67e094713e95f6e837ce171d8e6cf",
  "evaluation_sha256": "aeb0d74cba50f74d31800c2c87ca5c860e0e4765d77897a117d72da49e610a89",
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
  "model": "kimi-k3",
  "provider_base_url": "https://ollama.com/v1",
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
  "fingerprint": "cdaaf8e7e3e203ce3e2f56874ff111343f9fd78112f1460c0efa86ff618a910b",
  "started_utc": "2026-11-12T08:20:06.911182+00:00",
  "cases_not_run": 0,
  "elapsed_seconds": 388.8074576809995,
  "organizer_unchanged": true,
  "budget": {
    "requests": 231,
    "tokens_reserved": 1595463,
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
| fact_accuracy | 130 | 130 | 1.0 |
| completeness | 98 | 98 | 1.0 |
| citation_integrity | 161 | 161 | 1.0 |
| citation_support_accuracy | 130 | 130 | 1.0 |
| false_refusal_rate | 0 | 73 | 0.0 |
| unsupported_answer_rate | 1 | 88 | 0.011363636363636364 |
| correct_clarification_rate | 0 | 0 | N/A |
| temporal_accuracy | 12 | 12 | 1.0 |
| end_to_end_success | 87 | 88 | 0.9886363636363636 |
| api_error_rate | 0 | 229 | 0.0 |
| validator_false_acceptance_rate | 0 | 16 | 0.0 |
| validator_false_rejection_rate | 0 | 9 | 0.0 |

Исходы: {'not_evaluated': 12, 'pass': 87, 'fail': 1}

Ошибки: {'generation_failure': 1}

Непроверенные свойства: {'conditional_or_conflict_explanation_requires_manual_review': 12, 'conflict_explanation_requires_manual_review': 7}

API requests: 229. Латентность worker (без ожидания очереди): {'median_seconds': 6.642668894500275, 'p95_seconds': 13.817211798999779}

## Разбор

retrieval_failure означает отсутствие полного эталонного набора в фактически выбранном контексте; generation_failure — доказанное расхождение ограниченной грамматики. Причина вне этих данных остаётся гипотезой. Неоценённый свободный текст требует ручного чтения. Технические ошибки не считаются юридическими отказами.

## Примеры и воспроизведение

- `temporal-0019`: ['generation_failure']. См. cases/temporal-0019.json, reproduction/temporal-0019.json.

## Рекомендации

Сначала исправлять подтверждённые потери полного набора оснований. Отдельно измерять изменения TOP_K; не считать расширение контекста улучшением юридической точности. Для неразобранного текста нужна независимая ручная разметка. Прежде чем менять runtime, повторить кейсы с реальным API и бюджетом.
