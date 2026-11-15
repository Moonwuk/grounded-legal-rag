// Run against the local queue_fixture.py service only. No real model calls.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.env.CHROMIUM_PATH, args: ['--no-sandbox']});
  const base = process.env.BASE_URL || 'http://127.0.0.1:8002';
  const auth = {extraHTTPHeaders: {'X-Chat-User': 'queue-browser', 'X-Chat-Token': 'fixture-token'}};
  const context = await browser.newContext({...auth, viewport: {width: 390, height: 844}});
  const page = await context.newPage();
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  let id;
  try {
    await page.goto(base);
    await page.waitForFunction(() => !document.querySelector('#send').disabled);
    assert.equal(await page.locator('.masthead #reset').count(), 0);
    await page.locator('#open-history').click();
    await page.locator('#reset').click();
    await page.waitForFunction(() => !document.querySelector('#mobile-panel').open);
    async function send(text) {
      await page.locator('#question').fill(text);
      await page.locator('#send').click();
      await page.waitForFunction(() => document.querySelector('#question').value === '');
    }
    const created = page.waitForResponse(r => r.url().endsWith('/api/chats') && r.request().method() === 'POST');
    await send('Первый вопрос по договору');
    id = (await (await created).json()).id;
    await page.locator('#stop-generation').waitFor({state: 'visible'});
    await send('Второй вопрос по договору');
    await send('Третий вопрос по договору');
    await page.waitForFunction(() => document.querySelectorAll('#queue-list li').length === 2);
    await page.getByRole('button', {name: 'Выше: Третий вопрос по договору', exact: true}).click();
    await page.waitForFunction(() => document.querySelector('#queue-list li span').textContent.startsWith('Третий'));
    await page.getByRole('button', {name: 'Ниже: Третий вопрос по договору', exact: true}).click();
    await page.waitForFunction(() => document.querySelector('#queue-list li span').textContent.startsWith('Второй'));
    await page.getByRole('button', {name: 'Выше: Третий вопрос по договору', exact: true}).click();
    await page.waitForFunction(() => document.querySelector('#queue-list li span').textContent.startsWith('Третий'));
    // Typing survives queue polling and completion renders.
    await page.locator('#question').fill('Черновик');
    await page.screenshot({path: '/tmp/legal-rag-queue-mobile.png'});
    await page.reload();
    await page.locator('#stop-generation').waitFor({state: 'visible'});
    await page.waitForFunction(() => document.querySelectorAll('#queue-list li').length === 2);
    assert.match(await page.locator('#queue-list li span').first().textContent(), /^Третий/);
    await page.locator('#stop-generation').click();
    await page.locator('#resume-queue').waitFor({state: 'visible'});
    assert.match(await page.locator('#conversation').innerText(), /Ответ остановлен/);
    await page.locator('#queue-list li').last().getByRole('button', {name: /Убрать/}).click();
    await page.waitForFunction(() => document.querySelectorAll('#queue-list li').length === 1);
    const second = await browser.newContext({...auth, viewport: {width: 1440, height: 1000}});
    const desktop = await second.newPage();
    await desktop.goto(base);
    await desktop.locator('#resume-queue').waitFor({state: 'visible'});
    assert.equal(await desktop.locator('#queue-list li').count(), 1);
    const reset = await desktop.locator('#reset').boundingBox();
    const folders = await desktop.locator('#history-folders').boundingBox();
    assert.ok(reset.y < folders.y);
    await desktop.locator('#resume-queue').click();
    await page.locator('#question').fill('Набираю следующий вопрос');
    await page.waitForFunction(() => document.querySelector('#conversation').textContent.includes('Тестовый ответ: Третий вопрос'));
    assert.equal(await page.locator('#question').inputValue(), 'Набираю следующий вопрос');
    await page.locator('.inline-citation').click();
    await page.locator('#doc-text mark').waitFor({state: 'visible'});
    await page.locator('#close-mobile-panel').click();
    const saved = await (await context.request.get(base + '/api/chats/' + id)).json();
    assert.deepEqual(saved.turns.map(t => t.question), ['Первый вопрос по договору', 'Третий вопрос по договору']);
    assert.equal(saved.turns[0].answer.status, 'cancelled');
    assert.equal(saved.turns[1].answer.status, 'answer');
    assert.equal(await page.locator('#question-queue').isVisible(), false);
    await send('Одиночный вопрос для повтора');
    await page.locator('#stop-generation').waitFor({state: 'visible'});
    await page.locator('#stop-generation').click();
    await page.getByRole('button', {name: 'Повторить ответ', exact: true}).waitFor({state: 'visible'});
    assert.equal(await page.locator('#queue-list li').count(), 0);
    await page.getByRole('button', {name: 'Повторить ответ', exact: true}).click();
    await page.waitForFunction(() => document.querySelector('#conversation').textContent.includes('Тестовый ответ: Одиночный вопрос'));
    const retried = await (await context.request.get(base + '/api/chats/' + id)).json();
    assert.equal(retried.turns.length, 3);
    assert.equal(retried.turns.at(-1).answer.status, 'answer');
    assert.deepEqual(errors, []);
    console.log('PASS: server queue, sending during generation, reload, stop/pause, remove queued, second device resume, draft preservation, citations, new-dialog placement, reorder above/below, retry stopped answer with empty queue.');
  } finally {
    if (id) {
      const response = await context.request.get(base + '/api/chats/' + id + '/jobs');
      if (response.ok()) for (const job of (await response.json()).jobs) await context.request.delete(base + '/api/chats/' + id + '/jobs/' + job.id);
      await context.request.delete(base + '/api/chats/' + id);
      await context.request.delete(base + '/api/chats/' + id + '/permanent');
    }
    await browser.close();
  }
})().catch(e => {console.error(e); process.exit(1);});
