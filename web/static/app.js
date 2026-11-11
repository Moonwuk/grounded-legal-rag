"use strict";

const byId = id => document.getElementById(id);
const log = byId("conversation");
const input = byId("question");
const send = byId("send");
const reset = byId("reset");
const welcome = byId("welcome");
const list = byId("doc-list");
const docText = byId("doc-text");
const docTitle = byId("doc-title");
const docStatus = byId("doc-status");
const allDocs = byId("all-docs");
const labels = {
  partial: "Подтверждена часть ответа",
  clarify: "Нужно уточнение",
  insufficient: "Недостаточно оснований",
  out_of_scope: "Вопрос вне юридической тематики",
  disallowed: "Запрос отклонён",
  unverified: "Ответ не прошёл проверку",
  technical_error: "Техническая ошибка"
};

let messages = [];
let busy = false;
let activeDocument;

function bubble(role, text) {
  welcome.hidden = true;
  const item = document.createElement("article");
  item.className = "message " + role;
  const author = document.createElement("strong");
  author.textContent = role === "user" ? "Вы" : "Ассистент";
  const content = document.createElement("p");
  content.textContent = text;
  item.append(author, content);
  log.append(item);
  log.scrollTop = log.scrollHeight;
  return {item, content};
}

function showList() {
  activeDocument?.abort();
  docTitle.textContent = "Документы";
  docStatus.textContent = "";
  docText.hidden = true;
  list.hidden = false;
  allDocs.hidden = true;
}

async function openDocument(id, source) {
  activeDocument?.abort();
  const request = new AbortController();
  activeDocument = request;
  const timer = setTimeout(() => request.abort(), 10000);
  docStatus.textContent = "Открываем документ…";
  try {
    const response = await fetch("/api/documents/" + encodeURIComponent(id), {signal: request.signal});
    if (!response.ok) throw new Error();
    const doc = await response.json();
    if (activeDocument !== request) return;
    docTitle.textContent = doc.title;
    docStatus.textContent = [doc.status, source?.heading].filter(Boolean).join(" · ");
    docText.textContent = doc.text;
    list.hidden = true;
    docText.hidden = false;
    allDocs.hidden = false;
    docTitle.focus();
    if (source) {
      const characters = Array.from(doc.text);
      const quote = characters.slice(source.start, source.end).join("");
      if (quote !== source.quote) {
        docStatus.textContent = "Диапазон источника изменился. Показан полный документ.";
        return;
      }
      const mark = document.createElement("mark");
      mark.textContent = quote;
      docText.replaceChildren(characters.slice(0, source.start).join(""), mark, characters.slice(source.end).join(""));
      mark.scrollIntoView({block: "center"});
    } else {
      docText.scrollTop = 0;
    }
  } catch {
    if (activeDocument === request) docStatus.textContent = "Документ недоступен. Откройте его повторно.";
  } finally {
    clearTimeout(timer);
  }
}

async function loadDocuments() {
  try {
    const response = await fetch("/api/documents", {signal: AbortSignal.timeout(10000)});
    if (!response.ok) throw new Error();
    const docs = await response.json();
    for (const doc of docs) {
      const row = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = doc.title + (doc.status ? " · " + doc.status : "");
      button.addEventListener("click", () => openDocument(doc.id));
      row.append(button);
      list.append(row);
    }
  } catch {
    docStatus.textContent = "Список документов недоступен. Обновите страницу.";
  }
}

function renderAnswer(node, answer, retry) {
  node.item.dataset.status = answer.status;
  node.content.textContent = answer.text;
  if (labels[answer.status]) {
    const status = document.createElement("strong");
    status.textContent = labels[answer.status];
    node.content.before(status);
  }
  for (const source of answer.sources || []) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "source";
    button.textContent = ["[" + source.n + "] " + source.title, source.heading, source.status].filter(Boolean).join(" · ");
    button.addEventListener("click", () => openDocument(source.document_id, source));
    node.item.append(button);
  }
  if (answer.status === "technical_error") {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Повторить";
    button.addEventListener("click", retry);
    node.item.append(button);
  } else if (Number.isFinite(answer.elapsed_seconds)) {
    const duration = document.createElement("small");
    duration.textContent = new Intl.NumberFormat("ru-RU").format(answer.elapsed_seconds) + " с";
    node.item.append(duration);
  }
}

async function ask(question, existing) {
  if (busy) return;
  busy = true;
  send.disabled = reset.disabled = true;
  const pending = {role: "user", text: question};
  const userNode = existing || bubble("user", question).item;
  const node = bubble("assistant", "Готовим ответ…");
  const start = performance.now();
  const timer = setInterval(() => {
    node.content.textContent = "Готовим ответ… " + Math.floor((performance.now() - start) / 1000) + " с";
  }, 1000);
  let answer;
  try {
    const response = await fetch("/api/chat", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({messages: [...messages, pending]}),
      signal: AbortSignal.timeout(180000)
    });
    if (!response.ok) {
      const detail = response.status === 413 ? "Диалог слишком длинный. Начните новый." : "Сервис не ответил. Попробуйте снова.";
      answer = {status: "technical_error", text: detail};
    } else {
      answer = await response.json();
    }
  } catch (error) {
    answer = {status: "technical_error", text: error.name === "TimeoutError"
      ? "Истекло время ожидания. Повторите запрос." : "Нет связи с сервисом. Проверьте подключение и повторите запрос."};
  } finally {
    clearInterval(timer);
    busy = false;
    send.disabled = reset.disabled = false;
  }
  if (answer.status !== "technical_error") {
    messages.push(pending, {role: "assistant", text: answer.text});
  }
  const historyLength = messages.length;
  renderAnswer(node, answer, () => {
    if (busy) return;
    if (messages.length !== historyLength) {
      input.value = question;
      input.focus();
      return;
    }
    node.item.remove();
    ask(question, userNode);
  });
  input.focus();
  log.scrollTop = log.scrollHeight;
}

byId("chat-form").addEventListener("submit", event => {
  event.preventDefault();
  if (busy) return;
  const question = input.value.trim();
  byId("input-error").textContent = question ? "" : "Введите вопрос.";
  if (!question) {
    input.setAttribute("aria-invalid", "true");
    input.focus();
    return;
  }
  input.removeAttribute("aria-invalid");
  input.value = "";
  ask(question);
});
reset.addEventListener("click", () => {
  messages = [];
  log.replaceChildren(welcome);
  welcome.hidden = false;
  input.value = "";
  input.removeAttribute("aria-invalid");
  byId("input-error").textContent = "";
  showList();
  input.focus();
});
allDocs.addEventListener("click", () => { showList(); docTitle.focus(); });
for (const example of document.querySelectorAll(".example")) {
  example.addEventListener("click", () => { input.value = example.textContent; input.focus(); });
  example.disabled = false;
}
reset.disabled = false;
allDocs.disabled = false;
loadDocuments();
