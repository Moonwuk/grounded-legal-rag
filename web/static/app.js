"use strict";

const byId = id => document.getElementById(id);
function confirmAction(title, message, action) {
  const dialog = byId("confirm-dialog");
  if (dialog.open) return Promise.resolve(false);
  byId("confirm-title").textContent = title;
  byId("confirm-message").textContent = message;
  byId("confirm-accept").textContent = action;
  dialog.returnValue = "cancel";
  return new Promise(resolve => {
    dialog.addEventListener("close", () => resolve(dialog.returnValue === "accept"), {once: true});
    dialog.showModal();
    byId("confirm-cancel").focus();
  });
}
byId("confirm-cancel").addEventListener("click", () => byId("confirm-dialog").close("cancel"));
byId("confirm-accept").addEventListener("click", () => byId("confirm-dialog").close("accept"));
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
  cancelled: "Ответ остановлен",
  technical_error: "Техническая ошибка"
};

let messages = [];
let currentScene;
let busy = false;
let activeDocument;
let catalog = [];
let customTabs = [];
let selectedTab = "all";
let editingTab = null;
let savingTab = false;
const builtInTabs = [
  {id: "all", title: "Все"},
  {id: "laws", title: "Законы"}, {id: "contracts", title: "Договоры"},
  {id: "policies", title: "Регламенты"}, {id: "other", title: "Прочее"}
];
function documentGroup(doc) {
  if (doc.category.toLocaleLowerCase("ru") === "законы") return "laws";
  if (/^(договор|доп соглашение|дополнительное соглашение)/i.test(doc.title)) return "contracts";
  if (/^регламент/i.test(doc.title)) return "policies";
  return "other";
}
function documentsInTab(tab) {
  return catalog.filter(doc => tab.id === "all" || (tab.document_ids ? tab.document_ids.includes(doc.id) : documentGroup(doc) === tab.id));
}
function renderTabs() {
  const tabs = [...builtInTabs, ...customTabs];
  if (!tabs.some(tab => tab.id === selectedTab)) selectedTab = "all";
  const host = byId("doc-tabs");
  host.replaceChildren();
  for (const [index, tab] of builtInTabs.entries()) {
    const button = document.createElement("button");
    button.type = "button";
    button.id = "doc-tab-" + tab.id;
    button.textContent = tab.title + " · " + documentsInTab(tab).length;
    button.title = tab.title;
    button.setAttribute("role", "tab");
    button.setAttribute("aria-selected", String(tab.id === selectedTab));
    button.setAttribute("aria-controls", "doc-list");
    button.tabIndex = tab.id === selectedTab || (!builtInTabs.some(item => item.id === selectedTab) && index === 0) ? 0 : -1;
    button.addEventListener("click", () => {
      selectedTab = tab.id;
      docQuery.value = "";
      showList();
      byId("doc-tab-" + tab.id).focus();
    });
    button.addEventListener("keydown", event => {
      const offset = {ArrowRight: 1, ArrowLeft: -1, Home: -index, End: builtInTabs.length - index - 1}[event.key];
      if (offset === undefined) return;
      event.preventDefault();
      byId("doc-tab-" + builtInTabs[(index + offset + builtInTabs.length) % builtInTabs.length].id).click();
    });
    host.append(button);
  }
  const select = byId("custom-doc-tabs");
  select.replaceChildren();
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = customTabs.length ? "Выберите свою вкладку" : "Пока нет своих вкладок";
  placeholder.disabled = true;
  select.append(placeholder);
  for (const tab of customTabs) {
    const option = document.createElement("option");
    option.value = tab.id;
    option.textContent = tab.title + " · " + documentsInTab(tab).length;
    select.append(option);
  }
  const custom = customTabs.find(tab => tab.id === selectedTab);
  select.value = custom ? selectedTab : "";
  select.disabled = !customTabs.length;
  select.title = custom?.title || "Свои вкладки";
  list.setAttribute("aria-labelledby", custom ? "custom-tabs-label" : "doc-tab-" + selectedTab);
  byId("edit-doc-tab").hidden = !custom;
}
byId("custom-doc-tabs").addEventListener("change", () => {
  const id = byId("custom-doc-tabs").value;
  if (!customTabs.some(tab => tab.id === id)) return;
  selectedTab = id;
  docQuery.value = "";
  showList();
  byId("custom-doc-tabs").focus();
});
async function tabRequest(path = "", options = {}) {
  const response = await fetch("/api/document-tabs" + path, {
    ...options, headers: {"Content-Type": "application/json"}, signal: AbortSignal.timeout(10000)
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(response.status === 503 ? "Свои вкладки доступны после настройки серверного хранения и входа." :
      typeof data.detail === "string" ? data.detail : "Не удалось сохранить вкладку. Попробуйте ещё раз.");
  }
  return response.status === 204 ? null : response.json();
}
async function loadTabs() {
  byId("refresh-doc-tabs").disabled = true;
  try {
    customTabs = await tabRequest();
    byId("create-doc-tab").disabled = false;
    byId("tabs-status").textContent = "";
    renderTabs();
    if (docText.hidden) renderCatalog();
  } catch (error) {
    byId("tabs-status").textContent = error.message;
  } finally {
    byId("refresh-doc-tabs").disabled = false;
  }
}
function editTab(tab = null) {
  editingTab = tab;
  byId("tab-doc-query").value = "";
  byId("tab-doc-type").value = "";
  byId("tab-doc-status").value = "";
  byId("tab-doc-selected").checked = false;
  byId("tab-dialog-title").textContent = tab ? "Изменить вкладку" : "Создать вкладку";
  byId("tab-name").value = tab?.title || "";
  byId("tab-error").textContent = "";
  byId("delete-doc-tab").hidden = !tab;
  const choices = byId("tab-choices");
  choices.replaceChildren();
  const legend = document.createElement("legend");
  legend.textContent = "Документы во вкладке";
  choices.append(legend);
  for (const doc of catalog) {
    const label = document.createElement("label");
    label.dataset.documentId = doc.id;
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = doc.id;
    checkbox.checked = tab?.document_ids.includes(doc.id) || false;
    checkbox.addEventListener("change", filterTabChoices);
    const title = document.createElement("span");
    title.textContent = doc.title;
    label.append(checkbox, title);
    choices.append(label);
  }
  filterTabChoices();
  byId("tab-dialog").showModal();
  byId("tab-name").focus();
}
function filterTabChoices() {
  const query = byId("tab-doc-query").value.trim().toLocaleLowerCase("ru");
  const type = byId("tab-doc-type").value;
  const status = byId("tab-doc-status").value;
  const onlySelected = byId("tab-doc-selected").checked;
  const documents = new Map(catalog.map(doc => [doc.id, doc]));
  let visible = 0, selected = 0;
  for (const label of byId("tab-choices").querySelectorAll("label")) {
    const doc = documents.get(label.dataset.documentId);
    const checked = label.querySelector("input").checked;
    if (checked) selected++;
    const group = doc.status === "допсоглашение" ? "addenda" : documentGroup(doc);
    const edition = doc.status === "утратил силу" ? "expired" : doc.status === "действующая редакция" ? "current" : "unspecified";
    label.hidden = !doc.title.toLocaleLowerCase("ru").includes(query) || (type && group !== type) ||
      (status && edition !== status) || (onlySelected && !checked);
    if (!label.hidden) visible++;
  }
  byId("tab-selection-status").textContent = "Выбрано: " + selected + " · Найдено: " + visible +
    (visible ? "" : ". Измените или сбросьте фильтры.");
}
for (const id of ["tab-doc-query", "tab-doc-type", "tab-doc-status", "tab-doc-selected"]) {
  byId(id).addEventListener("input", filterTabChoices);
}
byId("reset-tab-filters").addEventListener("click", () => {
  byId("tab-doc-query").value = byId("tab-doc-type").value = byId("tab-doc-status").value = "";
  byId("tab-doc-selected").checked = false;
  filterTabChoices();
});
async function saveTab(remove = false) {
  if (savingTab) return;
  if (remove && !await confirmAction("Удалить вкладку?", "Вкладка «" + editingTab.title + "» будет удалена. Документы останутся в базе.", "Удалить вкладку")) return;
  savingTab = true;
  for (const id of ["save-doc-tab", "delete-doc-tab", "cancel-doc-tab"]) byId(id).disabled = true;
  byId("tab-error").textContent = "";
  try {
    const path = editingTab ? "/" + editingTab.id : "";
    const body = {title: byId("tab-name").value.trim(), revision: editingTab?.revision || 0,
      document_ids: [...byId("tab-choices").querySelectorAll("input:checked")].map(input => input.value)};
    const saved = await tabRequest(path, {method: remove ? "DELETE" : editingTab ? "PUT" : "POST",
      ...(remove ? {} : {body: JSON.stringify(body)})});
    customTabs = customTabs.filter(tab => tab.id !== editingTab?.id);
    if (saved) customTabs.push(saved);
    selectedTab = saved?.id || "all";
    docQuery.value = "";
    byId("tab-dialog").close();
    showList();
    (customTabs.some(tab => tab.id === selectedTab) ? byId("custom-doc-tabs") : byId("doc-tab-" + selectedTab)).focus();
  } catch (error) {
    byId("tab-error").textContent = error.message;
  } finally {
    savingTab = false;
    for (const id of ["save-doc-tab", "delete-doc-tab", "cancel-doc-tab"]) byId(id).disabled = false;
  }
}
byId("create-doc-tab").addEventListener("click", () => editTab());
byId("edit-doc-tab").addEventListener("click", () => editTab(customTabs.find(tab => tab.id === selectedTab)));
byId("refresh-doc-tabs").addEventListener("click", loadTabs);
byId("tab-form").addEventListener("submit", event => { event.preventDefault(); saveTab(); });
byId("cancel-doc-tab").addEventListener("click", () => byId("tab-dialog").close());
byId("delete-doc-tab").addEventListener("click", () => saveTab(true));
byId("tab-dialog").addEventListener("cancel", event => { if (savingTab) event.preventDefault(); });
let currentChat = null;
let savedChats = [];
let trashedChats = [];
let chatFolders = [];
let selectedFolder = "all";
let foldersEnabled = false;
let editingFolder = null;
let movingChat = null;
let folderSaving = false;

async function folderRequest(path = "", method = "GET", body) {
  const response = await fetch("/api" + path, {method, headers: {"Content-Type": "application/json"},
    ...(body === undefined ? {} : {body: JSON.stringify(body)}), signal: AbortSignal.timeout(10000)});
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === "string" ? data.detail : "Не удалось сохранить изменения. Обновите список и повторите.");
  }
  return response.status === 204 ? null : response.json();
}
async function loadFolders() {
  try {
    chatFolders = await folderRequest("/chat-folders");
    foldersEnabled = true;
    byId("folder-status").textContent = "";
  } catch (error) {
    byId("folder-status").textContent = error.message;
  }
}
function chatsInFolder(id) {
  if (id === "trash") return trashedChats;
  return savedChats.filter(chat => id === "all" || (id === "unfiled" ? !chat.folder_id : chat.folder_id === id));
}
function renderFolders() {
  if (!["all", "unfiled", "trash"].includes(selectedFolder) && !chatFolders.some(f => f.id === selectedFolder)) selectedFolder = "all";
  const host = byId("folder-list");
  host.replaceChildren();
  const folders = [{id: "all", title: "Все чаты"}, {id: "unfiled", title: "Без папки"}, ...chatFolders, {id: "trash", title: "Корзина"}];
  for (const folder of folders) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "folder-select";
    button.dataset.folderId = folder.id;
    button.title = folder.title;
    button.setAttribute("aria-current", String(selectedFolder === folder.id));
    const title = document.createElement("span");
    title.textContent = folder.title;
    const count = document.createElement("small");
    count.textContent = chatsInFolder(folder.id).length;
    button.append(title, count);
    button.addEventListener("click", () => {
      selectedFolder = folder.id;
      renderHistory();
      byId("folder-list").querySelector('[data-folder-id="' + folder.id + '"]')?.focus();
    });
    host.append(button);
  }
  byId("create-chat-folder").disabled = !foldersEnabled || folderSaving;
  byId("edit-chat-folder").hidden = ["all", "unfiled", "trash"].includes(selectedFolder);
  byId("trash-hint").hidden = selectedFolder !== "trash";
  reset.textContent = ["all", "unfiled", "trash"].includes(selectedFolder) ? "+ Новый диалог" : "+ Диалог в этой папке";
}
function editFolder(folder = null) {
  editingFolder = folder;
  byId("folder-dialog-title").textContent = folder ? "Изменить папку" : "Создать папку";
  byId("folder-name").value = folder?.title || "";
  byId("folder-error").textContent = "";
  byId("delete-chat-folder").hidden = !folder;
  byId("folder-dialog").showModal();
  byId("folder-name").focus();
}
function folderPending(pending) {
  folderSaving = pending;
  for (const id of ["save-chat-folder", "cancel-chat-folder", "delete-chat-folder", "save-chat-move", "cancel-chat-move"]) byId(id).disabled = pending;
}
async function saveFolder(remove = false) {
  if (folderSaving) return;
  if (remove && !await confirmAction("Удалить папку?", "Папка «" + editingFolder.title + "» будет удалена. Диалоги сохранятся в разделе «Без папки».", "Удалить папку")) return;
  folderPending(true);
  byId("folder-error").textContent = "";
  try {
    const folder = await folderRequest("/chat-folders" + (editingFolder ? "/" + editingFolder.id : ""),
      remove ? "DELETE" : editingFolder ? "PUT" : "POST", remove ? undefined : {title: byId("folder-name").value.trim()});
    if (remove) {
      [...savedChats, ...trashedChats].forEach(chat => { if (chat.folder_id === editingFolder.id) chat.folder_id = null; });
      chatFolders = chatFolders.filter(item => item.id !== editingFolder.id);
      selectedFolder = "unfiled";
    } else {
      const index = chatFolders.findIndex(item => item.id === folder.id);
      if (index === -1) chatFolders.push(folder); else chatFolders[index] = folder;
      selectedFolder = folder.id;
    }
    byId("folder-status").textContent = remove ? "Папка удалена. Чаты сохранены." : "";
    byId("folder-dialog").close();
    renderHistory();
  } catch (error) {
    byId("folder-error").textContent = error.message;
  } finally {
    folderPending(false);
    renderHistory();
    if (!byId("folder-dialog").open && !byId("move-dialog").open) {
      byId("folder-list").querySelector('[data-folder-id="' + selectedFolder + '"]')?.focus();
    }
  }
}
function editChatFolder(chat) {
  movingChat = chat;
  byId("move-chat-title").textContent = chat.title;
  byId("move-error").textContent = "";
  const select = byId("move-folder");
  select.replaceChildren();
  for (const folder of [{id: "", title: "Без папки"}, ...chatFolders]) {
    const option = document.createElement("option");
    option.value = folder.id;
    option.textContent = folder.title;
    select.append(option);
  }
  select.value = chat.folder_id || "";
  byId("move-dialog").showModal();
  select.focus();
}
async function saveChatMove() {
  if (folderSaving) return;
  folderPending(true);
  try {
    const result = await folderRequest("/chats/" + movingChat.id + "/folder", "PUT", {folder_id: byId("move-folder").value || null});
    const chat = savedChats.find(item => item.id === result.id);
    if (chat) chat.folder_id = result.folder_id;
    byId("move-dialog").close();
    renderHistory();
    byId("folder-status").textContent = "Чат перемещён в «" + (chatFolders.find(f => f.id === result.folder_id)?.title || "Без папки") + "».";
  } catch (error) {
    byId("move-error").textContent = error.message;
  } finally {
    folderPending(false);
    renderHistory();
    if (!byId("folder-dialog").open && !byId("move-dialog").open) {
      byId("folder-list").querySelector('[data-folder-id="' + selectedFolder + '"]')?.focus();
    }
  }
}
byId("create-chat-folder").addEventListener("click", () => editFolder());
byId("edit-chat-folder").addEventListener("click", () => editFolder(chatFolders.find(f => f.id === selectedFolder)));
byId("folder-form").addEventListener("submit", event => { event.preventDefault(); saveFolder(); });
byId("delete-chat-folder").addEventListener("click", () => saveFolder(true));
byId("cancel-chat-folder").addEventListener("click", () => byId("folder-dialog").close());
byId("move-form").addEventListener("submit", event => { event.preventDefault(); saveChatMove(); });
byId("cancel-chat-move").addEventListener("click", () => byId("move-dialog").close());
for (const id of ["folder-dialog", "move-dialog"]) byId(id).addEventListener("cancel", event => { if (folderSaving) event.preventDefault(); });
let historyEnabled = false;
let navigating = false;
let renamingChat = null, renameSaving = false;

