# Диагностика трёх `unverified` из holdout (`69f3c0e`)

Повтор `temporal-0009`, `temporal-0004`, `contradiction-0004` на `f08afbd`
(отчёты `diag-unverified-f08afbd-*`), `deepseek-flash`, публичный API DeepSeek.
Все три снова закончились `unverified`.

| Кейс | Попытка | Выбранные положения (роль документа) | Неприменимы по проверке |
|---|---|---|---|
| temporal-0009 | 1 | base, amendment, similar_party | amendment, similar_party |
| temporal-0009 | 2 | base, amendment | amendment |
| temporal-0004 | 1 | base, amendment, conflict | base |
| temporal-0004 | 2 | amendment, base | base |
| contradiction-0004 | 1 | base, amendment, conflict | base |
| contradiction-0004 | 2 | amendment, conflict, base | base |

Неподтверждённых положений нет ни в одной из 6 проверок. Каждый раз
неприменимым признано положение, которое модель привела для контраста, и
вердикт верен по эталону.

**Подтверждённая причина (на синтетике).** `psb_policy.approved` требует,
чтобы каждое выбранное положение было подтверждено и применимо. Одно
контрастное неприменимое положение отклоняет весь кандидат на обеих попытках,
и публикуется общий отказ. Исправление в решении отложено до проверки этого
механизма на демо-корпусе организаторов.
