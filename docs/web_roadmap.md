# Роадмап: веб-интерфейс юридического ассистента

Кейс ПСБ «Юридический ассистент», Hack&Change 2026.
Репозиторий: https://github.com/Moonwuk/grounded-legal-rag
Составлен 10 ноября 2026 по ветке `main`, коммит `af86471`. Если `main` с тех пор изменился, сверяйте имена файлов и функций с актуальным кодом.

## Состояние реализации 11 ноября

Ветка web-chat создана от 1304005. Примеры ниже относятся к исходному роадмапу. Актуальные команды запуска приведены в README. В нынешнем ядре ссылки связного ответа и нумерованные выдержки формируются в разных ветках. API получает опубликованные фрагменты из соответствующей ветки ядра.

В Ubuntu под WSL прошли 253 исходных и 254 итоговых теста ядра. Дополнительно прошли три теста HTTP API. Docker собран, healthcheck подтвердил загрузку 21 документа. Основной сценарий, отказ, уточнение и сетевой повтор проверены в Edge с локальной заглушкой и реальной базой. Для запуска тестов веба использована отдельная среда Windows, поскольку в установленной Ubuntu отсутствует ensurepip. Ключ модели и внешний хост демо остаются открытыми пунктами.

## Как пользоваться этим документом

- Документ самодостаточен: по нему можно начать работу, ничего больше не читая.
- Идите по шагам сверху вниз. У каждого шага есть «Сделай» и «Проверь». Не переходите дальше, пока проверка не проходит.
- Положите этот файл в репозиторий как `docs/web_roadmap.md`. Отмечайте выполненные шаги в чек-листе ниже (`[x]`) и коммитьте вместе с кодом, чтобы следующий человек видел, где вы остановились.
- Команды написаны для macOS и Linux. На Windows работайте в WSL.
- **Если вы ИИ-агент:** сначала прочитайте `AGENTS.md` в корне репозитория, его правила обязательны. Не меняйте файлы из раздела «Что нельзя трогать». Если шагу нужен ключ модели, а его нет, выполните проверки, которые возможны без ключа, и сообщите человеку, что осталось.

**Насколько проверен стартовый код.** Код из шагов 1.3, 1.4, 2.4 и 2.5 запускался на заглушках ядра (Python 3.13, FastAPI 0.162.4, uvicorn 0.54.0): эндпоинты отвечают, страница отправляет вопрос, фрагмент подсвечивается. Файл `compose.yaml` проверен командой `docker compose config`. С настоящим ядром, с моделью и в Docker-сборке код не запускался, правка ядра из шага 2.1 тоже. Поэтому проверки в шагах обязательны.

## Что строим

Веб-чат: пользователь задаёт юридический вопрос, получает ответ и может открыть документ и конкретный фрагмент, на который ответ опирается. Всё запускается одной Docker-командой.

Без работающего веб-чата команду не допускают к экспертной оценке, поэтому первый этап важнее всех остальных.

Что уже есть в репозитории:

| Термин | Что это |
|---|---|
| Ядро | Код в `prototype/`: загрузка документов, поиск, вызов модели, проверка ответа. Написано только на стандартной библиотеке Python. |
| Сабмит | ZIP с ядром для автоматической проверки на платформе. Собирается из `prototype/`. Веб в него не входит. |
| База знаний | `organizer/knowledge-base.zip`, 21 текстовый документ: законы и документы компании. |
| Фрагмент | Кусок документа с точными позициями начала и конца (`start`, `end`) в тексте документа. |
| Статус | Тип ответа ядра: `answer`, `partial`, `clarify`, `insufficient`, `out_of_scope`, `disallowed`, `unverified`, `technical_error`. |

Веб-интерфейса в репозитории нет совсем. Ядро умеет только читать CSV с вопросами и писать CSV с ответами.

## Этапы

| Этап | Результат | Что это даёт |
|---|---|---|
| 0. Подготовка | Репозиторий склонирован, тесты проходят, есть ключ модели | Можно начинать |
| 1. Каркас | Чат отвечает на вопрос, запуск одной командой | Допуск к экспертной оценке |
| 2. Источники | Клик по источнику открывает документ с подсвеченным фрагментом | Обязательное требование кейса |
| 3. Диалог и статусы | История, уточнения, отказы, ожидание, ошибки | Баллы за работоспособность и контроль достоверности |
| 4. Сдача | README, развёрнутая копия, проверка с нуля | Полный комплект материалов, без него не допустят |
| 5. Полировка | Статусы документов, примеры вопросов, внешний вид | Баллы за интерфейс и живое демо |

## Чек-лист прогресса

Этап 0
- [x] 0.1 Инструменты установлены
- [x] 0.2 Репозиторий склонирован, создана ветка
- [x] 0.3 Тесты ядра проходят
- [ ] 0.4 Создан `.env` с доступом к модели
- [x] 0.5 Прочитаны ключевые файлы
- [ ] 0.6 Задан вопрос организаторам

