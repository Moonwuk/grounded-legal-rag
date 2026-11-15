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
  select.closest(".collection-picker").hidden = !customTabs.length;
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
  byId("tab-filter-options").open = !globalThis.MobileLayout?.isMobile();
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
  const folders = [{id: "all", title: "Все диалоги"}, {id: "unfiled", title: "Без папки"}, ...chatFolders, {id: "trash", title: "Корзина"}];
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
  byId("history-folders").querySelector("summary").textContent = "Папки и корзина · " + (folders.find(folder => folder.id === selectedFolder)?.title || "Все диалоги");
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
let historyReady = false;
let historyInitialized = false;
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
    if (currentChat === result.id) byId("chat-title").textContent = result.title;
    if (byId("history-query").value.trim()) await searchHistory();
    byId("rename-dialog").close();
    byId("history-status").textContent = "Название сохранено";
  } catch (error) {
    byId("rename-error").textContent = error.message;
  } finally {
    renameSaving = false;
    for (const id of ["chat-name", "save-chat-name", "cancel-chat-name"]) byId(id).disabled = false;
    if (!byId("rename-dialog").open) {
      renderHistory();
      byId("chat-list").querySelector('[data-chat-id="' + renamingChat + '"] .chat-actions summary')?.focus();
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
  if (byId("history-query").value.trim()) await searchHistory();
}

let searchMatches = null, searchVersion = 0, searchTimer;
async function searchHistory() {
  const version = ++searchVersion;
  const query = byId("history-query").value.trim();
  if (!query) { searchMatches = null; byId("history-search-status").textContent = ""; renderHistory(); return; }
  byId("history-search-status").textContent = "Поиск…";
  try {
    const encoded = encodeURIComponent(query);
    const results = await Promise.all([historyRequest("?q=" + encoded), historyRequest("?trash=true&q=" + encoded)]);
    if (version !== searchVersion) return;
    searchMatches = new Map(results.flat().map(chat => [chat.id, chat]));
    byId("history-search-status").textContent = "Найдено: " + searchMatches.size + " · с учётом папок и корзины";
    renderHistory();
  } catch { if (version === searchVersion) byId("history-search-status").textContent = "Поиск недоступен. Повторите запрос."; }
}
byId("history-query").addEventListener("input", () => {
  ++searchVersion; clearTimeout(searchTimer);
  searchTimer = setTimeout(searchHistory, 250);
});

function renderHistory() {
  renderFolders();
  const chatList = byId("chat-list");
  chatList.replaceChildren();
  const visibleChats = chatsInFolder(selectedFolder).filter(chat => !searchMatches || searchMatches.has(chat.id));
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
    title.textContent = (chat.pinned ? "★ " : "") + chat.title;
    button.append(title);
    button.disabled = busy || navigating || selectedFolder === "trash";
    const date = document.createElement("small");
    date.textContent = (chat.deleted_at ? "Удалён: " : "") + new Date((chat.deleted_at || chat.updated) * 1000).toLocaleString("ru-RU", {dateStyle: "short", timeStyle: "short"});
    button.append(date);
    if (searchMatches?.get(chat.id)?.preview) {
      const preview = document.createElement("small");
      preview.className = "chat-preview";
      preview.textContent = searchMatches.get(chat.id).preview;
      button.append(preview);
    }
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
        if (currentChat === chat.id) {
          clearChat();
          if (globalThis.WebWorkspace) await globalThis.WebWorkspace.open(null);
        }
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
    const menu = document.createElement("details");
    menu.className = "chat-actions";
    const summary = document.createElement("summary");
    summary.textContent = "⋯";
    summary.setAttribute("aria-label", "Действия: " + chat.title);
    menu.append(summary);
    menu.addEventListener("keydown", event => { if (event.key === "Escape") { menu.open = false; summary.focus(); } });
    if (inTrash) menu.append(move, remove);
    else {
      const rename = document.createElement("button");
      rename.type = "button";
      rename.className = "chat-rename";
      rename.textContent = "Переименовать";
      rename.setAttribute("aria-label", "Переименовать диалог: " + chat.title);
      rename.disabled = navigating || renameSaving;
      rename.addEventListener("click", () => editChatTitle(chat));
      globalThis.WebIcons?.set(rename, "edit", undefined, false);
      const pin = document.createElement("button");
      pin.type = "button";
      pin.textContent = chat.pinned ? "Открепить" : "Закрепить";
      pin.disabled = navigating;
      pin.addEventListener("click", () => navigateHistory(async () => {
        await historyRequest("/" + encodeURIComponent(chat.id) + "/pin?pinned=" + !chat.pinned, "PUT");
        await loadChatLists();
      }));
      globalThis.WebIcons?.set(pin, "pin", undefined, false);
      menu.append(pin, rename, move, remove);
    }
    globalThis.WebIcons?.set(move, inTrash ? "restore" : "folder", undefined, false);
    globalThis.WebIcons?.set(remove, "trash", undefined, false);
    row.append(button, menu);
    chatList.append(row);
  }
  globalThis.WebWorkspace?.decorateHistory();
}

