/* text size (--fs on :root, all font sizes are rem), saved in localStorage.
   also the language menu and the phone nav. */
(function () {
    var STEPS = [14, 16, 18, 20];       // 16 is the default, index 1
    var root = document.documentElement;
    root.classList.add('js');

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

    try { localStorage.removeItem('ks-contrast'); } catch (e) { /* private mode */ }
    root.removeAttribute('data-contrast');

    document.addEventListener('DOMContentLoaded', function () {
        // close the language <details> on outside click / Escape
        var menus = document.querySelectorAll('details.langmenu');
        function closeMenus(except) {
            for (var m = 0; m < menus.length; m++) {
                if (menus[m] !== except) { menus[m].open = false; }
            }
        }
        document.addEventListener('click', function (e) {
            for (var m = 0; m < menus.length; m++) {
                if (menus[m].open && !menus[m].contains(e.target)) { menus[m].open = false; }
            }
        });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') { closeMenus(null); }
        });

        var toggle = document.querySelector('.navtoggle');
        var nav = document.getElementById('mainnav');
        if (toggle && nav) {
            var use = toggle.querySelector('use');
            var sprite = use ? use.getAttribute('href').split('#')[0] : '';
            var setOpen = function (open) {
                nav.classList.toggle('open', open);
                toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
                toggle.querySelector('.sr').textContent = toggle.getAttribute(open ? 'data-close' : 'data-open');
                if (use) { use.setAttribute('href', sprite + (open ? '#x' : '#menu')); }
            };
            toggle.addEventListener('click', function (e) {
                e.stopPropagation();
                setOpen(!nav.classList.contains('open'));
            });
            document.addEventListener('click', function (e) {
                if (nav.classList.contains('open') && !nav.contains(e.target)) { setOpen(false); }
            });
            document.addEventListener('keydown', function (e) {
                if (e.key === 'Escape' && nav.classList.contains('open')) { setOpen(false); toggle.focus(); }
            });
            nav.addEventListener('click', function (e) {
                if (e.target.closest('a')) { setOpen(false); }
            });
        }

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