Этап 1
- [x] 1.1 Создан каталог `web/`
- [x] 1.2 Зависимости установлены и зафиксированы
- [x] 1.3 Написан `web/app.py`
- [x] 1.4 Написана страница чата
- [x] 1.5 Локальный запуск проходит проверку
- [x] 1.6 Добавлены файлы Docker
- [ ] 1.7 Запуск одной командой проходит проверку
- [ ] 1.8 Открыт PR

Этап 2
- [x] 2.1 Ядро возвращает структурированный ответ
- [x] 2.2 Добавлен тест, все тесты проходят
- [x] 2.3 Сабмит пересобран
- [x] 2.4 Бэкенд отдаёт источники и документы
- [x] 2.5 Страница показывает источники и документ
- [x] 2.6 Сценарий с источниками проходит проверку

Этап 3
- [x] 3.1 У каждого статуса свой вид
- [x] 3.2 Диалог и кнопка «Новый диалог»
- [x] 3.3 Ожидание, таймаут, повтор
- [ ] 3.4 Все сценарии из таблицы проходят

Этап 4
- [x] 4.1 README дополнен
- [x] 4.2 Обновлены `AGENTS.md` и ссылки
- [ ] 4.3 Проверка с нуля в чистом клоне
- [ ] 4.4 Развёрнута демо-копия
- [ ] 4.5 Секретов нет в репозитории, образе и логах
- [ ] 4.6 PR влит, CI зелёный
- [ ] 4.7 Материалы для презентации

## Решения по умолчанию

Эти решения уже приняты, чтобы не останавливаться на выборе. Менять можно, но только осознанно и для всех шагов сразу.

| Вопрос | Решение |
|---|---|
| Бэкенд | Python, FastAPI, сервер uvicorn |
| Фронт | Одна HTML-страница, обычный JavaScript и CSS. Без npm и сборки |
| Где лежит веб | Каталог `web/` в корне репозитория |
| Порт | 8000 |
| Docker | Отдельный `web/Dockerfile` на образе `python:3.13-slim`, файл `compose.yaml` в корне |
| База знаний | `organizer/knowledge-base.zip` подключается в контейнер как файл только для чтения |
| Доступ к модели | Переменные `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` в файле `.env` |
| История диалога | Хранится в браузере и целиком отправляется с каждым вопросом |
| Идентификатор документа в адресе | Хеш `sha256` файла (поле `Document.sha256`), а не имя файла |

## Что нельзя трогать

- `deploy/compose.yml`, корневой `Dockerfile`, корневой `.dockerignore`, каталоги `containers/`, `infra/`, `.github/`. Это пакетный запуск и проверки CI. Проверка CI требует, чтобы в `deploy/compose.yml` был ровно один сервис без портов.
- `organizer/`. Это материалы организаторов.
- `prototype/` меняется один раз, в шаге 2.1. Сторонние библиотеки туда не добавляйте: ядро должно остаться на стандартной библиотеке.
- В каталог `tests/` не кладите тесты, которым нужен FastAPI. CI запускает этот каталог без сторонних пакетов, и такой тест упадёт. Тесты веба кладите в `web/tests/`.
- Логики ответа в `web/` быть не должно. Веб только вызывает ядро и показывает результат.
- Ключи и пароли не должны попадать в репозиторий, образ, логи и браузер.
- В логи не пишутся вопросы, тексты документов и ответы модели. Это правило репозитория.
- Текст на страницу вставляется только через `textContent`. `innerHTML` не используется: в документах базы есть строки, похожие на команды.

## Этап 0. Подготовка

### 0.1 Инструменты

**Сделай.** Установи git, Python 3.11 или новее, Docker с Docker Compose.

**Проверь.** Все три команды печатают версию:

```bash
git --version
python3 --version
docker compose version
```

### 0.2 Репозиторий и ветка

**Сделай.**

```bash
git clone https://github.com/Moonwuk/grounded-legal-rag
cd grounded-legal-rag
git checkout -b web-chat
```

**Проверь.** `git status` показывает ветку `web-chat` и чистую рабочую копию.

### 0.3 Тесты ядра

**Сделай.** Запусти тесты до любых изменений. Ставить для этого ничего не нужно.

```bash
python3 -m unittest discover -s tests -v
```

**Проверь.** В конце вывода стоит `OK`. Если тесты падают до ваших правок, сообщите команде и не продолжайте.

### 0.4 Доступ к модели

**Сделай.** Возьми у тимлида адрес API, ключ и имя модели. Создай в корне репозитория файл `.env`:

```
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=сюда_ключ
LLM_MODEL=deepseek-flash
```

Адрес и имя модели здесь взяты из последнего прогона команды (`results/boundary_final_20261110T110952Z/run_manifest.json`). Уточни у тимлида, что они актуальны.

**Проверь.** `git status` не показывает файл `.env`: он уже внесён в `.gitignore`.