async function navigateHistory(action) {
  if (busy || navigating) return false;
  navigating = true;
  send.disabled = byId("new-dialogue").disabled = reset.disabled = true;
  renderHistory();
  try {
    if (globalThis.WebWorkspace) await globalThis.WebWorkspace.leave();
    await action();
    byId("history-status").textContent = savedChats.length ? "Сохранено на сервере" : trashedChats.length ? "Удалённые диалоги — в корзине" : "Пока нет сохранённых диалогов";
    return true;
  } catch (error) {
    byId("history-status").textContent = error.message;
    return false;
  } finally {
    navigating = false;
    send.disabled = byId("new-dialogue").disabled = reset.disabled = false;
    renderHistory();
  }
}

function clearChat() {
  globalThis.WebWorkspace?.detach();
  globalThis.ChatQueue?.detach();
  if (currentScene) ArchiveScene.stop(currentScene);
  currentScene = null;
  sendController.reset();
  retryRequest = null;
  currentChat = null;
  byId("chat-title").textContent = "Диалог";
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

function renderSavedTurns(turns, animateIndex = -1) {
  globalThis.WebWorkspace?.beginTurns();
  if (currentScene) ArchiveScene.stop(currentScene);
  currentScene = null;
  messages = [];
  log.replaceChildren(welcome);
  welcome.hidden = false;
  for (const [turnIndex, turn] of turns.entries()) {
    const userNode = bubble("user", turn.question).item;
    const node = bubble("assistant", "");
    const restoredScene = ArchiveScene.create(ArchiveScene.stateFor(turn.answer), {animate: turnIndex === animateIndex});
    node.body.before(restoredScene);
    node.item.classList.add("with-scene");
    if (turnIndex === animateIndex) currentScene = restoredScene;
    if (!["technical_error", "cancelled"].includes(turn.answer.status)) messages.push(
      {role: "user", text: turn.question}, {role: "assistant", text: turn.answer.text});
    const contextLength = messages.length;
    renderAnswer(node, turn.answer, () => {
      if (busy || navigating) return;
      if (historyEnabled && globalThis.ChatQueue) {
        input.value = turn.question;
        globalThis.ChatQueue.submit(turn.question, true).then(() => { if (input.value.trim() === turn.question) input.value = ""; globalThis.MobileLayout?.resizeInput(); globalThis.WebWorkspace?.captureDraft(); }).catch(error => { byId("input-error").textContent = error.message; });
        return;
      }
      if (turn !== turns.at(-1) || messages.length !== contextLength) { input.value = turn.question; input.focus(); return; }
      retryRequest = {question: turn.question, userNode};
      node.item.remove();
      sendController.start();
    });
    globalThis.WebWorkspace?.addTurn(node, userNode, turn, turnIndex);
  }
  globalThis.WebWorkspace?.refresh();
}

async function selectChat(id) {
  if (globalThis.WebWorkspace) await globalThis.WebWorkspace.leave();
  const chat = await historyRequest("/" + encodeURIComponent(id));
  clearChat();
  currentChat = chat.id;
  byId("chat-title").textContent = chat.title;
  rememberChat();
  if (globalThis.WebWorkspace) await globalThis.WebWorkspace.open(chat.id);
  renderSavedTurns(chat.turns);
  globalThis.ChatQueue?.attach(chat);
  globalThis.MobileLayout?.close("history");
  if (chat.busy) byId("history-status").textContent = "Ответ ещё готовится. Обновите список через несколько секунд.";
  if (!globalThis.MobileLayout?.isMobile()) input.focus();
}

async function loadHistory() {
  try { if (historyReady && globalThis.WebWorkspace) await globalThis.WebWorkspace.leave(); }
  catch (error) { byId("input-error").textContent = error.message; return; }
  send.disabled = byId("new-dialogue").disabled = reset.disabled = true;
  navigating = true;
  historyReady = false;
  try {
    await loadChatLists();
    historyEnabled = true;
    globalThis.WebWorkspace?.setEnabled(true);
    await loadFolders();
    if (!historyInitialized) {
      let selected;
      try { selected = localStorage.getItem("psb-current-chat"); } catch { /* Optional selection only. */ }
      const chat = savedChats.find(item => item.id === selected) || savedChats[0];
      if (chat) await selectChat(chat.id);
      else if (globalThis.WebWorkspace) await globalThis.WebWorkspace.open(null);
    } else if (currentChat && !savedChats.some(item => item.id === currentChat)) {
      // The selected chat was removed on another device. Keep the draft, but
      // never move it silently into a different saved conversation.
      const draft = input.value;
      clearChat();
      input.value = draft;
      globalThis.MobileLayout?.resizeInput();
      if (globalThis.WebWorkspace) await globalThis.WebWorkspace.open(null, draft);
    } else if (globalThis.WebWorkspace) await globalThis.WebWorkspace.open(currentChat);
    historyReady = historyInitialized = true;
    byId("history-status").textContent = savedChats.length ? "Сохранено на сервере" : trashedChats.length ? "Удалённые диалоги — в корзине" : "Пока нет сохранённых диалогов";
    send.disabled = byId("new-dialogue").disabled = reset.disabled = false;
  } catch (error) {
    const unconfigured = !historyEnabled && error.status === 503 && error.message === "История на сервере не настроена.";
    byId("history-status").textContent = unconfigured
      ? "История на сервере не настроена. Диалог сохранится только до закрытия страницы." : error.message;
    if (unconfigured) {
      globalThis.WebWorkspace?.setEnabled(false);
      historyReady = historyInitialized = true;
      send.disabled = byId("new-dialogue").disabled = reset.disabled = false;
    }
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
  globalThis.WebWorkspace?.beforeDocument();
  activeDocument?.abort();
  activeDocument = null;
  clearQuote();
  byId("documents-panel").dataset.view = "list";
  byId("document-search").hidden = true;
  byId("print-document").disabled = true;
  printableDocument = null;
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
  globalThis.WebWorkspace?.beforeDocument();
  setDocumentsVisible(true);
  globalThis.MobileLayout?.open("documents");
  activeDocument?.abort();
  clearQuote();
  const request = new AbortController();
  activeDocument = request;
  printableDocument = null;
  byId("print-document").disabled = true;
  const timer = setTimeout(() => request.abort(), 10000);
  docStatus.textContent = "Открываем документ…";
  try {
    const response = await fetch("/api/documents/" + encodeURIComponent(id), {signal: request.signal});
    if (!response.ok) throw new Error();
    const doc = await response.json();
    if (activeDocument !== request) return;
    byId("documents-panel").dataset.view = "document";
    docTitle.textContent = doc.title;
    docTitle.title = doc.title;
    docStatus.textContent = [doc.status, source?.heading].filter(Boolean).join(" · ");
    docText.textContent = doc.text;
    list.hidden = true;
    docFilter.hidden = true;
    docText.hidden = false;
    byId("doc-navigation").hidden = true;
    allDocs.hidden = false;
    if (focus) docTitle.focus();
    documentBody = doc.text;
    printableDocument = {title: doc.title, text: doc.text, status: doc.status};
    byId("print-document").disabled = false;
    documentSource = null;
    byId("document-query").value = "";
    if (source) {
      const characters = Array.from(doc.text);
      const quote = characters.slice(source.start, source.end).join("");
      if (quote === source.quote && Number.isInteger(source.start) && Number.isInteger(source.end) &&
          source.start >= 0 && source.end <= characters.length && source.end > source.start) {
        documentSource = {start: characters.slice(0, source.start).join("").length,
          end: characters.slice(0, source.end).join("").length};
        selectedQuote = quote;
        quoteTools.hidden = false;
      } else docStatus.textContent = "Диапазон источника изменился. Показан полный документ.";
    }
    byId("document-search").hidden = false;
    byId("document-citation").hidden = !documentSource;
    renderDocumentSearch();
    if (documentSource) scrollDocumentTo(".source-highlight");
    else docText.scrollTop = 0;
    globalThis.WebWorkspace?.documentOpened(id, doc, !!documentSource);
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
  node.item.answerData = answer;
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
  const groups = new Map();
  if (sources.length) {
    const heading = document.createElement("h3"); heading.className = "answer-source-heading";
    heading.textContent = "Основания · " + new Set(sources.map(source => source.document_id)).size + " док.";
    node.body.append(heading);
  }
  for (const source of sources) {
    let group = groups.get(source.document_id);
    if (!group) {
      group = document.createElement("section");
      group.className = "source-group";
      const title = document.createElement("h4");
      title.textContent = source.title;
      group.append(title);
      if (source.status && !source.title.toLocaleLowerCase("ru").includes(source.status.toLocaleLowerCase("ru"))) {
        const meta = document.createElement("small"); meta.textContent = source.status; group.append(meta);
      }
      node.body.append(group); groups.set(source.document_id, group);
    }
    const excerpt = document.createElement("details");
    excerpt.className = "source-excerpt";
    const preview = document.createElement("summary");
    const quote = document.createElement("span"); quote.className = "quote-preview";
    quote.textContent = source.quote;
    preview.append(quote);
    preview.setAttribute("aria-label", "Развернуть цитату [" + source.n + "]");
    const full = document.createElement("blockquote"); full.textContent = source.quote;
    excerpt.append(preview, full);
    const button = document.createElement("button");
    button.type = "button"; button.className = "source";
    button.textContent = "[" + source.n + "] " + (source.heading || "Открыть в документе");
    button.addEventListener("click", () => openDocument(source.document_id, source));
    group.append(excerpt, button);
  }
  const copy = document.createElement("button");
  copy.type = "button"; copy.className = "copy-answer"; copy.textContent = "Копировать с источниками";
  copy.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(answerText(answer)); copy.textContent = "Скопировано"; globalThis.WebIcons?.set(copy, "check"); }
    catch { openCopyDialog(answerText(answer)); }
  });
  const share = document.createElement("button");
  share.type = "button"; share.className = "share-answer"; share.textContent = "Поделиться";
  share.addEventListener("click", async () => {
    const text = answerText(answer);
    share.disabled = true;
    try {
      if (typeof navigator.share === "function") {
        try { await navigator.share({title: "Ответ юридического ассистента", text}); return; }
        catch (error) { if (error.name === "AbortError") return; }
      }
      openCopyDialog(text, true);
    } finally { share.disabled = false; }
  });
  node.body.append(copy, share);
  globalThis.WebIcons?.set(copy, "copy");
  globalThis.WebIcons?.set(share, "share");
  globalThis.WebWorkspace?.answerSources(node, answer);
  if (answer.status === "clarify") renderClarification(node, answer);
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

function answerText(answer) {
  return answer.text + (answer.sources?.length ? "\n\nИсточники:\n" + answer.sources.map(source =>
    "[" + source.n + "] " + [source.title, source.heading, source.status].filter(Boolean).join(" · ") +
    "\n«" + source.quote + "»").join("\n\n") : "");
}
function openCopyDialog(text, sharing = false) {
  byId("copy-title").textContent = sharing ? "Поделиться ответом" : "Ответ с источниками";
  byId("copy-note").textContent = sharing ? "Скопируйте ответ с источниками и вставьте его в нужный мессенджер или письмо." : "Выделите текст и скопируйте его.";
  byId("copy-text").value = text;
  byId("copy-dialog-status").textContent = "";
  byId("copy-dialog").showModal(); byId("copy-text").select();
  byId("copy-text").scrollTop = 0;
}
byId("copy-dialog-button").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText(byId("copy-text").value); byId("copy-dialog-status").textContent = "Скопировано"; }
  catch { byId("copy-text").focus(); byId("copy-text").select(); byId("copy-dialog-status").textContent = "Скопируйте выделенный текст через меню устройства или Ctrl+C."; }
});
let printableDocument = null, printRequest = null;
byId("close-copy").addEventListener("click", () => byId("copy-dialog").close());
function preparePrint() {
  const host = byId("print-view"); host.replaceChildren();
  const title = document.createElement("h1");
  if (printRequest) {
    title.textContent = printRequest.title;
    const status = document.createElement("p"); status.textContent = printRequest.status || "";
    const content = document.createElement("p"); content.className = "printed-document"; content.textContent = printRequest.text;
    host.append(title, status, content); return;
  }
  title.textContent = savedChats.find(chat => chat.id === currentChat)?.title || "Юридический диалог";
  const date = document.createElement("p"); date.textContent = "Экспорт: " + new Date().toLocaleString("ru-RU");
  host.append(title, date);
  for (const item of log.querySelectorAll(".message")) {
    const article = document.createElement("article");
    const author = document.createElement("h2");
    const content = document.createElement("p");
    author.textContent = item.classList.contains("user") ? "Вы" : "Ассистент";
    content.textContent = item.answerData ? answerText(item.answerData) : item.querySelector(".message-body p")?.textContent || "";
    article.append(author, content); host.append(article);
  }
  if (!log.querySelector(".message")) { const empty = document.createElement("p"); empty.textContent = "В диалоге пока нет сообщений."; host.append(empty); }
}
globalThis.addEventListener?.("beforeprint", preparePrint);
globalThis.addEventListener?.("afterprint", () => { printRequest = null; });
function startPrint(doc = null) {
  printRequest = doc;
  preparePrint();
  try { window.print(); } catch {
    printRequest = null;
    byId(doc ? "document-search-status" : "input-error").textContent = "Не удалось открыть печать. Повторите попытку.";
  }
}
byId("print-dialogue").addEventListener("click", () => startPrint());
byId("print-document").addEventListener("click", () => { if (printableDocument) startPrint({...printableDocument}); });
function setDocumentsVisible(visible) {
  byId("workspace").classList[visible ? "remove" : "add"]("documents-collapsed");
  byId("toggle-documents").setAttribute("aria-expanded", String(visible));
  byId("toggle-documents").textContent = visible ? "Скрыть документы" : "Показать документы";
}
byId("toggle-documents").addEventListener("click", () => setDocumentsVisible(
  byId("toggle-documents").getAttribute("aria-expanded") !== "true"));
