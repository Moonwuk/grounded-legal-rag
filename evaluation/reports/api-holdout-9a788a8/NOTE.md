# Holdout на `9a788a8`

Те же 12 вопросов holdout; `deepseek-flash`, публичный API DeepSeek (не модель платформы). Один прогон.

| Итог | 69f3c0e | 9989f40 | 9a788a8 |
|---|---:|---:|---:|
| pass | 7 | 7 | **9** |
| unverified | 3 | 1 | **0** |
| system_error | 2 | 3 | 1 |
| not_evaluated | 0 | 1 | 2 |

- multi_document-0009: раньше `evidence_size_limit`, теперь pass.
- contradiction-0004: явное заявление о противоречии с обеими сторонами (ручная проверка по правилу для конфликтов).
- missing_information-0009: `partial` с положением базового договора и пробелом даты — ручная проверка.
- temporal-0004: `proxy_unavailable` — сбой транспорта, не решения.
