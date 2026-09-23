/* countdown until the mock bank answers, then reload */
(function () {
    var boxes = document.querySelectorAll('[data-wait]');
    if (!boxes.length) { return; }
    var soonest = Infinity;
    for (var i = 0; i < boxes.length; i++) {
        soonest = Math.min(soonest, parseInt(boxes[i].getAttribute('data-wait'), 10) || 0);
    }
    var left = soonest;
    function tick() {
        for (var j = 0; j < boxes.length; j++) {
            var own = Math.max(0, (parseInt(boxes[j].getAttribute('data-wait'), 10) || 0) - (soonest - left));
            var out = boxes[j].querySelector('[data-wait-left]');
            if (out) { out.textContent = own; }
        }
        if (left <= 0) {
            setTimeout(function () { window.location.reload(); }, 1500);
            return;
        }
        left -= 1;
        setTimeout(tick, 1000);
    }
    tick();
})();