byId("new-dialogue").addEventListener("click", () => { if (!reset.disabled) reset.click(); });

function renderClarification(node, answer) {
  const form = document.createElement("form"); form.className = "clarification-form";
  const hint = document.createElement("p"); hint.textContent = "Дополните сведения для продолжения диалога:"; form.append(hint);
  const fields = answer.clarification_fields?.length ? answer.clarification_fields : [{code: "facts", label: "Уточнение"}];
  const inputs = [];
  for (const field of fields) {
    const label = document.createElement("label"); label.textContent = field.label;
    const value = document.createElement("input"); value.type = "text"; value.maxLength = 1000; value.autocomplete = "off";
    label.append(value); form.append(label); inputs.push({value, label: field.label});
  }
  const error = document.createElement("p"); error.setAttribute("role", "status");
  const submit = document.createElement("button"); submit.type = "submit"; submit.textContent = "Продолжить";
  form.append(error, submit);
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const text = inputs.filter(field => field.value.value.trim()).map(field => field.label + ": " + field.value.value.trim()).join("\n");
    if (!text) { error.textContent = "Заполните хотя бы одно поле."; inputs[0].value.focus(); return; }
    if (send.disabled || busy || navigating || !historyReady) { error.textContent = "Дождитесь готовности диалога."; return; }
    if (input.value.trim() && !await confirmAction("Заменить черновик?", "В поле вопроса есть текст. Заменить его уточнением и отправить?", "Отправить уточнение")) return;
    input.value = text; globalThis.MobileLayout?.resizeInput();
    sendController.start();
  });
  node.body.append(form);
}

