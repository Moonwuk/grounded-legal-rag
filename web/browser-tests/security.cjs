// Read-only browser probe. Injected chat content is a local route fixture, never saved.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
(async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.env.CHROMIUM_PATH, args: ['--no-sandbox']});
  const base = process.env.BASE_URL || 'http://127.0.0.1:8002';
  const credentials = process.env.TEST_CREDENTIALS ? JSON.parse(fs.readFileSync(process.env.TEST_CREDENTIALS)) : null;
  const context = await browser.newContext(credentials ? {httpCredentials: {username: credentials.username, password: credentials.password}} : {});
  const page = await context.newPage();
  const errors = []; page.on('pageerror', e => errors.push(e.message));
  const payload = '<img src=x onerror="window.securityProbeExecuted=true">';
  const chat = {id: 'security-probe', title: payload, updated: 1,
    turns: [{question: payload, answer: {status: 'answer', text: payload, sources: []}}]};
  await page.route('**/api/chat-folders', route => route.fulfill({json: []}));
  await page.route('**/api/document-tabs', route => route.fulfill({json: []}));
  await page.route('**/api/chats**', route => {
    const url = route.request().url();
    return route.fulfill({json: url.endsWith('/jobs') ? {jobs: [], paused: false, turns: chat.turns, title: chat.title} :
      url.includes('?trash=true') ? [] : url.endsWith('/api/chats') ? [chat] : chat});
  });
  try {
    const response = await page.goto(base);
    assert.match(response.headers()['content-security-policy'], /frame-ancestors 'none'/);
    assert.match(response.headers()['content-security-policy'], /script-src 'self'/);
    await page.locator('.chat-select').click();
    await page.waitForFunction(() => document.querySelector('#conversation').textContent.includes('onerror='));
    assert.equal(await page.locator('#conversation img').count(), 0);
    assert.equal(await page.evaluate(() => window.securityProbeExecuted === true), false);
    assert.equal(await page.locator('.chat-select-title').textContent(), payload);
    assert.deepEqual(errors, []);
    console.log('PASS: CSP headers and literal rendering of untrusted chat titles, questions and model output; no injected image or script execution.');
  } finally { await browser.close(); }
})().catch(e => {console.error(e); process.exitCode = 1;});
