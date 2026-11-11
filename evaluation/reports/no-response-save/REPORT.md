# Результаты испытаний

Local experiment, not official competition Score. Raw BM25 rank is a separate diagnostic from production grouped context.

```json
{
  "version": "1.0.0",
  "git_commit": "b5ecfdc130c8f10aacd75a2d813b124f01e923c3",
  "runtime_sha256": "e74860d250de51d8b0e0b43d2eb5ac11513ea9bf090d593ed07613650302cea5",
  "evaluation_sha256": "9e90aa0a9264aa472bbc6c0c666d5f5f411bd0a2d7ea8402170f8a0323608517",
  "corpus_id": "pilot-744fab3025b65aeb",
  "corpus_sha256": "9f343a22614ea37d0c11bdb683dcc53d3e61ab8bec8f2ab4ca74bb7535a2c15c",
  "gold_sha256": "a77c7385da5f0fa4ab7a0d2e1e43c035830534e171639059573f8939e25e6447",
  "gold_version": "1.0.0",
  "questions_sha256": "5b2057166852b6de51e69cf447752bf6d78f69c66d193cb3c182e98bbad096cd",
  "selection_sha256": "d4d2969b06cfd22961952275dafed7c120745aa0bd812091ada5fb35bbe50f38",
  "documents": 40,
  "questions_selected": 12,
  "mode": "integration",
  "engine": "stub",
  "model": null,
  "provider_base_url": null,
  "config": {
    "top_k": 6,
    "workers": 2,
    "timeout": 30,
    "case_seconds": 240,
    "max_tokens": 2048,
    "temperature": 0,
    "max_requests": 60,
    "max_token_bound": 3000000,
    "max_cost": null,
    "input_price_per_million": 0,
    "output_price_per_million": 0,
    "save_responses": false,
    "bm25_k1": 1.5,
    "bm25_b": 0.75,
    "note": "No prices guessed. Set both unit prices to enforce monetary cap. Token bound reserves UTF-8 request bytes plus max_tokens per HTTP attempt; conservative, not billing.",
    "engine": "stub"
  },
  "fingerprint": "ba8ecd756a184d338d7d8b5d31579db73c809b3f321ba1ad49e70b960ebc1660",
  "started_utc": "2026-11-10T10:26:27.783714+00:00",
  "cases_not_run": 0,
  "elapsed_seconds": 0.890246500000103,
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
| raw_bm25_recall@1 | 5.0 | 9 | 0.5555555555555556 |
| raw_bm25_recall@5 | 8.0 | 9 | 0.8888888888888888 |
| raw_bm25_recall@10 | 8.0 | 9 | 0.8888888888888888 |
| production_context_sufficiency | 9 | 9 | 1.0 |
| context_available_and_sufficient | 9 | 9 | 1.0 |
| fact_accuracy | 0 | 0 | N/A |
| completeness | 0 | 11 | 0.0 |
| citation_integrity | 0 | 0 | N/A |
| citation_support_accuracy | 0 | 0 | N/A |
| false_refusal_rate | 9 | 9 | 1.0 |
| unsupported_answer_rate | 0 | 11 | 0.0 |
| correct_clarification_rate | 0 | 1 | 0.0 |
| temporal_accuracy | 0 | 0 | N/A |
| end_to_end_success | 1 | 11 | 0.09090909090909091 |
| api_error_rate | 0 | 0 | N/A |
| validator_false_acceptance_rate | 0 | 7 | 0.0 |
| validator_false_rejection_rate | 0 | 4 | 0.0 |

Исходы: {'fail': 11, 'pass': 1}

Ошибки: {'generation_failure': 2, 'false_refusal': 9, 'incomplete_answer': 10}

Непроверенные свойства: {'conflict_explanation_requires_manual_review': 1}

API requests: 36. Латентность worker (без ожидания очереди): {'median_seconds': 0.02188954999996895, 'p95_seconds': 0.028346599999622413}

## Разбор

retrieval_failure означает отсутствие полного эталонного набора в фактически выбранном контексте; generation_failure — доказанное расхождение ограниченной грамматики. Причина вне этих данных остаётся гипотезой. Неоценённый свободный текст требует ручного чтения. Технические ошибки не считаются юридическими отказами.

## Примеры и воспроизведение

- `contradiction-0000`: ['generation_failure']. См. cases/contradiction-0000.json, reproduction/contradiction-0000.json.
- `contradiction-0001`: ['false_refusal', 'incomplete_answer']. См. cases/contradiction-0001.json, reproduction/contradiction-0001.json.
- `fact-0000`: ['false_refusal', 'incomplete_answer']. См. cases/fact-0000.json, reproduction/fact-0000.json.
- `fact-0001`: ['false_refusal', 'incomplete_answer']. См. cases/fact-0001.json, reproduction/fact-0001.json.
- `missing_information-0000`: ['generation_failure', 'incomplete_answer']. См. cases/missing_information-0000.json, reproduction/missing_information-0000.json.
- `multi_document-0000`: ['false_refusal', 'incomplete_answer']. См. cases/multi_document-0000.json, reproduction/multi_document-0000.json.
- `multi_document-0001`: ['false_refusal', 'incomplete_answer']. См. cases/multi_document-0001.json, reproduction/multi_document-0001.json.
- `security-0000`: ['false_refusal', 'incomplete_answer']. См. cases/security-0000.json, reproduction/security-0000.json.

## Рекомендации

Сначала исправлять подтверждённые потери полного набора оснований. Отдельно измерять изменения TOP_K; не считать расширение контекста улучшением юридической точности. Для неразобранного текста нужна независимая ручная разметка. Прежде чем менять runtime, повторить кейсы с реальным API и бюджетом.
