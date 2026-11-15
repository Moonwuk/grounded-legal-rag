"use strict";

(() => {
  const get = id => document.getElementById(id);
  const fieldNames = {contract: "Договор", counterparty: "Контрагент", event_date: "Дата события", amount: "Сумма", situation: "Обстоятельства"};
  let bridge, activeId = null, data = null, generation = 0, refreshVersion = 0, bindings = [], renderedCount = 0;
  let draft = null, draftTimer, typingVersion = 0, enabled = false, activityTimer, unread = new Set();
  let noteTarget = null, questionTarget = null, saved = [], displayedDocument = null, passage = null;
  const drafts = new Map();

  async function request(path, method = "GET", body) {
    const response = await fetch("/api/workspace" + path, {method, headers: {"Content-Type": "application/json"},
      ...(body === undefined ? {} : {body: JSON.stringify(body)}), signal: AbortSignal.timeout(10000), keepalive: method === "PUT" && !path.endsWith("/checklist") && path !== "/searches"});
    if (!response.ok) {
      const result = await response.json().catch(() => ({}));
      const error = new Error(typeof result.detail === "string" ? result.detail : "Не удалось сохранить изменения. Попробуйте ещё раз.");
      error.status = response.status;
      throw error;
    }
    return response.status === 204 ? null : response.json();
  }
  const pathFor = id => "/chats/" + encodeURIComponent(id);
  function button(text, action, className = "") {
    const node = document.createElement("button"); node.type = "button"; node.textContent = text; node.className = className;
    node.addEventListener("click", action); return node;
  }
  function lock(dialog, value) {
    dialog.dataset.saving = String(value);
    for (const node of dialog.querySelectorAll("button, input, textarea, select")) node.disabled = value;
  }
  function showDraftStatus(message = "") {
    get("draft-status").textContent = message;
    get("resolve-draft").hidden = !draft?.conflict;
  }
  function captureDraft() {
    typingVersion++;
    if (!draft || !enabled) return;
    draft.text = get("question").value;
    draft.dirty = draft.text !== draft.saved;
    clearTimeout(draftTimer);
    if (!draft.dirty) return showDraftStatus(draft.text ? "Черновик сохранён на сервере" : "");
    showDraftStatus(draft.conflict ? "Есть другая версия черновика" : "Сохраняем черновик…");
    if (!draft.conflict) draftTimer = setTimeout(() => flushDraft().catch(() => {}), 600);
  }
  async function flushDraft(target = draft) {
    clearTimeout(draftTimer);
    if (!target) return;
    if (target.pending) await target.pending;
    if (target.conflict) throw new Error("Сначала выберите версию черновика.");
    if (!target.dirty) return;
    const operation = async () => {
      while (target.dirty) {
        const text = target.text;
        try {
          const result = await request("/drafts/" + target.id, "PUT", {text, revision: target.revision});
          target.revision = result.revision; target.saved = text; target.dirty = target.text !== text;
          if (target === draft) showDraftStatus(target.dirty ? "Сохраняем черновик…" : target.text ? "Черновик сохранён на сервере" : "");
        } catch (error) {
          target.conflict = error.status === 409;
          if (target === draft) showDraftStatus(target.conflict ? "Черновик изменён на другом устройстве" : "Черновик пока не сохранён. Проверьте подключение.");
          throw error;
        }
      }
    };
    target.pending = operation();
    try { await target.pending; } finally { target.pending = null; }
  }
  async function leave() { captureDraft(); await flushDraft(); }
  function detach() {
    generation++; refreshVersion++; clearTimeout(draftTimer);
    activeId = null; data = null; draft = null; bindings = []; renderedCount = 0;
    get("open-matter").disabled = true; get("parent-dialogue").hidden = true;
    get("matter-summary").textContent = ""; showDraftStatus();
  }
  async function open(id, preservedText) {
    const token = ++generation, typed = typingVersion;
    activeId = id; data = null; draft = null;
    if (!enabled) return;
    showDraftStatus("Загружаем черновик…");
    try {
      const loaded = id ? await request(pathFor(id)) : await request("/drafts/new");
      if (generation !== token) return;
      data = id ? loaded : null;
      const text = id ? loaded.draft : loaded.text;
      const revision = id ? loaded.draft_revision : loaded.revision;
      const cached = drafts.get(id || "new");
      draft = {id: id || "new", text, saved: text, revision, dirty: false, conflict: false};
      if (cached?.dirty) {
        draft.text = cached.text; draft.dirty = cached.text !== text;
        draft.conflict = cached.revision !== revision && draft.dirty;
      } else if (preservedText !== undefined || typed !== typingVersion) {
        draft.text = preservedText === undefined ? get("question").value : preservedText;
        draft.dirty = draft.text !== text;
        draft.conflict = typed !== typingVersion && !!text && draft.dirty;
      }
      drafts.set(draft.id, draft);
      get("question").value = draft.text;
      globalThis.MobileLayout?.resizeInput();
      get("open-matter").disabled = false;
      showDraftStatus(draft.conflict ? "Есть другая версия черновика" : draft.text ? "Черновик сохранён на сервере" : "");
      reflectMatter(); updateBindings();
      if (draft.dirty && !draft.conflict) await flushDraft();
    } catch (error) {
      if (generation === token) {
        showDraftStatus(error.message + " Нажмите «Обновить список».");
        get("open-matter").disabled = true;
      }
    }
  }
  async function clearNewDraft() {
    if (!draft || draft.id === "new" || draft.dirty || draft.conflict) return;
    const previous = drafts.get("new");
    if (previous && !previous.conflict) { previous.text = ""; previous.dirty = previous.saved !== ""; await flushDraft(previous); }
  }
  function reflectMatter() {
    const matter = data?.matter || {};
    get("matter-summary").textContent = [matter.contract, matter.counterparty, matter.event_date].filter(Boolean).join(" · ");
    get("matter-summary").title = get("matter-summary").textContent;
    get("parent-dialogue").hidden = !data?.parent;
    get("parent-dialogue").title = data?.parent?.title || "";
  }
  async function refresh() {
    const id = activeId, token = generation, version = ++refreshVersion;
    if (!id || !enabled) return;
    try {
      const loaded = await request(pathFor(id));
      if (activeId !== id || generation !== token || refreshVersion !== version) return;
      data = loaded; reflectMatter(); updateBindings();
      const last = bindings.at(-1)?.turn;
      if (renderedCount && renderedCount === loaded.answers.length && last?.question === loaded.last_question &&
          last?.answer.text === loaded.last_answer && document.visibilityState === "visible") {
        await request(pathFor(id) + "/read", "PUT", {turn_key: loaded.answers.at(-1).turn_key});
        unread.delete(id); decorateHistory();
      }
    } catch (error) {
      if (activeId === id) for (const binding of bindings) binding.error.textContent = "Действия с ответом недоступны. Обновите список.";
    }
  }
  function beginTurns() { bindings = []; renderedCount = 0; }
  function addTurn(node, userNode, turn, index) {
    if (!activeId || !enabled) return;
    renderedCount = index + 1;
    const binding = {chat: activeId, index, turn, node, info: null};
    const edit = button("Изменить вопрос", () => editQuestion(binding, false), "edit-question");
    globalThis.WebIcons?.set(edit, "edit");
    const questionActions = document.createElement("div"); questionActions.className = "question-workspace-actions";
    questionActions.append(edit); userNode.append(questionActions);
    const actions = document.createElement("div"); actions.className = "answer-workspace-actions";
    const star = button("☆ Сохранить", () => toggleSaved(binding), "save-answer");
    const note = button("Заметка", () => editNote(binding), "note-answer");
    const branch = button("Продолжить в ветке", () => editQuestion(binding, true), "branch-answer");
    globalThis.WebIcons?.set(branch, "branch", undefined, false);
    const preview = document.createElement("p"); preview.className = "answer-note-preview"; preview.hidden = true;
    const error = document.createElement("p"); error.className = "answer-workspace-error"; error.setAttribute("role", "status");
    if (!["technical_error", "cancelled"].includes(turn.answer.status)) actions.append(star, note);
    actions.append(branch); node.body.append(actions, preview, error);
    Object.assign(binding, {edit, star, note, branch, preview, error}); bindings.push(binding); updateBinding(binding);
  }
  function updateBinding(binding) {
    if (binding.chat !== activeId) return;
    binding.info = data?.answers[binding.index];
    for (const node of [binding.edit, binding.star, binding.note, binding.branch]) node.disabled = !binding.info;
    const info = binding.info;
    binding.star.textContent = info?.saved ? "★ Сохранено" : "☆ Сохранить";
    binding.star.setAttribute("aria-pressed", String(!!info?.saved));
    globalThis.WebIcons?.set(binding.star, "star", info?.saved ? "Убрать из избранного" : "Сохранить в избранное");
    binding.note.textContent = info?.note ? "Изменить заметку" : "Заметка";
    globalThis.WebIcons?.set(binding.note, "note", undefined, false);
    binding.preview.textContent = info?.note ? "Ваша заметка: " + info.note : "";
    binding.preview.hidden = !info?.note;
  }
  function updateBindings() { for (const binding of bindings) updateBinding(binding); }
  async function writeAnnotation(target, savedValue, noteValue) {
    const result = await request(pathFor(target.chat) + "/answers/" + target.index, "PUT",
      {revision: target.info.revision, turn_key: target.info.turn_key, saved: savedValue, note: noteValue});
    refreshVersion++;
    if (target.chat === activeId && data) { data.answers[target.index] = result; updateBindings(); }
  }
  async function toggleSaved(target) {
    if (!target.info || target.star.disabled) return;
    target.star.disabled = true; target.error.textContent = "";
    try { await writeAnnotation(target, !target.info.saved, target.info.note); }
    catch (error) { target.error.textContent = error.message; await refresh(); }
    finally { if (target.star.isConnected) target.star.disabled = false; }
  }
  function editNote(target) {
    if (!target.info) return;
    noteTarget = {...target, info: {...target.info}};
    get("note-question").textContent = target.turn.question;
    get("answer-note").value = target.info.note;
    get("note-error").textContent = "";
    get("note-dialog").showModal(); get("answer-note").focus();
  }
  function editQuestion(target, includeAnswer) {
    if (!target.info) return;
    questionTarget = {type: "branch", chat: target.chat, index: target.index, key: target.info.turn_key,
      includeAnswer, id: crypto.randomUUID()};
    get("copy-branch-checklist-label").hidden = false;
    get("copy-branch-checklist").checked = false;
    get("question-dialog-title").textContent = includeAnswer ? "Продолжить в новой ветке" : "Изменить вопрос в новой ветке";
    get("question-edit-help").textContent = includeAnswer ? "Ветка сохранит историю до этого ответа. Следующий вопрос можно отправить после её создания." :
      "В новой ветке останутся предыдущие сообщения и ваш исправленный вопрос в поле ввода. Исходный диалог сохранится целиком.";
    get("question-edit-text").value = includeAnswer ? "" : target.turn.question;
    get("save-question-edit").textContent = "Создать ветку";
    get("question-edit-error").textContent = "";
    get("question-dialog").showModal(); get("question-edit-text").focus();
  }
  function editQueued(chat, job) {
    questionTarget = {type: "queue", chat, job: job.id, expected: job.question};
    get("copy-branch-checklist-label").hidden = true;
    get("question-dialog-title").textContent = "Изменить вопрос в очереди";
    get("question-edit-help").textContent = "Изменение доступно, пока вопрос ожидает обработки. Его место в очереди сохранится.";
    get("question-edit-text").value = job.question; get("save-question-edit").textContent = "Сохранить вопрос";
    get("question-edit-error").textContent = ""; get("question-dialog").showModal(); get("question-edit-text").focus();
  }
  async function insertText(text) {
    const value = [get("question").value.trim(), text].filter(Boolean).join("\n\n");
    if (value.length > 10000) throw new Error("Вопрос получился длиннее 10 000 символов. Сократите черновик или выделенный фрагмент.");
    get("question").value = value; captureDraft(); globalThis.MobileLayout?.resizeInput();
  }
  async function showSaved() {
    get("saved-dialog").showModal(); get("saved-status").textContent = "Загружаем…";
    get("saved-answers").replaceChildren();
    try { saved = await request("/saved"); renderSaved(); }
    catch (error) { get("saved-status").textContent = error.message; }
  }
  function renderSaved() {
    const query = get("saved-search").value.trim().toLocaleLowerCase("ru");
    const filter = get("saved-filter").value;
    const visible = saved.filter(item => (filter !== "saved" || item.saved) && (filter !== "notes" || item.note) &&
      [item.title, item.question, item.answer.text, item.note].join("\n").toLocaleLowerCase("ru").includes(query));
    get("saved-status").textContent = visible.length ? "Найдено: " + visible.length : "Пока ничего нет. Сохраните ответ или добавьте заметку в диалоге.";
    const host = get("saved-answers"); host.replaceChildren();
    for (const item of visible) {
      const card = document.createElement("article"); card.className = "saved-answer";
      const title = document.createElement("h3"); title.textContent = (item.saved ? "★ " : "") + item.question;
      const meta = document.createElement("small"); meta.textContent = item.title;
      const preview = document.createElement("p"); preview.className = "saved-preview"; preview.textContent = item.answer.text;
      card.append(meta, title, preview);
      if (item.note) { const note = document.createElement("p"); note.className = "answer-note-preview"; note.textContent = "Ваша заметка: " + item.note; card.append(note); }
      const actions = document.createElement("div"); actions.className = "answer-workspace-actions";
      actions.append(button("Открыть ответ и источники", async () => {
        try {
          await leave(); get("saved-dialog").close();
          await bridge.openChat(item.chat_id);
          const target = bindings.find(b => b.index === item.turn_index);
          target?.node.item.scrollIntoView({block: "start"});
        } catch (error) { get("saved-status").textContent = error.message; }
      }), button("Копировать с источниками", async () => {
        try { await navigator.clipboard.writeText(bridge.answerText(item.answer)); }
        catch { bridge.copy(bridge.answerText(item.answer)); }
      }));
      card.append(actions); host.append(card);
    }
  }
  function decorateHistory() {
    for (const row of document.querySelectorAll("#chat-list > li")) {
      row.querySelector(".unread-badge")?.remove();
      if (!unread.has(row.dataset.chatId) || row.dataset.trashed === "true" || row.dataset.chatId === activeId) continue;
      const badge = document.createElement("span"); badge.className = "unread-badge"; badge.textContent = "Новый ответ";
      row.querySelector(".chat-select")?.append(badge);
    }
  }
  async function pollActivity() {
    clearTimeout(activityTimer);
    if (!enabled) return;
    try {
      if (document.visibilityState === "visible") {
        const result = await request("/activity"); unread = new Set(result.filter(item => item.unread).map(item => item.id)); decorateHistory();
      }
    } catch { /* Queue and history report connection failures separately. */ }
    activityTimer = setTimeout(pollActivity, 8000);
  }
  function setEnabled(value) {
    enabled = value; get("open-saved").disabled = !value;
    globalThis.WorkspaceTools?.setEnabled(value);
    if (value) pollActivity(); else clearTimeout(activityTimer);
  }
  function readingPositions() {
    try {
      const value = JSON.parse(localStorage.getItem("psb-document-positions") || "{}");
      return value && typeof value === "object" && !Array.isArray(value) ? value : {};
    } catch { return {}; }
  }
  function rememberPosition() {
    if (!displayedDocument) return;
    const positions = readingPositions();
    positions[displayedDocument.id] = {text: get("doc-text").scrollTop, panel: get("documents-panel").scrollTop};
    try { localStorage.setItem("psb-document-positions", JSON.stringify(positions)); } catch { /* Optional reading position. */ }
  }
  function beforeDocument() {
    rememberPosition(); displayedDocument = null; passage = null;
    get("document-workspace-actions").hidden = true; get("ask-selection").disabled = true;
  }
  function documentOpened(id, doc, hasSource, manual) {
    if (manual) globalThis.WorkspaceTools?.rememberDocument(id);
    displayedDocument = {id, ...doc}; passage = null;
    get("document-workspace-actions").hidden = false;
    get("selection-status").textContent = "Выделите фрагмент текста.";
    if (!hasSource) {
      const position = readingPositions()[id];
      if (position) requestAnimationFrame(() => {
        if (displayedDocument?.id !== id) return;
        get("doc-text").scrollTop = Number(position.text) || 0; get("documents-panel").scrollTop = Number(position.panel) || 0;
      });
    }
  }
  function selectionChanged() {
    if (!displayedDocument) return;
    const selection = document.getSelection();
    if (!selection?.rangeCount || selection.isCollapsed || !get("doc-text").contains(selection.anchorNode) || !get("doc-text").contains(selection.focusNode)) return;
    const text = selection.toString().trim();
    passage = text && text.length <= 6000 ? {text, title: displayedDocument.title, id: displayedDocument.id} : null;
    get("ask-selection").disabled = !passage;
    get("selection-status").textContent = text.length > 6000 ? "Выберите фрагмент до 6000 символов." : "Выделено символов: " + text.length;
  }
  function openPassage() {
    if (!passage) return;
    get("passage-document").textContent = passage.title; get("passage-quote").textContent = passage.text;
    get("passage-question").value = ""; get("passage-error").textContent = "";
    get("passage-dialog").showModal(); get("passage-question").focus();
  }
  function init(api) {
    bridge = api;
    globalThis.WorkspaceTools?.init(api, request, button, key => {
      const info = data?.answers.find(answer => answer.turn_key === key && answer.saved);
      const binding = info && bindings.find(item => item.index === info.turn_index);
      if (!binding) throw new Error("Связанный ответ недоступен. Обновите диалог.");
      return binding.node.item;
    });
    for (const node of document.querySelectorAll("[data-close]")) node.addEventListener("click", () => {
      const dialog = get(node.dataset.close); if (dialog.dataset.saving !== "true") dialog.close();
    });
    for (const dialog of document.querySelectorAll(".workspace-dialog")) dialog.addEventListener("cancel", event => { if (dialog.dataset.saving === "true") event.preventDefault(); });
    get("question").addEventListener("input", captureDraft);
    get("open-saved").addEventListener("click", showSaved);
    get("saved-search").addEventListener("input", renderSaved); get("saved-filter").addEventListener("change", renderSaved);
    get("parent-dialogue").addEventListener("click", async () => {
      try { if (data?.parent) await bridge.openChat(data.parent.id); }
      catch (error) { get("input-error").textContent = error.message; }
    });
    get("open-matter").addEventListener("click", async () => {
      try {
        await bridge.ensureChat();
        const loaded = await request(pathFor(activeId)); data = loaded;
        const form = get("matter-form");
        for (const name of Object.keys(fieldNames)) form.elements[name].value = data.matter[name] || "";
        form.dataset.revision = data.matter_revision; form.dataset.chat = activeId;
        get("matter-error").textContent = ""; get("matter-dialog").showModal(); form.elements.contract.focus();
        globalThis.WorkspaceTools?.openChecklist(activeId);
      } catch (error) { get("input-error").textContent = error.message; }
    });
    get("matter-form").addEventListener("submit", async event => {
      event.preventDefault(); const dialog = get("matter-dialog"), form = get("matter-form");
      const matter = Object.fromEntries(Object.keys(fieldNames).map(name => [name, form.elements[name].value.trim()]));
      lock(dialog, true); get("matter-error").textContent = "";
      try {
        const result = await request(pathFor(form.dataset.chat) + "/matter", "PUT", {matter, revision: Number(form.dataset.revision)});
        if (activeId === form.dataset.chat) { Object.assign(data, result); reflectMatter(); }
        dialog.close();
      } catch (error) { get("matter-error").textContent = error.message; }
      finally { lock(dialog, false); }
    });
    get("insert-matter").addEventListener("click", async () => {
      const form = get("matter-form");
      const text = Object.entries(fieldNames).filter(([name]) => form.elements[name].value.trim()).map(([name, label]) => label + ": " + form.elements[name].value.trim()).join("\n");
      try { if (!text) throw new Error("Заполните сведения, которые хотите добавить."); await insertText(text); get("matter-dialog").close(); globalThis.MobileLayout?.close(); get("question").focus(); }
      catch (error) { get("matter-error").textContent = error.message; }
    });
    get("note-form").addEventListener("submit", async event => {
      event.preventDefault(); const target = noteTarget, dialog = get("note-dialog"), text = get("answer-note").value;
      lock(dialog, true); get("note-error").textContent = "";
      try { await writeAnnotation(target, !!target.info.saved, text); dialog.close(); }
      catch (error) { get("note-error").textContent = error.message; }
      finally { lock(dialog, false); }
    });
    get("question-edit-form").addEventListener("submit", async event => {
      event.preventDefault(); const target = questionTarget, dialog = get("question-dialog"), text = get("question-edit-text").value.trim();
      if (!text && (target.type === "queue" || !target.includeAnswer)) { get("question-edit-error").textContent = "Введите вопрос."; return; }
      lock(dialog, true); get("question-edit-error").textContent = "";
      try {
        if (target.type === "queue") {
          await request(pathFor(target.chat) + "/queued/" + target.job, "PUT", {expected_question: target.expected, question: text});
          await globalThis.ChatQueue?.refresh(); dialog.close();
        } else {
          await leave();
          const copyChecklist = get("copy-branch-checklist").checked;
          if (target.submittedText !== undefined && (target.submittedText !== text || target.copyChecklist !== copyChecklist))
            target.id = crypto.randomUUID();
          target.copyChecklist = copyChecklist;
          target.submittedText = text;
          const result = await request(pathFor(target.chat) + "/branch", "POST", {id: target.id, index: target.index, turn_key: target.key, include_answer: target.includeAnswer, draft: text, ...(copyChecklist ? {copy_checklist: true} : {})});
          await bridge.openChat(result.id); dialog.close(); get("question").focus();
        }
      } catch (error) { get("question-edit-error").textContent = error.message; }
      finally { lock(dialog, false); }
    });
    get("ask-selection").addEventListener("click", openPassage);
    document.addEventListener("selectionchange", selectionChanged);
    for (const node of document.querySelectorAll("[data-passage]")) node.addEventListener("click", () => { get("passage-question").value = node.dataset.passage; });
    get("passage-form").addEventListener("submit", async event => {
      event.preventDefault(); const question = get("passage-question").value.trim();
      try {
        if (!question) throw new Error("Введите вопрос о фрагменте.");
        await insertText(question + "\n\nДокумент: " + get("passage-document").textContent + "\nВыделенный фрагмент:\n«" + get("passage-quote").textContent + "»");
        get("passage-dialog").close(); globalThis.MobileLayout?.close(); get("question").focus();
      } catch (error) { get("passage-error").textContent = error.message; }
    });
    let positionTimer;
    for (const id of ["doc-text", "documents-panel"]) get(id).addEventListener("scroll", () => { clearTimeout(positionTimer); positionTimer = setTimeout(rememberPosition, 250); }, {passive: true});
    get("resolve-draft").addEventListener("click", async () => {
      if (!draft) return;
      try {
        const remote = await request("/drafts/" + draft.id);
        get("draft-local").value = draft.text; get("draft-remote").value = remote.text;
        const dialog = get("draft-conflict-dialog"); dialog.dataset.revision = remote.revision;
        dialog.dataset.draft = draft.id; get("draft-conflict-error").textContent = ""; dialog.showModal();
      } catch (error) { showDraftStatus(error.message); }
    });
    for (const [id, remote] of [["draft-keep-local", false], ["draft-use-remote", true]]) get(id).addEventListener("click", async () => {
      const dialog = get("draft-conflict-dialog"); if (!draft || draft.id !== dialog.dataset.draft) return;
      lock(dialog, true);
      try {
        draft.revision = Number(dialog.dataset.revision); draft.saved = get("draft-remote").value;
        draft.text = remote ? draft.saved : get("draft-local").value; draft.dirty = draft.text !== draft.saved; draft.conflict = false;
        get("question").value = draft.text; globalThis.MobileLayout?.resizeInput();
        await flushDraft(); showDraftStatus(draft.text ? "Черновик сохранён на сервере" : ""); dialog.close();
      } catch (error) { get("draft-conflict-error").textContent = error.message; }
      finally { lock(dialog, false); }
    });
    document.addEventListener("visibilitychange", () => { if (document.hidden) { captureDraft(); flushDraft().catch(() => {}); rememberPosition(); } else { pollActivity(); refresh(); } });
    window.addEventListener("pagehide", () => { captureDraft(); flushDraft().catch(() => {}); rememberPosition(); });
  }
  window.WebWorkspace = {init, open, detach, leave, clearNewDraft, captureDraft, flushDraft, refresh, beginTurns,
    addTurn, setEnabled, decorateHistory, editQueued, beforeDocument, documentOpened};
})();
