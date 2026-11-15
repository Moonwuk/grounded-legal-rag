"use strict";
// Templates only compose visible draft text in the browser. Nothing here sends a question or calls the model.
(() => {
  const get = id => document.getElementById(id);
  const placeholder = /\{([^{}\n]{0,40})\}/g;
  const cardFields = ["contract", "counterparty", "event_date", "amount"];
  let library = null, active = null, manual = false, editing = null, editorId = null, submitted = null, required = new Set();

  async function request(path = "", method = "GET", body) {
    const response = await fetch("/api/question-templates" + path, {method, headers: {"Content-Type": "application/json"},
      ...(body === undefined ? {} : {body: JSON.stringify(body)}), signal: AbortSignal.timeout(10000)});
    if (!response.ok) {
      const result = await response.json().catch(() => ({}));
      const error = new Error(typeof result.detail === "string" ? result.detail : "Шаблоны недоступны. Повторите попытку.");
      error.status = response.status;
      throw error;
    }
    return response.status === 204 ? null : response.json();
  }
  const storage = () => Array.isArray(library?.own);
  const field = key => library.fields.find(item => item.key === key);
  const byToken = token => library.fields.find(item => item.token === token);
  const tokenList = () => library.fields.map(item => "{" + item.token + "}").join(", ");
  function fieldsIn(text) {
    const keys = [];
    for (const match of text.matchAll(placeholder)) {
      const item = byToken(match[1]);
      if (item && !keys.includes(item.key)) keys.push(item.key);
    }
    return keys;
  }
  function problem(text) {
    for (const match of text.matchAll(placeholder)) if (!byToken(match[1])) return "Неизвестное поле {" + match[1] + "}. Доступны: " + tokenList() + ".";
    const rest = text.replace(placeholder, "");
    return rest.includes("{") || rest.includes("}") ? "Фигурные скобки используются только для полей: " + tokenList() + "." : "";
  }
  function sortOwn() { library.own.sort((a, b) => a.title.localeCompare(b.title, "ru") || a.id.localeCompare(b.id)); }
  function action(text, label, handler) {
    const node = document.createElement("button"); node.type = "button"; node.textContent = text;
    node.setAttribute("aria-label", label);
    node.addEventListener("click", async () => { node.disabled = true; try { await handler(); } finally { if (node.isConnected) node.disabled = false; } });
    return node;
  }
  function status(message) { get("templates-status").textContent = message; }

  async function load() { library = await request(); if (storage()) sortOwn(); renderLibrary(); }
  function showLibrary() {
    active = null;
    get("templates-dialog").dataset.view = "library";
    get("template-library").hidden = false;
    get("template-fill").hidden = get("template-fill-actions").hidden = true;
  }
  async function openLibrary(message = "") {
    const dialog = get("templates-dialog");
    showLibrary();
    get("template-search").value = "";
    status(message || "Загружаем шаблоны…");
    if (!dialog.open) dialog.showModal();
    get("template-search").focus();
    try { await load(); status(message); } catch (error) { status(error.message); }
  }
  function renderLibrary() {
    if (!library) return;
    const query = get("template-search").value.trim().toLocaleLowerCase("ru");
    const matches = item => [item.title, item.description, item.text].join("\n").toLocaleLowerCase("ru").includes(query);
    const builtin = library.builtin.filter(matches), own = storage() ? library.own.filter(matches) : [];
    renderList(get("builtin-templates"), builtin, false);
    renderList(get("own-templates"), own, true);
    get("create-template").hidden = !storage();
    get("own-templates-status").textContent = !storage() ? "Свои шаблоны доступны после входа через защищённый адрес и включения серверной истории." :
      !library.own.length ? "Сохраните свой вариант кнопкой «+ Новый шаблон» или из меню своего вопроса в диалоге." :
      query && !own.length ? "Среди ваших шаблонов ничего не найдено." : "";
    if (query) status(builtin.length + own.length ? "Найдено: " + (builtin.length + own.length) : "Ничего не найдено. Измените запрос.");
  }
  function renderList(host, items, own) {
    host.replaceChildren();
    for (const item of items) {
      const row = document.createElement("li"); row.className = "template-item";
      const choose = document.createElement("button"); choose.type = "button"; choose.className = "template-choose";
      const title = document.createElement("strong"); title.textContent = item.title;
      const description = document.createElement("small"); description.textContent = item.description || item.text.split("\n")[0];
      choose.append(title, description);
      choose.addEventListener("click", () => selectTemplate(item));
      const actions = document.createElement("div"); actions.className = "template-item-actions";
      if (own) actions.append(action("Изменить", "Изменить шаблон: " + item.title, () => openEditor(item)),
        action("Копия", "Создать копию шаблона: " + item.title, () => duplicate(item)),
        action("Удалить", "Удалить шаблон: " + item.title, () => remove(item)));
      else if (storage()) actions.append(action("Копия в мои", "Скопировать в мои шаблоны: " + item.title, () => duplicate(item)));
      row.append(choose, actions); host.append(row);
    }
  }

  function selectTemplate(item) {
    active = item; manual = false;
    get("templates-dialog").dataset.view = "fill";
    get("template-library").hidden = true;
    get("template-fill").hidden = get("template-fill-actions").hidden = false;
    get("template-fill-title").textContent = item.title;
    get("template-fill-description").textContent = item.description;
    const host = get("template-fields"); host.replaceChildren();
    for (const key of item.fields) {
      const info = field(key), needed = item.required.includes(key);
      const label = document.createElement("label");
      const input = document.createElement("input");
      input.type = info.kind === "date" ? "date" : "text"; input.maxLength = info.max_length; input.autocomplete = "off";
      input.dataset.field = key; input.required = needed;
      input.addEventListener("input", rebuild);
      label.append(info.label + (needed ? " (обязательно)" : " (необязательно)"), input); host.append(label);
    }
    const chat = globalThis.WebWorkspace?.chatId(), usesCard = item.fields.some(key => cardFields.includes(key));
    get("template-from-matter").hidden = !usesCard;
    get("template-from-matter").disabled = !chat;
    get("template-matter-status").textContent = usesCard && !chat ? "Карточка дела есть только у сохранённого диалога." : "";
    get("template-fill-error").textContent = "";
    get("template-preview").value = build();
    updateState(); updateFooter();
    (host.querySelector("input") || get("template-preview")).focus();
  }
  function values() {
    return Object.fromEntries([...get("template-fields").querySelectorAll("input")].map(input => [input.dataset.field, input.value.trim()]));
  }
  function display(key, value) {
    // The core reads numeric dates in this form both in search and in checks of user facts.
    const date = key === "event_date" && /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
    return date ? date[3] + "." + date[2] + "." + date[1] : value;
  }
  function build() {
    const current = values(), lines = [];
    for (const line of active.text.split("\n")) {
      // An empty optional field removes its own line; an empty required one stays visible as {поле}.
      if (fieldsIn(line).some(key => !active.required.includes(key) && !current[key])) continue;
      lines.push(line.replace(placeholder, (match, token) => {
        const item = byToken(token);
        return item && current[item.key] ? display(item.key, current[item.key]) : match;
      }));
    }
    return lines.join("\n").trim();
  }
  const missing = text => fieldsIn(text).map(key => field(key).label);
  function updateState() {
    const absent = missing(get("template-preview").value);
    get("template-state").textContent = (manual ? "Текст изменён вручную, поля его больше не меняют. " : "") +
      (absent.length ? "Заполните: " + absent.join(", ") + "." : "Вопрос готов. Проверьте его перед добавлением.");
    get("template-rebuild").hidden = !manual;
  }
  function updateFooter() {
    const draft = !!get("question").value.trim();
    get("template-insert").textContent = draft ? "Добавить к вопросу" : "Добавить в вопрос";
    get("template-replace").hidden = !draft;
  }
  // Any edit makes an earlier "fill in" error stale; the state line keeps listing what is still missing.
  function rebuild() { if (!manual) get("template-preview").value = build(); get("template-fill-error").textContent = ""; updateState(); }
  async function fillFromCard() {
    const chat = globalThis.WebWorkspace?.chatId(), note = get("template-matter-status"), trigger = get("template-from-matter");
    if (!chat) { note.textContent = "Карточка дела есть только у сохранённого диалога."; return; }
    trigger.disabled = true; note.textContent = "Загружаем карточку дела…";
    try {
      const response = await fetch("/api/workspace/chats/" + encodeURIComponent(chat), {headers: {"Content-Type": "application/json"}, signal: AbortSignal.timeout(10000)});
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Карточка дела недоступна.");
      const filled = [], kept = [];
      for (const input of get("template-fields").querySelectorAll("input")) {
        const value = String(data.matter?.[input.dataset.field] || "").trim();
        if (!value) continue;
        // Values the user already typed are never overwritten.
        if (input.value.trim()) { if (input.value.trim() !== value) kept.push(field(input.dataset.field).label); continue; }
        input.value = value; filled.push(field(input.dataset.field).label);
      }
      note.textContent = filled.length ? "Подставлено из карточки: " + filled.join(", ") + "." + (kept.length ? " Заполненные вами поля не изменены: " + kept.join(", ") + "." : "") :
        kept.length ? "Поля уже заполнены вами, карточка их не меняет: " + kept.join(", ") + "." : "В карточке дела нет сведений для полей этого шаблона.";
      rebuild();
    } catch (error) { note.textContent = error.message; }
    finally { trigger.disabled = false; }
  }
  async function insert(replace) {
    const text = get("template-preview").value.trim(), error = get("template-fill-error");
    error.textContent = "";
    if (!text) { error.textContent = "Итоговый вопрос пуст."; return; }
    const absent = fieldsIn(text);
    if (absent.length) {
      error.textContent = "Заполните: " + absent.map(key => field(key).label).join(", ") + ". Шаблон не подставляет неизвестные значения.";
      (get("template-fields").querySelector('input[data-field="' + absent[0] + '"]') || get("template-preview")).focus();
      return;
    }
    try {
      if (replace) {
        if (!await confirmAction("Заменить текст вопроса?", "Текущий текст в поле вопроса будет заменён собранным вопросом.", "Заменить")) return;
        globalThis.WebWorkspace.replaceText(text);
      } else await globalThis.WebWorkspace.insertText(text);
      get("templates-dialog").close();
      get("question").focus();
    } catch (failure) { error.textContent = failure.message; }
  }

  function renderTokens() {
    const host = get("template-tokens-label").parentElement;
    for (const node of host.querySelectorAll("button")) node.remove();
    for (const item of library.fields) {
      const node = document.createElement("button"); node.type = "button"; node.textContent = "{" + item.token + "}";
      node.setAttribute("aria-label", "Вставить поле «" + item.label + "»");
      node.addEventListener("click", () => {
        const area = get("template-text"), start = area.selectionStart ?? area.value.length, end = area.selectionEnd ?? start;
        area.setRangeText("{" + item.token + "}", start, end, "end");
        area.focus(); renderRequired();
      });
      host.append(node);
    }
  }
  function renderRequired() {
    const host = get("template-required"), keys = fieldsIn(get("template-text").value);
    host.replaceChildren(host.querySelector("legend"));
    if (!keys.length) {
      const empty = document.createElement("p"); empty.className = "workspace-help";
      empty.textContent = "В тексте пока нет полей."; host.append(empty);
    }
    for (const key of keys) {
      const label = document.createElement("label"); label.className = "template-check";
      const input = document.createElement("input"); input.type = "checkbox"; input.checked = required.has(key);
      input.addEventListener("change", () => { if (input.checked) required.add(key); else required.delete(key); });
      label.append(input, field(key).label + " {" + field(key).token + "}"); host.append(label);
    }
  }
  function openEditor(template = null, preset = null) {
    editing = template; editorId = crypto.randomUUID(); submitted = null;
    const source = template || preset || {title: "", description: "", text: "", required: []};
    required = new Set(source.required || []);
    get("template-editor-title").textContent = template ? "Изменить шаблон" : "Новый шаблон";
    get("template-name").value = source.title; get("template-description").value = source.description || "";
    get("template-text").value = source.text;
    get("template-editor-error").textContent = "";
    renderTokens(); renderRequired();
    get("template-editor").showModal(); get("template-name").focus();
  }
  function lockEditor(value) {
    const dialog = get("template-editor"); dialog.dataset.saving = String(value);
    for (const node of dialog.querySelectorAll("button, input, textarea")) node.disabled = value;
  }
  async function saveTemplate(event) {
    event.preventDefault();
    if (get("template-editor").dataset.saving === "true") return;
    const text = get("template-text").value.trim(), error = get("template-editor-error");
    const body = {title: get("template-name").value.trim(), description: get("template-description").value.trim(), text,
      required: fieldsIn(text).filter(key => required.has(key))};
    error.textContent = !body.title ? "Укажите название шаблона." : !text ? "Введите текст шаблона." :
      text.length > 4000 ? "Текст шаблона — не более 4000 символов. Сократите его." : problem(text);
    if (error.textContent) return;
    lockEditor(true);
    try {
      let saved;
      if (editing) saved = await request("/" + encodeURIComponent(editing.id), "PUT", {...body, revision: editing.revision});
      else {
        // The same id makes a retry after a lost response idempotent; changed text gets a new id.
        const signature = JSON.stringify(body);
        if (submitted !== null && submitted !== signature) editorId = crypto.randomUUID();
        submitted = signature;
        saved = await request("", "POST", {...body, id: editorId});
      }
      library.own = [...library.own.filter(item => item.id !== saved.id), saved]; sortOwn();
      lockEditor(false); get("template-editor").close();
      const message = "Шаблон «" + saved.title + "» сохранён в разделе «Мои шаблоны».";
      if (get("templates-dialog").open) { showLibrary(); renderLibrary(); status(message); }
      else await openLibrary(message);
    } catch (failure) {
      error.textContent = failure.message + (failure.status === 409 && editing ? " Ваш текст остался в форме; закройте окно и откройте шаблон заново." : "");
      if (failure.status === 409) load().catch(() => {});
    } finally { lockEditor(false); }
  }
  async function duplicate(item) {
    try {
      const saved = await request("", "POST", {id: crypto.randomUUID(), title: (item.title + " (копия)").slice(0, 80),
        description: item.description || "", text: item.text, required: item.required});
      library.own.push(saved); sortOwn(); renderLibrary();
      status("Создана копия «" + saved.title + "». Её можно изменить.");
    } catch (error) { status(error.message); }
  }
  async function remove(item) {
    if (!await confirmAction("Удалить шаблон?", "Шаблон «" + item.title + "» будет удалён. Диалоги и черновики не изменятся.", "Удалить шаблон")) return;
    try { await request("/" + encodeURIComponent(item.id) + "?revision=" + item.revision, "DELETE"); }
    catch (error) {
      if (error.status !== 404) { status(error.message); await load().catch(() => {}); return; }
    }
    library.own = library.own.filter(entry => entry.id !== item.id); renderLibrary();
    status("Шаблон «" + item.title + "» удалён.");
  }
  async function saveQuestion(question) {
    try {
      if (!library) await load();
      if (!storage()) throw new Error("Свои шаблоны доступны после входа и включения серверной истории.");
      const first = question.split("\n")[0].trim();
      openEditor(null, {title: first.length > 80 ? first.slice(0, 79) + "…" : first, description: "", text: question.slice(0, 4000), required: []});
      if (question.length > 4000) get("template-editor-error").textContent = "Вопрос длиннее 4000 символов: в шаблон перенесено начало текста.";
    } catch (error) { get("input-error").textContent = error.message; }
  }

  get("open-templates").addEventListener("click", () => openLibrary());
  get("template-search").addEventListener("input", renderLibrary);
  get("create-template").addEventListener("click", () => openEditor());
  get("template-back").addEventListener("click", () => { showLibrary(); renderLibrary(); get("template-search").focus(); });
  get("template-from-matter").addEventListener("click", fillFromCard);
  get("template-preview").addEventListener("input", () => { manual = true; get("template-fill-error").textContent = ""; updateState(); });
  get("template-rebuild").addEventListener("click", async () => {
    if (!await confirmAction("Собрать текст заново?", "Ручные правки итогового вопроса будут заменены текстом по шаблону.", "Собрать заново")) return;
    manual = false; rebuild(); get("template-preview").focus();
  });
  get("template-fill").addEventListener("submit", event => { event.preventDefault(); insert(false); });
  get("template-insert").addEventListener("click", () => insert(false));
  get("template-replace").addEventListener("click", () => insert(true));
  get("template-text").addEventListener("input", renderRequired);
  get("template-editor-form").addEventListener("submit", saveTemplate);
  document.addEventListener("DOMContentLoaded", () => globalThis.WebIcons?.set(get("open-templates"), "template", undefined, false));
  get("open-templates").disabled = false;
  window.QuestionTemplates = {open: openLibrary, saveQuestion};
})();
