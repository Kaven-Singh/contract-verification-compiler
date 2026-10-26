/*
 * Shared helpers and the single global namespace (window.CVC) used by every other script.
 * These are plain scripts rather than ES modules because the browser test environment (jsdom) cannot load
 * <script type="module">; each file is an IIFE that attaches its public functions to CVC.
 */
'use strict';
window.CVC = window.CVC || {};

(function (CVC) {
  const $ = (id) => document.getElementById(id);

  const HTML_ESCAPES = {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'};
  /** Escape text for innerHTML. Contract source, diagnostics and every API string go through this. */
  const esc = (value) => String(value).replace(/[&<>"']/g, (c) => HTML_ESCAPES[c]);

  /** Application state shared by the views. Mutated only by app.js, repairs.js and execution.js. */
  const state = {
    last: null, // most recent /api/compile result
    lastRun: null, // most recent /api/execute result for `last`
    loaded: '', // source of the last loaded example (target of Reset)
    undoSource: null, // editor text before the last applied repair
    repairs: [], // suggestions for `last`
    compiles: 0,
    compileSeq: 0, // ticket counters: a response is applied only if it is still the newest request
    runSeq: 0,
  };

  CVC.util = {$, esc};
  CVC.state = state;
})(window.CVC);
