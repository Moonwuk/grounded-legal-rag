// Creates an empty test chat and folder, tests trash across two browser contexts,
// then removes only these IDs. No model requests or existing chat mutations.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
(async () => {
  const browser = await chromium.launch({headless: true,
    ...(process.env.CHROMIUM_PATH ? {executablePath: process.env.CHROMIUM_PATH} : {}), args: ['--no-sandbox']});
  const base = process.env.BASE_URL || 'http://127.0.0.1:8002';
  const credentials = process.env.TEST_CREDENTIALS ? JSON.parse(fs.readFileSync(process.env.TEST_CREDENTIALS)) : null;
  const auth = credentials ? {httpCredentials: {username: credentials.username, password: credentials.password}} :
    {extraHTTPHeaders: {'X-Chat-User': 'trash-browser', 'X-Chat-Token': 'fixture-token'}};
  const context = await browser.newContext({...auth, viewport: {width: 1440, height: 1000}});
  const page = await context.newPage();
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  context.on('page', p => p.on('dialog', async d => { errors.push('Unexpected native dialog: ' + d.type()); await d.dismiss(); }));
  page.on('dialog', async d => { errors.push('Unexpected native dialog: ' + d.type()); await d.dismiss(); });
  let chatId, folderId;
  try {
    const folder = await context.request.post(base + '/api/chat-folders', {data: {title: 'Корзина тест ' + Date.now()}});
    assert.equal(folder.status(), 201); folderId = (await folder.json()).id;
    const chat = await context.request.post(base + '/api/chats?folder_id=' + folderId, {data: {}});
    assert.equal(chat.status(), 201); chatId = (await chat.json()).id;
    await page.goto(base);
    await page.waitForFunction(() => !document.querySelector('#send').disabled);
    if (!await page.locator('[data-chat-id="' + chatId + '"] .chat-actions').getAttribute('open').then(v => v !== null)) await page.locator('[data-chat-id="' + chatId + '"] .chat-actions').locator('summary').click();
    await page.locator('[data-chat-id="' + chatId + '"] .chat-delete').click();
    await page.locator('#confirm-accept').click();
    await page.locator('[data-chat-id="' + chatId + '"]').waitFor({state: 'detached'});
    assert.equal((await context.request.get(base + '/api/chats/' + chatId)).status(), 404);
    const other = await browser.newContext({...auth, viewport: {width: 390, height: 844}});
    const phone = await other.newPage(); phone.on('pageerror', e => errors.push(e.message));
    phone.on('dialog', async d => { errors.push('Unexpected native dialog: ' + d.type()); await d.dismiss(); });
    await phone.goto(base);
    await phone.waitForFunction(() => !document.querySelector('#send').disabled);
    await phone.locator('#open-history').click();
    if (!await phone.locator('#history-folders').getAttribute('open').then(v => v !== null)) await phone.locator('#history-folders > summary').click();
    await phone.locator('[data-folder-id="trash"]').click();
    const row = phone.locator('[data-chat-id="' + chatId + '"]');
    await row.waitFor();
    assert.equal(await row.locator('.chat-select').isDisabled(), true);
    await phone.screenshot({path: '/tmp/legal-rag-trash-mobile.png'});
    if (!await row.locator('.chat-actions').getAttribute('open').then(v => v !== null)) await row.locator('.chat-actions').locator('summary').click();
    await row.locator('.chat-move').click();
    await phone.waitForFunction(() => !document.querySelector('#mobile-panel').open);
    assert.equal((await (await context.request.get(base + '/api/chats/' + chatId)).json()).folder_id, folderId);
    await phone.locator('#open-history').click();
    if (!await row.locator('.chat-actions').getAttribute('open').then(v => v !== null)) await row.locator('.chat-actions').locator('summary').click();
    await row.locator('.chat-delete').click();
    await phone.locator('#confirm-accept').click();
    await row.waitFor({state: 'detached'});
    if (!await phone.locator('#history-folders').getAttribute('open').then(v => v !== null)) await phone.locator('#history-folders > summary').click();
    await phone.locator('[data-folder-id="trash"]').click();
    if (!await row.locator('.chat-actions').getAttribute('open').then(v => v !== null)) await row.locator('.chat-actions').locator('summary').click();
    await row.locator('.chat-delete').click();
    assert.equal(await phone.locator('#confirm-cancel').evaluate(e => document.activeElement === e), true);
    await phone.screenshot({path: '/tmp/legal-rag-confirm-mobile.png'});
    await phone.locator('#confirm-cancel').click();
    assert.equal(await row.count(), 1);
    if (!await row.locator('.chat-actions').getAttribute('open').then(v => v !== null)) await row.locator('.chat-actions').locator('summary').click();
    await row.locator('.chat-delete').click();
    await phone.keyboard.press('Escape');
    await phone.waitForFunction(() => !document.querySelector('#confirm-dialog').open);
    assert.equal(await phone.locator('#mobile-panel').evaluate(e => e.open), true);
    assert.equal(await row.count(), 1);
    if (!await row.locator('.chat-actions').getAttribute('open').then(v => v !== null)) await row.locator('.chat-actions').locator('summary').click();
    await row.locator('.chat-delete').click();
    await phone.locator('#confirm-accept').click();
    await row.waitFor({state: 'detached'});
    assert.equal((await context.request.post(base + '/api/chats/' + chatId + '/restore', {data: {}})).status(), 404);
    assert.deepEqual(errors, []);
    console.log('PASS: trash, second device, restore to original folder, mobile navigation, cancelled permanent deletion, final deletion.');
  } finally {
    if (chatId) {
      await context.request.delete(base + '/api/chats/' + chatId);
      await context.request.delete(base + '/api/chats/' + chatId + '/permanent');
    }
    if (folderId) await context.request.delete(base + '/api/chat-folders/' + folderId);
    await browser.close();
  }
})().catch(error => {console.error(error); process.exit(1);});
