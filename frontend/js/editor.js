/* Source editor: text access, syntax highlighting layer, diagnostics list and download. */
'use strict';

(function (CVC) {
  const {$, esc} = CVC.util;
  const state = CVC.state;

  // One alternation in priority order; the index of the matching capture group selects the CSS class.
  const TOKEN_RE = /(#.*)|\b(VAR|STATE|INITIAL|RULE|FROM|IF|THEN|UNLESS|GOTO|AND|OR|NOT|TRUE|FALSE)\b|\b(DATE|NUMBER|MONEY|BOOL|ENUM)\b|\b(PENALTY|WAIVE_PENALTY|TERMINATE)\b|\b(\d+(?:\.\d+)?)\b|\b(DAYS|MONTHS)\b/g;
  const CLASS_BY_GROUP = [null, 'c', 'k', 't', 'a', 'n', 'k'];

  function highlightLine(line) {
    let html = '';
    let last = 0;
    for (const match of line.matchAll(TOKEN_RE)) {
      const group = match.findIndex((part, i) => i > 0 && part !== undefined);
      html += esc(line.slice(last, match.index)) + `<i class="${CLASS_BY_GROUP[group]}">${esc(match[0])}</i>`;
      last = match.index + match[0].length;
    }
    return html + esc(line.slice(last));
  }

  /** Redraw the highlight layer; lines with diagnostics from the last compile get a wavy underline. */
  function highlight() {
    const diagnostics = state.last ? state.last.diagnostics : [];
    const lineClass = (n) => {
      const here = diagnostics.filter((d) => d.line === n);
      return here.some((d) => d.severity === 'error') ? 'ln err' : here.length ? 'ln warn' : 'ln';
    };
    const lines = $('src').value.split('\n');
    // The trailing newline keeps the last (possibly empty) line the same height as in the textarea.
    $('hl').innerHTML = lines.map((l, i) => `<span class="${lineClass(i + 1)}">${highlightLine(l)}</span>`).join('\n') + '\n';
    syncScroll();
  }

  function syncScroll() {
    $('hl').scrollTop = $('src').scrollTop;
    $('hl').scrollLeft = $('src').scrollLeft;
  }

  function renderDiagnostics() {
    const diagnostics = state.last.diagnostics;
    $('diags').innerHTML = diagnostics.length
      ? diagnostics.map((d, i) => `<li class="${d.severity}" data-i="${i}"><b>${d.code}</b> ${d.severity} @ ${d.line}:${d.col} — ${esc(d.message)}</li>`).join('')
      : '<li class="ok">No diagnostics.</li>';
  }

  /** Replace the diagnostics list by a single message (errors, progress, "Cleared."). */
  function showMessage(text, kind) {
    $('diags').innerHTML = `<li${kind ? ` class="${kind}"` : ''}>${esc(text)}</li>`;
  }

  /** Select the reported position in the textarea. */
  function jumpTo(diagnostic) {
    const lines = $('src').value.split('\n');
    let offset = 0;
    for (let i = 0; i < diagnostic.line - 1; i++) offset += lines[i].length + 1;
    $('src').focus();
    $('src').setSelectionRange(offset + diagnostic.col - 1, offset + diagnostic.col);
  }

  function download() {
    const link = document.createElement('a');
    link.href = URL.createObjectURL(new Blob([$('src').value], {type: 'text/plain'}));
    link.download = 'contract.cvc';
    link.click();
    URL.revokeObjectURL(link.href);
  }

  function init() {
    $('src').addEventListener('input', highlight);
    $('src').addEventListener('scroll', syncScroll);
    $('diags').addEventListener('click', (event) => {
      const item = event.target.closest('li[data-i]');
      if (item && state.last) jumpTo(state.last.diagnostics[Number(item.dataset.i)]);
    });
  }

  CVC.editor = {
    init,
    highlight,
    renderDiagnostics,
    showMessage,
    download,
    getSource: () => $('src').value,
    setSource(text) {
      $('src').value = text;
      highlight();
    },
  };
})(window.CVC);
