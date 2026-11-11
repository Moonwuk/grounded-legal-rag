# Реестр публичных источников

Фактически включено 135 документов. Отклонено дубликатов/near-duplicates: 5. Источники зафиксированы commit SHA в public_documents/sources.lock.json.

| Источник | Лицензия | Фактически включено |
|---|---|---:|
| [capysta2016/samozanyaty-docs-templates](https://github.com/capysta2016/samozanyaty-docs-templates) | [CC0-1.0](https://raw.githubusercontent.com/capysta2016/samozanyaty-docs-templates/76e35c876b64ebea8c2ab13ba1f0ac8ed50bb899/LICENSE) | 2 |
| [dshushin/nvim.bilingual](https://github.com/dshushin/nvim.bilingual) | [MIT](https://raw.githubusercontent.com/dshushin/nvim.bilingual/5b655ab30adada65808f58efd5ce5c9af168aa0a/LICENSE) | 1 |
| [General-Legal/legal-templates](https://github.com/General-Legal/legal-templates) | [CC0-1.0](https://raw.githubusercontent.com/General-Legal/legal-templates/6d6805425eabd41bed86fc1e2ec51612760f716c/LICENSE) | 12 |
| [mozilla/legal-docs](https://github.com/mozilla/legal-docs) | [CC-BY-SA-3.0](https://raw.githubusercontent.com/mozilla/legal-docs/68c62051e7ca282a023a2560ca72edf227097a1f/LICENSE.md) | 120 |

Оригинальные байты и отдельные LICENSE сохранены в public_documents/. Mozilla: CC BY-SA 3.0, автор Mozilla, source URL и SHA каждого файла в registry.json; тексты не изменены. Они сохраняют свою лицензию, не перелицензируются вместе со стендом. General Legal и capysta2016: CC0; nvim.bilingual: MIT с сохранением notice.

Это опубликованные шаблоны и корпоративные политики, не подписанные сделки. Большая часть Mozilla — переводы одних семейств; число файлов не равно числу независимых правовых ситуаций. Языки указаны отдельно. Документы не объявляются действующим правом и не превращаются в эталоны ответа модели.

Исследованы, но не включены: wpcraft-ru/kb-wordpress (README заявляет MIT, явный LICENSE не найден); irlcode/RusLawOD (CC BY-NC 4.0, не переносим в банковский/коммерческий контур); неизвестные договоры с неясной лицензией и банковские формы без явного разрешения на распространение. Их содержимое не копировалось в корпус.

Публичный набор оценивается отдельно: вопросы проверяют поиск буквального диапазона, а не юридическую правильность. Вручную размеченной реальной базы организаторов пока нет. Для mixed используются только синтетические юридические эталоны; публичные тексты служат отвлекающими источниками.

Повторная загрузка: python -m evaluation.collect_public. Уже сохранённый lock фиксирует ревизии; --refresh явно обновляет источники. Сетевой сбой даёт ошибку, не выдуманный документ.