let documentBody = "", documentSource = null, documentHits = [], documentHit = 0;
function scrollDocumentTo(selector) {
  const target = docText.querySelector(selector);
  target?.scrollIntoView({block: "center", inline: "nearest"});
}
function renderDocumentSearch(resetHit = true) {
  const query = byId("document-query").value.trim();
  documentHits = [];
  if (query) {
    const regex = new RegExp(query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "giu");
    for (const match of documentBody.matchAll(regex)) {
      documentHits.push({start: match.index, end: match.index + match[0].length});
      if (documentHits.length === 500) break;
    }
  }
  if (resetHit) documentHit = 0;
  const edges = new Set([0, documentBody.length]);
  for (const range of [...documentHits, ...(documentSource ? [documentSource] : [])]) { edges.add(range.start); edges.add(range.end); }
  const sorted = [...edges].sort((a, b) => a - b);
  docText.replaceChildren();
  for (let i = 0; i < sorted.length - 1; i++) {
    const start = sorted[i], end = sorted[i + 1];
    const hit = documentHits.findIndex(range => range.start <= start && range.end >= end);
    const cited = documentSource && documentSource.start <= start && documentSource.end >= end;
    const text = documentBody.slice(start, end);
    if (hit < 0 && !cited) { docText.append(text); continue; }
    const mark = document.createElement("mark"); mark.textContent = text;
    if (cited) mark.classList.add("source-highlight");
    if (hit >= 0) { mark.classList.add("document-hit"); if (hit === documentHit) mark.classList.add("current-hit"); }
    docText.append(mark);
  }
  byId("document-search-status").textContent = query ? documentHits.length ?
    (documentHit + 1) + " / " + documentHits.length + (documentHits.length === 500 ? "+" : "") : "Не найдено" : "";
  byId("document-prev").disabled = byId("document-next").disabled = !documentHits.length;
}
byId("document-query").addEventListener("input", () => { renderDocumentSearch(); scrollDocumentTo(".current-hit"); });
for (const [id, step] of [["document-prev", -1], ["document-next", 1]]) byId(id).addEventListener("click", () => {
  if (!documentHits.length) return;
  documentHit = (documentHit + step + documentHits.length) % documentHits.length;
  renderDocumentSearch(false); scrollDocumentTo(".current-hit");
});
byId("document-query").addEventListener("keydown", event => {
  if (event.key === "Enter") { event.preventDefault(); byId(event.shiftKey ? "document-prev" : "document-next").click(); }
});
byId("document-citation").addEventListener("click", () => scrollDocumentTo(".source-highlight"));

