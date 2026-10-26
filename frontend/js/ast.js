/* AST viewer: the tree as indented JSON, exactly as the parser produced it. */
'use strict';

(function (CVC) {
  const {$} = CVC.util;

  function render(ast) {
    $('ast').textContent = ast ? JSON.stringify(ast, null, 1) : 'No AST: an earlier stage failed.';
  }

  CVC.ast = {render, clear: () => { $('ast').textContent = 'Compile a contract to see its AST.'; }};
})(window.CVC);
