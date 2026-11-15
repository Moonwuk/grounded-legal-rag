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
  disallowed: "Ограничение правовой помощи",
  unverified: "Ответ не прошёл проверку",
  technical_error: "Техническая ошибка"
};

let messages = [];
let currentScene;
let busy = false;
let activeDocument;
let catalog = [];
let currentChat = null;
let savedChats = [];
let historyEnabled = false;
let navigating = false;

function rememberChat() {
  try {
    if (currentChat) localStorage.setItem("psb-current-chat", currentChat);
    else localStorage.removeItem("psb-current-chat");
  } catch { /* Chat contents stay on the server even if browser storage is unavailable. */ }
}

async function historyRequest(path = "", method = "GET") {
  const response = await fetch("/api/chats" + path, {
    method, headers: {"Content-Type": "application/json"}, signal: AbortSignal.timeout(10000)
  });
  if (!response.ok) {
    const error = new Error("История недоступна. Повторите загрузку.");
    error.status = response.status;
    try { error.message = (await response.json()).detail || error.message; } catch { /* Use safe fallback. */ }
    throw error;
  }
  return response.status === 204 ? null : response.json();
}

function renderHistory() {
  const chatList = byId("chat-list");
  chatList.replaceChildren();
  for (const chat of savedChats) {
    const row = document.createElement("li");
    if (chat.id === currentChat) row.setAttribute("aria-current", "true");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "chat-select";
    button.title = chat.title;
    button.setAttribute("aria-label", chat.title);
    const title = document.createElement("span");
    title.className = "chat-select-title";
    title.textContent = chat.title;
    button.append(title);
    button.disabled = busy || navigating;
    const date = document.createElement("small");
    date.textContent = new Date(chat.updated * 1000).toLocaleString("ru-RU", {dateStyle: "short", timeStyle: "short"});
    button.append(date);
    button.addEventListener("click", () => navigateHistory(() => selectChat(chat.id)));
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "chat-delete";
    remove.textContent = "Удалить";
    remove.setAttribute("aria-label", "Удалить диалог: " + chat.title);
    remove.disabled = busy || navigating;
    remove.addEventListener("click", () => {
      if (busy || navigating || !confirm("Удалить этот диалог и все его сообщения?")) return;
      navigateHistory(async () => {
        await historyRequest("/" + encodeURIComponent(chat.id), "DELETE");
        if (currentChat === chat.id) clearChat();
        savedChats = await historyRequest();
      });
    });
    row.append(button, remove);
    chatList.append(row);
  }
}

async function navigateHistory(action) {
  if (busy || navigating) return;
  navigating = true;
  send.disabled = reset.disabled = true;
  renderHistory();
  try {
    await action();
    byId("history-status").textContent = savedChats.length ? "Сохранено на сервере" : "Пока нет сохранённых диалогов";
  } catch (error) {
    byId("history-status").textContent = error.message;
  } finally {
    navigating = false;
    send.disabled = reset.disabled = false;
    renderHistory();
  }
}

function clearChat() {
  if (currentScene) ArchiveScene.stop(currentScene);
  currentScene = null;
  sendController.reset();
  retryRequest = null;
  currentChat = null;
  rememberChat();
  messages = [];
  log.replaceChildren(welcome);
  welcome.hidden = false;
  input.value = "";
  input.removeAttribute("aria-invalid");
  byId("input-error").textContent = "";
  showList();
}

async function selectChat(id) {
  const chat = await historyRequest("/" + encodeURIComponent(id));
  clearChat();
  currentChat = chat.id;
  rememberChat();
  for (const turn of chat.turns) {
    const userNode = bubble("user", turn.question).item;
    const node = bubble("assistant", "");
    if (turn.answer.status === "clarify") {
      node.body.before(ArchiveScene.create("clarify"));
      node.item.classList.add("with-scene");
    }
    if (turn.answer.status !== "technical_error") messages.push(
      {role: "user", text: turn.question}, {role: "assistant", text: turn.answer.text});
    const contextLength = messages.length;
    renderAnswer(node, turn.answer, () => {
      if (busy || navigating) return;
      if (turn !== chat.turns.at(-1) || messages.length !== contextLength) { input.value = turn.question; input.focus(); return; }
      retryRequest = {question: turn.question, userNode};
      node.item.remove();
      sendController.start();
    });
  }
  if (chat.busy) byId("history-status").textContent = "Ответ ещё готовится. Обновите список через несколько секунд.";
  input.focus();
}

