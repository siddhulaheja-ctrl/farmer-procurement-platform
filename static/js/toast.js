/* toasts, and the "slot booked" dialog */
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
