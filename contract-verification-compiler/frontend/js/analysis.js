/* Static-analysis panel: reachability, conflicts and cycles. Proven and possible conflicts stay visibly distinct. */
'use strict';

(function (CVC) {
  const {$, esc} = CVC.util;

  const list = (items) => (items.length ? items.map(esc).join(', ') : 'none');

  function conflictHtml(c) {
    const witness = c.witness ? `, witness ${esc(JSON.stringify(c.witness))}` : '';
    return `<p>State <b>${esc(c.state)}</b>: ${c.rules.map(esc).join(' vs ')} (${c.actions.map(esc).join(' vs ')}) — overlap ${c.overlap}${witness}</p>`;
  }

  function render(analysis) {
    if (!analysis) {
      $('analysis').textContent = 'Analysis did not run: an earlier stage failed.';
      return;
    }
    const r = analysis.reachability;
    const diagnostics = analysis.diagnostics.map((d) => `<li class="${d.severity}"><b>${d.code}</b> ${d.line}:${d.col} — ${esc(d.message)}</li>`).join('');
    $('analysis').innerHTML = `
      <h3>Reachability (BFS)</h3>
      <p>Reachable: ${list(r.reachable)}<br>Unreachable states: ${list(r.unreachable_states)}<br>Unreachable rules: ${list(r.unreachable_rules)}</p>
      <p class="legend">${esc(r.note)}</p>
      <h3>Conflicts</h3>${analysis.conflicts.length ? analysis.conflicts.map(conflictHtml).join('') : '<p>No conflicts found.</p>'}
      <h3>Cycles (Tarjan SCC)</h3>${analysis.cycles.length
        ? analysis.cycles.map((c) => `<p>${c.states.map(esc).join(' ↔ ')} — rules ${c.rules.map(esc).join(', ')}; exit: <b>${c.exit_status}</b></p>`).join('')
        : '<p>No structural cycles.</p>'}
      <h3>Diagnostics</h3><ul class="diagnostics">${diagnostics || '<li class="ok">None.</li>'}</ul>`;
  }

  CVC.analysis = {render, clear: () => { $('analysis').textContent = 'Compile a contract to see the analysis.'; }};
})(window.CVC);
