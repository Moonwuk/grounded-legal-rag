# Результаты испытаний

Local experiment, not official competition Score. Raw BM25 rank is a separate diagnostic from production grouped context.

```json
{
  "version": "1.0.0",
  "git_commit": "b5ecfdc130c8f10aacd75a2d813b124f01e923c3",
  "runtime_sha256": "e74860d250de51d8b0e0b43d2eb5ac11513ea9bf090d593ed07613650302cea5",
  "evaluation_sha256": "85ee79689f2dcfe66b2593f6177e43f36106157ef9638018d9b1bfee9bb1705e",
  "corpus_id": "pilot-744fab3025b65aeb",
  "corpus_sha256": "9f343a22614ea37d0c11bdb683dcc53d3e61ab8bec8f2ab4ca74bb7535a2c15c",
  "gold_sha256": "a77c7385da5f0fa4ab7a0d2e1e43c035830534e171639059573f8939e25e6447",
  "gold_version": "1.0.0",
  "questions_sha256": "5b2057166852b6de51e69cf447752bf6d78f69c66d193cb3c182e98bbad096cd",
  "selection_sha256": "d4d2969b06cfd22961952275dafed7c120745aa0bd812091ada5fb35bbe50f38",
  "documents": 40,
  "questions_selected": 12,
  "mode": "integration",
  "engine": "retrieval",
  "model": null,
  "config": {
    "top_k": 6,
    "workers": 2,
    "timeout": 30,
    "case_seconds": 240,
    "max_requests": 60,
    "max_token_bound": 3000000,
    "max_cost": null,
    "input_price_per_million": 0,
    "output_price_per_million": 0,
    "save_responses": true,
    "bm25_k1": 1.5,
    "bm25_b": 0.75,
    "note": "No prices guessed. Set both unit prices to enforce monetary cap. Token bound reserves UTF-8 request bytes plus max_tokens per HTTP attempt; conservative, not billing.",
    "engine": "retrieval"
  },
  "fingerprint": "7296a3f9aa50ffb131c1ba069433164cbce4de67785b4978026d30c13b1e21f6",
  "started_utc": "2026-11-10T10:08:56.455570+00:00",
  "elapsed_seconds": 5.31592569999998,
  "organizer_unchanged": true,
  "budget": {
    "requests": 0,
    "tokens_reserved": 0,
    "cost_reserved": 0.0
  },
  "isolation": "fresh subprocess per case; only copied runtime, corpus and public question; no gold/specs copied",
  "api_status": "not_requested"
}
```

| Метрика | Числитель | Знаменатель | Значение |
|---|---:|---:|---:|
| raw_bm25_recall@1 | 4 | 9 | 0.4444444444444444 |
| raw_bm25_recall@5 | 7 | 9 | 0.7777777777777778 |
| raw_bm25_recall@10 | 7 | 9 | 0.7777777777777778 |
| production_context_sufficiency | 9 | 9 | 1.0 |
| fact_accuracy | 0 | 0 | N/A |
| completeness | 0 | 0 | N/A |
| citation_integrity | 0 | 0 | N/A |
| citation_support_accuracy | 0 | 0 | N/A |
| false_refusal_rate | 0 | 0 | N/A |
| unsupported_answer_rate | 0 | 0 | N/A |
| correct_clarification_rate | 0 | 0 | N/A |
| temporal_accuracy | 0 | 0 | N/A |
| end_to_end_success | 0 | 0 | N/A |
| api_error_rate | 0 | 0 | N/A |
| validator_false_acceptance_rate | 0 | 0 | N/A |
| validator_false_rejection_rate | 0 | 0 | N/A |

Исходы: {'not_evaluated': 12}

Ошибки: {}

Непроверенные свойства: {'generation_not_run': 12}

API requests: 0. Латентность worker (без ожидания очереди): {'median_seconds': 0.02071149999994759, 'p95_seconds': 0.024349400000119203}

## Разбор

retrieval_failure означает отсутствие полного эталонного набора в фактически выбранном контексте; generation_failure — доказанное расхождение ограниченной грамматики. Причина вне этих данных остаётся гипотезой. Неоценённый свободный текст требует ручного чтения. Технические ошибки не считаются юридическими отказами.

## Примеры и воспроизведение


## Рекомендации

Сначала исправлять подтверждённые потери полного набора оснований. Отдельно измерять изменения TOP_K; не считать расширение контекста улучшением юридической точности. Для неразобранного текста нужна независимая ручная разметка. Прежде чем менять runtime, повторить кейсы с реальным API и бюджетом.
