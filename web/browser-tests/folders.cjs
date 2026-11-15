// Uses a test account or TEST_CREDENTIALS. Creates only its own empty test chats
// and uniquely named folder, then removes those IDs. Model answers are stubbed.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
(async () => {
  const browser = await chromium.launch({headless: true,
    ...(process.env.CHROMIUM_PATH ? {executablePath: process.env.CHROMIUM_PATH} : {}), args: ['--no-sandbox']});
  const base = process.env.BASE_URL || 'http://127.0.0.1:8002';
  const credentials = process.env.TEST_CREDENTIALS ? JSON.parse(fs.readFileSync(process.env.TEST_CREDENTIALS)) : null;
  const auth = credentials ? {httpCredentials: {username: credentials.username, password: credentials.password}} :
    {extraHTTPHeaders: {'X-Chat-User': 'folder-browser', 'X-Chat-Token': 'fixture-token'}};
  const context = await browser.newContext({...auth, viewport: {width: 390, height: 844}});
  const page = await context.newPage();
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  page.on('dialog', async d => { errors.push('Unexpected native dialog: ' + d.type()); await d.dismiss(); });
  let folderId, chats = [];
  const name = 'Проверка папки ' + Date.now();
  try {
    const created = await context.request.post(base + '/api/chats', {data: {}});
    assert.equal(created.status(), 201);
    chats.push((await created.json()).id);
    await page.goto(base);
    await page.waitForFunction(() => !document.querySelector('#send').disabled);
    await page.locator('#open-history').click();
    await page.locator('#create-chat-folder').click();
    await page.locator('#folder-name').fill(name);
    const saved = page.waitForResponse(r => r.url().endsWith('/api/chat-folders') && r.request().method() === 'POST');
    await page.locator('#save-chat-folder').click();
    folderId = (await (await saved).json()).id;
    await page.waitForFunction(() => !document.querySelector('#folder-dialog').open);
    assert.equal(await page.locator('#folder-empty').isVisible(), true);
    await page.locator('[data-folder-id="all"]').click();
    await page.locator('[data-chat-id="' + chats[0] + '"] .chat-move').click();
    await page.locator('#move-folder').selectOption(folderId);
    await page.locator('#save-chat-move').click();
    await page.waitForFunction(() => !document.querySelector('#move-dialog').open);
    await page.locator('[data-folder-id="' + folderId + '"]').click();
    assert.equal(await page.locator('#chat-list li').count(), 1);
    await page.locator('#edit-chat-folder').click();
    await page.locator('#folder-name').fill(name + ' — сделки');
    await page.locator('#save-chat-folder').click();
    await page.waitForFunction(() => !document.querySelector('#folder-dialog').open);
    await page.screenshot({path: '/tmp/legal-rag-chat-folders-mobile.png'});
    const other = await browser.newContext({...auth, viewport: {width: 1440, height: 1000}});
    const desktop = await other.newPage();
    await desktop.goto(base);
    await desktop.locator('[data-folder-id="' + folderId + '"]').click();
    assert.equal(await desktop.locator('#chat-list li').count(), 1);
    assert.equal(await desktop.locator('[data-folder-id="' + folderId + '"]').getAttribute('title'), name + ' — сделки');
    await desktop.screenshot({path: '/tmp/legal-rag-chat-folders-desktop.png'});
    await page.locator('#reset').click();
    await page.waitForFunction(() => !document.querySelector('#mobile-panel').open);
    // The folder scenario checks placement; generation/queue is covered separately.
    await page.route('**/jobs', route => route.request().method() === 'POST'
      ? route.fulfill({status: 202, json: {id: route.request().postDataJSON().id, status: 'queued'}}) : route.continue());
    const newChat = page.waitForResponse(r => r.url().includes('/api/chats?folder_id=') && r.request().method() === 'POST');
    await page.locator('#question').fill('Проверка создания диалога в папке');
    await page.locator('#send').click();
    const newData = await (await newChat).json();
    chats.push(newData.id);
    assert.equal(newData.folder_id, folderId);
    await page.waitForFunction(() => document.querySelector('#question').value === '');
    await page.locator('#open-history').click();
    assert.equal(await page.locator('#chat-list li').count(), 2);
    await page.locator('#edit-chat-folder').click();
    await page.locator('#delete-chat-folder').click();
    await page.locator('#confirm-cancel').click();
    assert.equal(await page.locator('#folder-dialog').evaluate(e => e.open), true);
    await page.locator('#delete-chat-folder').click();
    await page.locator('#confirm-accept').click();
    await page.waitForFunction(() => !document.querySelector('#folder-dialog').open);
    for (const id of chats) {
      const kept = await context.request.get(base + '/api/chats/' + id);
      assert.equal(kept.status(), 200);
      assert.equal((await kept.json()).folder_id, null);
    }
    assert.equal(await page.locator('[data-folder-id="unfiled"]').getAttribute('aria-current'), 'true');
    assert.equal(await page.locator('#create-chat-folder').isEnabled(), true);
    assert.deepEqual(errors, []);
    console.log('PASS: create, move, rename, second browser, mobile drawer, new chat in folder, delete folder without deleting chats.');
  } finally {
    if (folderId) await context.request.delete(base + '/api/chat-folders/' + folderId);
    for (const id of chats) {
      await context.request.delete(base + '/api/chats/' + id);
      await context.request.delete(base + '/api/chats/' + id + '/permanent');
    }
    await browser.close();
  }
})().catch(error => {console.error(error); process.exit(1);});
