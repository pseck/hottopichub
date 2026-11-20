// Show "3h ago"-style times for recent items, computed in the reader's browser.
(function () {
  var now = Date.now();
  document.querySelectorAll("time[datetime]").forEach(function (t) {
    var d = Date.parse(t.getAttribute("datetime"));
    if (isNaN(d)) return;
    var m = Math.round((now - d) / 60000);
    if (m < 0 || m > 60 * 48) return;
    t.textContent = m < 1 ? "just now" : m < 60 ? m + "m ago" : Math.round(m / 60) + "h ago";
    t.title = new Date(d).toLocaleString();
  });
})();
