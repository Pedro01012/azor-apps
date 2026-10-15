// Captura o site real (site/) em alta resolução, servido em http://site.local/
const {chromium} = require('playwright');
const {execFileSync} = require('child_process');
const fs = require('fs'), path = require('path');
const ROOT = path.join(__dirname, 'site'), OUT = path.join(__dirname, 'shots_site');
fs.mkdirSync(OUT, {recursive: true});
const cache = {};
const vw = Number(process.argv[2] || 430), dpr = Number(process.argv[3] || 3), tag = process.argv[4] || 'm';
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({viewport: {width: vw, height: 900}, deviceScaleFactor: dpr, reducedMotion: 'reduce', colorScheme: process.env.SCHEME || 'dark'});
  await ctx.route('**/*', route => {
    const u = new URL(route.request().url());
    if (u.host === 'site.local') {
      let f = path.join(ROOT, u.pathname === '/' ? 'index.html' : decodeURIComponent(u.pathname));
      if (!fs.existsSync(f)) return route.fulfill({status: 404, body: ''});
      return route.fulfill({status: 200, contentType: f.endsWith('.html') ? 'text/html' : f.endsWith('.png') ? 'image/png' : 'application/octet-stream', body: fs.readFileSync(f)});
    }
    if (/fonts\.(googleapis|gstatic)\.com/.test(u.host)) {
      if (!cache[u.href]) cache[u.href] = execFileSync('curl', ['-sS', '-A', 'Mozilla/5.0 Chrome/124', u.href], {maxBuffer: 1 << 26});
      return route.fulfill({status: 200, contentType: u.host.includes('googleapis') ? 'text/css' : 'font/woff2', body: cache[u.href], headers: {'access-control-allow-origin': '*'}});
    }
    return route.abort();
  });
  const page = await ctx.newPage();
  page.on('pageerror', e => console.log('ERR', e.message));
  await page.goto('http://site.local/', {waitUntil: 'networkidle'});
  await page.evaluate(() => document.fonts.ready);
  await page.addStyleTag({content: '*{animation-play-state:paused!important} [data-reveal],.reveal{opacity:1!important;transform:none!important}'});
  // força tudo que aparece com scroll
  for (let y = 0; y < 30000; y += 600) { await page.evaluate(y => scrollTo(0, y), y); await page.waitForTimeout(60); }
  await page.evaluate(() => scrollTo(0, 0)); await page.waitForTimeout(400);
  await page.screenshot({path: path.join(OUT, `${tag}_top.png`)});
  await page.evaluate(() => document.querySelectorAll('*').forEach(e => { const p = getComputedStyle(e).position; if ((p === 'fixed' || p === 'sticky') && e.tagName !== 'HTML') e.style.visibility = 'hidden'; }));
  const secs = await page.evaluate(() => [...document.querySelectorAll('header, section, footer, [id]')].filter(e => e.id || e.tagName != 'DIV')
    .map(e => { const r = e.getBoundingClientRect(); return {tag: e.tagName, id: e.id, cls: e.className && String(e.className).slice(0, 40), y: r.top + scrollY, h: r.height, w: r.width}; }).filter(s => s.h > 40));
  fs.writeFileSync(path.join(OUT, `rects_${tag}.json`), JSON.stringify(secs, null, 1));
  for (const s of secs.filter(s => s.id && s.h < 4000 && !/pix|pagamento|proof/.test(s.id) && /^[a-z][\w-]*$/i.test(s.id))) {
    try { await page.locator('#' + s.id).first().screenshot({path: path.join(OUT, `${tag}_${s.id}.png`), timeout: 60000}); console.log('ok', s.id, Math.round(s.y), Math.round(s.h)); }
    catch (e) { console.log('fail', s.id); }
  }
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
