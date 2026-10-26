# Known limitations

* **Scope:** logical consistency only — no legal validity, no natural-language input.
* **Solver:** exact only for conjunctions/disjunctions of `variable OP number` and BOOL conditions. Date arithmetic,
  enum comparisons and conditions with more than 64 DNF alternatives are *undecided*: conflicts become `W311` warnings
  without a witness, and such guards are never treated as dead.
* **Reachability:** graph reachability ignores guards; logical reachability removes only provably dead transitions.
* **Cycles:** structural only. The tool says whether a satisfiable exit exists, never that termination is guaranteed
  or that execution is infinite.
* **VM semantics:** one ordered pass per event (see `BYTECODE.md`). Re-evaluating earlier rules after a transition is
  not supported; whether this matches a particular contract's intent is a modelling decision for the author.
* **Repairs:** cover type mismatches (E201), typos (E202/E204), unreachable rules (W302), conflicts (E301/W311) and
  no-exit cycles (E401) only. They are proposals: each states its assumption and a sampled behavioural comparison, which
  is evidence of change, not proof of equivalence.
* **Months:** `n MONTHS` is calendar arithmetic; durations in months cannot be compared or added on their own.
* **Frontend:** textarea with a highlighting layer, not an IDE editor (no autocomplete or inline quick-fixes); verified
  with jsdom, not a real browser engine.
* **Operations:** in-memory, single-process rate limiter and counters; no authentication, TLS or persistent monitoring.
  Behind a proxy the client address is the proxy's.
