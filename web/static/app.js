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
const quoteTools = byId("quote-tools");
const docFilter = byId("doc-filter");
const docQuery = byId("doc-query");
const clearDocQuery = byId("clear-doc-query");
let selectedQuote = "";
const copyController = MatteCopy.mount(quoteTools.querySelector(".sl-copy"), {
  getText: () => selectedQuote,
  feedback: quoteTools.querySelector(".copy-feedback")
});
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
let catalog = [];

function bubble(role, text) {
  welcome.hidden = true;
  const item = document.createElement("article");
  item.className = "message " + role;
  const author = document.createElement("strong");
  author.textContent = role === "user" ? "Вы" : "Ассистент";
  const content = document.createElement("p");
  const body = document.createElement("div");
  body.className = "message-body";
  content.textContent = text;
  body.append(content);
  item.append(author, body);
  log.append(item);
  log.scrollTop = log.scrollHeight;
  return {item, content, body};
}

function showList() {
  activeDocument?.abort();
  activeDocument = null;
  clearQuote();
  docTitle.textContent = "Документы";
  docStatus.textContent = "";
  docText.hidden = true;
  list.hidden = false;
  docFilter.hidden = catalog.length === 0;
  allDocs.hidden = true;
  renderCatalog();
}

function clearQuote() {
  selectedQuote = "";
  quoteTools.hidden = true;
  copyController.reset();
}

async function openDocument(id, source, focus = true) {
  activeDocument?.abort();
  clearQuote();
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
    docFilter.hidden = true;
    docText.hidden = false;
    allDocs.hidden = false;
    if (focus) docTitle.focus();
    if (source) {
      const characters = Array.from(doc.text);
      const quote = characters.slice(source.start, source.end).join("");
      if (quote !== source.quote) {
        docStatus.textContent = "Диапазон источника изменился. Показан полный документ.";
        return;
      }
      const mark = document.createElement("mark");
      mark.textContent = quote;
      selectedQuote = quote;
      quoteTools.hidden = false;
      docText.replaceChildren(characters.slice(0, source.start).join(""), mark, characters.slice(source.end).join(""));
      docText.scrollTop += mark.getBoundingClientRect().top - docText.getBoundingClientRect().top
        - docText.clientHeight / 2 + mark.offsetHeight / 2;
    } else {
      docText.scrollTop = 0;
    }
  } catch {
    if (activeDocument === request) docStatus.textContent = "Документ недоступен. Откройте его повторно.";
  } finally {
    clearTimeout(timer);
  }
}

function renderCatalog() {
  const query = docQuery.value.trim().toLocaleLowerCase("ru");
  clearDocQuery.hidden = !docQuery.value;
  list.replaceChildren();
  if (!catalog.length) return;
  const matching = catalog.filter(doc => doc.title.toLocaleLowerCase("ru").includes(query));
  for (const doc of matching) {
    const row = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    const title = document.createElement("span");
    title.className = "catalog-title";
    title.textContent = doc.title;
    const meta = document.createElement("small");
    meta.textContent = doc.status || doc.category;
    button.append(title, meta);
    button.addEventListener("click", () => openDocument(doc.id));
    row.append(button);
    list.append(row);
  }
  docStatus.textContent = matching.length ? "Документов: " + matching.length : "По этому запросу документов нет.";
}

async function loadDocuments() {
  try {
    const response = await fetch("/api/documents", {signal: AbortSignal.timeout(10000)});
    if (!response.ok) throw new Error();
    catalog = await response.json();
    docFilter.hidden = !catalog.length;
    renderCatalog();
  } catch {
    docStatus.textContent = "Список документов недоступен. Обновите страницу.";
  }
}

function renderAnswer(node, answer, retry) {
  node.item.dataset.status = answer.status;
  const missingModel = answer.error_code === "model_not_configured";
  const sources = answer.sources || [];
  const sourcesByNumber = new Map(sources.map(source => [String(source.n), source]));
  const parts = answer.text.split(/\[(\d+)\]/);
  node.content.replaceChildren(parts[0]);
  for (let index = 1; index < parts.length; index += 2) {
    const number = parts[index];
    const label = "[" + number + "]";
    const source = sourcesByNumber.get(number);
    if (source) {
      const link = document.createElement("a");
      link.className = "inline-citation";
      link.href = "#doc-title";
      link.textContent = label;
      link.setAttribute("aria-label", label + " Источник: " + source.title);
      link.addEventListener("click", event => {
        event.preventDefault();
        openDocument(source.document_id, source);
      });
      node.content.append(link);
    } else {
      node.content.append(label);
    }
    node.content.append(parts[index + 1]);
  }
  if (labels[answer.status] || sources.length) {
    const status = document.createElement("strong");
    status.className = "message-status";
    status.textContent = missingModel ? "Модель не настроена" : labels[answer.status] || "Найдены источники";
    node.content.before(status);
  }
  for (const source of sources) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "source";
    button.textContent = ["[" + source.n + "] " + source.title, source.heading, source.status].filter(Boolean).join(" · ");
    button.addEventListener("click", () => openDocument(source.document_id, source));
    node.body.append(button);
  }
  if (answer.status === "technical_error" && !missingModel) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Повторить";
    button.addEventListener("click", retry);
    node.body.append(button);
  } else if (answer.status !== "technical_error" && Number.isFinite(answer.elapsed_seconds)) {
    const duration = document.createElement("small");
    duration.textContent = new Intl.NumberFormat("ru-RU").format(answer.elapsed_seconds) + " с";
    node.body.append(duration);
  }
}