function editChatTitle(chat) {
  renamingChat = chat.id;
  byId("chat-name").value = chat.title;
  byId("rename-error").textContent = "";
  byId("rename-dialog").showModal();
  byId("chat-name").focus();
  byId("chat-name").select();
}
byId("rename-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (renameSaving) return;
  renameSaving = true;
  for (const id of ["chat-name", "save-chat-name", "cancel-chat-name"]) byId(id).disabled = true;
  byId("rename-error").textContent = "";
  try {
    const result = await folderRequest("/chats/" + renamingChat + "/title", "PUT", {title: byId("chat-name").value.trim()});
    const chat = savedChats.find(item => item.id === result.id);
    if (chat) chat.title = result.title;
    byId("rename-dialog").close();
    byId("history-status").textContent = "Название сохранено";
  } catch (error) {
    byId("rename-error").textContent = error.message;
  } finally {
    renameSaving = false;
    for (const id of ["chat-name", "save-chat-name", "cancel-chat-name"]) byId(id).disabled = false;
    if (!byId("rename-dialog").open) {
      renderHistory();
      byId("chat-list").querySelector('[data-chat-id="' + renamingChat + '"] .chat-rename')?.focus();
    }
  }
});
byId("cancel-chat-name").addEventListener("click", () => byId("rename-dialog").close());
byId("rename-dialog").addEventListener("cancel", event => { if (renameSaving) event.preventDefault(); });

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

