(function () {
  var params = new URLSearchParams(window.location.search);
  var fromQuery = params.get("api") || "";
  if (fromQuery) {
    window.DEMO_API_BASE = fromQuery.replace(/\/$/, "");
    return;
  }
  // When UI is under /ai or /demo/ai, API still lives at host root (/v1/...).
  // Leave DEMO_API_BASE empty so requests use same origin absolute paths like /v1/lab/config.
  window.DEMO_API_BASE = "";
})();
