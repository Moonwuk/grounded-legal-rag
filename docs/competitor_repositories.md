# Публичные репозитории по кейсу ПСБ (Hack&Change 2026)

Сводка находок на 13.11.2026. Поиск вёлся по GitHub: запросы «psb legal», «psb hackathon»,
«hack change 2026», «юридический ассистент ПСБ» и по ссылкам из найденных README.
Нужна для ориентира, не как источник кода. Чужой код мы не копируем и не коммитим.

В таблицах:
- «.py / строк» — число Python-файлов и строк кода в репозитории на момент просмотра (грубая
  оценка объёма; 0 — кода нет);
- «Балл» — только баллы, которые команда сама публикует в репозитории.

## 1. Главная находка

| Репозиторий | .py / строк | Балл | Что там |
|---|---|---|---|
| [yenqo/hack-change-psb](https://github.com/yenqo/hack-change-psb) | 54 / 12 817 | до 51,7 | Журнал всех сабмитов с баллами и выводами. Вероятно, команда `misis-mirea-usptu-innopolis` (0,5175 в таблице лидеров) — это предположение по совпадению балла |

Журнал их сабмитов:

| Версия | Балл | Изменение |
|---|---|---|
| v1 | 20,8 | модель не ответила, в файле только запасные цитаты |
| v1.3–v1.5 | 14–29 | модель отвечает; разброс от нагрузки платформы |
| v1.6 | 43,8 | «строго на вопрос»: +18 |
| v1.8 | 47,0 | формат эталона «ответ. Источник: документ, п. N.» |
| v1.9 | 51,7 | вымышленные примеры ответов (few-shot) в промпте: +4,7 |

Их выводы, которые мы проверили и учли (см. [answer_form.md](answer_form.md)):

- Судья — DeepSeek. Верные детали сверх эталона он читает как выдумку и обнуляет вопрос: ответы
  с лишним в среднем 0,33–0,49, без лишнего — 0,88.
- Около 21 балла — уровень «одни запасные цитаты».
- Шум платформы около 5 баллов: один архив дал 28,9 днём и 15,7 вечером. Сравнивать можно
  только сабмиты подряд в одно время суток.
- Поиск у них не узкое место; ошибки почти все в генерации (лишние детали, неверный источник).

Что сделали мы:

- Резервная копия: git bundle лежит локально в `external_backup/`, в git исключён.
- Их решение мы запустили с нашим ключом. Наш локальный судья оценил оба решения одинаково
  (≈ 0,84–0,86), то есть он не повторяет платформенного.
- Из их выводов мы взяли идеи, не код:
  - строго на вопрос, 20–60 слов;
  - строка «Источник: …»;
  - вымышленные примеры в промпте;
  - короткий отказ.

## 2. Репозитории с описанной схемой или баллами

| Репозиторий | .py / строк | Балл | Что там |
|---|---|---|---|
| [LaimOr127/hacaton_psb](https://github.com/LaimOr127/hacaton_psb) | — | нет | Подробнее всех описанная схема, см. ниже |
| [LankiSer/psb_hack](https://github.com/LankiSer/psb_hack) | 29 / 1 562 | 18 / 17,4 / 25,9 | Последний результат — за 575 с; уровень наших архивов до №12 |
| [psb-hack/psb-legal-assistant](https://github.com/psb-hack/psb-legal-assistant) | 141 / 24 945 | нет | «Ответы только по базе документов…»; много документации (кейс, модель угроз, практики) |
| [Koomaz/PSBcase-bablteam](https://github.com/Koomaz/PSBcase-bablteam) | 44 / 9 316 | нет | Модули поиска и ответа с проверкой ссылок; по README генерация через DeepSeek и отправка не проверены |
| [dasharum2006-byte/psb-legal-assistant](https://github.com/dasharum2006-byte/psb-legal-assistant) | 23 / 2 277 | нет | FastAPI + React, в планах проверка ответа; пайплайн в README не описан |
| [Svalbard1/legal-assistant](https://github.com/Svalbard1/legal-assistant) | — | нет | bge-m3 + Qdrant; генерация на 9 ноября была заглушкой |

Схема LaimOr127/hacaton_psb:

- **Поиск:** TF-IDF + bge-m3, объединение через RRF, реранкер Qwen3.
- **Ответ:** один вызов модели на вопрос плюс максимум один повтор, если программная проверка
  нашла неподтверждённое число или пункт. Отдельного проверяющего вызова модели нет.
- **Контекст:** документы до 6 000 символов целиком; у крупных — найденные пункты и оглавление
  статьи.
- **Время:** 4 параллельных вопроса, бюджет 960 с; в их оценке есть пересчёт времени «на 300
  вопросов» — вероятный размер скрытого набора.

От них мы взяли идеи (не код): один вызов с повтором по программной проверке (архивы №12 и №14)
и оглавление длинной статьи закона (№15).

## 3. Остальные репозитории по кейсу

Заготовки, ранняя стадия или код без описания; баллов нет.

| Репозиторий | .py / строк | Описание / дата обновления |
|---|---|---|
| [BespalovPavel/psb-legal-assistant](https://github.com/BespalovPavel/psb-legal-assistant) | 20 / 3 770 | 12.11 |
| [vladislavprozorov/psb-legal-assistant](https://github.com/vladislavprozorov/psb-legal-assistant) | 10 / 2 789 | 10.11 |
| [menzurka228/psb-legal-assistant](https://github.com/menzurka228/psb-legal-assistant) | 6 / 2 546 | 11.11 |
| [Mihail-sudo/Hack_Change_2026](https://github.com/Mihail-sudo/Hack_Change_2026) | 27 / 2 307 | 13.11 |
| [lev1080p/psb-assistant-hackchange-hackaton](https://github.com/lev1080p/psb-assistant-hackchange-hackaton) | 14 / 1 563 | 13.11 |
| [jabovik/PSB_hackathon](https://github.com/jabovik/PSB_hackathon) | 22 / 1 550 | 12.11; рядом — [jabovik/PSB_hackathon_test_models](https://github.com/jabovik/PSB_hackathon_test_models) |
| [Ainyr-Akhmadishin/PSB-Legal-Assistant](https://github.com/Ainyr-Akhmadishin/PSB-Legal-Assistant) | 13 / 1 447 | 11.11 |
| [weltenmelon/psb_hack](https://github.com/weltenmelon/psb_hack) | 2 / 985 | — |
| [ProofMrNick/psb_hackathon](https://github.com/ProofMrNick/psb_hackathon) | 27 / 961 | 13.11 |
| [Kamil-Fatekhov/psb-legal-assistant](https://github.com/Kamil-Fatekhov/psb-legal-assistant) | 13 / 715 | 11.11 |
| [antonshkelll/opora-psb](https://github.com/antonshkelll/opora-psb) | 9 / 482 | «ОПОРА: юридический RAG с проверяемыми цитатами», 13.11 |
| [mashashvi37-eng/Hackaton-PSB](https://github.com/mashashvi37-eng/Hackaton-PSB) | 2 / 433 | — |
| [PaulPchel/hack-and-change-2026](https://github.com/PaulPchel/hack-and-change-2026) | 1 / 269 | — |
| [huzouskaya/Changellenge_Hackaton_PSB](https://github.com/huzouskaya/Changellenge_Hackaton_PSB) | 15 / 0 | — |
| [KRKI2/hack-and-change-2026](https://github.com/KRKI2/hack-and-change-2026) | — | README пустой; папка решения и материалы организаторов |
| [beketovfedor/psb-legal-assistant](https://github.com/beketovfedor/psb-legal-assistant) | 0 | «Юридический ассистент для кейса ПСБ», 13.11 |
| [TimofeevArtem/PSB_legal_assistent](https://github.com/TimofeevArtem/PSB_legal_assistent) | 0 | — |
| [metriiics/hack_and_change_2026](https://github.com/metriiics/hack_and_change_2026) | 0 | — |
| [outsider8946/PSB-hack](https://github.com/outsider8946/PSB-hack) | 0 | — |
| [closqee/hackathon-hard](https://github.com/closqee/hackathon-hard) | 0 | Правила команды и расписание трека: дедлайн 16.11 14:00 МСК, финалисты 20.11, финал 21–22.11 (по README, официально не сверено) |

## 4. Смежные, не по кейсу

Юридический RAG и наборы данных, которые встречались при поиске.

| Репозиторий | Зачем смотрели |
|---|---|
| [AlsKozlov/legalbench-ru](https://github.com/AlsKozlov/legalbench-ru) | LegalBench-RU — использован в нашей оценке ([evaluation/](../evaluation/README.md)) |
| [zeroentropy-cc/legalbenchrag](https://github.com/zeroentropy-cc/legalbenchrag) | LegalBench-RAG, англоязычный набор для поиска |
| [rutar-anonymous/RuTaR](https://github.com/rutar-anonymous/RuTaR) | русскоязычный набор юридических рассуждений |
| [alekseevpavel04/ru-law-retrieval](https://github.com/alekseevpavel04/ru-law-retrieval) | поиск по российскому законодательству |
| [VectifyAI/PageIndex](https://github.com/VectifyAI/PageIndex) | поиск по структуре документа без векторов |
| [Gopota58/Kodeksbot-RAG](https://github.com/Gopota58/Kodeksbot-RAG) | юридический RAG на GigaChat, гибридный поиск |
| [SholbanDongak/LegalHelp](https://github.com/SholbanDongak/LegalHelp) | ответы на запросы госорганов и контрагентов |
| [murzikminsk-del/rag-legal-v2](https://github.com/murzikminsk-del/rag-legal-v2) | юридический RAG |

Поиск по «PSB hackathon» выдаёт и много проектов индийского PSBs Hackathon 2026 (банковская
безопасность, антифрод). К нашему кейсу они не относятся и в таблицы не включены.

## Ограничения сводки

- В большинстве репозиториев мы читали только README и список файлов. Подробно разобраны только
  yenqo и LaimOr127.
- Баллы взяты из самих репозиториев и не сверены с таблицей лидеров (кроме совпадения 0,5175).
- Репозитории меняются; число файлов и строк — на 13.11.2026.
