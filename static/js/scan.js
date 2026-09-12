/* Camera scanning for the gate pass, on browsers that can already do it.

   Uses BarcodeDetector, which Chrome and Edge build into the browser, so
   there is no library to ship - the whole scanner is this file. Where it is
   missing (Firefox, Safari, older Chrome) or where the page is not on https,
   none of this runs and the typed token box is the way in. Phones only hand
   over a camera on a secure page, so over plain http on a laptop this will
   sit out even in Chrome.

   The typed box is always there and is never hidden behind this, because it
   is the one that works at a gate with a cracked lens and no signal. */
(function () {
    var panel = document.getElementById('scan-panel');
    if (!panel) { return; }

    var why = document.getElementById('scan-why');
    var start = document.getElementById('scan-start');
    var stop = document.getElementById('scan-stop');
    var video = document.getElementById('scan-video');
    var shot = document.getElementById('scan-status');
    var stream = null;
    var timer = null;

    function say(msg) { if (shot) { shot.textContent = msg; } }

    function unavailable(reason) {
        panel.hidden = true;
        if (why) {
            why.hidden = false;
            why.textContent = reason + ' Type the token number below instead - it is printed '
                + 'on the pass under the code.';
        }
    }

    if (!('BarcodeDetector' in window)) {
        unavailable('This browser cannot read a code from the camera.');
        return;
    }
    if (!window.isSecureContext) {
        unavailable('The camera needs a secure (https) address, and this page is not on one.');
        return;
    }

    /* A qr code is just text, and the text is whatever was printed on the
       paper. So never navigate to it. Pull out what looks like a token and
       build our own address from it - then the worst a forged pass can do is
       send us to our own "no booking found". */
    function tokenFrom(raw) {
        var s = String(raw || '').trim();
        var at = s.lastIndexOf('/t/');
        if (at !== -1) { s = s.slice(at + 3); }
        s = s.split('?')[0].split('#')[0].toUpperCase().replace(/[^A-Z0-9-]/g, '');
        return /^[A-Z0-9][A-Z0-9-]{3,31}$/.test(s) ? s : '';
    }

    function halt() {
        if (timer) { clearInterval(timer); timer = null; }
        if (stream) {
            stream.getTracks().forEach(function (t) { t.stop(); });
            stream = null;
        }
        panel.classList.remove('live');
        if (start) { start.hidden = false; }
        if (stop) { stop.hidden = true; }
    }

    function begin() {
        var detector;
        try {
            detector = new BarcodeDetector({ formats: ['qr_code'] });
        } catch (e) {
            unavailable('This browser cannot read QR codes from the camera.');
            return;
        }
        say('Starting the camera...');
        // the back camera on a phone, which is the one pointing at the pass
        navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
            .then(function (s) {
                stream = s;
                video.srcObject = s;
                video.play();
                panel.classList.add('live');
                if (start) { start.hidden = true; }
                if (stop) { stop.hidden = false; }
                say('Hold the gate pass in front of the camera.');
                // four looks a second. any faster just warms the phone up
                timer = setInterval(function () {
                    if (!video.videoWidth) { return; }
                    detector.detect(video).then(function (codes) {
                        for (var i = 0; i < codes.length; i++) {
                            var token = tokenFrom(codes[i].rawValue);
                            if (token) {
                                halt();
                                say('Opening ' + token + '...');
                                window.location.href = '/t/' + encodeURIComponent(token);
                                return;
                            }
                        }
                    }).catch(function () { /* a blurred frame, try the next */ });
                }, 250);
            })
            .catch(function (err) {
                var name = err && err.name;
                if (name === 'NotAllowedError') {
                    say('Camera permission was refused. Type the token below instead.');
                } else if (name === 'NotFoundError') {
                    say('No camera on this device. Type the token below instead.');
                } else {
                    say('The camera could not be started. Type the token below instead.');
                }
            });
    }

    if (start) { start.addEventListener('click', begin); }
    if (stop) { stop.addEventListener('click', function () { halt(); say('Camera stopped.'); }); }
    // don't leave the camera light on when someone walks away from the page
    window.addEventListener('pagehide', halt);
})();
