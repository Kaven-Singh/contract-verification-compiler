/* Backend communication. */
'use strict';

(function (CVC) {
  /**
   * Call the backend: POST when `body` is given, otherwise GET `/api/<path>`.
   * Resolves to {status, data} for ANY HTTP response (so callers can show the server's message); rejects only on
   * network failure. A body that is not JSON is reported as {error: ...}.
   */
  async function request(path, body) {
    const response = await fetch('/api/' + path, {
      method: body ? 'POST' : 'GET',
      headers: {'Content-Type': 'application/json'},
      body: body ? JSON.stringify(body) : undefined,
    });
    let data;
    try {
      data = await response.json();
    } catch (e) {
      data = {error: 'Non-JSON response (HTTP ' + response.status + ')'};
    }
    return {status: response.status, data};
  }

  CVC.api = {request};
})(window.CVC);
