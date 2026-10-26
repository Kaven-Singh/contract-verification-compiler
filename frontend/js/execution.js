/* Bytecode listing, runtime inputs and VM execution view. All values come from the backend. */
'use strict';

(function (CVC) {
  const {$, esc} = CVC.util;
  const state = CVC.state;
  const {request} = CVC.api;

  const INPUT_DEFAULTS = {DATE: '2026-03-10', BOOL: false, NUMBER: 0, MONEY: 0};

  function inputTemplate(bytecode) {
    const template = {};
    for (const [name, type] of Object.entries(bytecode.vars)) {
      template[name] = type === 'ENUM' ? bytecode.enums[name][0] : INPUT_DEFAULTS[type];
    }
    return template;
  }

  function renderBytecode(bytecode) {
    if (!bytecode) {
      $('bc').textContent = 'No bytecode: compilation did not succeed.';
      return;
    }
    $('bc').textContent = bytecode.code
      .map((ins, i) => String(i).padStart(3) + '  ' + ins.op.padEnd(19) + (ins.arg === null ? '' : JSON.stringify(ins.arg)))
      .join('\n');
    // Regenerate the input template only when the variable set changes, so the user's edits survive recompiles.
    const signature = JSON.stringify(bytecode.vars);
    if ($('inputs').dataset.sig !== signature) {
      $('inputs').value = JSON.stringify(inputTemplate(bytecode), null, 2);
      $('inputs').dataset.sig = signature;
    }
  }

  function table(headers, rows) {
    const cell = (x) => `<td>${esc(typeof x === 'object' ? JSON.stringify(x) : x)}</td>`;
    return `<div class="table-scroll"><table><tr>${headers.map((h) => `<th>${h}</th>`).join('')}</tr>${rows.map((r) => `<tr>${r.map(cell).join('')}</tr>`).join('')}</table></div>`;
  }

  function renderRun(run) {
    $('vmOut').innerHTML = `<h3>Result</h3><p>Status: <b>${esc(run.status)}</b> · final state: <b>${esc(run.final_state)}</b> · steps: ${run.steps}</p>
      ${run.errors.length ? '<pre>' + esc(run.errors.join('\n')) + '</pre>' : ''}
      <h3>Obligations</h3>${table(['rule', 'action', 'args'], run.obligations.map((o) => [o.rule, o.name, o.args]))}
      <h3>Transitions</h3>${table(['rule', 'from', 'to'], run.transitions.map((o) => [o.rule, o.from, o.to]))}
      <h3>Guard evaluations</h3>${table(['rule', 'check', 'result'], run.guard_evals.map((o) => [o.rule, o.check, o.result]))}
      <h3>Trace</h3>${table(['step', 'pc', 'op', 'arg', 'stack'], run.trace.map((o) => [o.step, o.pc, o.op, o.arg, o.stack]))}`;
  }

  function showText(text) {
    CVC.app.showTab('vm');
    $('vmOut').innerHTML = `<p>${esc(text)}</p>`;
  }

  async function execute() {
    if (!state.last || !state.last.bytecode) await CVC.app.compile();
    if (!state.last || !state.last.bytecode) return showText('Cannot execute: the contract did not compile cleanly.');
    let inputs;
    try {
      inputs = JSON.parse($('inputs').value);
    } catch (e) {
      return showText('Inputs are not valid JSON: ' + e.message);
    }
    const ticket = ++state.runSeq;
    CVC.app.setBusy(1);
    try {
      const {status, data} = await request('execute', {source: CVC.editor.getSource(), inputs, max_steps: Number($('steps').value) || 10000});
      if (ticket !== state.runSeq) return; // superseded by a newer run or by Clear
      CVC.app.showTab('vm');
      if (status !== 200) return showText('Execution refused: ' + JSON.stringify(data));
      state.lastRun = data;
      CVC.pipeline.render();
      renderRun(data);
    } catch (e) {
      showText('Request failed: ' + e.message);
    } finally {
      CVC.app.setBusy(-1);
    }
  }

  CVC.execution = {renderBytecode, execute, clear: () => { $('bc').textContent = 'Compile a valid contract to see bytecode.'; $('vmOut').innerHTML = ''; }};
})(window.CVC);
