// Usage: (server running on :8000)  npm i jsdom && node tests/e2e_browser.js [baseUrl]
const {JSDOM} = require('jsdom');
const base = process.argv[2] || 'http://127.0.0.1:8000';
const sleep = ms => new Promise(r => setTimeout(r, ms));
let fails = 0;
const check = (name, ok) => { console.log((ok ? 'PASS ' : 'FAIL ') + name); if (!ok) fails++; };
(async () => {
  const dom = await JSDOM.fromURL(base + '/', {runScripts: 'dangerously', resources: 'usable', pretendToBeVisual: true,
    beforeParse(w) {
      w.fetch = async (u, o) => {                       // test hooks: '# slow' delays the reply, '# fail' simulates a broken server
        const b = (o && o.body) || '';
        if (b.includes('# slow')) await sleep(1500);
        if (b.includes('# fail')) return new Response('oops', {status: 500});
        return fetch(new URL(u, base), o);
      };
      w.confirm = () => true;
    }});
  const w = dom.window, d = w.document, $ = id => d.getElementById(id);
  const pick = async id => { $('examples').value = id; $('examples').dispatchEvent(new w.Event('change')); await sleep(1500); };
  await sleep(1500);
  check('examples loaded into the dropdown', $('examples').options.length === 9);
  await pick('conflict');
  check('conflict example shows E301 diagnostic', $('diags').textContent.includes('E301'));
  check('static stage failed, bytecode skipped', $('stages').textContent.includes('failed') && $('stages').querySelectorAll('.skipped').length >= 2);
  check('syntax highlighting renders keywords and marks the error line', $('hl').innerHTML.includes('<i class="k">RULE</i>') && $('hl').innerHTML.includes('ln err'));
  check('FSM svg drawn', !!d.querySelector('#fsm svg'));
  check('repair suggestion rendered with assumption', $('repairs').textContent.includes('Assumes'));
  check('repair card reports sampled behavioural difference', $('repairs').textContent.includes('Behaviour differs on'));
  d.querySelector('#repairs button[data-a="0"]').click(); await sleep(2000);
  check('applying repair edits the editor and recompiles clean', $('src').value.includes('UNLESS') && $('diags').textContent.includes('No diagnostics'));
  $('bUndo').click(); await sleep(1500);
  check('undo restores original source', !$('src').value.includes('UNLESS') && $('diags').textContent.includes('E301'));
  await pick('valid_service');
  $('inputs').value = JSON.stringify({paymentDate: '2026-03-10', dueDate: '2026-01-01', forceMajeure: false, amount: 100});
  $('bExec').click(); await sleep(2000);
  check('execute shows VM result', $('vmOut').textContent.includes('halted') && $('vmOut').textContent.includes('PENALTY'));
  $('inputs').value = '{ not json'; $('bExec').click(); await sleep(500);
  check('bad JSON inputs handled', $('vmOut').textContent.includes('not valid JSON'));
  $('bClear').click();
  check('clear resets editor, results and repairs', $('src').value === '' && $('repairs').textContent === 'No repairs yet.' && $('stages').innerHTML === '' && $('vmOut').innerHTML === '');
  await pick('type_mismatch'); $('src').value = $('src').value + '\n'; $('bReset').click(); await sleep(1500);
  check('reset restores example and recompiles', $('diags').textContent.includes('E201') && !$('src').value.endsWith('\n\n'));
  $('src').value = 'VAR p: DATE; VAR d: DATE; STATE S INITIAL; RULE r1 FROM S: IF p > d + 30 DAYS THEN PENALTY(1); RULE r2 FROM S: IF p > d + 60 DAYS THEN WAIVE_PENALTY();';
  $('bCompile').click(); await sleep(1500);
  check('undecidable overlap is shown as possible (W311), never as proven (E301)', $('diags').textContent.includes('W311') && !$('diags').textContent.includes('E301') && $('analysis').textContent.includes('overlap possible'));
  const valid = 'VAR a: NUMBER; STATE S INITIAL; RULE r FROM S: IF a > 1 THEN PENALTY(1);';
  $('src').value = valid.replace('VAR a: NUMBER;', 'VAR a: NUMBER; VAR a: NUMBER;') + ' # slow';    // slow request that would show E203
  $('bCompile').click();
  $('src').value = valid; $('bCompile').click();                                                 // fast, newer request
  await sleep(3000);
  check('stale (slow, older) response does not overwrite the newer result', $('diags').textContent.includes('No diagnostics') && !$('diags').textContent.includes('E203'));
  $('src').value = valid + ' # fail'; $('bCompile').click(); await sleep(800);
  check('API failure shows an error and does not crash', $('diags').textContent.includes('Server error'));
  $('src').value = valid; $('bCompile').click(); await sleep(1000);
  check('app recovers after a failure', $('diags').textContent.includes('No diagnostics'));
  $('src').value = '# <img src=x onerror="window.__xss=1"> & "quotes"\nVAR x: DATE; @';
  $('bCompile').click(); await sleep(1200);
  check('contract text is rendered as text, never as HTML', !w.__xss && !d.querySelector('#hl img') && !d.querySelector('#diags img') && $('hl').textContent.includes('<img'));
  const firstTab = d.querySelector('#tabs button'); firstTab.focus();
  firstTab.dispatchEvent(new w.KeyboardEvent('keydown', {key: 'ArrowRight', bubbles: true}));
  const selected = d.querySelectorAll('#tabs [aria-selected="true"]');
  check('arrow keys move between tabs and update aria-selected', selected.length === 1 && selected[0] !== firstTab);
  process.exit(fails ? 1 : 0);
})();
