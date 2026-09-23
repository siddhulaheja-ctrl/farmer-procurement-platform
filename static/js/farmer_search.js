/* live search on the farmers list, fetches ?partial=1 from the server */
(function () {
    var WAIT = 180;   // ms after the last key before asking

    document.addEventListener('DOMContentLoaded', function () {
        var form = document.getElementById('farmer-search');
        var results = document.getElementById('farmer-results');
        if (!form || !results || !window.fetch) { return; }
        var box = form.querySelector('input[name="q"]');
        var clear = form.querySelector('.search-clear');
        var timer = null;
        var latest = 0;

        function search() {
            clearTimeout(timer);
            var q = box.value.trim();
            var mine = ++latest;
            clear.hidden = !box.value;
            fetch(window.location.pathname + '?partial=1&q=' + encodeURIComponent(q), { credentials: 'same-origin' })
                .then(function (r) {
                    if (!r.ok) { throw new Error('search ' + r.status); }
                    return r.text();
                })
                .then(function (html) {
                    if (mine !== latest) { return; }   // an older answer arriving late
                    results.innerHTML = html;
                    var url = window.location.pathname + (q ? '?q=' + encodeURIComponent(q) : '');
                    window.history.replaceState(null, '', url);
                })
                .catch(function () {});
        }

        box.addEventListener('input', function () {
            clear.hidden = !box.value;
            clearTimeout(timer);
            timer = setTimeout(search, WAIT);
        });
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            search();
        });
        clear.addEventListener('click', function (e) {
            e.preventDefault();
            box.value = '';
            search();
            box.focus();
        });
    });
})();
