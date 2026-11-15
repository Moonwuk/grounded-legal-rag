"use strict";
// A brief shows saved answers verbatim. Building, saving, copying or printing it never sends a question or calls the model.
(() => {
  const get = id => document.getElementById(id);
  const excluded = new Set(["technical_error", "cancelled"]);
  const cardLabels = [["contract", "Договор"], ["counterparty", "Контрагент"], ["event_date", "Дата события"],
    ["amount", "Сумма и валюта"], ["situation", "Обстоятельства и рабочие заметки"]];
  const reviewNames = {sources_viewed: "Источники просмотрены", needs_check: "Нужна дополнительная проверка"};
  const shortTime = seconds => new Date(seconds * 1000).toLocaleString("ru-RU", {dateStyle: "short", timeStyle: "short"});
  let state = null, saving = false, pendingId = null, submitted = null;

  async function request(path, method = "GET", body) {
    const response = await fetch(path, {method, headers: {"Content-Type": "application/json"},
      ...(body === undefined ? {} : {body: JSON.stringify(body)}), signal: AbortSignal.timeout(10000)});
    if (!response.ok) {
      const result = await response.json().catch(() => ({}));
      const detail = typeof result.detail === "string" ? result.detail : "Справка недоступна. Повторите попытку.";
      const error = new Error(detail === "Диалог не найден." ?
        "Диалог не найден: возможно, он перемещён в корзину на другом устройстве. Восстановите его из корзины, чтобы продолжить сборку справки." : detail);
      error.status = response.status;
      throw error;
    }
    return response.status === 204 ? null : response.json();
  }
  const base = () => "/api/workspace/chats/" + encodeURIComponent(state.chat) + "/briefs";
  const status = message => { get("brief-status").textContent = message; };
  const blank = title => ({id: null, revision: 0, title: ("Справка: " + title).slice(0, 120), intro: "", sections: [], matter_fields: [], include_reviews: false});
  const fromSaved = brief => ({id: brief.id, revision: brief.revision, title: brief.title, intro: brief.intro,
    sections: brief.sections.map(({turn_index, turn_key, comment}) => ({turn_index, turn_key, comment})),
    matter_fields: [...brief.matter_fields], include_reviews: brief.include_reviews});
  function available(section) {
    const turn = state.turns[section.turn_index], info = state.answers[section.turn_index];
    return !!(turn && info && info.turn_key === section.turn_key && !excluded.has(turn.answer.status));
  }
  const selectable = () => state.turns.map((turn, index) => index).filter(index => available({turn_index: index, turn_key: state.answers[index]?.turn_key}));
  function statusLabel(answer) {
    const names = typeof labels === "object" && labels ? labels : {};
    return answer.ui_state === "role_protection" ? "Защита роли" : names[answer.status] || (answer.sources?.length ? "Найдены источники" : "Ответ");
  }
  const formatDate = value => /^(\d{4})-(\d{2})-(\d{2})$/.test(value) ? value.slice(8) + "." + value.slice(5, 7) + "." + value.slice(0, 4) : value;

  async function open() {
    const chat = globalThis.WebWorkspace?.chatId(), dialog = get("brief-dialog");
    if (!chat || dialog.open) return;
    state = null; setStep("compose"); status("Загружаем ответы диалога…");
    for (const id of ["brief-answers", "brief-matter"]) get(id).replaceChildren(get(id).querySelector("legend"));
    get("brief-sections").replaceChildren(); get("brief-preview").replaceChildren();
    dialog.showModal(); get("close-brief").focus();
    try {
      const path = "/api/workspace/chats/" + encodeURIComponent(chat);
      const [conversation, workspace, briefs] = await Promise.all([request("/api/chats/" + encodeURIComponent(chat)), request(path), request(path + "/briefs")]);
      if (!dialog.open) return;
      state = {chat, chatTitle: conversation.title, turns: conversation.turns, answers: workspace.answers, matter: workspace.matter || {},
        briefs, brief: blank(conversation.title), dirty: false};
      pendingId = crypto.randomUUID(); submitted = null;
      render();
      status(selectable().length ? "" : "В диалоге пока нет готовых ответов для справки.");
    } catch (error) { status(error.message); }
  }
  function render() { renderSaved(); renderForm(); renderSections(); renderPreview(); }
  function renderSaved() {
    const select = get("brief-saved");
    select.replaceChildren(new Option("Новая справка", ""));
    for (const brief of state.briefs) select.append(new Option(brief.title + " · " + shortTime(brief.updated), brief.id));
    select.value = state.brief.id || "";
    get("delete-brief").hidden = !state.brief.id;
  }
  function check(label, value, checked, text, note) {
    const node = document.createElement("label"); node.className = "brief-check";
    const input = document.createElement("input"); input.type = "checkbox"; input.value = value; input.checked = checked;
    input.dataset.kind = label;
    const caption = document.createElement("span"); caption.textContent = text;
    if (note) { const small = document.createElement("small"); small.textContent = note; caption.append(small); }
    node.append(input, caption);
    return node;
  }
  function renderForm() {
    const brief = state.brief;
    get("brief-name").value = brief.title; get("brief-intro").value = brief.intro; get("brief-reviews").checked = brief.include_reviews;
    const answers = get("brief-answers"); answers.replaceChildren(answers.querySelector("legend"));
    for (const index of selectable()) {
      const turn = state.turns[index];
      answers.append(check("answer", index, brief.sections.some(section => section.turn_index === index),
        "Вопрос " + (index + 1) + ": " + turn.question, statusLabel(turn.answer)));
    }
    if (!answers.querySelector("input")) {
      const empty = document.createElement("p"); empty.className = "workspace-help";
      empty.textContent = "Готовых ответов пока нет."; answers.append(empty);
    }
    const card = get("brief-matter"); card.replaceChildren(card.querySelector("legend"));
    for (const [key, label] of cardLabels) {
      const value = String(state.matter[key] || "").trim();
      if (value) card.append(check("matter", key, brief.matter_fields.includes(key), label, key === "event_date" ? formatDate(value) : value));
    }
    if (!card.querySelector("input")) {
      const empty = document.createElement("p"); empty.className = "workspace-help";
      empty.textContent = "Карточка дела пуста. Заполните её, если сведения нужны в справке."; card.append(empty);
    }
  }
  function renderSections(focus) {
    const host = get("brief-sections"), sections = state.brief.sections;
    host.replaceChildren();
    sections.forEach((section, index) => {
      const item = document.createElement("li"); item.className = "brief-order-item";
      const ok = available(section); item.dataset.available = String(ok);
      const title = document.createElement("p"); title.className = "brief-order-title";
      title.textContent = "Раздел " + (index + 1) + ": " + (ok ? state.turns[section.turn_index].question :
        "недоступен — исходный ответ изменён или удалён. Уберите его из справки.");
      const actions = document.createElement("div"); actions.className = "brief-order-actions";
      for (const [move, text, label, disabled] of [[-1, "↑ Выше", "Переместить выше: раздел " + (index + 1), index === 0],
        [1, "↓ Ниже", "Переместить ниже: раздел " + (index + 1), index === sections.length - 1], [0, "Убрать", "Убрать из справки: раздел " + (index + 1), false]]) {
        const node = document.createElement("button"); node.type = "button"; node.textContent = text; node.disabled = disabled;
        node.setAttribute("aria-label", label); node.dataset.move = String(move);
        node.addEventListener("click", () => moveSection(index, move));
        actions.append(node);
      }
      item.append(title, actions);
      if (ok) {
        const label = document.createElement("label"); label.textContent = "Комментарий пользователя к разделу " + (index + 1) + " (необязательно)";
        const comment = document.createElement("textarea"); comment.rows = 2; comment.maxLength = 2000; comment.value = section.comment;
        comment.addEventListener("input", () => { section.comment = comment.value; changed(); });
        label.append(comment); item.append(label);
      }
      host.append(item);
    });
    get("brief-sections-empty").hidden = sections.length > 0;
    if (focus) {
      const target = host.children[focus.index];
      (target?.querySelector('[data-move="' + focus.move + '"]:not(:disabled)') || target?.querySelector("button:not(:disabled)") || get("brief-name")).focus();
    }
  }
  function moveSection(index, move) {
    const sections = state.brief.sections;
    if (move === 0) {
      sections.splice(index, 1);
      renderForm(); renderSections({index: Math.min(index, sections.length - 1), move: 0});
    } else {
      const target = index + move;
      [sections[index], sections[target]] = [sections[target], sections[index]];
      renderSections({index: target, move});
    }
    changed();
  }
  function changed() { if (state) { state.dirty = true; renderPreview(); } }

  // One description feeds the preview, the printed page and the copied text, so they cannot diverge.
  function blocks() {
    const brief = state.brief, list = [
      {type: "title", text: brief.title.trim() || "Справка"},
      {type: "meta", text: "Сформирована " + new Date().toLocaleString("ru-RU", {dateStyle: "long", timeStyle: "short"}) + " · Диалог «" + state.chatTitle + "»"},
      {type: "notice", text: "Ответы ассистента приведены полностью, без сокращений и правок. Номера [1], [2] в тексте ответа относятся к источникам того же раздела. " +
        "Вступление, комментарии, сведения карточки дела и отметки подписаны как пользовательские. Справка не является проверенным юридическим заключением."}];
    if (brief.intro.trim()) list.push({type: "user", heading: "Вступление пользователя", children: [{type: "text", text: brief.intro.trim()}]});
    const card = cardLabels.filter(([key]) => brief.matter_fields.includes(key) && String(state.matter[key] || "").trim());
    if (card.length) list.push({type: "user", heading: "Сведения карточки дела — введены пользователем", children: card.map(([key, label]) =>
      ({type: "field", label, text: key === "event_date" ? formatDate(state.matter[key]) : String(state.matter[key]).trim()}))});
    brief.sections.forEach((section, index) => {
      const number = index + 1, heading = "Раздел " + number;
      if (!available(section)) {
        list.push({type: "section", heading, children: [{type: "unavailable", text: "Раздел недоступен: исходный ответ изменён или удалён."}]});
        return;
      }
      const answer = state.turns[section.turn_index].answer, review = state.answers[section.turn_index].review, children = [
        {type: "label", text: "Вопрос"}, {type: "text", text: state.turns[section.turn_index].question},
        {type: "status", text: "Статус ответа: " + statusLabel(answer)},
        {type: "label", text: "Ответ ассистента"}, {type: "answer", text: answer.text}];
      if (answer.sources?.length) children.push({type: "sources", heading: "Источники раздела " + number, items: answer.sources.map(source => ({
        label: "[" + source.n + "] " + [source.title, source.heading, source.status].filter(Boolean).join(" · "), quote: source.quote}))});
      if (brief.include_reviews && review?.state) children.push({type: "mark",
        text: "Отметка пользователя: " + reviewNames[review.state] + (review.updated ? " · " + shortTime(review.updated) : "")});
      if (section.comment.trim()) children.push({type: "user", heading: "Комментарий пользователя к разделу " + number,
        children: [{type: "text", text: section.comment.trim()}]});
      list.push({type: "section", heading, children});
    });
    return list;
  }
  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function draw(block, depth = 0) {
    const heading = depth ? "h3" : "h2";
    switch (block.type) {
      case "title": return element("h1", "brief-heading", block.text);
      case "section": case "user": {
        const node = element(block.type === "section" ? "section" : "div", "brief-" + block.type);
        node.append(element(heading, "", block.heading), ...block.children.map(child => draw(child, depth + 1)));
        return node;
      }
      case "sources": {
        const node = element("div", "brief-sources"), items = element("ul");
        for (const item of block.items) {
          const row = element("li");
          row.append(element("p", "brief-source-title", item.label), element("blockquote", "", item.quote));
          items.append(row);
        }
        node.append(element("h3", "", block.heading), items);
        return node;
      }
      case "field": {
        const node = element("p", "brief-field");
        node.append(element("strong", "", block.label + ": "), block.text);
        return node;
      }
      default: return element("p", "brief-" + block.type, block.text);
    }
  }
  function renderBlocks(host, list) {
    const root = element("article", "brief-document");
    root.append(...list.map(block => draw(block)));
    host.replaceChildren(root);
  }
  function plain(list) {
    const lines = [];
    const add = block => {
      if (block.type === "section" || block.type === "user") { lines.push("", block.heading + (block.type === "user" ? ":" : "")); block.children.forEach(add); }
      else if (block.type === "sources") { lines.push("", block.heading + ":"); for (const item of block.items) lines.push(item.label, "«" + item.quote + "»", ""); }
      else if (block.type === "field") lines.push(block.label + ": " + block.text);
      else if (block.type === "label") lines.push(block.text + ":");
      else lines.push(block.text, "");
    };
    list.forEach(add);
    return lines.join("\n").replace(/\n{3,}/g, "\n\n").trim();
  }
  function renderPreview() { if (state) renderBlocks(get("brief-preview"), blocks()); }

  function problem() {
    if (!state) return "Справка ещё не загружена.";
    if (!state.brief.title.trim()) return "Укажите заголовок справки.";
    if (!state.brief.sections.length) return "Отметьте хотя бы один ответ.";
    if (state.brief.sections.some(section => !available(section))) return "Уберите недоступные разделы: исходные ответы изменены или удалены.";
    return "";
  }
  async function copy() {
    const issue = problem();
    if (issue) return status(issue);
    const text = plain(blocks());
    try { await navigator.clipboard.writeText(text); status("Справка скопирована."); }
    catch {
      openCopyDialog(text);
      get("copy-title").textContent = "Справка";
      get("copy-note").textContent = "Выделите текст справки и скопируйте его.";
    }
  }
  function print() {
    const issue = problem();
    if (issue) return status(issue);
    const list = blocks();
    status("");
    startPrint({render: host => renderBlocks(host, list), statusId: "brief-status"});
  }
  function lock(value) {
    saving = value;
    for (const id of ["save-brief", "copy-brief", "print-brief", "delete-brief", "brief-saved", "close-brief"]) get(id).disabled = value;
    get("brief-dialog").dataset.saving = String(value);
  }
  async function save() {
    const issue = problem();
    if (issue) return status(issue);
    const brief = state.brief, body = {title: brief.title.trim(), intro: brief.intro.trim(),
      sections: brief.sections.map(({turn_index, turn_key, comment}) => ({turn_index, turn_key, comment: comment.trim()})),
      matter_fields: brief.matter_fields, include_reviews: brief.include_reviews};
    lock(true); status("Сохраняем справку…");
    try {
      let saved;
      if (brief.id) saved = await request(base() + "/" + encodeURIComponent(brief.id), "PUT", {...body, revision: brief.revision});
      else {
        const signature = JSON.stringify(body);
        if (submitted !== null && submitted !== signature) pendingId = crypto.randomUUID();
        submitted = signature;
        saved = await request(base(), "POST", {...body, id: pendingId});
      }
      state.briefs = [saved, ...state.briefs.filter(item => item.id !== saved.id)];
      state.brief = fromSaved(saved); state.dirty = false; pendingId = crypto.randomUUID(); submitted = null;
      render(); status("Справка «" + saved.title + "» сохранена.");
    } catch (error) {
      status(error.message + (error.status === 409 ? " Состав остался в форме: его можно скопировать или распечатать. Чтобы загрузить свежую версию, закройте окно и откройте справку снова." : ""));
    } finally { lock(false); }
  }
  async function choose() {
    const select = get("brief-saved"), id = select.value;
    if (state.dirty && !await confirmAction("Открыть другую справку?", "Несохранённые изменения текущей справки будут потеряны.", "Открыть")) {
      select.value = state.brief.id || ""; return;
    }
    const brief = state.briefs.find(item => item.id === id);
    state.brief = brief ? fromSaved(brief) : blank(state.chatTitle); state.dirty = false;
    pendingId = crypto.randomUUID(); submitted = null;
    render();
    status(state.brief.sections.some(section => !available(section)) ?
      "Часть разделов недоступна: исходные ответы изменены или удалены. Уберите их перед копированием и печатью." : "");
  }
  async function remove() {
    const brief = state.brief;
    if (!brief.id || !await confirmAction("Удалить справку?", "Сохранённая справка «" + brief.title + "» будет удалена. Диалог и ответы не изменятся.", "Удалить справку")) return;
    lock(true);
    try { await request(base() + "/" + encodeURIComponent(brief.id) + "?revision=" + brief.revision, "DELETE"); }
    catch (error) { if (error.status !== 404) { status(error.message); lock(false); return; } }
    state.briefs = state.briefs.filter(item => item.id !== brief.id);
    state.brief = blank(state.chatTitle); state.dirty = false; lock(false);
    render(); status("Справка удалена.");
  }
  async function close() {
    if (saving) return;
    if (state?.dirty && !await confirmAction("Закрыть без сохранения?", "Изменения справки не сохранены. Скопировать или распечатать её можно и без сохранения.", "Закрыть")) return;
    get("brief-dialog").close();
  }
  function setStep(step) {
    get("brief-dialog").dataset.step = step;
    get("brief-step-compose").setAttribute("aria-pressed", String(step === "compose"));
    get("brief-step-preview").setAttribute("aria-pressed", String(step === "preview"));
  }

  get("open-brief").addEventListener("click", open);
  get("close-brief").addEventListener("click", close);
  get("brief-dialog").addEventListener("cancel", event => { event.preventDefault(); close(); });
  get("brief-step-compose").addEventListener("click", () => setStep("compose"));
  get("brief-step-preview").addEventListener("click", () => { setStep("preview"); renderPreview(); });
  get("brief-form").addEventListener("submit", event => event.preventDefault());
  get("brief-name").addEventListener("input", () => { if (state) { state.brief.title = get("brief-name").value; changed(); } });
  get("brief-intro").addEventListener("input", () => { if (state) { state.brief.intro = get("brief-intro").value; changed(); } });
  get("brief-reviews").addEventListener("change", () => { if (state) { state.brief.include_reviews = get("brief-reviews").checked; changed(); } });
  get("brief-answers").addEventListener("change", event => {
    if (!state || event.target.dataset.kind !== "answer") return;
    const index = Number(event.target.value), sections = state.brief.sections;
    if (event.target.checked && !sections.some(section => section.turn_index === index)) {
      sections.push({turn_index: index, turn_key: state.answers[index].turn_key, comment: ""});
    } else if (!event.target.checked) state.brief.sections = sections.filter(section => section.turn_index !== index);
    renderSections(); changed();
  });
  get("brief-matter").addEventListener("change", event => {
    if (!state || event.target.dataset.kind !== "matter") return;
    const checked = new Set([...get("brief-matter").querySelectorAll("input:checked")].map(input => input.value));
    state.brief.matter_fields = cardLabels.map(([key]) => key).filter(key => checked.has(key));
    changed();
  });
  get("brief-saved").addEventListener("change", choose);
  get("delete-brief").addEventListener("click", remove);
  get("save-brief").addEventListener("click", save);
  get("copy-brief").addEventListener("click", copy);
  get("print-brief").addEventListener("click", print);
  document.addEventListener("DOMContentLoaded", () => globalThis.WebIcons?.set(get("close-brief"), "close"));
  window.AnswerBriefs = {open, text: () => state && plain(blocks())};
})();