async function ask(question, existing, signal) {
  busy = true;
  reset.disabled = true;
  const pending = {role: "user", text: question};
  const userNode = existing || bubble("user", question).item;
  const node = bubble("assistant", "Ищем в документах…");
  const documentAtStart = activeDocument;
  const scene = ArchiveScene.create();
  const progress = document.createElement("small");
  progress.textContent = "Подбираем подтверждающие положения";
  progress.setAttribute("aria-hidden", "true");
  node.body.append(progress);
  node.body.before(scene);
  node.item.classList.add("with-scene");
  node.item.dataset.status = "searching";
  log.scrollTop = log.scrollHeight;
  const start = performance.now();
  const timer = setInterval(() => {
    progress.textContent = "Подбираем подтверждающие положения · " + Math.floor((performance.now() - start) / 1000) + " с";
  }, 1000);
  let answer;
  try {
    const response = await fetch("/api/chat", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({messages: [...messages, pending]}),
      signal: AbortSignal.any([signal, AbortSignal.timeout(180000)])
    });
    if (!response.ok) {
      const detail = response.status === 413 ? "Диалог слишком длинный. Начните новый." : "Сервис не ответил. Попробуйте снова.";
      answer = {status: "technical_error", text: detail};
    } else {
      answer = await response.json();
    }
  } catch (error) {
    if (signal.aborted) {
      node.item.remove();
      userNode.remove();
      if (!log.querySelector(".message")) welcome.hidden = false;
      if (!input.value) input.value = question;
      input.focus();
      throw error;
    }
    answer = {status: "technical_error", text: error.name === "TimeoutError"
      ? "Истекло время ожидания. Повторите запрос." : "Нет связи с сервисом. Проверьте подключение и повторите запрос."};
  } finally {
    clearInterval(timer);
    busy = false;
    reset.disabled = false;
  }
  scene.dataset.state = ArchiveScene.stateFor(answer);
  progress.remove();
  if (answer.status !== "technical_error" && answer.sources?.length) {
    if (activeDocument === documentAtStart && docText.hidden) {
      const first = answer.sources[0];
      openDocument(first.document_id, first, false);
    }
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
    retryRequest = {question, userNode};
    node.item.remove();
    sendController.start();
  });
  input.focus();
  log.scrollTop = log.scrollHeight;
  if (answer.status === "technical_error") throw new Error("chat_request_failed");
}

let retryRequest;
const sendController = SLComponent.mount(send.closest(".sl-component"), {
  async onSend({signal}) {
    const retry = retryRequest;
    retryRequest = null;
    const question = retry?.question || input.value.trim();
    byId("input-error").textContent = question ? "" : "Введите вопрос.";
    if (!question) {
      input.setAttribute("aria-invalid", "true");
      input.focus();
      throw new Error("empty_question");
    }
    input.removeAttribute("aria-invalid");
    if (!retry) input.value = "";
    await ask(question, retry?.userNode, signal);
  }
});
send.disabled = false;
byId("chat-form").addEventListener("submit", event => {
  event.preventDefault();
  sendController.start();
});
input.addEventListener("keydown", event => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey) && !event.isComposing) {
    event.preventDefault();
    sendController.start();
  }
});
reset.addEventListener("click", () => {
  sendController.reset();
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
docQuery.addEventListener("input", renderCatalog);
clearDocQuery.addEventListener("click", () => {
  docQuery.value = "";
  renderCatalog();
  docQuery.focus();
});
clearDocQuery.disabled = false;
for (const example of document.querySelectorAll(".example")) {
  example.addEventListener("click", () => { input.value = example.textContent; input.focus(); });
  example.disabled = false;
}
reset.disabled = false;
allDocs.disabled = false;
loadDocuments();
