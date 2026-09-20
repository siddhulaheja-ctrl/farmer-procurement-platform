/* Text size control.

   Every font size in the stylesheet is a rem, so setting --fs on the root
   scales the whole page from one value. Text size, not zoom, so padding and
   column widths stay put and the wide admin tables still fit.

   Kept in localStorage per browser and applied before first paint, otherwise
   the page renders at the default size and jumps. Everything is wrapped
   because localStorage throws outright in some privacy modes. */
(function () {
    var STEPS = [14, 16, 18, 20];       // 16 is the default, index 1
    var root = document.documentElement;
    // lets the stylesheet fold the phone menu only when this script can open it
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

    // contrast mode was dropped, clear the key it left behind
    try { localStorage.removeItem('ks-contrast'); } catch (e) { /* private mode */ }
    root.removeAttribute('data-contrast');

    document.addEventListener('DOMContentLoaded', function () {
        // the language menu opens on its own (details/summary); close it on a
        // tap anywhere else or on Escape, the way people expect a menu to behave
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

        // the phone menu: the hamburger opens and closes the top navigation
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
            // picking a link closes the menu instead of leaving it open behind the new page
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
