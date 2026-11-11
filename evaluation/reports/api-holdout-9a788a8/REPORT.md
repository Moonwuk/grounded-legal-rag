# Результаты испытаний

Local experiment, not official competition Score. Raw BM25 rank is a separate diagnostic from production grouped context.

```json
{
  "version": "1.0.0",
  "git_commit": "87f40a873a8415daee075377380c5497f8e2c4da",
  "runtime_sha256": "e93fe2a4abd4580429eb066e5ee89d500a149b3a4fd309b565a873bbb6398433",
  "evaluation_sha256": "d7c79970784e2abab796c90de667e706de0c441049051fd572b2994261f1ba8f",
  "validator_sha256": "e833da8a064cc9dabaa97e20bfc2756f3232e582d4c1af7ea0ec3fa4d7514305",
  "retrieval_adapter_sha256": "17a03efaa958ee5f1ff64a6154f3feef07c685611e3fbef753291cd02afbfd43",
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
  "fingerprint": "9e039607fa48c5e75148a3bbc7a3dec569218ffe78bec5aa8db66bcee58a62c7",
  "started_utc": "2026-11-11T09:09:19.958160+00:00",
  "cases_not_run": 0,
  "elapsed_seconds": 322.783763541,
  "organizer_unchanged": true,
  "budget": {
    "requests": 36,
    "tokens_reserved": 382010,
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
| fact_accuracy | 17 | 17 | 1.0 |
| completeness | 10 | 10 | 1.0 |
| citation_integrity | 17 | 17 | 1.0 |
| citation_support_accuracy | 17 | 17 | 1.0 |
| false_refusal_rate | 0 | 8 | 0.0 |
| unsupported_answer_rate | 0 | 9 | 0.0 |
| correct_clarification_rate | 0 | 0 | N/A |
| temporal_accuracy | 1 | 1 | 1.0 |
| end_to_end_success | 9 | 9 | 1.0 |
| api_error_rate | 0 | 34 | 0.0 |
| validator_false_acceptance_rate | 0 | 16 | 0.0 |
| validator_false_rejection_rate | 0 | 9 | 0.0 |

Исходы: {'not_evaluated': 2, 'pass': 9, 'system_error': 1}

Ошибки: {'system_error': 1}

Непроверенные свойства: {'conditional_or_conflict_explanation_requires_manual_review': 2, 'conflict_explanation_requires_manual_review': 1}

API requests: 34. Латентность worker (без ожидания очереди): {'median_seconds': 21.503166805999967, 'p95_seconds': 162.16135043600002}

## Разбор

retrieval_failure означает отсутствие полного эталонного набора в фактически выбранном контексте; generation_failure — доказанное расхождение ограниченной грамматики. Причина вне этих данных остаётся гипотезой. Неоценённый свободный текст требует ручного чтения. Технические ошибки не считаются юридическими отказами.

## Примеры и воспроизведение

- `temporal-0004`: ['system_error']. См. cases/temporal-0004.json, reproduction/temporal-0004.json.

## Рекомендации

Сначала исправлять подтверждённые потери полного набора оснований. Отдельно измерять изменения TOP_K; не считать расширение контекста улучшением юридической точности. Для неразобранного текста нужна независимая ручная разметка. Прежде чем менять runtime, повторить кейсы с реальным API и бюджетом.