async function loadChatLists() {
  const [active, trash] = await Promise.all([historyRequest(), historyRequest("?trash=true")]);
  savedChats = active;
  trashedChats = trash;
}

function renderHistory() {
  renderFolders();
  const chatList = byId("chat-list");
  chatList.replaceChildren();
  const visibleChats = chatsInFolder(selectedFolder);
  byId("folder-empty").hidden = !historyEnabled || !!visibleChats.length;
  byId("folder-empty").textContent = selectedFolder === "trash" ? "Корзина пуста." :
    "Здесь пока нет чатов. Перенесите сюда диалог кнопкой «В папку» или начните новый.";
  for (const chat of visibleChats) {
    const row = document.createElement("li");
    row.dataset.chatId = chat.id;
    row.dataset.trashed = String(selectedFolder === "trash");
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
    button.disabled = busy || navigating || selectedFolder === "trash";
    const date = document.createElement("small");
    date.textContent = (chat.deleted_at ? "Удалён: " : "") + new Date((chat.deleted_at || chat.updated) * 1000).toLocaleString("ru-RU", {dateStyle: "short", timeStyle: "short"});
    button.append(date);
    button.addEventListener("click", () => navigateHistory(() => selectChat(chat.id)));
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "chat-delete";
    const inTrash = selectedFolder === "trash";
    remove.textContent = inTrash ? "Удалить навсегда" : "В корзину";
    remove.setAttribute("aria-label", (inTrash ? "Удалить навсегда: " : "В корзину: ") + chat.title);
    remove.disabled = busy || navigating;
    remove.addEventListener("click", async () => {
      const question = inTrash ? "Удалить диалог «" + chat.title + "» навсегда? Восстановить его будет нельзя." :
        "Переместить диалог «" + chat.title + "» в корзину? Его можно будет восстановить.";
      if (busy || navigating) return;
      if (!await confirmAction(inTrash ? "Удалить диалог навсегда?" : "Переместить в корзину?", question,
        inTrash ? "Удалить навсегда" : "В корзину")) return;
      navigateHistory(async () => {
        await historyRequest("/" + encodeURIComponent(chat.id) + (inTrash ? "/permanent" : ""), "DELETE");
        if (currentChat === chat.id) clearChat();
        await loadChatLists();
      });
    });
    const move = document.createElement("button");
    move.type = "button";
    move.className = "chat-move";
    move.textContent = inTrash ? "Восстановить" : "В папку";
    move.setAttribute("aria-label", (inTrash ? "Восстановить диалог: " : "Переместить диалог: ") + chat.title);
    move.disabled = inTrash ? busy || navigating : !foldersEnabled || folderSaving;
    move.addEventListener("click", () => {
      if (!inTrash) return editChatFolder(chat);
      navigateHistory(async () => {
        await historyRequest("/" + encodeURIComponent(chat.id) + "/restore", "POST");
        await loadChatLists();
        selectedFolder = "all";
        await selectChat(chat.id);
      });
    });
    if (inTrash) row.append(button, move, remove);
    else {
      const rename = document.createElement("button");
      rename.type = "button";
      rename.className = "chat-rename";
      rename.textContent = "Переименовать";
      rename.setAttribute("aria-label", "Переименовать диалог: " + chat.title);
      rename.disabled = navigating || renameSaving;
      rename.addEventListener("click", () => editChatTitle(chat));
      row.append(button, rename, move, remove);
    }
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
    byId("history-status").textContent = savedChats.length ? "Сохранено на сервере" : trashedChats.length ? "Чаты находятся в корзине" : "Пока нет сохранённых диалогов";
  } catch (error) {
    byId("history-status").textContent = error.message;
  } finally {
    navigating = false;
    send.disabled = reset.disabled = false;
    renderHistory();
  }
}

