# Результаты испытаний

Local experiment, not official competition Score. Raw BM25 rank is a separate diagnostic from production grouped context.

```json
{
  "version": "1.0.0",
  "git_commit": "7258f7deb2b393853d300cc819b6f5694d967973",
  "runtime_sha256": "f757d78bd5e5f502818810e90a4543c01a7060c246e5d984a9b85125a134704b",
  "evaluation_sha256": "d7c79970784e2abab796c90de667e706de0c441049051fd572b2994261f1ba8f",
  "validator_sha256": "e833da8a064cc9dabaa97e20bfc2756f3232e582d4c1af7ea0ec3fa4d7514305",
  "retrieval_adapter_sha256": "17a03efaa958ee5f1ff64a6154f3feef07c685611e3fbef753291cd02afbfd43",
  "corpus_id": "synthetic-b148e60beaa44f30",
  "corpus_sha256": "283b6ac186a36c6ca6a10078c9e31f7d41ab65672c3bbe32b8f9ef62c6190fe1",
  "gold_sha256": "99440bd422a366e25c601a1708ba326b2913bdcd1cc76d5fda9d14ae413a164e",
  "gold_version": "1.0.0",
  "questions_sha256": "7e4336e1b6a67c18a8bfae589587c1a035d67d8213455c97d03ac354d9daaf61",
  "selection_sha256": "3fea43b13623e9987c4e59de99832560abef1b9e77073fcddce78eb8e8f0e35f",
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
  "fingerprint": "9050c98fdec31c3f2615d9a6ae1fbb29e14d0147da3dcf8ef0ab56cc22dae42b",
  "started_utc": "2026-11-11T04:09:55.563448+00:00",
  "cases_not_run": 0,
  "elapsed_seconds": 21.794130666,
  "organizer_unchanged": true,
  "budget": {
    "requests": 5,
    "tokens_reserved": 47506,
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
| fact_accuracy | 1 | 1 | 1.0 |
| completeness | 1 | 1 | 1.0 |
| citation_integrity | 1 | 1 | 1.0 |
| citation_support_accuracy | 1 | 1 | 1.0 |
| false_refusal_rate | 0 | 1 | 0.0 |
| unsupported_answer_rate | 0 | 1 | 0.0 |
| correct_clarification_rate | 0 | 0 | N/A |
| temporal_accuracy | 0 | 0 | N/A |
| end_to_end_success | 1 | 1 | 1.0 |
| api_error_rate | 0 | 3 | 0.0 |
| validator_false_acceptance_rate | 0 | 16 | 0.0 |
| validator_false_rejection_rate | 0 | 9 | 0.0 |

Исходы: {'pass': 1}

Ошибки: {}

Непроверенные свойства: {}

API requests: 3. Латентность worker (без ожидания очереди): {'median_seconds': 19.69455599999992, 'p95_seconds': 19.69455599999992}

## Разбор

retrieval_failure означает отсутствие полного эталонного набора в фактически выбранном контексте; generation_failure — доказанное расхождение ограниченной грамматики. Причина вне этих данных остаётся гипотезой. Неоценённый свободный текст требует ручного чтения. Технические ошибки не считаются юридическими отказами.

## Примеры и воспроизведение


## Рекомендации

Сначала исправлять подтверждённые потери полного набора оснований. Отдельно измерять изменения TOP_K; не считать расширение контекста улучшением юридической точности. Для неразобранного текста нужна независимая ручная разметка. Прежде чем менять runtime, повторить кейсы с реальным API и бюджетом.
