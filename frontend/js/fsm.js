/* FSM visualizer: an SVG graph generated from the backend's FSM (no graph library needed for contract-sized FSMs). */
'use strict';

(function (CVC) {
  const {$, esc} = CVC.util;

  const SVG_DEFS = '<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="#6ea8fe"/></marker></defs>';

  /** Place states on a circle so the layout is deterministic and needs no physics simulation. */
  function layout(states) {
    const radius = Math.min(170, 50 + states.length * 24);
    const positions = {};
    states.forEach((s, i) => {
      const angle = (2 * Math.PI * i) / states.length - Math.PI / 2;
      positions[s.name] = states.length > 1
        ? {x: 260 + radius * Math.cos(angle), y: 220 + radius * Math.sin(angle)}
        : {x: 260, y: 220};
    });
    return positions;
  }

  /** Path and label position for one edge. Edges are curved so opposite directions do not overlap. */
  function edgeGeometry(from, to) {
    if (from === to) return {path: `M${from.x - 12} ${from.y - 25}c-10-45 34-45 24 0`, label: {x: from.x, y: from.y - 58}};
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const length = Math.hypot(dx, dy);
    const ux = dx / length;
    const uy = dy / length;
    // Start/end just outside the node circles (radius 27) so arrowheads stay visible.
    const sx = from.x + ux * 28;
    const sy = from.y + uy * 28;
    const ex = to.x - ux * 31;
    const ey = to.y - uy * 31;
    const cx = (sx + ex) / 2 - uy * 34;
    const cy = (sy + ey) / 2 + ux * 34;
    return {path: `M${sx} ${sy}Q${cx} ${cy} ${ex} ${ey}`, label: {x: (sx + ex) / 2 - uy * 17, y: (sy + ey) / 2 + ux * 17}};
  }

  function describe(fsm, edges, key) {
    if (key[0] === 'e') {
      const t = edges[Number(key.slice(1))];
      return {rule: t.id, from: t.src, to: t.dst, guard: t.guard_text, unless: t.unless_text, action: t.action, line: t.line};
    }
    const state = fsm.states.find((s) => s.name === key.slice(1));
    return {...state, rules_from_here: fsm.transitions.filter((t) => t.src === state.name).map((t) => t.id)};
  }

  /** Draw `fsm`; states in `unreachable` are highlighted. Rules without GOTO stay in their state and are not edges. */
  function render(fsm, unreachable) {
    const positions = layout(fsm.states);
    const edges = fsm.transitions.filter((t) => t.dst);
    let svg = `<svg viewBox="0 0 520 440" role="img" aria-label="Finite state machine">${SVG_DEFS}`;
    edges.forEach((t, i) => {
      const {path, label} = edgeGeometry(positions[t.src], positions[t.dst]);
      svg += `<path class="edge" data-k="e${i}" d="${path}" marker-end="url(#ar)"/><text class="lbl" x="${label.x}" y="${label.y}">${esc(t.id)}: ${esc(t.action.name)}</text>`;
    });
    fsm.states.forEach((s) => {
      const p = positions[s.name];
      const classes = [s.initial ? 'init' : '', s.terminal ? 'term' : '', unreachable.includes(s.name) ? 'un' : ''].join(' ');
      svg += `<g class="node ${classes}" data-k="n${esc(s.name)}"><circle cx="${p.x}" cy="${p.y}" r="27"/><text x="${p.x}" y="${p.y + 4}">${esc(s.name)}</text></g>`;
    });
    $('fsm').innerHTML = svg + '</svg><p class="legend">Blue = initial · green = terminal · red dashed = unreachable · rules without GOTO stay in their state (not drawn). Click a state or edge.</p>';
    $('fsmInfo').textContent = '';
    // Replacing onclick (not adding a listener) keeps exactly one handler per render.
    $('fsm').onclick = (event) => {
      const target = event.target.closest('[data-k]');
      if (target) $('fsmInfo').textContent = JSON.stringify(describe(fsm, edges, target.dataset.k), null, 2);
    };
  }

  function clear() {
    $('fsm').textContent = 'Compile a contract to see its FSM.';
    $('fsmInfo').textContent = '';
  }

  CVC.fsm = {render, clear, showUnavailable: () => { $('fsm').textContent = 'No FSM: an earlier stage failed.'; $('fsmInfo').textContent = ''; }};
})(window.CVC);
