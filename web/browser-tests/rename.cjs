// Exercises real server persistence on two devices; creates/deletes only its own chat.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
(async () => {
  const browser = await chromium.launch({headless: true,
    ...(process.env.CHROMIUM_PATH ? {executablePath: process.env.CHROMIUM_PATH} : {}), args: ['--no-sandbox']});
  const base = process.env.BASE_URL || 'http://127.0.0.1:8002';
  const credentials = process.env.TEST_CREDENTIALS ? JSON.parse(fs.readFileSync(process.env.TEST_CREDENTIALS)) : null;
  const auth = credentials ? {httpCredentials: {username: credentials.username, password: credentials.password}} :
    {extraHTTPHeaders: {'X-Chat-User': 'rename-browser', 'X-Chat-Token': 'fixture-token'}};
  const context = await browser.newContext({...auth, viewport: {width: 390, height: 844}});
  const page = await context.newPage();
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  let id;
  const title = 'Аренда склада · ' + Date.now();
  try {
    const created = await context.request.post(base + '/api/chats', {data: {}});
    assert.equal(created.status(), 201); id = (await created.json()).id;
    const row = '[data-chat-id="' + id + '"]';
    await page.goto(base);
    await page.locator('#open-history').click();
    await page.locator(row + ' .chat-rename').click();
    assert.equal(await page.locator('#chat-name').inputValue(), 'Новый диалог');
    await page.locator('#chat-name').fill('Отменённое название');
    await page.locator('#cancel-chat-name').click();
    assert.equal((await (await context.request.get(base + '/api/chats/' + id)).json()).title, 'Новый диалог');
    await page.locator(row + ' .chat-rename').click();
    await page.locator('#chat-name').fill('   ');
    await page.locator('#save-chat-name').click();
    await page.waitForFunction(() => document.querySelector('#rename-error').textContent.length > 0);
    await page.locator('#chat-name').fill(title);
    await page.locator('#save-chat-name').click();
    await page.waitForFunction(() => !document.querySelector('#rename-dialog').open);
    assert.equal(await page.locator(row + ' .chat-select-title').textContent(), title);
    assert.equal(await page.locator(row + ' .chat-rename').isEnabled(), true);
    await page.locator(row + ' .chat-rename').click();
    assert.equal(await page.locator('#chat-name').inputValue(), title);
    await page.locator('#cancel-chat-name').click();
    await page.screenshot({path: '/tmp/legal-rag-rename-mobile.png'});
    await page.reload();
    await page.locator('#open-history').click();
    assert.equal(await page.locator(row + ' .chat-select-title').textContent(), title);
    const other = await browser.newContext({...auth, viewport: {width: 1440, height: 1000}});
    const desktop = await other.newPage(); await desktop.goto(base);
    assert.equal(await desktop.locator(row + ' .chat-select-title').textContent(), title);
    assert.equal((await context.request.delete(base + '/api/chats/' + id)).status(), 204);
    assert.equal((await context.request.post(base + '/api/chats/' + id + '/restore', {data: {}})).status(), 204);
    assert.equal((await (await context.request.get(base + '/api/chats/' + id)).json()).title, title);
    assert.deepEqual(errors, []);
    await other.close();
    console.log('PASS: mobile rename/cancel/validation, reload, second device, trash and restore.');
  } finally {
    if (id) {
      await context.request.delete(base + '/api/chats/' + id);
      await context.request.delete(base + '/api/chats/' + id + '/permanent');
    }
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
