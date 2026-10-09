// Renderizador quadro a quadro para cenas WebGL (three.js) + HTML, servidas em http://ad.local/
// Uso: node render3.js <pagina.html> <w> <h> <fps> <saida.mp4 | pasta> [stills t1,t2] [--from N --to M]
const {chromium} = require('playwright');
const {spawn} = require('child_process');
const fs = require('fs');
const path = require('path');
const ROOT = __dirname;
const MIME = {'.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.png': 'image/png', '.jpg': 'image/jpeg',
  '.woff2': 'font/woff2', '.woff': 'font/woff', '.json': 'application/json', '.svg': 'image/svg+xml', '.hdr': 'application/octet-stream'};
(async () => {
  const args = process.argv.slice(2);
  const [page_, w, h, fps, out, stills] = args;
  const W = Number(w), H = Number(h), F = Number(fps);
  const browser = await chromium.launch({args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--enable-webgl']});
  const ctx = await browser.newContext({viewport: {width: W, height: H}, deviceScaleFactor: 1});
  await ctx.route('http://ad.local/**', route => {
    const u = new URL(route.request().url());
    let f = path.join(ROOT, decodeURIComponent(u.pathname));
    if (!f.startsWith(ROOT)) return route.fulfill({status: 403, body: ''});
    try { f = fs.realpathSync(f); } catch (e) { return route.fulfill({status: 404, body: ''}); }
    if (!fs.existsSync(f) || fs.statSync(f).isDirectory()) return route.fulfill({status: 404, body: ''});
    route.fulfill({status: 200, contentType: MIME[path.extname(f)] || 'application/octet-stream', body: fs.readFileSync(f)});
  });
  const page = await ctx.newPage();
  page.on('pageerror', e => console.log('ERR', e.message));
  page.on('console', m => { if (m.type() === 'error' || m.text().startsWith('LOG')) console.log('console:', m.text()); });
  await page.goto(`http://ad.local/${page_}?w=${W}&h=${H}` + (process.env.Q ? '&' + process.env.Q : ''));
  await page.waitForFunction(() => window.ready, null, {timeout: 240000});
  const info = await page.evaluate(() => window.ready());
  const D = info.D;
  const sfxOut = out.endsWith('.mp4') ? out.replace(/\.mp4$/, '.sfx.json') : path.join(ROOT, 'sfx.json');
  fs.writeFileSync(sfxOut, JSON.stringify(await page.evaluate(() => window.SFX || [])));
  if (stills) {
    fs.mkdirSync(out, {recursive: true});
    for (const t of stills.split(',').map(Number)) {
      const t0 = Date.now();
      await page.evaluate(t => window.renderFrame(t), t);
      await page.screenshot({path: path.join(out, `s_${t.toFixed(2)}.jpg`), type: 'jpeg', quality: 90, timeout: 180000});
      console.log(`still ${t} ${Date.now() - t0}ms`);
    }
    await browser.close(); return;
  }
  const from = Number(process.env.FROM || 0), N = Math.round(D * F), to = Math.min(N, Number(process.env.TO || N));
  const toDir = !out.endsWith('.mp4');
  let ff;
  if (toDir) fs.mkdirSync(out, {recursive: true});
  else ff = spawn('ffmpeg', ['-v', 'error', '-y', '-f', 'image2pipe', '-framerate', String(F), '-c:v', 'mjpeg', '-i', '-',
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '14', '-pix_fmt', 'yuv420p', '-r', String(F), out], {stdio: ['pipe', 'inherit', 'inherit']});
  const t0 = Date.now();
  for (let i = from; i < to; i++) {
    await page.evaluate(t => window.renderFrame(t), i / F);
    const buf = await page.screenshot({type: 'jpeg', quality: 95, timeout: 180000});
    if (toDir) fs.writeFileSync(path.join(out, `f${String(i).padStart(5, '0')}.jpg`), buf);
    else if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    if ((i - from) % 60 === 0) console.log(`frame ${i}/${to} ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  }
  if (ff) { ff.stdin.end(); await new Promise(r => ff.on('close', r)); }
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
