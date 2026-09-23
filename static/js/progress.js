/* scroll progress bar under the header */
(function () {
    var bar = document.querySelector('.progress i');
    if (!bar) { return; }
    var ticking = false;
    function draw() {
        ticking = false;
        var max = document.documentElement.scrollHeight - window.innerHeight;
        bar.style.transform = 'scaleX(' + (max > 0 ? Math.min(1, window.pageYOffset / max) : 0).toFixed(4) + ')';
    }
    window.addEventListener('scroll', function () {
        if (!ticking) { ticking = true; requestAnimationFrame(draw); }
    }, { passive: true });
    window.addEventListener('resize', draw);
    draw();
})();
