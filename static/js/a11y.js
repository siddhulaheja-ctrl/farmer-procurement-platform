/* Text size and contrast controls.

   Both settings are per browser, kept in localStorage, and applied to the root
   element before anything else runs so the page does not flash at the default
   size first. Everything is wrapped in try/catch - localStorage throws outright
   in some privacy modes, and losing a font size preference should not take the
   page down with it.

   Font sizes are a multiplier on --fs rather than a zoom, so the layout keeps
   its proportions and the tables still fit. */
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

    function applyContrast(on) {
        if (on) { root.setAttribute('data-contrast', 'high'); }
        else { root.removeAttribute('data-contrast'); }
        write('ks-contrast', on ? '1' : '0');
        var btn = document.getElementById('contrast-toggle');
        if (btn) { btn.setAttribute('aria-pressed', on ? 'true' : 'false'); }
    }

    var step = parseInt(read('ks-fontstep', '1'), 10);
    if (isNaN(step)) { step = 1; }
    applySize(step);
    applyContrast(read('ks-contrast', '0') === '1');

    document.addEventListener('DOMContentLoaded', function () {
        applySize(step);                     // re-run, the buttons exist now
        applyContrast(read('ks-contrast', '0') === '1');

        var buttons = document.querySelectorAll('[data-fontstep]');
        for (var n = 0; n < buttons.length; n++) {
            buttons[n].addEventListener('click', function (e) {
                e.preventDefault();
                step = applySize(parseInt(this.dataset.fontstep, 10));
            });
        }
        var toggle = document.getElementById('contrast-toggle');
        if (toggle) {
            toggle.addEventListener('click', function (e) {
                e.preventDefault();
                applyContrast(read('ks-contrast', '0') !== '1');
            });
        }
    });
})();
