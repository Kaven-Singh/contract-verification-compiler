/* Pipeline view: one row per compiler stage plus the VM, showing the backend's real status. */
'use strict';

(function (CVC) {
  const {$, esc} = CVC.util;
  const state = CVC.state;

  const STAGES = [
    ['lexer', 'Lexical analysis'],
    ['parser', 'Parsing & AST'],
    ['semantic', 'Semantic analysis'],
    ['fsm', 'FSM generation'],
    ['static', 'Static analysis'],
    ['bytecode', 'Bytecode generation'],
  ];

  const stageDetails = (stage) =>
    Object.entries(stage).filter(([key]) => key !== 'status').map(([key, value]) => `${key}: ${value}`).join(', ');

  const row = (number, title, status, label, details) =>
    `<div class="stage ${status}"><span>${number}</span><b>${title}</b><em>${label}</em><small>${esc(details)}</small></div>`;

  function render() {
    const rows = STAGES.map(([key, title], i) => {
      const stage = state.last.stages[key];
      return row(i + 1, title, stage.status, stage.status, stageDetails(stage));
    });
    // The VM row is derived from the last execution: "skipped" without bytecode, "not run" until executed.
    const vm = !state.last.bytecode ? 'skipped' : state.lastRun ? (['halted', 'terminated'].includes(state.lastRun.status) ? 'ok' : 'failed') : 'notrun';
    const detail = state.lastRun ? `${state.lastRun.status}, steps: ${state.lastRun.steps}` : '';
    rows.push(row(7, 'Virtual machine execution', vm, vm === 'notrun' ? 'not run' : vm, detail));
    $('stages').innerHTML = rows.join('');
  }

  CVC.pipeline = {render, clear: () => { $('stages').innerHTML = ''; }};
})(window.CVC);
