/* Repair suggestions: before/after, assumptions, sampled behaviour, preview and explicit apply (with undo). */
'use strict';

(function (CVC) {
  const {$, esc} = CVC.util;
  const state = CVC.state;
  const {editor} = CVC;

  function behaviorText(behavior) {
    if (!behavior) return 'Behavioural comparison unavailable (original does not reach FSM generation).';
    const summary = behavior.differences
      ? `Behaviour differs on ${behavior.differences} of ${behavior.samples} sampled inputs, e.g. ${esc(JSON.stringify(behavior.example))}`
      : `No behavioural difference on ${behavior.samples} sampled inputs`;
    return `${summary} (bounded sampling, not a proof).`;
  }

  function card(repair, index) {
    const issues = repair.new_issues.length ? ` · new issues: ${esc(repair.new_issues.map((x) => x.code).join(', '))}` : '';
    return `<div class="repair"><b>${esc(repair.code)}</b> · rule <code>${esc(repair.rule)}</code> <span class="tag ${repair.status}">${esc(repair.status.replace('_', ' '))}</span>
      <p>${esc(repair.description)}</p>
      <p class="legend">⚠ ${esc(repair.assumption)} Review before applying.</p>
      <p class="legend">${behaviorText(repair.behavior)}</p>
      <div class="before-after"><div><small>Before</small><pre>${esc(repair.before)}</pre></div><div><small>After</small><pre>${esc(repair.after)}</pre></div></div>
      <p class="legend">syntax valid: ${repair.syntax_valid} · diagnostic resolved: ${repair.resolved} · no errors remain: ${repair.valid}${issues}</p>
      <button type="button" data-p="${index}">Preview diagnostics</button> <button type="button" data-a="${index}" class="primary">Apply to editor</button>
      <div id="pv${index}"></div></div>`;
  }

  function render() {
    $('repairs').innerHTML = state.repairs.length ? state.repairs.map(card).join('') : 'No repair suggestions for the current diagnostics.';
  }

  function preview(index) {
    const items = state.repairs[index].after_diagnostics.map((d) => `<li class="${d.severity}"><b>${d.code}</b> ${esc(d.message)}</li>`).join('');
    $('pv' + index).innerHTML = `<ul class="diagnostics">${items || '<li class="ok">Repaired contract has no diagnostics.</li>'}</ul>`;
  }

  /** Put the repaired source in the editor only after the user confirms, keep the original for Undo, then recompile. */
  async function apply(index) {
    const repair = state.repairs[index];
    if (!window.confirm('Replace the editor source with the repaired contract? You can undo afterwards.')) return;
    state.undoSource = editor.getSource();
    $('bUndo').disabled = false;
    editor.setSource(repair.new_source);
    await CVC.app.compile();
    if (!state.last) return;
    const [code, rule] = repair.id.split('#')[0].split(':'); // ids look like "E301:waive" or "E301:waive#1"
    const remains = state.last.diagnostics.some((d) => d.code === code && d.rule === rule);
    $('repMsg').textContent = `Applied ${repair.id}. Recompiled: ${state.last.diagnostics.length} diagnostic(s) remain${remains ? ' (the targeted diagnostic is still present)' : '; the targeted diagnostic is resolved'}.`;
    CVC.app.showTab('rep');
  }

  function clear() {
    $('repairs').textContent = 'No repairs yet.';
    $('repMsg').textContent = '';
  }

  function init() {
    // One delegated handler: cards are re-rendered often, so listeners on the buttons themselves would leak.
    $('repairs').addEventListener('click', (event) => {
      const button = event.target.closest('button');
      if (!button) return;
      if (button.dataset.p !== undefined) preview(Number(button.dataset.p));
      else if (button.dataset.a !== undefined) apply(Number(button.dataset.a));
    });
  }

  CVC.repairs = {init, render, clear};
})(window.CVC);
