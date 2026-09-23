/* home page animations and the photo slideshow. kept ES5 for old phones */
(function () {
    var body = document.body;
    function all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
    var items = all('[data-reveal]');
    if (body.classList.contains('still')) {
        items.forEach(function (el) { el.classList.add('in'); });
        return;
    }
    // reduced motion: short fades only, nothing looping
    var gentle = !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
    var hasIO = 'IntersectionObserver' in window;
    body.classList.add('motion');
    if (gentle) { body.classList.add('gentle'); }
    all('.rise-words .w').forEach(function (w, i) { w.style.setProperty('--n', i); });
    var mode = document.getElementById('motion-mode');
    if (mode) { mode.textContent = 'motion: ' + (gentle ? 'gentle' : 'full') + (hasIO ? '' : ', no IO'); }

    function countUp(el) {
        var to = +el.getAttribute('data-count'), t0 = null, dur = 1400;
        function step(t) {
            if (t0 === null) { t0 = t; }
            var k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
            el.textContent = Math.round(to * e).toLocaleString('en-IN');
            if (k < 1) { requestAnimationFrame(step); }
        }
        requestAnimationFrame(step);
    }

    var io = null, started = false;
    function reveal(el) {
        if (el.classList.contains('in')) { return; }
        el.classList.add('in');
        all('[data-count]', el).forEach(countUp);
        if (io) { io.unobserve(el); }
    }
    function sweep() {
        if (!started) { return; }
        var h = window.innerHeight, w = window.innerWidth;
        items.forEach(function (el) {
            var r = el.getBoundingClientRect();
            if (r.top < h * .94 && r.bottom > 0 && r.left < w && r.right > 0) { reveal(el); }
        });
    }
    // on slow phones the animations finished before anything painted. wait for load (max 1.2s)
    function start() {
        if (started) { return; }
        started = true;
        requestAnimationFrame(function () {
            requestAnimationFrame(function () {
                if (hasIO) {
                    io = new IntersectionObserver(function (entries) {
                        entries.forEach(function (en) { if (en.isIntersecting) { reveal(en.target); } });
                    }, { threshold: 0.18, rootMargin: '0px 0px -6% 0px' });
                    items.forEach(function (el) { io.observe(el); });
                }
                sweep();
            });
        });
    }
    if (document.readyState === 'complete') { start(); }
    else { window.addEventListener('load', start); setTimeout(start, 1200); }
    window.addEventListener('scroll', sweep, { passive: true });
    window.addEventListener('resize', sweep);
    all('.plates').forEach(function (p) { p.addEventListener('scroll', sweep, { passive: true }); });
    // fallback so nothing stays hidden
    setTimeout(function () { started = true; sweep(); }, 3000);

})();

