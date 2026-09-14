/* Toasts, and the big "slot booked" confirmation.

   Toasts are short notes that pop up in a corner. Each closes itself after a
   few seconds, or on its cross. One that is being pointed at or tabbed into
   stays put. Without script a toast simply stays on the page.

   The booking confirmation is a <dialog> in the middle of the screen with its
   animation in the stylesheet. Here it only becomes modal (focus stays inside,
   Escape closes it) and fades out on Done. It never closes by itself - the
   token number is on it. */
(function () {
    var SHOW_FOR = 7000;

    document.addEventListener('DOMContentLoaded', function () {
        var toasts = document.querySelectorAll('.toast');
        for (var i = 0; i < toasts.length; i++) {
            (function (toast) {
                function close() { toast.hidden = true; }
                var timer = setTimeout(close, SHOW_FOR);
                function keep() { clearTimeout(timer); }

                var button = toast.querySelector('.toast-close');
                if (button) {
                    button.hidden = false;
                    button.addEventListener('click', close);
                }
                toast.addEventListener('mouseenter', keep);
                toast.addEventListener('focusin', keep);
            })(toasts[i]);
        }

        var cel = document.querySelector('dialog.celebrate');
        if (!cel) { return; }
        if (typeof cel.showModal === 'function') {
            try { cel.close(); cel.showModal(); } catch (e) { cel.setAttribute('open', ''); }
        }
        var done = cel.querySelector('.cel-done');
        if (done) { done.focus({ preventScroll: true }); }
        var form = cel.querySelector('form');
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            cel.classList.add('closing');
            setTimeout(function () {
                if (typeof cel.close === 'function') { cel.close(); } else { cel.removeAttribute('open'); }
            }, 220);
        });
    });
})();
