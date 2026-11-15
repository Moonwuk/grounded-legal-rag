"use strict";
(() => {
  const get = id => document.getElementById(id);
  let chatId = null, timer = null, controller = null, revision = 0;
  let snapshot = null, transcript = "", activityKey = "", nodes = [], scene = null;
  let submission = null, pendingSubmission = false, pollId = 0, waitingSignature = "";
  let actionError = "", resumePending = false;
  const clearActivity = () => {
    if (scene) ArchiveScene.stop(scene);
    scene = null;
    for (const node of nodes) node.remove();
    nodes = [];
    activityKey = "";
  };
  function detach() {
    revision++;
    clearTimeout(timer);
    controller?.abort();
    clearActivity();
    chatId = null; snapshot = null; transcript = ""; waitingSignature = "";
    actionError = "";
    get("question-queue").hidden = true;
    get("queue-error").textContent = "";
    get("queue-list").replaceChildren();
  }
  async function request(id, path = "", method = "GET", body, signal) {
    const response = await fetch("/api/chats/" + id + "/jobs" + path, {
      method, headers: {"Content-Type": "application/json"},
      ...(body ? {body: JSON.stringify(body)} : {}), signal: signal || AbortSignal.timeout(10000)
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(typeof data.detail === "string" ? data.detail : "Очередь недоступна. Повторите действие.");
    }
    return response.status === 204 ? null : response.json();
  }
  function render(data) {
    snapshot = data;
    const signature = JSON.stringify(data.turns);
    const follow = log.scrollHeight - log.scrollTop - log.clientHeight < 160;
    const previousScroll = log.scrollTop;
    if (signature !== transcript) {
      clearActivity();
      renderSavedTurns(data.turns);
      transcript = signature;
      const saved = savedChats.find(chat => chat.id === chatId);
      if (saved) saved.title = data.title;
      renderHistory();
    }
    const active = data.jobs.find(job => ["running", "cancelling"].includes(job.status));
    const key = active ? active.id + active.status : "";
    if (key !== activityKey) {
      clearActivity();
      activityKey = key;
      if (active) {
        const user = bubble("user", active.question);
        const assistant = bubble("assistant", active.status === "cancelling" ? "Останавливаем ответ…" : "Ищем в документах…");
        assistant.item.dataset.status = "searching";
        scene = ArchiveScene.create();
        assistant.body.before(scene);
        assistant.item.classList.add("with-scene");
        nodes = [user.item, assistant.item];
      }
    }
    log.scrollTop = follow ? log.scrollHeight : previousScroll;
    const waiting = data.jobs.filter(job => job.status === "queued");
    get("question-queue").hidden = !data.jobs.length && !data.paused;
    get("queue-status").textContent = active ? active.status === "cancelling" ? "Останавливаем…" : "Готовим ответ · в очереди: " + waiting.length :
      data.paused ? "Очередь на паузе" : waiting.length ? "Ожидаем свободное место · вопросов: " + waiting.length : "";
    get("stop-generation").hidden = !active;
    get("stop-generation").disabled = active?.status === "cancelling";
    get("resume-queue").hidden = !data.paused || !!active;
    const retry = !waiting.length && ["cancelled", "technical_error"].includes(data.turns.at(-1)?.answer.status);
    get("resume-queue").textContent = retry ? "Повторить ответ" : "Продолжить очередь";
    get("resume-queue").disabled = resumePending;
    const nextWaiting = JSON.stringify(waiting);
    if (nextWaiting === waitingSignature) return;
    waitingSignature = nextWaiting;
    const list = get("queue-list");
    list.replaceChildren();
    for (const [index, job] of waiting.entries()) {
      const row = document.createElement("li");
      const text = document.createElement("span"); text.textContent = job.question; text.title = job.question;
      const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "Убрать";
      remove.setAttribute("aria-label", "Убрать из очереди: " + job.question);
      remove.addEventListener("click", () => action("/" + job.id, "DELETE"));
      const controls = document.createElement("div"); controls.className = "queue-item-actions";
      for (const [direction, label, disabled] of [["up", "↑ Выше", index === 0], ["down", "↓ Ниже", index === waiting.length - 1]]) {
        const move = document.createElement("button"); move.type = "button"; move.textContent = label;
        move.disabled = disabled;
        move.setAttribute("aria-label", (direction === "up" ? "Выше: " : "Ниже: ") + job.question);
        move.addEventListener("click", async () => {
          move.disabled = true;
          await action("/" + job.id + "/move/" + direction, "POST");
          if (move.isConnected) move.disabled = disabled;
        });
        controls.append(move);
      }
      controls.append(remove);
      row.append(text, controls); list.append(row);
    }
  }
  async function refresh() {
    if (!chatId) return;
    const id = chatId, version = revision, ticket = ++pollId;
    clearTimeout(timer);
    controller?.abort();
    controller = new AbortController();
    try {
      const data = await request(id, "", "GET", null, AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]));
      if (id !== chatId || version !== revision || ticket !== pollId) return;
      get("queue-error").textContent = actionError;
      render(data);
    } catch (error) {
      if (version !== revision || id !== chatId || error.name === "AbortError") return;
      get("question-queue").hidden = false;
      get("queue-error").textContent = "Не удалось обновить очередь. Повторяем подключение…";
    } finally {
      if (version === revision && id === chatId && ticket === pollId) timer = setTimeout(refresh, snapshot?.jobs.length ? 700 : 2500);
    }
  }
  function attach(chat) {
    detach();
    chatId = chat.id;
    transcript = JSON.stringify(chat.turns);
    refresh();
  }
  async function submit(question, resume = false) {
    if (pendingSubmission) throw new Error("Дождитесь добавления вопроса в очередь.");
    const id = currentChat;
    if (!id) throw new Error("Сначала создайте диалог.");
    if (chatId !== id) attach({id, turns: []});
    // Reuse the ID after a lost response: POST may already have been accepted.
    if (!submission || submission.chat !== id || submission.question !== question) {
      submission = {chat: id, id: crypto.randomUUID(), question};
    }
    pendingSubmission = true;
    try {
      await request(id, "", "POST", {id: submission.id, question});
      if (resume) await request(id, "/resume", "POST");
      submission = null;
      await refresh();
    } finally { pendingSubmission = false; }
  }
  async function action(path, method) {
    const id = chatId;
    if (!id) return;
    actionError = "";
    try {
      await request(id, path, method);
      if (chatId === id) await refresh();
    } catch (error) {
      if (chatId === id) get("queue-error").textContent = actionError = error.message;
    }
  }
  get("stop-generation").addEventListener("click", () => {
    const active = snapshot?.jobs.find(job => ["running", "cancelling"].includes(job.status));
    if (active) action("/" + active.id, "DELETE");
  });
  get("resume-queue").addEventListener("click", async () => {
    if (resumePending) return;
    const id = chatId, last = snapshot?.turns.at(-1);
    resumePending = true;
    get("resume-queue").disabled = true;
    actionError = "";
    try {
      if (!snapshot?.jobs.length && last && ["cancelled", "technical_error"].includes(last.answer.status)) {
        await submit(last.question, true);
      } else await action("/resume", "POST");
    } catch (error) {
      if (chatId === id) get("queue-error").textContent = actionError = error.message;
    } finally {
      resumePending = false;
      get("resume-queue").disabled = false;
    }
  });
  window.addEventListener("pagehide", detach);
  window.addEventListener("pageshow", event => { if (event.persisted && currentChat) attach({id: currentChat, turns: []}); });
  window.ChatQueue = {attach, detach, submit};
})();
