// Writes only to a disposable local fixture; run with web/browser-tests/queue_fixture.py.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {randomUUID} = require('node:crypto');

(async () => {
  const base = process.env.BASE_URL || 'http://127.0.0.1:8003';
  assert.ok(['127.0.0.1', 'localhost', '[::1]'].includes(new URL(base).hostname));
  assert.equal(process.env.WEB_FIXTURE_CONFIRMED, '1', 'Use only a local stub model and disposable database.');
  const output = process.env.AUDIT_OUTPUT || '/tmp/legal-workspace-audit'; fs.mkdirSync(output, {recursive: true});
  const browser = await chromium.launch({headless: true, executablePath: process.env.CHROMIUM_PATH, args: ['--no-sandbox']});
  const options = {viewport: {width: 1440, height: 1000}, reducedMotion: 'reduce',
    extraHTTPHeaders: {'X-Chat-User': 'workspace-browser', 'X-Chat-Token': 'fixture-token'}};
  const context = await browser.newContext(options), secondContext = await browser.newContext(options);
  const page = await context.newPage(), second = await secondContext.newPage(), errors = [];
  for (const tab of [page, second]) {
    tab.on('pageerror', error => errors.push(error.message));
    tab.on('dialog', async dialog => { errors.push('Unexpected browser dialog: ' + dialog.type()); await dialog.dismiss(); });
  }
  const api = async (path, method = 'GET', data) => {
    const result = await context.request.fetch(base + '/api' + path, {method, headers: {'Content-Type': 'application/json'}, ...(data === undefined ? {} : {data})});
    assert.ok(result.ok(), path + ': ' + result.status() + ' ' + await result.text());
    return result.status() === 204 ? null : result.json();
  };
  const until = async predicate => {
    for (let i = 0; i < 150; i++) { if (await predicate()) return; await new Promise(resolve => setTimeout(resolve, 100)); }
    assert.fail('Fixture condition did not complete');
  };
  const ready = async tab => tab.waitForFunction(() => !document.querySelector('#send').disabled && !document.querySelector('#open-matter').disabled);
  const savedDraft = async tab => tab.waitForFunction(() => document.querySelector('#draft-status').textContent === 'Черновик сохранён на сервере');
  const visibleButton = async (tab, selector) => {
    await tab.locator(selector).waitFor({state: 'visible'});
    const box = await tab.locator(selector).boundingBox(), view = tab.viewportSize();
    assert.ok(box && box.y >= 0 && box.x >= 0 && box.y + box.height <= view.height + 1 && box.x + box.width <= view.width + 1,
      JSON.stringify({selector, box, view}));
  };
  try {
    const original = await api('/chats', 'POST');
    for (const question of ['Какие условия есть в договоре?', 'Какие положения нужно проверить?']) {
      const job = await api('/chats/' + original.id + '/jobs', 'POST', {id: randomUUID(), question});
      await until(async () => !(await api('/chats/' + original.id + '/jobs')).jobs.some(item => item.id === job.id));
    }
    const before = await api('/chats/' + original.id);
    await page.addInitScript(id => localStorage.setItem('psb-current-chat', id), original.id);
    await second.addInitScript(id => localStorage.setItem('psb-current-chat', id), original.id);
    await page.goto(base); await ready(page);
    await page.waitForFunction(() => !document.querySelector('.save-answer').disabled);
    const injection = '<img src=x onerror="window.workspaceInjected=true">';
    await page.locator('#open-matter').click();
    await page.locator('#matter-form [name=contract]').fill('Тестовый договор Орион');
    await page.locator('#matter-form [name=event_date]').fill('2026-10-12');
    await page.locator('#matter-form [name=situation]').fill('PRIVATE_CARD_SENTINEL ' + injection);
    await page.locator('#save-matter').click();
    await page.locator('.save-answer').first().click();
    await page.waitForFunction(() => document.querySelector('.save-answer').getAttribute('aria-pressed') === 'true');
    await page.locator('.note-answer').first().click();
    await page.locator('#answer-note').fill('PRIVATE_NOTE_SENTINEL ' + original.id + ' ' + injection); await page.locator('#save-note').click();
    await page.locator('#note-dialog').waitFor({state: 'hidden'});
    assert.equal(await page.locator('.answer-note-preview img').count(), 0);
    assert.equal(await page.evaluate(() => !!window.workspaceInjected), false);
    await page.locator('#question').fill('Первая версия черновика'); await savedDraft(page);
    await second.goto(base); await ready(second);
    assert.equal(await second.locator('#question').inputValue(), 'Первая версия черновика');
    assert.match(await second.locator('#matter-summary').textContent(), /Орион/);
    await page.locator('#question').fill('Новая версия с первого устройства'); await savedDraft(page);
    await second.locator('#question').fill('Версия со второго устройства');
    await second.locator('#resolve-draft').waitFor({state: 'visible'});
    assert.equal((await api('/workspace/drafts/' + original.id)).text, 'Новая версия с первого устройства');
    await second.locator('#resolve-draft').click();
    await second.locator('#draft-conflict-dialog').waitFor({state: 'visible'});
    assert.equal(await second.locator('#draft-remote').inputValue(), 'Новая версия с первого устройства');
    await second.locator('#draft-keep-local').click();
    await second.locator('#draft-conflict-dialog').waitFor({state: 'hidden'});
    await page.reload(); await ready(page);
    assert.equal(await page.locator('#question').inputValue(), 'Версия со второго устройства');
    await page.locator('#open-saved').click();
    await page.locator('#saved-search').fill(original.id);
    await page.waitForFunction(() => document.querySelectorAll('.saved-answer').length === 1);
    assert.equal(await page.locator('#saved-answers img').count(), 0);
    await page.locator('[data-close="saved-dialog"]').click();

    await page.locator('.edit-question').nth(1).click();
    await page.locator('#question-edit-text').fill('Что изменится на другую дату?');
    await page.locator('#save-question-edit').click();
    await page.locator('#question-dialog').waitFor({state: 'hidden'});
    await until(async () => (await page.locator('#question').inputValue()) === 'Что изменится на другую дату?');
    const branchId = await page.evaluate(() => localStorage.getItem('psb-current-chat'));
    assert.notEqual(branchId, original.id);
    assert.equal(await page.locator('.message.user').count(), 1);
    assert.deepEqual((await api('/chats/' + original.id)).turns, before.turns);
    assert.deepEqual((await api('/chats/' + branchId)).turns, before.turns.slice(0, 1));
    assert.equal((await api('/chats/' + branchId + '/jobs')).jobs.length, 0);
    assert.equal((await api('/workspace/chats/' + branchId)).matter.contract, 'Тестовый договор Орион');

    // Full texts and an explicitly composed question from a selected passage.
    const docs = await api('/documents');
    assert.equal(await page.locator('#compare-documents, #compare-current, #comparison-dialog').count(), 0);
    await page.locator('#doc-list button').first().click();
    await page.locator('#document-workspace-actions').waitFor({state: 'visible'});
    const selection = await page.locator('#doc-text').evaluate(element => {
      const range = document.createRange(); range.setStart(element.firstChild, 0); range.setEnd(element.firstChild, Math.min(240, element.firstChild.length));
      const selected = window.getSelection(); selected.removeAllRanges(); selected.addRange(range); return selected.toString();
    });
    await page.locator('#ask-selection').click();
    await page.getByRole('button', {name: 'Условия и исключения', exact: true}).click();
    await page.locator('#passage-form button[type=submit]').click();
    assert.ok((await page.locator('#question').inputValue()).includes(selection));
    assert.equal((await api('/chats/' + branchId + '/jobs')).jobs.length, 0);
    await savedDraft(page);
    await page.locator('#doc-text').evaluate(element => element.scrollTop = 160);
    const position = await page.locator('#doc-text').evaluate(element => element.scrollTop);
    await page.locator('#all-docs').click(); await page.locator('#doc-list button').first().click();
    await page.waitForFunction(value => Math.abs(document.querySelector('#doc-text').scrollTop - value) < 2, position);

    // Edit only a waiting question; keep the paused queue and its order.
    await page.locator('#question').fill('Первый тест остановки'); await page.locator('#send').click();
    await page.locator('#stop-generation').waitFor({state: 'visible'}); await page.locator('#stop-generation').click();
    await page.locator('#resume-queue').waitFor({state: 'visible'});
    for (const question of ['Ожидающий вопрос А', 'Ожидающий вопрос Б']) {
      await page.locator('#question').fill(question); await page.locator('#send').click();
      await page.waitForFunction(() => document.querySelector('#send').closest('.sl-component').dataset.phase !== 'pending');
    }
    await page.locator('#queue-list button').filter({hasText: /^Изменить$/}).first().click();
    await page.locator('#question-edit-text').fill('Исправленный ожидающий вопрос'); await page.locator('#save-question-edit').click();
    await page.locator('#question-dialog').waitFor({state: 'hidden'});
    let queue = await api('/chats/' + branchId + '/jobs');
    assert.deepEqual(queue.jobs.map(item => item.question), ['Исправленный ожидающий вопрос', 'Ожидающий вопрос Б']);
    assert.equal(queue.paused, true);
    await page.getByRole('button', {name: 'Ниже: Исправленный ожидающий вопрос', exact: true}).click();
    await until(async () => (await api('/chats/' + branchId + '/jobs')).jobs[0].question === 'Ожидающий вопрос Б');
    await page.locator('#resume-queue').click();
    await until(async () => (await api('/chats/' + branchId + '/jobs')).jobs.length === 0);
    // Close the other device before a background answer finishes, then show its badge.
    await second.close();
    await api('/chats/' + original.id + '/jobs', 'POST', {id: randomUUID(), question: 'Ответ в другом диалоге'});
    await page.locator('[data-chat-id="' + original.id + '"] .unread-badge').waitFor({state: 'visible', timeout: 20000});

    await page.locator('#open-appearance').click();
    await page.locator('#appearance-theme').selectOption('dark');
    await page.locator('#appearance-font').selectOption('Inter');
    await page.locator('#appearance-size').fill('22');
    await page.locator('#close-appearance').click();
    for (const [width, height] of [[1440, 1000], [390, 844], [320, 568], [390, 420]]) {
      await page.setViewportSize({width, height});
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
      await page.locator('#open-matter').click(); await visibleButton(page, '#save-matter');
      await page.screenshot({path: output + '/matter-' + width + '-' + height + '.png'});
      await page.locator('[data-close="matter-dialog"]').click();
      await visibleButton(page, '#send');
      await page.screenshot({path: output + '/chat-' + width + '-' + height + '.png'});
    }
    assert.deepEqual(errors, []);
    console.log('PASS workspace: server persistence, two-device conflicts, isolated branches, selection, full documents, queue editing, unread badge, XSS and responsive dark theme at 22px.');
  } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