function clearChat() {
  globalThis.ChatQueue?.detach();
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
  globalThis.MobileLayout?.resizeInput();
  input.removeAttribute("aria-invalid");
  byId("input-error").textContent = "";
  showList();
}

function renderSavedTurns(turns) {
  if (currentScene) ArchiveScene.stop(currentScene);
  currentScene = null;
  messages = [];
  log.replaceChildren(welcome);
  welcome.hidden = false;
  for (const turn of turns) {
    const userNode = bubble("user", turn.question).item;
    const node = bubble("assistant", "");
    if (turn.answer.status === "clarify") {
      node.body.before(ArchiveScene.create("clarify"));
      node.item.classList.add("with-scene");
    }
    if (!["technical_error", "cancelled"].includes(turn.answer.status)) messages.push(
      {role: "user", text: turn.question}, {role: "assistant", text: turn.answer.text});
    const contextLength = messages.length;
    renderAnswer(node, turn.answer, () => {
      if (busy || navigating) return;
      if (historyEnabled && globalThis.ChatQueue) {
        input.value = turn.question;
        globalThis.ChatQueue.submit(turn.question, true).then(() => { if (input.value.trim() === turn.question) input.value = ""; globalThis.MobileLayout?.resizeInput(); }).catch(error => { byId("input-error").textContent = error.message; });
        return;
      }
      if (turn !== turns.at(-1) || messages.length !== contextLength) { input.value = turn.question; input.focus(); return; }
      retryRequest = {question: turn.question, userNode};
      node.item.remove();
      sendController.start();
    });
  }
}

