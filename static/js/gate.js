/* The gate scanner.

   "Scan pass" opens the phone's back camera inside the page and looks for a
   QR code a few times a second. The browser's own BarcodeDetector is used
   where it exists (Chrome on Android); anywhere else the jsQR library in
   static/vendor is loaded the first time it is needed.

   A found code goes to the server, which checks the signature and the
   booking and sends back the result card. The camera needs an https address
   (or localhost) - on plain http the "take a photo" button still works,
   because a photo from the camera app needs no permission. */
(function () {
    var root = document.getElementById('gate');
    if (!root || !window.fetch) { return; }

    var resultBox = document.getElementById('gate-result');
    var startBtn = document.getElementById('scan-start');
    var view = root.querySelector('.scan-view');
    var video = view.querySelector('video');
    var stopBtn = view.querySelector('.scan-stop');
    var photo = document.getElementById('scan-photo');
    var typeForm = document.getElementById('scan-type');
    var msg = document.getElementById('scan-msg');
    var canvas = document.createElement('canvas');
    var ctx = canvas.getContext('2d', { willReadFrequently: true });

    var stream = null;
    var detector = null;
    var ready = null;       // promise: a decoder is available

    // the page hands over its messages in the reader's language (data-words on #gate)
    var WORDS = {};
    try { WORDS = JSON.parse(root.getAttribute('data-words') || '{}'); } catch (e) { WORDS = {}; }
    function w(text) { return WORDS[text] || text; }
    function say(text) { msg.textContent = text || ''; }

    function loadJsQR() {
        if (window.jsQR) { return Promise.resolve(); }
        return new Promise(function (ok, fail) {
            var s = document.createElement('script');
            s.src = root.getAttribute('data-jsqr');
            s.onload = ok;
            s.onerror = fail;
            document.head.appendChild(s);
        });
    }

    function decoder() {
        if (ready) { return ready; }
        if ('BarcodeDetector' in window && window.BarcodeDetector.getSupportedFormats) {
            ready = window.BarcodeDetector.getSupportedFormats().then(function (formats) {
                if (formats.indexOf('qr_code') !== -1) {
                    detector = new window.BarcodeDetector({ formats: ['qr_code'] });
                    return null;
                }
                return loadJsQR();
            }).catch(loadJsQR);
        } else {
            ready = loadJsQR();
        }
        return ready;
    }

    // one picture -> the text in its QR code, or null
    function decode(source, width, height) {
        if (detector) {
            return detector.detect(source).then(function (codes) {
                return codes.length ? codes[0].rawValue : null;
            });
        }
        canvas.width = width;
        canvas.height = height;
        ctx.drawImage(source, 0, 0, width, height);
        var pixels = ctx.getImageData(0, 0, width, height);
        var found = window.jsQR(pixels.data, width, height, { inversionAttempts: 'attemptBoth' });
        return Promise.resolve(found ? found.data : null);
    }

    function fit(w, h, most) {
        var scale = Math.min(1, most / Math.max(w, h));
        return [Math.round(w * scale), Math.round(h * scale)];
    }

    function beep(good) {
        try {
            var AC = window.AudioContext || window.webkitAudioContext;
            var ac = new AC();
            var osc = ac.createOscillator();
            var gain = ac.createGain();
            osc.frequency.value = good ? 880 : 300;
            gain.gain.value = 0.15;
            osc.connect(gain);
            gain.connect(ac.destination);
            osc.start();
            osc.stop(ac.currentTime + (good ? 0.12 : 0.35));
        } catch (e) { /* no sound is fine */ }
        if (navigator.vibrate) { navigator.vibrate(good ? 60 : [90, 60, 90]); }
    }

    function stop() {
        if (stream) {
            stream.getTracks().forEach(function (tr) { tr.stop(); });
        }
        stream = null;
        video.srcObject = null;
        view.hidden = true;
        startBtn.hidden = false;
    }

    function start() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            say(window.isSecureContext
                ? w('This browser cannot open the camera. Take a photo of the pass instead.')
                : w('The camera only opens on an https:// address. Use the share link, or take a photo of the pass instead.'));
            return;
        }
        say(w('Opening the camera...'));
        decoder().then(function () {
            return navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false });
        }).then(function (s) {
            stream = s;
            video.srcObject = s;
            view.hidden = false;
            startBtn.hidden = true;
            return video.play();
        }).then(function () {
            say(w('Point the camera at the QR code on the pass.'));
            view.scrollIntoView({ block: 'center', behavior: 'smooth' });
            look();
        }).catch(function (err) {
            stop();
            if (err && err.name === 'NotAllowedError') {
                say(w('Camera permission was refused. Allow the camera for this site, or take a photo instead.'));
            } else if (!window.isSecureContext) {
                say(w('The camera only opens on an https:// address. Take a photo of the pass instead.'));
            } else {
                say(w('Could not open the camera. Take a photo of the pass instead.'));
            }
        });
    }

    function look() {
        if (!stream) { return; }
        if (video.readyState < 2 || !video.videoWidth) {
            setTimeout(look, 200);
            return;
        }
        var size = fit(video.videoWidth, video.videoHeight, 720);
        decode(video, size[0], size[1]).then(function (text) {
            if (!stream) { return; }
            if (text) {
                stop();
                check(text);
            } else {
                setTimeout(look, 180);
            }
        }).catch(function () { setTimeout(look, 400); });
    }

    function show(data) {
        resultBox.innerHTML = data.html;
        beep(data.tone === 'ok' || data.tone === 'info');
        say('');
        resultBox.scrollIntoView({ block: 'start', behavior: 'smooth' });
    }

    function post(url, body) {
        return fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        }).then(function (r) {
            return r.json().catch(function () { return {}; }).then(function (json) {
                if (!r.ok) { throw new Error(json.error || 'The server said no (' + r.status + ').'); }
                return json;
            });
        });
    }

    function check(code) {
        say(w('Checking...'));
        post(root.getAttribute('data-check'), { code: code }).then(show).catch(function (e) {
            say(e.message || w('Could not reach the server. Try again.'));
        });
    }

    startBtn.addEventListener('click', start);
    stopBtn.addEventListener('click', function () { stop(); say(''); });

    typeForm.addEventListener('submit', function (e) {
        var code = typeForm.querySelector('input').value.trim();
        if (!code) { return; }
        e.preventDefault();
        check(code);
    });

    photo.addEventListener('change', function () {
        var file = photo.files && photo.files[0];
        if (!file) { return; }
        say(w('Reading the photo...'));
        var img = new Image();
        var url = URL.createObjectURL(file);
        img.onload = function () {
            decoder().then(function () {
                var size = fit(img.naturalWidth, img.naturalHeight, 1400);
                return decode(detector ? img : img, size[0], size[1]);
            }).then(function (text) {
                URL.revokeObjectURL(url);
                photo.value = '';
                if (text) { check(text); } else { say(w('No QR code found in that photo. Hold the phone closer and try again.')); }
            }).catch(function () { say(w('Could not read that photo.')); });
        };
        img.onerror = function () { say(w('Could not open that photo.')); };
        img.src = url;
    });

    // the buttons on a result card
    resultBox.addEventListener('click', function (e) {
        var next = e.target.closest('[data-next]');
        if (next) { start(); return; }
        var btn = e.target.closest('[data-action]');
        if (!btn) { return; }
        var card = btn.closest('.gate-card');
        var noteBox = card.querySelector('[name="note"]');
        var error = card.querySelector('.gc-error');
        btn.disabled = true;
        post(root.getAttribute('data-act'), {
            code: card.getAttribute('data-code'),
            action: btn.getAttribute('data-action'),
            note: noteBox ? noteBox.value : ''
        }).then(show).catch(function (err) {
            btn.disabled = false;
            error.textContent = err.message;
            error.hidden = false;
        });
    });
})();
