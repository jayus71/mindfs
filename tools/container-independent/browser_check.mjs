import { pathToFileURL } from 'node:url';
const [modulePath, url, screenshot] = process.argv.slice(2);
const { chromium } = await import(pathToFileURL(modulePath + '/index.mjs'));
const browser = await chromium.launch({ headless: true });
try {
  const context = await browser.newContext();
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(url, {waitUntil: 'networkidle'});
  await page.waitForTimeout(500);
  const title = await page.title();
  const text = await page.locator('body').innerText();
  if (!title.includes('MindFS') || !text.trim() || errors.length) {
    throw new Error(JSON.stringify({title, text: text.slice(0, 300), errors}));
  }
  await page.screenshot({path: screenshot, fullPage: true});
  console.log(JSON.stringify({title, text_excerpt:text.slice(0, 300), page_errors:errors}));
  await context.close();
} finally { await browser.close(); }
