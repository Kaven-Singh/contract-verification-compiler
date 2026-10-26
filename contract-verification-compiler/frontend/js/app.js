/* Application orchestration: tabs, the compile workflow, dashboard counters and toolbar wiring. */
'use strict';

(function (CVC) {
  const {$} = CVC.util;
  const state = CVC.state;
  const {request} = CVC.api;
  const {editor} = CVC;

  // ---- loading indicator: a counter, so overlapping requests keep it visible until the last one ends --------
  let pending = 0;
  function setBusy(delta) {
    pending += delta;
    document.body.classList.toggle('busy', pending > 0);
    $('spin').hidden = pending <= 0;
  }

  // ---- tabs (generated from each panel's data-title; arrow keys move between tabs) ---------------------------
  function showTab(id) {
    document.querySelectorAll('.tab').forEach((panel) => { panel.hidden = panel.id !== id; });
    document.querySelectorAll('#tabs button').forEach((button) => button.setAttribute('aria-selected', String(button.dataset.t === id)));
  }

  function createTabs() {
    const tabs = $('tabs');
    document.querySelectorAll('.tab').forEach((panel) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.setAttribute('role', 'tab');
      button.setAttribute('aria-controls', panel.id);
      button.dataset.t = panel.id;
      button.textContent = panel.dataset.title;
      button.addEventListener('click', () => showTab(panel.id));
      tabs.appendChild(button);
    });
    tabs.addEventListener('keydown', (event) => {
      const buttons = [...tabs.querySelectorAll('button')];
      const step = {ArrowRight: 1, ArrowLeft: -1}[event.key];
      if (!step) return;
      const next = buttons[(buttons.indexOf(document.activeElement) + step + buttons.length) % buttons.length];
      next.focus();
      showTab(next.dataset.t);
    });
  }

  // ---- results ---------------------------------------------------------------------------------------------
  function renderStats() {
    const diagnostics = state.last ? state.last.diagnostics : [];
    const card = (value, label) => `<div class="card"><b>${value}</b>${label}</div>`;
    $('stats').innerHTML = card(state.compiles, 'compilations')
      + card(diagnostics.filter((d) => d.severity === 'error').length, 'errors')
      + card(diagnostics.filter((d) => d.severity === 'warning').length, 'warnings')
      + card(state.repairs.length, 'repair suggestions');
  }

  function renderResults() {
    const compiled = state.last;
    editor.renderDiagnostics();
    CVC.pipeline.render();
    CVC.ast.render(compiled.ast);
    if (compiled.fsm) CVC.fsm.render(compiled.fsm, compiled.analysis ? compiled.analysis.reachability.unreachable_states : []);
    else CVC.fsm.showUnavailable();
    CVC.analysis.render(compiled.analysis);
    CVC.execution.renderBytecode(compiled.bytecode);
    $('vmOut').innerHTML = '';
    editor.highlight();
  }

  /**
   * Compile the editor text, then fetch repair suggestions for its diagnostics.
   * Each call takes a ticket; if a newer compile started meanwhile, this one's results are dropped so a slow
   * older response can never overwrite a newer one.
   */
  async function compile() {
    setBusy(1);
    try {
      editor.highlight();
      const ticket = ++state.compileSeq;
      const source = editor.getSource();
      const {status, data} = await request('compile', {source});
      if (ticket !== state.compileSeq) return;
      if (status !== 200) return editor.showMessage('Server error: ' + JSON.stringify(data), 'error');
      state.last = data;
      state.lastRun = null;
      state.compiles++;
      renderResults();
      const repairResponse = data.diagnostics.length ? await request('repair', {source}) : null;
      if (ticket !== state.compileSeq) return;
      state.repairs = repairResponse && repairResponse.status === 200 ? repairResponse.data.repairs : [];
      CVC.repairs.render();
      renderStats();
    } catch (e) {
      editor.showMessage('Request failed: ' + e.message, 'error');
    } finally {
      setBusy(-1);
    }
  }

  /** Reset the editor and every derived view; also invalidates in-flight requests. */
  function clearAll() {
    state.compileSeq++;
    state.runSeq++;
    Object.assign(state, {last: null, lastRun: null, repairs: [], undoSource: null});
    $('bUndo').disabled = true;
    editor.setSource('');
    editor.showMessage('Cleared.');
    CVC.pipeline.clear();
    CVC.ast.clear();
    CVC.fsm.clear();
    CVC.analysis.clear();
    CVC.repairs.clear();
    CVC.execution.clear();
    renderStats();
  }

  async function loadExample(id) {
    if (!id) return;
    const {status, data} = await request('examples/' + id);
    if (status !== 200) return editor.showMessage('Could not load example: ' + (data.error || status), 'error');
    state.loaded = data.source;
    editor.setSource(state.loaded);
    await compile();
  }

  async function populateExamples() {
    try {
      const {data} = await request('examples');
      for (const example of data) {
        const option = document.createElement('option');
        option.value = example.id;
        option.textContent = example.title;
        $('examples').appendChild(option);
      }
    } catch (e) {
      editor.showMessage('Cannot reach the API: ' + e.message, 'error');
    }
  }

  function init() {
    createTabs();
    editor.init();
    CVC.repairs.init();
    $('bCompile').addEventListener('click', compile);
    $('bBytecode').addEventListener('click', async () => { await compile(); showTab('vm'); });
    $('bExec').addEventListener('click', CVC.execution.execute);
    $('bClear').addEventListener('click', clearAll);
    $('bReset').addEventListener('click', async () => { editor.setSource(state.loaded); await compile(); });
    $('bUndo').addEventListener('click', async () => {
      if (state.undoSource === null) return;
      editor.setSource(state.undoSource);
      state.undoSource = null;
      $('bUndo').disabled = true;
      await compile();
    });
    $('bDl').addEventListener('click', editor.download);
    $('examples').addEventListener('change', (event) => loadExample(event.target.value));
    showTab('dash');
    renderStats();
    populateExamples();
  }

  CVC.app = {compile, showTab, setBusy};
  init();
})(window.CVC);
