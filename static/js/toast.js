/* Toasts: short confirmations that pop up in a corner, like a slot just booked.

   Each closes itself after a few seconds, or on its cross. One that is being
   pointed at or tabbed into stays put, so there is time to note a token
   number. Without script a toast simply stays on the page. */
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
    });
})();
