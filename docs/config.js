(function () {
  var params = new URLSearchParams(window.location.search);
  var fromQuery = params.get("api") || "";
  if (fromQuery) {
    window.DEMO_API_BASE = fromQuery.replace(/\/$/, "");
  }
})();