Если ключа пока нет, этапы 1 и 2 всё равно можно делать: без ключа чат отвечает сообщением о технической ошибке, а страницу и запуск проверить можно.

### 0.5 Что прочитать

**Сделай.** Прочитай четыре места, этого хватит для начала:

- `AGENTS.md`, разделы 1, 2 и 6: правила работы в репозитории.
- `prototype/solution.py`, функция `main`: как ядро создаётся и вызывается.
- `tests/test_baseline.py`, первые 40 строк: как импортировать ядро и как подменить модель заглушкой `ScriptedModel`.
- `prototype/psb_policy.py`, функции `render` и `answer_question`: как собирается текст ответа и откуда берутся номера источников `[1]`, `[2]`.

**Проверь.** Ты можешь ответить на три вопроса: какая функция возвращает ответ, что она принимает, что такое `Fragment.start` и `Fragment.end`.

Ответы для самопроверки: `answer_question(question, retriever, client, top_k)` возвращает пару `(текст, статус)`; `start` и `end` — позиции символов фрагмента в полном тексте документа `Document.text`.

### 0.6 Вопрос организаторам

**Сделай.** Спроси организаторов: как жюри будет запускать решение и откуда возьмёт доступ к модели. Прокси организаторов работает только на платформе, а ключ в репозиторий класть нельзя.

Этот шаг не блокирует работу. Ответ понадобится на этапе 4.

## Этап 1. Каркас

Цель: чат отвечает на вопрос текстом, всё поднимается одной командой. Источники пока не показываются.

### 1.1 Каталог

**Сделай.** Создай такую структуру:

```
web/
  __init__.py        (пустой файл)
  app.py
  requirements.txt
  Dockerfile
  Dockerfile.dockerignore
  static/
    index.html
    app.js
    style.css
compose.yaml         (в корне репозитория)
.env.example         (в корне репозитория)
```

### 1.2 Зависимости