async function ask(question, existing, signal) {
  busy = true;
  const chatAtStart = currentChat;
  byId("new-dialogue").disabled = reset.disabled = true;
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
    byId("new-dialogue").disabled = reset.disabled = false;
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
let creatingChat;
async function ensureCurrentChat() {
  if (currentChat) return currentChat;
  if (!historyEnabled || !historyReady) throw new Error("Дождитесь загрузки серверной истории.");
  if (creatingChat) return creatingChat;
  creatingChat = (async () => {
    if (globalThis.WebWorkspace) await globalThis.WebWorkspace.leave();
    const previousNavigation = navigating;
    navigating = true;
    byId("new-dialogue").disabled = reset.disabled = true;
    try {
      const folderPath = ["all", "unfiled", "trash"].includes(selectedFolder) ? "" : "?folder_id=" + encodeURIComponent(selectedFolder);
      const chat = await historyRequest(folderPath, "POST");
      currentChat = chat.id; rememberChat(); savedChats.unshift(chat);
      await globalThis.WebWorkspace?.open(chat.id, input.value);
      await globalThis.WebWorkspace?.clearNewDraft().catch(() => {});
      return chat.id;
    } finally {
      navigating = previousNavigation; byId("new-dialogue").disabled = reset.disabled = navigating; renderHistory();
    }
  })();
  try { return await creatingChat; } finally { creatingChat = null; }
}
const sendController = SLComponent.mount(send.closest(".sl-component"), {
  async onSend({signal}) {
    if (navigating || !historyReady) {
      byId("input-error").textContent = "Дождитесь загрузки истории или нажмите «Обновить список».";
      throw new Error("history_unavailable");
    }
    if (historyEnabled && !globalThis.ChatQueue) {
      byId("input-error").textContent = "Не удалось загрузить очередь. Обновите страницу.";
      throw new Error("queue_unavailable");
    }
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
    if (historyEnabled && globalThis.ChatQueue) {
      navigating = true;
      byId("new-dialogue").disabled = reset.disabled = true; renderHistory();
      try {
        if (globalThis.WebWorkspace) await globalThis.WebWorkspace.leave();
        if (!currentChat) await ensureCurrentChat();
        await globalThis.ChatQueue.submit(question);
        if (!retry && input.value.trim() === question) input.value = "";
        globalThis.WebWorkspace?.captureDraft();
        await globalThis.WebWorkspace?.flushDraft().catch(() => {});
        globalThis.MobileLayout?.resizeInput();
        return {queued: true};
      } catch (error) {
        byId("input-error").textContent = error.message; throw error;
      } finally {
        navigating = false; byId("new-dialogue").disabled = reset.disabled = false; renderHistory();
      }
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
reset.addEventListener("click", async () => {
  if (busy || navigating) return;
  try { if (globalThis.WebWorkspace) await globalThis.WebWorkspace.leave(); }
  catch (error) { byId("input-error").textContent = error.message; return; }
  globalThis.MobileLayout?.close();
  if (selectedFolder === "trash") selectedFolder = "all";
  clearChat();
  if (globalThis.WebWorkspace) await globalThis.WebWorkspace.open(null);
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
  example.addEventListener("click", () => { input.value = example.textContent; globalThis.WebWorkspace?.captureDraft(); globalThis.MobileLayout?.resizeInput(); input.focus(); });
  example.disabled = false;
}
byId("new-dialogue").disabled = reset.disabled = false;
allDocs.disabled = false;
globalThis.WebWorkspace?.init({ensureChat: ensureCurrentChat, documents: () => catalog, answerText, copy: openCopyDialog,
  openChat: async id => {
    if (!await navigateHistory(async () => { await selectChat(id); await loadChatLists(); })) {
      throw new Error("Не удалось открыть диалог. Завершите текущее действие или обновите список.");
    }
  }});
loadDocuments();
loadHistory();