async function selectChat(id) {
  const chat = await historyRequest("/" + encodeURIComponent(id));
  clearChat();
  currentChat = chat.id;
  rememberChat();
  renderSavedTurns(chat.turns);
  globalThis.ChatQueue?.attach(chat);
  globalThis.MobileLayout?.close("history");
  if (chat.busy) byId("history-status").textContent = "Ответ ещё готовится. Обновите список через несколько секунд.";
  if (!globalThis.MobileLayout?.isMobile()) input.focus();
}

async function loadHistory() {
  send.disabled = reset.disabled = true;
  navigating = true;
  try {
    await loadChatLists();
    historyEnabled = true;
    await loadFolders();
    let selected;
    try { selected = localStorage.getItem("psb-current-chat"); } catch { /* Optional selection only. */ }
    const chat = savedChats.find(item => item.id === (currentChat || selected)) || savedChats[0];
    if (chat) await selectChat(chat.id);
    else clearChat();
    byId("history-status").textContent = savedChats.length ? "Сохранено на сервере" : trashedChats.length ? "Чаты находятся в корзине" : "Пока нет сохранённых диалогов";
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
  byId("doc-navigation").hidden = catalog.length === 0;
  renderTabs();
  allDocs.hidden = true;
  renderCatalog();
}

function clearQuote() {
  selectedQuote = "";
  quoteTools.hidden = true;
  copyController.reset();
}

async function openDocument(id, source, focus = true) {
  globalThis.MobileLayout?.open("documents");
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
    byId("doc-navigation").hidden = true;
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
  const tab = [...builtInTabs, ...customTabs].find(tab => tab.id === selectedTab) || builtInTabs[0];
  const documents = documentsInTab(tab);
  const matching = documents.filter(doc => doc.title.toLocaleLowerCase("ru").includes(query));
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
  docStatus.textContent = matching.length ? "Документов: " + matching.length + " из " + documents.length :
    query ? "В этой вкладке ничего не найдено." : tab.document_ids ? "Вкладка пока пустая. Нажмите «Изменить», чтобы добавить документы." : "В этой вкладке пока нет документов.";
}

async function loadDocuments() {
  try {
    const response = await fetch("/api/documents", {signal: AbortSignal.timeout(10000)});
    if (!response.ok) throw new Error();
    catalog = await response.json();
    showList();
    await loadTabs();
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
  if ((answer.status === "technical_error" && !missingModel) || answer.status === "cancelled") {
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
    if (activeDocument === documentAtStart && docText.hidden && !globalThis.MobileLayout?.isMobile()) {
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
  if (!globalThis.MobileLayout?.isMobile()) input.focus();
  log.scrollTop = log.scrollHeight;
  if (historyEnabled) {
    try {
      await loadChatLists();
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
        const folderPath = ["all", "unfiled", "trash"].includes(selectedFolder) ? "" : "?folder_id=" + encodeURIComponent(selectedFolder);
        const chat = await historyRequest(folderPath, "POST");
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
    if (historyEnabled && globalThis.ChatQueue) {
      await globalThis.ChatQueue.submit(question);
      if (!retry && input.value.trim() === question) input.value = "";
      globalThis.MobileLayout?.resizeInput();
      return {queued: true};
    }
    if (!retry) input.value = "";
    globalThis.MobileLayout?.resizeInput();
    if (globalThis.MobileLayout?.isMobile()) input.blur();
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
  globalThis.MobileLayout?.close();
  if (selectedFolder === "trash") selectedFolder = "all";
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
  example.addEventListener("click", () => { input.value = example.textContent; globalThis.MobileLayout?.resizeInput(); input.focus(); });
  example.disabled = false;
}
reset.disabled = false;
allDocs.disabled = false;
loadDocuments();
loadHistory();
