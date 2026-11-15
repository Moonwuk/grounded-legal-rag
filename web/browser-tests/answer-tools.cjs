// Templates, review marks and briefs. Writes only to a disposable local fixture; run with web/browser-tests/queue_fixture.py.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {randomUUID} = require('node:crypto');

(async () => {
  const base = process.env.BASE_URL || 'http://127.0.0.1:8000';
  assert.ok(['127.0.0.1', 'localhost', '[::1]'].includes(new URL(base).hostname));
  assert.equal(process.env.WEB_FIXTURE_CONFIRMED, '1', 'Use only a local stub model and disposable database.');
  const output = process.env.AUDIT_OUTPUT || '/tmp/legal-answer-tools'; fs.mkdirSync(output, {recursive: true});
  const browser = await chromium.launch({headless: true, executablePath: process.env.CHROMIUM_PATH, args: ['--no-sandbox']});
  // A fresh login per run keeps the saved-answer filters independent of earlier runs on the same disposable database.
  const headers = {'X-Chat-User': 'answer-tools-' + randomUUID().slice(0, 8), 'X-Chat-Token': 'fixture-token'};
  const desktop = {viewport: {width: 1440, height: 1000}, reducedMotion: 'reduce', extraHTTPHeaders: headers};
  const context = await browser.newContext(desktop), secondContext = await browser.newContext(desktop);
  const page = await context.newPage(), second = await secondContext.newPage(), errors = [];
  const watch = tab => {
    tab.on('pageerror', error => errors.push(error.message));
    tab.on('dialog', async dialog => { errors.push('Unexpected browser dialog: ' + dialog.type()); await dialog.dismiss(); });
  };
  watch(page); watch(second);
  const api = async (path, method = 'GET', data) => {
    const result = await context.request.fetch(base + '/api' + path, {method, headers: {'Content-Type': 'application/json'}, ...(data === undefined ? {} : {data})});
    assert.ok(result.ok(), path + ': ' + result.status() + ' ' + await result.text());
    return result.status() === 204 ? null : result.json();
  };
  const until = async predicate => {
    for (let i = 0; i < 150; i++) { if (await predicate()) return; await new Promise(resolve => setTimeout(resolve, 100)); }
    assert.fail('Fixture condition did not complete');
  };
  const ready = async tab => tab.waitForFunction(() => !document.querySelector('#send').disabled && !document.querySelector('#open-brief').disabled);
  const noOverflow = async (tab, label) => assert.ok(await tab.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), label + ': horizontal overflow');
  const accept = async tab => { await tab.locator('#confirm-dialog').waitFor({state: 'visible'}); await tab.locator('#confirm-accept').click(); };
  const injection = '<img src=x onerror="window.answerToolsInjected=true">';
  try {
    const chat = await api('/chats', 'POST');
    const questions = ['Какие сроки оплаты указаны в договоре?', 'Какая неустойка предусмотрена договором?'];
    for (const question of questions) {
      const job = await api('/chats/' + chat.id + '/jobs', 'POST', {id: randomUUID(), question});
      await until(async () => !(await api('/chats/' + chat.id + '/jobs')).jobs.some(item => item.id === job.id));
    }
    const before = await api('/chats/' + chat.id);
    assert.equal(before.turns.length, 2);
    for (const tab of [page, second]) await tab.addInitScript(id => localStorage.setItem('psb-current-chat', id), chat.id);
    await page.goto(base); await ready(page);
    await page.waitForFunction(() => document.querySelectorAll('.review-select:not(:disabled)').length === 2);

    // 1. Templates compose visible text only; missing values are not guessed and nothing is sent.
    await page.locator('#open-templates').click();
    await page.locator('#builtin-templates .template-item').nth(3).waitFor();
    assert.equal(await page.locator('#builtin-templates .template-item').count(), 4);
    await page.locator('#template-search').fill('редакц');
    assert.equal(await page.locator('#builtin-templates .template-item').count(), 1);
    await page.locator('#builtin-templates .template-choose').first().click();
    await page.locator('[data-field="event_date"]').fill('2026-03-15');
    assert.match(await page.locator('#template-preview').inputValue(), /15\.03\.2026/);
    assert.match(await page.locator('#template-preview').inputValue(), /\{договор\}/);
    await page.locator('#template-insert').click();
    assert.match(await page.locator('#template-fill-error').textContent(), /Заполните: Договор/);
    assert.equal(await page.locator('#question').inputValue(), '');
    await page.locator('[data-field="contract"]').fill('Тестовый договор Вега');
    assert.equal(await page.locator('#template-fill-error').textContent(), '');
    const composed = await page.locator('#template-preview').inputValue();
    assert.doesNotMatch(composed, /[{}]/);
    await page.screenshot({path: output + '/templates-fill-1440.png'});
    await page.locator('#template-insert').click();
    await page.locator('#templates-dialog').waitFor({state: 'hidden'});
    assert.equal(await page.locator('#question').inputValue(), composed);
    assert.equal((await api('/chats/' + chat.id)).turns.length, 2, 'A template must never send a question');

    // Own template from a question, with markup kept as text, then edit and delete with confirmation.
    await page.locator('.question-workspace-actions [data-icon="template"]').first().click();
    await page.locator('#template-editor').waitFor({state: 'visible'});
    assert.equal(await page.locator('#template-text').inputValue(), questions[0]);
    await page.locator('#template-name').fill('Мой шаблон ' + injection);
    await page.locator('#template-text').fill('Какие сроки по договору {договор}?\n');
    await page.locator('.template-tokens button', {hasText: '{уточнение}'}).click();
    await page.locator('#template-required input').first().check();
    await page.locator('#save-template').click();
    await page.locator('#own-templates .template-item').first().waitFor();
    assert.equal(await page.locator('#own-templates img').count(), 0);
    assert.match(await page.locator('#own-templates .template-choose strong').first().textContent(), /<img/);
    await page.locator('#own-templates button', {hasText: 'Изменить'}).click();
    await page.locator('#template-name').fill('Сроки по договору');
    await page.locator('#save-template').click();
    await page.waitForFunction(() => document.querySelector('#own-templates .template-choose strong')?.textContent === 'Сроки по договору');
    const stored = (await api('/question-templates')).own;
    assert.deepEqual(stored.map(item => [item.title, item.revision, item.required]), [['Сроки по договору', 2, ['contract']]]);
    await page.locator('#own-templates button', {hasText: 'Удалить'}).click(); await accept(page);
    await page.waitForFunction(() => !document.querySelector('#own-templates .template-item'));
    assert.deepEqual((await api('/question-templates')).own, []);
    await page.locator('#templates-dialog [data-close]').click();

    // 3. A review mark is the user's own and survives reload and another device; the core status does not change.
    const statusBefore = await page.locator('.message.assistant .message-status').first().textContent();
    await page.locator('.review-select').first().selectOption('needs_check');
    await page.waitForFunction(() => document.querySelector('.review-date')?.textContent.startsWith('Ваша отметка'));
    await page.reload(); await ready(page);
    await page.waitForFunction(() => document.querySelector('.review-select')?.value === 'needs_check');
    assert.equal(await page.locator('.message.assistant .message-status').first().textContent(), statusBefore);
    assert.deepEqual((await api('/chats/' + chat.id)).turns, before.turns);
    await second.goto(base); await ready(second);
    await second.waitForFunction(() => document.querySelector('.review-select')?.value === 'needs_check');
    await page.locator('#open-saved').click();
    await page.locator('#saved-review').selectOption('needs_check');
    await page.waitForFunction(() => document.querySelectorAll('#saved-answers .saved-answer').length === 1);
    assert.match(await page.locator('#saved-answers .saved-review').textContent(), /Нужна дополнительная проверка/);
    await page.locator('#saved-review').selectOption('sources_viewed');
    await page.waitForFunction(() => document.querySelectorAll('#saved-answers .saved-answer').length === 0);
    await page.locator('#saved-dialog [data-close]').click();

    // 2. A brief keeps the chosen order, shows answers verbatim, separates user text and never calls the model.
    await page.locator('#open-brief').click();
    await page.locator('#brief-answers input').nth(1).waitFor();
    await page.locator('#brief-answers input').nth(0).check();
    await page.locator('#brief-answers input').nth(1).check();
    await page.locator('#brief-sections [data-move="-1"]').nth(1).click();
    await page.locator('#brief-sections textarea').first().fill('Проверить расчёт ' + injection);
    await page.locator('#brief-intro').fill('Для руководителя');
    await page.locator('#brief-reviews').check();
    const preview = page.locator('#brief-preview');
    const sections = await preview.locator('.brief-section').allInnerTexts();
    assert.equal(sections.length, 2);
    assert.ok(sections[0].includes(questions[1]) && sections[0].includes(before.turns[1].answer.text), 'Second answer first and verbatim');
    assert.ok(sections[1].includes(before.turns[0].answer.text) && sections[1].includes('Нужна дополнительная проверка'));
    assert.equal(await preview.locator('img').count(), 0);
    assert.equal(await preview.locator('.brief-user').count(), 2);
    await page.screenshot({path: output + '/brief-1440.png'});
    await page.locator('#save-brief').click();
    await page.waitForFunction(() => document.querySelector('#brief-status').textContent.includes('сохранена'));
    const briefs = await api('/workspace/chats/' + chat.id + '/briefs');
    assert.deepEqual(briefs[0].sections.map(item => item.turn_index), [1, 0]);
    await page.evaluate(() => { window.print = () => { window.printedBrief = document.querySelector('#print-view').innerText; }; });
    await page.locator('#print-brief').click();
    const printed = await page.evaluate(() => window.printedBrief);
    const body = printed.slice(printed.indexOf('Раздел 1'));
    assert.ok(body.includes(before.turns[1].answer.text) && body.indexOf(questions[1]) < body.indexOf(questions[0]), 'Printed in the chosen order');
    assert.ok(printed.includes('не является проверенным юридическим заключением'));
    const copied = await page.evaluate(() => window.AnswerBriefs.text());
    assert.ok(copied.includes('Комментарий пользователя к разделу 1') && copied.includes('Источники раздела 2'));
    await page.locator('#close-brief').click();
    await page.locator('#brief-dialog').waitFor({state: 'hidden'});
    const after = await api('/chats/' + chat.id);
    assert.deepEqual(after.turns, before.turns);
    assert.equal((await api('/chats/' + chat.id + '/jobs')).jobs.length, 0, 'Brief actions must not queue generation');
    assert.equal(await page.evaluate(() => window.answerToolsInjected === true), false);
    await noOverflow(page, 'desktop');

    // Phone: icon-only template button inside the composer, one brief step at a time, no horizontal scroll.
    const phone = await browser.newContext({viewport: {width: 390, height: 844}, isMobile: true, hasTouch: true, reducedMotion: 'reduce', extraHTTPHeaders: headers});
    const mobile = await phone.newPage(); watch(mobile);
    await mobile.addInitScript(id => localStorage.setItem('psb-current-chat', id), chat.id);
    await mobile.goto(base); await ready(mobile);
    const box = await mobile.locator('#open-templates').boundingBox();
    assert.ok(box && box.width >= 44 && box.height >= 44 && box.x >= 0 && box.x + box.width <= 390 && box.y + box.height <= 844, JSON.stringify(box));
    assert.equal(await mobile.locator('#open-templates').getAttribute('aria-label'), 'Шаблоны');
    await noOverflow(mobile, 'phone');
    await mobile.screenshot({path: output + '/composer-390.png'});
    await mobile.locator('#open-templates').click();
    await mobile.locator('#builtin-templates .template-item').nth(3).waitFor();
    await noOverflow(mobile, 'phone templates');
    await mobile.screenshot({path: output + '/templates-390.png'});
    await mobile.locator('#templates-dialog [data-close]').click();
    const tools = await mobile.locator('#open-brief').boundingBox();
    assert.ok(tools && tools.x + tools.width <= 390, 'Brief button stays on screen: ' + JSON.stringify(tools));
    await mobile.locator('#open-brief').click();
    await mobile.locator('#brief-saved option').nth(1).waitFor({state: 'attached'});
    await mobile.locator('#brief-saved').selectOption({index: 1});
    assert.equal(await mobile.locator('.brief-preview-pane').isVisible(), false);
    await mobile.screenshot({path: output + '/brief-compose-390.png'});
    await mobile.locator('#brief-step-preview').click();
    assert.equal(await mobile.locator('.brief-compose').isVisible(), false);
    assert.equal(await mobile.locator('#brief-preview .brief-section').count(), 2);
    await noOverflow(mobile, 'phone brief');
    await mobile.screenshot({path: output + '/brief-preview-390.png'});
    assert.deepEqual(errors, []);
    console.log('answer tools browser check passed; screenshots in ' + output);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
