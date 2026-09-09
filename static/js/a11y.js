/* Text size control.

   Every font size in the stylesheet is a rem, so setting --fs on the root
   scales the whole page from one value. Text size, not zoom, so padding and
   column widths stay put and the wide admin tables still fit.

   Kept in localStorage per browser and applied before first paint, otherwise
   the page renders at the default size and jumps. Everything is wrapped
   because localStorage throws outright in some privacy modes. */
(function () {
    var STEPS = [12.5, 14, 15.5, 17];   // 14 is the default, index 1
    var root = document.documentElement;

    function read(key, fallback) {
        try { var v = localStorage.getItem(key); return v === null ? fallback : v; }
        catch (e) { return fallback; }
    }
    function write(key, value) {
        try { localStorage.setItem(key, value); } catch (e) { /* private mode */ }
    }

    function applySize(i) {
        i = Math.max(0, Math.min(STEPS.length - 1, i));
        root.style.setProperty('--fs', STEPS[i] + 'px');
        write('ks-fontstep', i);
        var buttons = document.querySelectorAll('[data-fontstep]');
        for (var n = 0; n < buttons.length; n++) {
            buttons[n].setAttribute('aria-pressed', buttons[n].dataset.fontstep == i);
        }
        return i;
    }

    var step = parseInt(read('ks-fontstep', '1'), 10);
    if (isNaN(step)) { step = 1; }
    applySize(step);

    // contrast mode was dropped, clear the key it left behind
    try { localStorage.removeItem('ks-contrast'); } catch (e) { /* private mode */ }
    root.removeAttribute('data-contrast');

    document.addEventListener('DOMContentLoaded', function () {
        applySize(step);                     // re-run, the buttons exist now
        var buttons = document.querySelectorAll('[data-fontstep]');
        for (var n = 0; n < buttons.length; n++) {
            buttons[n].addEventListener('click', function (e) {
                e.preventDefault();
                step = applySize(parseInt(this.dataset.fontstep, 10));
            });
        }
    });
})();
