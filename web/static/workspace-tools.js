"use strict";

(() => {
  const get = id => document.getElementById(id);
  let api, request, button, locateAnswer;
  let enabled = false, catalogShown = false;
  let scope, searchOpener, searchState, renaming, searchBusy = false;
  let recentWrite = Promise.resolve();
  let chat, tasks, editing, taskBusy = false;

  function catalogVisible(value) {
    catalogShown = value;
    if (!value) get("recent-documents").open = false;
    get("catalog-tools").hidden = !enabled || !value || !api.catalog().length;
  }

  function setEnabled(value) {
    enabled = value;
    catalogVisible(catalogShown);
    get("open-picker-searches").hidden = !value;
  }

  function searchStatus(message) { get("searches-status").textContent = message; }

  async function showSearches(targetScope, opener) {
    scope = targetScope;
    searchOpener = opener;
    searchState = null;
    clearSearchForm();
    get("searches-list").replaceChildren();
    get("save-search").disabled = true;
    searchStatus("Загружаем поиски…");
    get("searches-dialog").showModal();
    // A reopened dialog must not receive an earlier response.
    const token = get("searches-dialog");
    const operation = request("/searches");
    activeSearchLoad = operation;
    try {
      const result = await operation;
      if (activeSearchLoad !== operation || !token.open) return;
      searchState = result;
      renderSearches();
    } catch (error) {
      if (activeSearchLoad === operation) searchStatus(error.message);
    }
  }
  let activeSearchLoad;

  function clearSearchForm() {
    renaming = null;
    get("saved-search-title").value = "";
    get("save-search").textContent = "Сохранить текущий поиск";
    get("cancel-search-rename").hidden = true;
  }

  function renderSearches() {
    const host = get("searches-list");
    host.replaceChildren();
    get("save-search").disabled = !searchState;
    const items = searchState.items.filter(item => item.scope === scope);
    searchStatus(items.length ? "" : "Для этого экрана пока нет сохранённых поисков.");
    for (const item of items) {
      const row = document.createElement("li");
      const title = document.createElement("strong");
      title.textContent = item.title;
      const actions = document.createElement("div");
      actions.className = "workspace-tool-actions";
      actions.append(button("Применить", () => {
        if (searchBusy) return;
        try { api.restoreSearch(item); get("searches-dialog").close(); }
        catch (error) { searchStatus(error.message); }
      }), button("Переименовать", () => {
        if (searchBusy) return;
        renaming = item.id;
        get("saved-search-title").value = item.title;
        get("save-search").textContent = "Сохранить название";
        get("cancel-search-rename").hidden = false;
        get("saved-search-title").focus();
      }), button("Удалить", async () => {
        if (searchBusy || !await api.confirm("Удалить поиск?", "Будут удалены только сохранённые параметры.", "Удалить поиск")) return;
        await saveSearches(searchState.items.filter(value => value.id !== item.id));
      }));
      row.append(title, actions);
      host.append(row);
    }
  }

  async function saveSearches(items) {
    if (searchBusy || !searchState) return;
    searchBusy = true;
    const dialog = get("searches-dialog");
    dialog.dataset.saving = "true";
    get("save-search").disabled = true;
    try {
      searchState = await request("/searches", "PUT", {items, revision: searchState.revision});
      clearSearchForm();
      renderSearches();
    } catch (error) {
      searchStatus(error.message + (error.status === 409 ? " Закройте и откройте список снова." : ""));
    } finally {
      searchBusy = false;
      dialog.dataset.saving = "false";
      get("save-search").disabled = false;
    }
  }

  function recentStatus(message) { get("recent-documents-status").textContent = message; }

  async function renderRecent() {
    const operation = recentWrite.then(() => request("/recent-documents"));
    recentLoad = operation;
    try {
      const items = await operation;
      if (operation !== recentLoad) return;
      const host = get("recent-documents-list");
      host.replaceChildren();
      for (const item of items) {
        const row = document.createElement("li");
        if (item.available) row.append(button(item.title, () => api.openDocument(item.document_id)));
        else row.textContent = item.title + " · недоступен";
        host.append(row);
      }
      get("clear-recent-documents").hidden = !items.length;
      recentStatus(items.length ? "" : "Пока нет недавно открытых документов.");
    } catch (error) {
      if (operation === recentLoad) recentStatus(error.message);
    }
  }
  let recentLoad;

  function rememberDocument(document_id) {
    if (!enabled) return;
    recentWrite = recentWrite.then(() => request("/recent-documents", "PUT", {document_id}))
      .catch(() => recentStatus("Не удалось сохранить документ в недавних."));
  }

  async function openChecklist(id) {
    chat = id;
    tasks = null;
    editing = null;
    get("checklist-items").replaceChildren();
    get("checklist-count").textContent = "";
    get("checklist-status").textContent = "Загружаем задачи…";
    get("add-checklist-item").disabled = true;
    get("reload-checklist").disabled = true;
    const operation = request("/chats/" + encodeURIComponent(id) + "/checklist");
    activeTaskLoad = operation;
    try {
      const result = await operation;
      if (operation !== activeTaskLoad) return;
      tasks = result;
      renderChecklist();
    } catch (error) {
      if (operation === activeTaskLoad) get("checklist-status").textContent = error.message;
    } finally {
      if (operation === activeTaskLoad) get("reload-checklist").disabled = false;
    }
  }
  let activeTaskLoad;

  function renderChecklist() {
    if (!tasks) return;
    const host = get("checklist-items");
    host.replaceChildren();
    const filter = get("checklist-filter").value;
    const finished = tasks.items.filter(item => item.done).length;
    get("checklist-count").textContent = "· " + finished + " из " + tasks.items.length + " выполнено";
    const status = get("checklist-status");
    status.textContent = "";
    for (const [index, item] of tasks.items.entries()) {
      if ((filter === "open" && item.done) || (filter === "done" && !item.done)) continue;
      const row = document.createElement("li");
      row.dataset.taskId = item.id;
      const label = document.createElement("label");
      label.className = "workspace-check-option";
      const check = document.createElement("input");
      check.type = "checkbox";
      check.checked = item.done;
      check.addEventListener("change", async () => {
        const done = check.checked;
        check.checked = item.done;
        await saveTasks(tasks.items.map(value => value.id === item.id ? {...value, done} : value), item.id);
      });
      label.append(check, item.title);
      row.append(label);
      if (item.comment) {
        const comment = document.createElement("p");
        comment.className = "workspace-task-comment";
        comment.textContent = item.comment;
        row.append(comment);
      }
      const actions = document.createElement("div");
      actions.className = "workspace-tool-actions";
      const edit = button("Изменить", () => showTask(item));
      actions.append(edit, button("Удалить", async () => {
        if (taskBusy || !await api.confirm("Удалить задачу?", item.title, "Удалить задачу")) return;
        await saveTasks(tasks.items.filter(value => value.id !== item.id));
      }));
      for (const [direction, text] of [[-1, "Выше"], [1, "Ниже"]]) {
        const target = index + direction;
        const move = button(text, () => {
          const items = [...tasks.items];
          [items[index], items[target]] = [items[target], items[index]];
          return saveTasks(items, item.id);
        });
        move.disabled = target < 0 || target >= tasks.items.length;
        move.setAttribute("aria-label", text + ": " + item.title);
        actions.append(move);
      }
      if (item.document_id) {
        const doc = api.catalog().find(value => value.id === item.document_id);
        actions.append(button(doc ? "Открыть документ" : "Документ недоступен", () => {
          if (!doc) return;
          get("matter-dialog").close();
          api.openDocument(doc.id);
        }));
        actions.lastChild.disabled = !doc;
      }
      if (item.answer_key) {
        const answer = tasks.answers.some(value => value.key === item.answer_key);
        actions.append(button(answer ? "Открыть ответ" : "Ответ недоступен", () => {
          try {
            const node = locateAnswer(item.answer_key);
            get("matter-dialog").close();
            node.tabIndex = -1;
            node.focus();
            node.scrollIntoView({block: "start"});
          } catch (error) { status.textContent = error.message; }
        }));
        actions.lastChild.disabled = !answer;
      }
      row.append(actions);
      host.append(row);
    }
    if (!host.children.length) status.textContent = tasks.items.length ? "В этом фильтре задач нет." : "В карточке пока нет задач.";
    get("add-checklist-item").disabled = tasks.items.length >= 40;
    if (tasks.items.length >= 40) status.textContent = "В карточке можно сохранить до 40 задач.";
  }

  function selectOptions(select, entries, selected) {
    select.replaceChildren(new Option("Без ссылки", ""));
    for (const [key, title] of entries) select.append(new Option(title, key));
    if (selected && !entries.some(([key]) => key === selected)) select.append(new Option("Связанный материал недоступен", selected));
    select.value = selected || "";
  }

  function showTask(item) {
    if (taskBusy || !tasks) return;
    editing = item;
    const form = get("task-form");
    form.elements.title.value = item?.title || "";
    form.elements.comment.value = item?.comment || "";
    selectOptions(form.elements.document_id, api.catalog().map(doc => [doc.id, doc.title]), item?.document_id);
    selectOptions(form.elements.answer_key, tasks.answers.map(answer => [answer.key, answer.title]), item?.answer_key);
    get("task-error").textContent = "";
    get("task-dialog").showModal();
    form.elements.title.focus();
  }

  async function saveTasks(items, focusId, fromEditor = false) {
    if (taskBusy || !tasks) return;
    taskBusy = true;
    const dialog = get(fromEditor ? "task-dialog" : "matter-dialog");
    const errorNode = get(fromEditor ? "task-error" : "checklist-status");
    dialog.dataset.saving = "true";
    const host = get("checklist-items");
    host.inert = true;
    get("reload-checklist").disabled = true;
    get("add-checklist-item").disabled = true;
    get("task-form").querySelector('[type="submit"]').disabled = true;
    let saved = false;
    try {
      const updated = await request("/chats/" + encodeURIComponent(chat) + "/checklist", "PUT", {items, revision: tasks.revision});
      Object.assign(tasks, updated);
      if (fromEditor) dialog.close();
      renderChecklist();
      saved = true;
    } catch (error) { errorNode.textContent = error.message; }
    finally {
      dialog.dataset.saving = "false";
      taskBusy = false;
      host.inert = false;
      if (saved) {
        const focusRow = [...host.children].find(row => row.dataset.taskId === focusId);
        (focusRow?.querySelector("input") || get("checklist-filter")).focus();
      }
      get("reload-checklist").disabled = false;
      get("add-checklist-item").disabled = tasks.items.length >= 40;
      get("task-form").querySelector('[type="submit"]').disabled = false;
    }
  }

  function init(bridge, requester, makeButton, answerLocator) {
    api = bridge; request = requester; button = makeButton; locateAnswer = answerLocator;
    const dialog = get("searches-dialog");
    for (const [id, value] of [["open-catalog-searches", "catalog"], ["open-picker-searches", "picker"]]) {
      get(id).addEventListener("click", event => showSearches(value, event.currentTarget));
    }
    dialog.addEventListener("close", () => searchOpener?.focus());
    get("cancel-search-rename").addEventListener("click", clearSearchForm);
    get("saved-search-form").addEventListener("submit", event => {
      event.preventDefault();
      if (!searchState || searchBusy) return;
      const title = get("saved-search-title").value.trim();
      if (!title) return searchStatus("Введите название поиска.");
      const items = renaming ? searchState.items.map(item => item.id === renaming ? {...item, title} : item) :
        [...searchState.items, {id: crypto.randomUUID(), title, scope, ...api.captureSearch(scope)}];
      saveSearches(items);
    });
    get("recent-documents").addEventListener("toggle", event => { if (event.currentTarget.open) renderRecent(); });
    get("clear-recent-documents").addEventListener("click", async () => {
      if (!await api.confirm("Очистить недавние документы?", "Документы и диалоги останутся на месте.", "Очистить историю")) return;
      recentWrite = recentWrite.then(async () => {
        try { await request("/recent-documents", "DELETE"); }
        catch (error) { recentStatus(error.message); return false; }
        return true;
      });
      if (await recentWrite) renderRecent();
    });
    get("checklist-filter").addEventListener("change", () => renderChecklist());
    get("reload-checklist").addEventListener("click", () => openChecklist(chat));
    get("add-checklist-item").addEventListener("click", () => showTask(null));
    get("task-form").addEventListener("submit", event => {
      event.preventDefault();
      if (!tasks || taskBusy) return;
      const fields = event.currentTarget.elements;
      const title = fields.title.value.trim();
      if (!title) { get("task-error").textContent = "Введите название задачи."; return; }
      const item = {id: editing?.id || crypto.randomUUID(), title, comment: fields.comment.value.trim(),
        done: editing?.done || false, document_id: fields.document_id.value || null, answer_key: fields.answer_key.value || null};
      saveTasks(editing ? tasks.items.map(value => value.id === editing.id ? item : value) : [...tasks.items, item], item.id, true);
    });
  }

  window.WorkspaceTools = {init, setEnabled, catalogVisible, rememberDocument, openChecklist};
})();
