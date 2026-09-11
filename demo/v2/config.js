(function () {
  var params = new URLSearchParams(window.location.search);
  var fromQuery = params.get("api") || "";
  if (fromQuery) {
    window.DEMO_API_BASE = fromQuery.replace(/\/$/, "");
    return;
  }
  // API lives at host root (/v2/lab/...).
  // Leave DEMO_API_BASE empty so requests use same-origin absolute paths.
  window.DEMO_API_BASE = "";
})();