**Сделай.**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn
pip freeze > web/requirements.txt
```

**Проверь.** В `web/requirements.txt` каждая строка имеет вид `имя==версия`. Каталог `.venv` не виден в `git status`.

### 1.3 Бэкенд

**Сделай.** Создай `web/app.py`:

```python
"""Веб-обёртка над ядром из prototype/. Логики ответа здесь нет, только HTTP."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "prototype"))  # ядро лежит плоскими модулями, как в tests/

from psb_corpus import load_corpus  # noqa: E402
from psb_llm import ProxyClient, integer  # noqa: E402
from psb_policy import TECHNICAL, answer_question  # noqa: E402
from psb_retrieval import Retriever  # noqa: E402

KB_PATH = Path(os.getenv("KB_PATH") or ROOT / "organizer" / "knowledge-base.zip")
STATIC = Path(__file__).resolve().parent / "static"
ANSWER_SECONDS = 150   # общий предел времени на один ответ
MAX_QUESTION = 30000   # ядро отклоняет вопросы длиннее 32 000 символов
LABELS = {"user": "Пользователь", "assistant": "Ассистент"}

documents, fragments = load_corpus(KB_PATH)  # один раз при старте
retriever = Retriever(documents, fragments)

app = FastAPI(title="Юридический ассистент")


class Message(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=10000)


class ChatRequest(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=40)


def to_question(messages: list[Message]) -> str:
    """Один вопрос уходит как есть, диалог — в формате тестов организаторов."""
    if len(messages) == 1:
        return messages[0].text.strip()
    return "\n".join(f"{LABELS[m.role]}: {m.text.strip()}" for m in messages)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "documents": len(documents), "fragments": len(fragments)}


@app.post("/api/chat")
def chat(request: ChatRequest):
    if request.messages[-1].role != "user":
        raise HTTPException(400, "Последнее сообщение должно быть от пользователя.")
    question = to_question(request.messages)
    if len(question) > MAX_QUESTION:
        raise HTTPException(413, "Диалог слишком длинный. Начните новый.")
    started = time.monotonic()
    try:
        client = ProxyClient(deadline=started + ANSWER_SECONDS)  # новый клиент на каждый вопрос
        text, status = answer_question(question, retriever, client,
                                       top_k=integer("TOP_K", 6, 1, 40))
    except Exception as error:  # нет ключа, сбой модели, предел поиска
        # В лог идёт только тип ошибки: без вопроса, текстов источников и ключей.
        print("question_error: " + type(error).__name__, file=sys.stderr)
        text, status = TECHNICAL, "technical_error"
    return {"status": status, "text": text, "sources": [],
            "elapsed_seconds": round(time.monotonic() - started, 1)}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
```

Что здесь важно понимать:

- Документы загружаются и индекс строится один раз при старте, а не на каждый вопрос.
- `ProxyClient` создаётся на каждый вопрос заново: у него лимит в четыре вызова модели.
- Функции объявлены через обычный `def`, а не `async def`. Тогда FastAPI выполняет их в отдельных потоках, и долгий ответ не блокирует сервер.

### 1.4 Страница

**Сделай.** Создай `web/static/index.html`:

```html
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Юридический ассистент</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <main>
    <section id="chat-pane">
      <div id="chat"></div>
      <form id="form">
        <textarea id="input" rows="3" placeholder="Задайте вопрос по документам базы" required></textarea>
        <button id="send">Отправить</button>
      </form>
    </section>
    <aside id="doc-pane">
      <h2 id="doc-title">Документ</h2>
      <div id="doc-text">Нажмите на источник под ответом, чтобы открыть документ.</div>
    </aside>
  </main>
  <script src="/static/app.js"></script>
</body>
</html>
```

`web/static/style.css`:

```css
body { margin: 0; font-family: system-ui, sans-serif; }
main { display: flex; height: 100vh; }
#chat-pane, #doc-pane { flex: 1; display: flex; flex-direction: column; padding: 16px; min-width: 0; }
#chat, #doc-text { flex: 1; overflow-y: auto; }
.message, #doc-text { white-space: pre-wrap; }   /* сохраняет переносы строк */
.message { margin: 8px 0; padding: 8px 12px; border-radius: 8px; background: #f2f2f2; }
.message.user { background: #dbeafe; }
mark { background: #fde68a; }
```

`web/static/app.js`:

```js
const chat = document.getElementById("chat");
const form = document.getElementById("form");
const input = document.getElementById("input");
const send = document.getElementById("send");
const messages = [];   // история диалога хранится только в браузере

function addMessage(role, text) {
  const node = document.createElement("div");
  node.className = "message " + role;
  node.textContent = text;   // только textContent, никогда innerHTML
  chat.append(node);
  node.scrollIntoView();
  return node;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  messages.push({role: "user", text});
  addMessage("user", text);
  input.value = "";
  send.disabled = true;
  const waiting = addMessage("assistant", "Ищу в документах и проверяю ответ. Обычно это занимает до минуты…");
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({messages}),
    });
    if (!response.ok) throw new Error("HTTP " + response.status);
    const answer = await response.json();
    waiting.textContent = answer.text;
    waiting.dataset.status = answer.status;
    if (answer.status === "technical_error") messages.pop();
    else messages.push({role: "assistant", text: answer.text});
  } catch (error) {
    waiting.textContent = "Не удалось получить ответ. Повторите запрос.";
    messages.pop();   // вопрос не засчитан, его можно отправить снова
  } finally {
    send.disabled = false;
  }
});
```

### 1.5 Локальный запуск

**Сделай.** Из корня репозитория:

```bash
source .venv/bin/activate
set -a; source .env; set +a
uvicorn web.app:app --port 8000 --reload --reload-dir web
```

**Проверь.**

1. В другом терминале `curl -s localhost:8000/healthz` возвращает `"status":"ok"` и `"documents":21`.
2. Страница `http://localhost:8000` открывается, видно поле ввода.
3. Задай вопрос: «Какая арендная плата по договору с ООО «Северный Склад» и до какого числа её нужно вносить?» В течение примерно минуты приходит ответ. Ожидаемое содержание: цитаты пунктов 3.1 (450 000 рублей в месяц) и 3.2 (не позднее 5-го числа) договора аренды.
4. Без ключа вместо ответа приходит «Не удалось проверить ответ из-за технической ошибки…», а в терминале сервера появляется `question_error: ProviderError`. Это правильное поведение без ключа.

В последнем прогоне команды один ответ занимал около 40 секунд. Это нормально.

### 1.6 Файлы Docker

**Сделай.** Создай `web/Dockerfile`:

```dockerfile
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv
COPY web/requirements.txt web/requirements.txt
RUN pip install --no-cache-dir -r web/requirements.txt
COPY prototype/ prototype/
COPY web/ web/
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

Создай `web/Dockerfile.dockerignore`. Он нужен потому, что корневой `.dockerignore` пропускает в сборку только пакетный код, и без отдельного файла Docker не увидит каталог `web/`:

```
**
!prototype/
!prototype/*.py
!web/
!web/**
**/__pycache__
```

Создай в корне `compose.yaml`:

```yaml
name: psb-web

services:
  web:
    build:
      context: .
      dockerfile: web/Dockerfile
    ports:
      - "${WEB_BIND:-127.0.0.1}:${WEB_PORT:-8000}:8000"
    environment:
      LLM_BASE_URL: ${LLM_BASE_URL:?Заполните LLM_BASE_URL в файле .env}
      LLM_API_KEY: ${LLM_API_KEY:?Заполните LLM_API_KEY в файле .env}
      LLM_MODEL: ${LLM_MODEL:?Заполните LLM_MODEL в файле .env}
      KB_PATH: /data/knowledge-base.zip
    volumes:
      - ./organizer/knowledge-base.zip:/data/knowledge-base.zip:ro
    read_only: true
    tmpfs:
      - /tmp
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true
    restart: unless-stopped
```

Создай в корне `.env.example`:

```
# Скопируйте этот файл в .env и заполните. Файл .env в репозиторий не попадает.
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
WEB_PORT=8000
WEB_BIND=127.0.0.1
```

### 1.7 Запуск одной командой

**Сделай.** Останови локальный сервер из шага 1.5 и выполни:

```bash
docker compose up --build
```

**Проверь.** Повтори все четыре проверки из шага 1.5, теперь через Docker. Остановка: `Ctrl+C`, затем `docker compose down`.

Если сборка падает с ошибкой вида `"/web/requirements.txt": not found`, файл `web/Dockerfile.dockerignore` не подхватился. Проверь его имя и расположение. Если не помогает, обсуди с командой добавление тех же строк в корневой `.dockerignore`.

### 1.8 PR

**Сделай.**

```bash
git add web compose.yaml .env.example docs/web_roadmap.md
git commit -m "Add web chat skeleton"
git push -u origin web-chat
```

Открой PR в `main` на GitHub. Его можно пометить как черновик.

**Проверь.** На странице PR запустились проверки `Security scans`. Дождись результата и разберись с красными сейчас, а не в последний день.

**Этап 1 готов, когда** чат поднимается командой `docker compose up --build` и отвечает на вопрос.

## Этап 2. Источники

Цель: под ответом видны источники, клик открывает документ и подсвечивает фрагмент.

Сейчас ядро возвращает только готовый текст. Источники в нём записаны строками вида `[1] Название: «цитата».` Для клика нужны данные: какой документ и какие позиции. Их надо достать из ядра.

### 2.1 Структурированный ответ в ядре

Это единственная правка в `prototype/`. Согласуй её с тем, кто ведёт ядро.

**Сделай.** В файле `prototype/psb_policy.py`:

1. Добавь перед `answer_question` новую функцию:

```python
def cited_fragments(candidate: dict, evidence: list[Fragment]) -> list[Fragment]:
    """Фрагменты в том же порядке, в каком render() раздаёт номера [1], [2], …"""
    if candidate.get("status") not in {"answer", "partial"}:
        return []
    by_id = {f.id: f for f in evidence}
    result = {}
    for claim in candidate["claims"]:
        for cite in claim["sources"]:
            result.setdefault(cite["fragment_id"], by_id[cite["fragment_id"]])
    return list(result.values())
```

2. Переименуй существующую `answer_question` в `answer_structured` и поменяй тип результата на `dict`. Тело функции не трогай, замени только пять мест, где она возвращает или запоминает результат:

| Было | Стало |
|---|---|
| `return TECHNICAL, "technical_error"` (в начале функции) | `return {"text": TECHNICAL, "status": "technical_error", "sources": []}` |
| `fallback = (rendered, "partial")` | `fallback = {"text": rendered, "status": "partial", "sources": cited_fragments(candidate, evidence)}` |
| `return rendered, candidate["status"]` | `return {"text": rendered, "status": candidate["status"], "sources": cited_fragments(candidate, evidence)}` |
| `return fallback or (UNVERIFIED, "unverified")` | `return fallback or {"text": UNVERIFIED, "status": "unverified", "sources": []}` |
| `return fallback or (TECHNICAL, "technical_error")` | `return fallback or {"text": TECHNICAL, "status": "technical_error", "sources": []}` |

3. Добавь после неё новую `answer_question` с прежним именем и прежним результатом, чтобы сабмит и тесты работали как раньше:

```python
def answer_question(question: str, retriever, client, top_k: int = 6) -> tuple[str, str]:
    result = answer_structured(question, retriever, client, top_k)
    return result["text"], result["status"]
```

**Проверь.** `python3 -m unittest discover -s tests -v` по-прежнему заканчивается на `OK`.

### 2.2 Тест

**Сделай.** В `tests/test_baseline.py` добавь `answer_structured` в строку импорта из `psb_policy` и новый тест в класс `BaselineTests`. Образец рядом: `test_pipeline_renders_only_cited_claims`.

```python
    def test_structured_answer_keeps_text_and_numbering(self):
        question='Арендная плата Северный Склад'
        result=answer_structured(question,self.r,ScriptedModel([draft,VERDICT]))
        text,status=answer_question(question,self.r,ScriptedModel([draft,VERDICT]))
        self.assertEqual((result['text'],result['status']),(text,status))
        count=len(result['sources'])
        self.assertGreaterEqual(count,1)
        self.assertIn(f'[{count}]',text)
        self.assertNotIn(f'[{count+1}]',text)
        for f in result['sources']:
            self.assertEqual(f.text,self.r.documents[f.document].text[f.start:f.end])
```

Тест проверяет три вещи: текст и статус не изменились, число источников совпадает с номерами в тексте, позиции фрагмента точно указывают на его текст в документе.

**Проверь.** Все тесты проходят, включая новый.

### 2.3 Пересборка сабмита

CI сверяет ZIP сабмита с файлами в `prototype/` побайтно. После правки ядра архив надо пересобрать.

**Сделай.**

```bash
python3 build_submission.py
python3 .github/scripts/check_submission.py
git status
```

**Проверь.** Вторая команда печатает строку, начинающуюся с `Submission: six root files`. В `git status` изменены только `prototype/psb_policy.py`, `tests/test_baseline.py`, `dist/PSB_baseline_submission.zip` и `results/submission_manifest.json`. Закоммить их отдельным коммитом.

### 2.4 Бэкенд: источники и документы

**Сделай.** В `web/app.py`:

1. Замени в импорте `answer_question` на `answer_structured`.

2. После строки `retriever = Retriever(documents, fragments)` добавь:

```python
BY_ID = {d.sha256: d for d in documents}
BY_NAME = {d.name: d for d in documents}
```

3. Добавь после `to_question` две функции:

```python
def describe(doc) -> dict:
    """Название, категория и статус из имени файла. Только для показа, не для логики ответа."""
    category, _, title = doc.name.partition("__")
    if not title:
        category, title = "", doc.name
    for suffix in (".txt", ".md", ".docx"):
        title = title.removesuffix(suffix)
    title = title.replace("_", " ")
    lowered = title.lower()
    status = ("утратил силу" if "утратил силу" in lowered
              else "действующая редакция" if lowered.endswith("действующая") else "")
    return {"id": doc.sha256, "title": title, "category": category, "status": status}


def source_json(number: int, fragment) -> dict:
    doc = BY_NAME[fragment.document]
    return {"n": number, "document_id": doc.sha256, "title": describe(doc)["title"],
            "heading": fragment.heading, "start": fragment.start, "end": fragment.end,
            "quote": fragment.text}
```

4. В функции `chat` замени блок от `try:` до конца функции на:

```python
    try:
        client = ProxyClient(deadline=started + ANSWER_SECONDS)
        result = answer_structured(question, retriever, client, top_k=integer("TOP_K", 6, 1, 40))
    except Exception as error:
        print("question_error: " + type(error).__name__, file=sys.stderr)
        result = {"text": TECHNICAL, "status": "technical_error", "sources": []}
    return {"status": result["status"], "text": result["text"],
            "sources": [source_json(i, f) for i, f in enumerate(result["sources"], 1)],
            "elapsed_seconds": round(time.monotonic() - started, 1)}
```

5. Добавь два эндпоинта перед функцией `index`:

```python
@app.get("/api/documents")
def list_documents():
    return [describe(d) for d in documents]


@app.get("/api/documents/{doc_id}")
def get_document(doc_id: str):
    doc = BY_ID.get(doc_id)  # поиск по словарю, а не подстановка в путь файла
    if doc is None:
        raise HTTPException(404, "Документ не найден.")
    return {**describe(doc), "text": doc.text}
```

**Проверь.** `curl -s localhost:8000/api/documents` возвращает список из 21 документа. У регламента 2023 года поле `status` равно `утратил силу`.

### 2.5 Страница: источники и документ

**Сделай.** В `web/static/app.js` добавь две функции перед обработчиком формы:

```js
async function showSource(source) {
  const response = await fetch("/api/documents/" + source.document_id);
  if (!response.ok) return;
  const doc = await response.json();
  // Позиции start и end считаются в символах Юникода, как в Python.
  // Array.from делит строку так же; обычный slice ошибся бы на редких символах.
  const chars = Array.from(doc.text);
  const mark = document.createElement("mark");
  mark.textContent = chars.slice(source.start, source.end).join("");
  const panel = document.getElementById("doc-text");
  panel.textContent = "";
  panel.append(chars.slice(0, source.start).join(""), mark, chars.slice(source.end).join(""));
  document.getElementById("doc-title").textContent =
    doc.title + (doc.status ? " (" + doc.status + ")" : "");
  mark.scrollIntoView({block: "center"});
}

function addSources(node, sources) {
  for (const source of sources) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "source";
    button.textContent = "[" + source.n + "] " + source.title;
    button.addEventListener("click", () => showSource(source));
    node.append(document.createElement("br"), button);
  }
}
```

В обработчике формы после строки `waiting.dataset.status = answer.status;` добавь:

```js
    addSources(waiting, answer.sources);
```

Текст документа показывай как есть. Не обрезай пробелы и не меняй переносы строк, иначе позиции съедут.

### 2.6 Проверка этапа

**Проверь.** Перезапусти сервер и задай вопрос про аренду из шага 1.5.

1. Под ответом появились кнопки источников `[1] …`.
2. Клик по кнопке открывает справа договор аренды, страница прокручена к подсвеченному фрагменту.
3. Подсвеченный текст дословно совпадает с цитатой в ответе под тем же номером.
4. В заголовке панели видно название документа.

Закоммить и отправь в PR.

**Этап 2 готов, когда** на любом ответе со статусом `answer` каждая кнопка источника открывает нужный документ на нужном месте.

## Этап 3. Диалог и статусы

Цель: интерфейс правильно ведёт себя не только на удачном ответе.

### 3.1 Вид для каждого статуса

**Сделай.** У сообщения уже есть атрибут `data-status`. Добавь над текстом ответа короткую подпись и стиль в CSS, например `.message[data-status="insufficient"] { … }`.

| Статус | Подпись | Что ещё сделать |
|---|---|---|
| `answer` | не нужна | Показать источники |
| `partial` | «Подтверждена только часть ответа» | Показать источники |
| `clarify` | «Нужно уточнение» | Поставить курсор в поле ввода |
| `insufficient` | «В базе нет оснований для ответа» | — |
| `out_of_scope` | «Вопрос вне юридической тематики» | — |
| `disallowed` | «Запрос отклонён» | — |
| `unverified` | «Ответ не прошёл проверку» | Предложить уточнить вопрос |
| `technical_error` | «Техническая ошибка» | Кнопка «Повторить», в историю не добавлять |

Техническая ошибка не должна выглядеть как «в базе нет сведений». Это разные ситуации.

### 3.2 Диалог

**Сделай.**

- Добавь кнопку «Новый диалог»: она очищает массив `messages` и ленту сообщений.
- Если бэкенд вернул код 413, покажи текст «Диалог слишком длинный. Начните новый.»
- По желанию: вместо ошибки 413 отбрасывай в `to_question` самые старые пары «вопрос — ответ», пока строка не уложится в `MAX_QUESTION`. Последний вопрос пользователя отбрасывать нельзя.

**Проверь.** Диалог из трёх реплик: «Какой гарантийный срок на товар по договору с ООО «Альфа-Трейд»?», затем после ответа «А за сколько дней после поставки нужно проверить качество?». Второй ответ относится к тому же договору, хотя договор во втором вопросе не назван.

### 3.3 Ожидание и ошибки

**Сделай.**

- Пока идёт запрос, кнопка отправки выключена (уже сделано) и видно, что идёт работа: например, счётчик секунд в сообщении ожидания.
- Ограничь ожидание на стороне браузера через `AbortController`, предел 180 секунд. По истечении покажи сообщение и кнопку «Повторить».
- Кнопка «Повторить» отправляет тот же вопрос ещё раз.

**Проверь.** Останови сервер во время ожидания ответа: на странице появляется понятное сообщение, кнопка отправки снова работает.

### 3.4 Сценарии

**Проверь.** Пройди все строки. Ожидаемый статус зависит от модели, поэтому смотри в первую очередь на то, что интерфейс показывает статус правильно.

| Что ввести | Чего ждать |
|---|---|
| Вопрос про аренду из шага 1.5 | `answer`, источники открываются |
| «Какой размер пособия по беременности и родам?» | `insufficient`: в базе нет такого документа |
| «Какая завтра погода в Москве?» | `out_of_scope` |
| «Какой гарантийный срок по договору?» | `clarify` или ответ с оговоркой: договор не назван |
| «Договор на 12 млн рублей заключали в августе 2024 года. Нужно ли было одобрение генерального директора?» | Источник — редакция регламента от 10.01.2023 (действовала до 01.03.2025), а не редакция 2025 года |
| «По договору с «Альфа-Трейдинг» можем оплатить технику авансом или только после поставки?» | Источник — договор ПТ-05-2023 с «Альфа-Трейдинг», а не П-17-2024 с «Альфа-Трейд» |
| Диалог из шага 3.2 | Второй ответ учитывает первый вопрос |
| Любой вопрос с неверным ключом в `.env` | `technical_error`, кнопка «Повторить» |

Если статус или источник выглядит неверно, это вопрос к ядру, а не к вебу. Запиши вопрос и ответ и передай владельцу ядра.

**Этап 3 готов, когда** все строки таблицы пройдены и ни в одном сценарии страница не зависает и не показывает пустой ответ.

## Этап 4. Сдача

Цель: жюри может запустить и проверить решение без помощи команды.

### 4.1 README

**Сделай.** Добавь в корневой `README.md` раздел «Веб-интерфейс». Кейс требует, чтобы в README были:

- назначение и архитектура: веб вызывает то же ядро, что и сабмит;
- запуск: `cp .env.example .env`, заполнить три переменные, `docker compose up --build`, открыть `http://localhost:8000`;
- переменные окружения: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `WEB_PORT`, `WEB_BIND`;
- какой сервис и какая модель используются и как подключить ключ;
- порт;
- зависимости: `web/requirements.txt`;
- порядок проверки основного сценария: вопрос, ответ, клик по источнику, подсвеченный фрагмент;
- известные ограничения: время ответа, история хранится только в браузере, нет входа по паролю.

Исправь в начале README фразу о том, что веб-интерфейса нет.

### 4.2 Навигация репозитория

**Сделай.** По правилам `AGENTS.md` новый компонент добавляется в карту в разделе 1. Добавь строку про веб: файлы `web/app.py`, `web/static/`, `compose.yaml`, документ `docs/web_roadmap.md`. Добавь ссылку на этот роадмап из README.

### 4.3 Проверка с нуля

**Сделай.** Склонируй репозиторий в новый пустой каталог, переключись на свою ветку, создай `.env` и выполни только то, что написано в README.

**Проверь.** Чат поднялся и основной сценарий проходит. Лучше всего, если это сделает человек, который не участвовал в разработке.

### 4.4 Демо-копия

**Сделай.** На сервере с Docker: склонируй репозиторий, создай `.env` с ключом и строкой `WEB_BIND=0.0.0.0`, выполни `docker compose up -d --build`. Ссылку на развёрнутый интерфейс команда ставит на первый слайд презентации.

Открытая ссылка означает, что любой, кто её знает, тратит ваш ключ модели. Реши с командой, как ограничить доступ: пароль на обратном прокси или ссылка только для жюри.

**Проверь.** Основной сценарий проходит по ссылке с другого устройства.

### 4.5 Секреты

**Проверь.**

- `git status` и `git log -p` не содержат ключа.
- В `.env.example` нет настоящих значений.
- В логах контейнера (`docker compose logs`) нет ключа, вопросов и текстов документов.
- В инструментах разработчика браузера, во вкладке «Сеть», ключ нигде не виден.

### 4.6 PR

**Сделай.** Дождись зелёных проверок, попроси ревью, влей PR в `main`.

**Проверь.** На `main` после слияния проверки `Security scans` зелёные.

### 4.7 Презентация

**Сделай.** Передай тому, кто готовит презентацию: скриншот ответа с открытым источником, скриншот обоснованного отказа, скриншот уточняющего вопроса, команду запуска и ссылку на демо-копию.

**Этап 4 готов, когда** чистый клон поднимается по README, демо-копия доступна по ссылке и PR влит.

## Этап 5. Полировка

Делается только после этапа 4. В порядке убывания пользы:

1. Метка статуса документа («действующая редакция», «утратил силу») прямо на кнопке источника. Данные уже приходят в `/api/documents`.
2. Примеры вопросов на пустом экране. Возьми удачные сценарии из шага 3.4.
3. Время ответа под сообщением: поле `elapsed_seconds` уже приходит с бэкенда.
4. Список всех документов базы с открытием по клику: эндпоинт `/api/documents` уже есть.
5. Кликабельные номера `[1]` прямо в тексте ответа.
6. Внешний вид и узкие экраны.

## Если что-то не работает

| Симптом | Причина | Что делать |
|---|---|---|
| `ModuleNotFoundError: No module named 'psb_corpus'` | Сервер запущен не из корня репозитория или удалена строка с `sys.path` | Запускай `uvicorn` из корня репозитория |
| Каждый ответ — «техническая ошибка», в логе `question_error: ProviderError` | Не заданы переменные `LLM_*` | Проверь `.env` и то, что переменные загружены: `echo $LLM_MODEL` |
| В логе `provider_error: http_401` | Неверный ключ | Попроси актуальный ключ |
| В логе `provider_error: http_404` | Неверный адрес API или имя модели | Сверь `LLM_BASE_URL` и `LLM_MODEL` с тимлидом |
| В логе `provider_failure` со словом `timeout` | Модель или сеть не отвечают | Проверь доступ к API с этой машины, повтори позже |
| `required variable LLM_API_KEY is missing a value` при `docker compose up` | Не заполнен `.env` | Заполни три переменные |
| `"/web/requirements.txt": not found` при сборке | Не подхватился `web/Dockerfile.dockerignore` | См. конец шага 1.7 |
| `port is already allocated` | Порт 8000 занят | Добавь в `.env` строку `WEB_PORT=8001` |
| Подсветка съехала относительно цитаты | Текст документа изменён перед показом или использован `slice` по строке | Показывай текст как есть и режь через `Array.from` |
| После правки ядра CI красный на шаге сборки сабмита | Не пересобран архив | Повтори шаг 2.3 |
| Тест в `tests/` падает в CI с `No module named 'fastapi'` | Тест веба лежит в `tests/` | Перенеси его в `web/tests/` |

## Если времени не хватает

Отказывайся в таком порядке, сверху вниз:

1. Весь этап 5.
2. Шаг 3.3, кроме выключенной кнопки отправки.
3. Отдельные подписи для редких статусов `disallowed` и `unverified`.
4. Подсветка фрагмента в полном тексте: оставь кнопку источника, которая показывает цитату.
5. Демо-копия, если организаторы подтвердят, что проверяют локально.

Нельзя отказываться от запуска одной командой, работающего основного сценария, просмотра документа и README.

## Вопросы к команде

Работу они не блокируют, но ответы нужны до этапа 4.

- Как жюри получит доступ к модели (шаг 0.6).
- Кто отвечает за ядро и согласует правку из шага 2.1.
- Где разворачивать демо-копию и кто следит за ней во время защиты.
- Добавлять ли каталог `web/` в проверки CI (Bandit, сканирование образа). Сейчас CI проверяет код веба только через CodeQL и поиск секретов.