async function loadHistory() {
  send.disabled = reset.disabled = true;
  navigating = true;
  try {
    savedChats = await historyRequest();
    historyEnabled = true;
    let selected;
    try { selected = localStorage.getItem("psb-current-chat"); } catch { /* Optional selection only. */ }
    const chat = savedChats.find(item => item.id === (currentChat || selected)) || savedChats[0];
    if (chat) await selectChat(chat.id);
    else clearChat();
    byId("history-status").textContent = savedChats.length ? "Сохранено на сервере" : "Пока нет сохранённых диалогов";
    send.disabled = reset.disabled = false;
  } catch (error) {
    byId("history-status").textContent = error.status === 503
      ? "История на сервере не настроена. Диалог сохранится только до закрытия страницы." : error.message;
    if (error.status === 503) send.disabled = reset.disabled = false;
  } finally {
    navigating = false;
    renderHistory();
  }
}

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
    status.textContent = missingModel ? "Модель не настроена"
      : answer.ui_state === "role_protection" ? "Защита роли"
      : labels[answer.status] || "Найдены источники";
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
  const chatAtStart = currentChat;
  reset.disabled = true;
  renderHistory();
  const pending = {role: "user", text: question};
  const userNode = existing || bubble("user", question).item;
  const node = bubble("assistant", "Ищем в документах…");
  const documentAtStart = activeDocument;
  if (currentScene) ArchiveScene.stop(currentScene);
  const scene = ArchiveScene.create();
  currentScene = scene;
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
      body: JSON.stringify(currentChat ? {chat_id: currentChat, messages: [pending]} : {messages: [...messages, pending]}),
      signal: AbortSignal.any([signal, AbortSignal.timeout(180000)])
    });
    if (!response.ok) {
      let detail = response.status === 413 ? "Диалог слишком длинный. Начните новый." : "Сервис не ответил. Попробуйте снова.";
      if (response.status === 409) detail = "В этом диалоге уже готовится ответ. Обновите список через несколько секунд.";
      answer = {status: "technical_error", text: detail};
    } else {
      answer = await response.json();
    }
  } catch (error) {
    if (signal.aborted) {
      ArchiveScene.stop(scene);
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
    renderHistory();
  }
  ArchiveScene.setState(scene, ArchiveScene.stateFor(answer));
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
    if (busy || navigating || currentChat !== chatAtStart) return;
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
  if (historyEnabled) {
    try {
      savedChats = await historyRequest();
      byId("history-status").textContent = "Сохранено на сервере";
      renderHistory();
    } catch { byId("history-status").textContent = "Не удалось обновить список. Нажмите «Обновить список»."; }
  }
  if (answer.status === "technical_error") throw new Error("chat_request_failed");
}

let retryRequest;
const sendController = SLComponent.mount(send.closest(".sl-component"), {
  async onSend({signal}) {
    if (navigating) throw new Error("history_loading");
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
    if (historyEnabled && !currentChat) {
      navigating = true;
      reset.disabled = true;
      try {
        const chat = await historyRequest("", "POST");
        currentChat = chat.id;
        rememberChat();
        savedChats.unshift(chat);
      } catch (error) {
        byId("input-error").textContent = error.message;
        throw error;
      } finally {
        navigating = false;
        reset.disabled = false;
        renderHistory();
      }
    }
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
  // Enter sends, as in common chats; Shift+Enter keeps a line break.
  if (event.key === "Enter" && !event.shiftKey && !event.altKey && !event.isComposing) {
    event.preventDefault();
    sendController.start();
  }
});
reset.addEventListener("click", () => {
  if (busy || navigating) return;
  clearChat();
  renderHistory();
  input.focus();
});
byId("refresh-history").addEventListener("click", () => { if (!busy && !navigating) loadHistory(); });
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
loadHistory();
