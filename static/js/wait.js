/* A payment with the bank. Counts down the seconds until the (demo) bank
   answers, then reloads so the page shows the credit or the return.
   The answer is worked out on the server on the next page load. */
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
            // a moment's grace so the server's clock is past the answer too
            setTimeout(function () { window.location.reload(); }, 1500);
            return;
        }
        left -= 1;
        setTimeout(tick, 1000);
    }
    tick();
})();
