# Результаты испытаний

Local experiment, not official competition Score. Raw BM25 rank is a separate diagnostic from production grouped context.

```json
{
  "version": "1.0.0",
  "git_commit": "b5ecfdc130c8f10aacd75a2d813b124f01e923c3",
  "runtime_sha256": "e74860d250de51d8b0e0b43d2eb5ac11513ea9bf090d593ed07613650302cea5",
  "evaluation_sha256": "20607e3dbe811f7d150e151b9540f8cce9e988831a91b49d2fa46df43c615de9",
  "corpus_id": "public-24b8adf1546470b5",
  "corpus_sha256": "24b8adf1546470b503ffc1d7f4171f2059a2ea1c17bae41ec644216884cb7641",
  "gold_sha256": "9e99549f00f4f619f73a1758cc5d02f3714b782a16eb030e7f89975ee5846ecf",
  "gold_version": "1.0.0",
  "questions_sha256": "96bcf5d47c7d2a4f5f6e8c4cf449fded13e50364936d52e1ce64d4bbba62fd89",
  "selection_sha256": "ea66abcedfe96a823a2aa422d0402d878e4f343ff5887b7e4ddb0d9c0e7e5083",
  "documents": 135,
  "questions_selected": 20,
  "mode": "full",
  "engine": "retrieval",
  "model": null,
  "provider_base_url": null,
  "config": {
    "top_k": 6,
    "workers": 4,
    "timeout": 30,
    "case_seconds": 240,
    "max_tokens": 2048,
    "temperature": 0,
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
  "fingerprint": "7646808d2d2bcfe71589fe7801f94f5343b2f186ea41ccb16324b10dd0e48ac0",
  "started_utc": "2026-11-10T10:17:53.851139+00:00",
  "elapsed_seconds": 7.8830596000002515,
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
| raw_bm25_recall@1 | 19.0 | 20 | 0.95 |
| raw_bm25_recall@5 | 20.0 | 20 | 1.0 |
| raw_bm25_recall@10 | 20.0 | 20 | 1.0 |
| production_context_sufficiency | 20 | 20 | 1.0 |
| context_available_and_sufficient | 20 | 20 | 1.0 |
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
| validator_false_acceptance_rate | 0 | 7 | 0.0 |
| validator_false_rejection_rate | 0 | 4 | 0.0 |

Исходы: {'not_evaluated': 20}

Ошибки: {}

Непроверенные свойства: {'generation_not_run': 20}

API requests: 0. Латентность worker (без ожидания очереди): {'median_seconds': 1.1647341999998844, 'p95_seconds': 1.532849400000032}

## Разбор

retrieval_failure означает отсутствие полного эталонного набора в фактически выбранном контексте; generation_failure — доказанное расхождение ограниченной грамматики. Причина вне этих данных остаётся гипотезой. Неоценённый свободный текст требует ручного чтения. Технические ошибки не считаются юридическими отказами.

## Примеры и воспроизведение


## Рекомендации

Сначала исправлять подтверждённые потери полного набора оснований. Отдельно измерять изменения TOP_K; не считать расширение контекста улучшением юридической точности. Для неразобранного текста нужна независимая ручная разметка. Прежде чем менять runtime, повторить кейсы с реальным API и бюджетом.
