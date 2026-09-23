/* voice booking / voice registration conversation.

   speak -> /farmer/voice/step -> read the reply out -> listen for yes / no / a correction.
   uses the browser's SpeechRecognition where it works, otherwise records and posts
   the audio to /transcribe (speech_to_text.py). ?stt=server forces recording.
   console shows [voice] logs for each step. */
(function () {
    var Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    var canRecord = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
    var forceServer = /[?&]stt=server(&|$)/.test(window.location.search);
    var useBrowser = !!Recognition && !forceServer;
    var canListen = useBrowser || canRecord;
    var canFetch = !!(window.fetch && window.JSON && window.FormData);

    var TIMING = {
        request: { quietAfter: 4000, quietBefore: 8000 },   // a whole sentence, with pauses
        answer: { quietAfter: 1200, quietBefore: 7000 }     // "haan" is over quickly
    };
    var LONGEST = 30000;
    var GUESSES = 5;
    var MAX_RETRIES = 2;
    var AFTER_SPEAKING = 250;   // let our own voice die away before the mic opens

    // shorter silence timeout after yes / no. no waits a bit longer, "nahi, tees quintal" is a correction
    var ONLY_YES = /^(?:\s*(?:haan?|haa|hanji|haanji|ji|yes|yeah|ok|okay|theek hai|thik hai|sahi hai|kar do|kardo|book kar do|bilkul|हां|हाँ|हा|जी|ठीक है|सही है|कर दो|बुक कर दो|बिल्कुल|হ্যাঁ|হ্যা|ঠিক আছে|আচ্ছা)[\s,.!।]*)+$/i;
    var ONLY_NO = /^(?:\s*(?:nahi|nahin|nai|na|no|mat karo|नहीं|नही|ना|मत|না|নাহ)[\s,.!।]*)+$/i;
    var YES_SETTLES = 600;
    var NO_SETTLES = 1000;
    var VOICE_LANGS = { hi: 'hi-IN', bn: 'bn-IN', en: 'en-IN' };

    function trace(message) {
        if (window.console && console.info) { console.info('[voice] ' + message); }
    }
    function read(key) {
        try { return localStorage.getItem(key); } catch (e) { return null; }
    }
    function write(key, value) {
        try { localStorage.setItem(key, value); } catch (e) { /* private mode */ }
    }

    document.addEventListener('DOMContentLoaded', function () {
        var form = document.getElementById('voice-form');
        var box = document.getElementById('said');
        var mic = document.getElementById('mic');
        var status = document.getElementById('mic-status');
        var controls = document.getElementById('mic-controls');
        var language = document.getElementById('mic-lang');
        var result = document.getElementById('voice-result');
        var note = document.getElementById('voice-note');
        if (!form || !box || !mic || !status || !controls || !language || !result || !canFetch) { return; }

        var pageLang = document.documentElement.lang;
        var synth = window.speechSynthesis || null;

        var turns = [];          // what the farmer has said: the request, then each reply
        var guesses = [];        // the browser's other guesses at the request
        var slotId = null;       // the slot that was read out, so "yes" books that one
        var lastStep = null;
        var retries = 0;
        var generation = 0;      // bumped whenever the conversation moves on, so old callbacks give up
        var stopListening = null;    // while the mic is live: stop and use what was heard
        var abandonListening = null; // while the mic is live: stop and throw it away

        function show(key) { status.textContent = status.dataset[key] || ''; }

        if (canListen) {
            controls.hidden = false;
        } else {
            show('unsupported');
        }
        language.value = read('ks-mic-lang') || (pageLang === 'bn' ? 'bn-IN' : 'hi-IN');
        language.addEventListener('change', function () { write('ks-mic-lang', language.value); });
        trace('listening with ' + (useBrowser ? 'browser recognition' : canRecord ? 'recording + server' : 'nothing'));

        // whisper takes a few seconds to load
        function warm() {
            if (form.dataset.warm) {
                fetch(form.dataset.warm, { method: 'POST', credentials: 'same-origin' }).catch(function () {});
            }
        }
        if (canListen && !useBrowser) { warm(); }

        // ---- speaking --------------------------------------------------------

        function voiceFor(tag) {
            if (!synth) { return null; }
            var voices = synth.getVoices();
            var i;
            for (i = 0; i < voices.length; i++) {
                if (voices[i].lang.replace('_', '-') === tag) { return voices[i]; }
            }
            for (i = 0; i < voices.length; i++) {
                if (voices[i].lang.slice(0, 2) === tag.slice(0, 2)) { return voices[i]; }
            }
            return null;
        }
        if (synth) { synth.getVoices(); }   // chrome loads its list on first ask

        // chrome bug: onend doesn't fire if the utterance gets garbage collected
        var talking = null;

        function speak(text, then) {
            var voice = voiceFor(VOICE_LANGS[pageLang] || 'en-IN');
            if (!text || !voice) {
                // no english voice reading hindi
                if (text && note) { note.hidden = false; }
                trace('no ' + pageLang + ' voice on this device, not speaking');
                then(false);
                return;
            }
            if (synth.speaking || synth.pending) { synth.cancel(); }

            var utterance = new SpeechSynthesisUtterance(text);
            utterance.voice = voice;
            utterance.lang = voice.lang;
            utterance.rate = 0.9;
            talking = utterance;

            var startedAt = Date.now();
            var finished = false;
            var watch = null;
            var guard = null;
            function end(why) {
                if (finished) { return; }
                finished = true;
                clearInterval(watch);
                clearTimeout(guard);
                if (talking === utterance) { talking = null; }
                trace('finished speaking (' + why + ')');
                setTimeout(function () { then(true); }, AFTER_SPEAKING);
            }
            utterance.onend = function () { end('onend'); };
            utterance.onerror = function (e) { end('error ' + (e && e.error)); };
            trace('speaking with ' + voice.name + ': ' + text);
            synth.speak(utterance);

            // onend isn't reliable, poll speaking too
            watch = setInterval(function () {
                if (Date.now() - startedAt > 1000 && !synth.speaking && !synth.pending) { end('went quiet'); }
            }, 250);
            guard = setTimeout(function () { end('time limit'); }, 4000 + text.length * 120);
        }

        var audioCtx = null;
        function audio() {
            var Context = window.AudioContext || window.webkitAudioContext;
            if (!audioCtx && Context) {
                try { audioCtx = new Context(); } catch (e) { audioCtx = null; }
            }
            return audioCtx;
        }

        // iOS only allows audio started from a tap, so unlock speech + the audio context on the first one
        var unlocked = false;
        function unlockAudio() {
            if (unlocked) { return; }
            unlocked = true;
            if (synth) {
                try { synth.speak(new SpeechSynthesisUtterance('')); } catch (e) { /* nothing to start */ }
            }
            var ctx = audio();
            if (ctx && ctx.resume) { ctx.resume(); }
            trace('audio started by a tap');
        }
        ['touchend', 'click', 'keydown'].forEach(function (name) {
            document.addEventListener(name, unlockAudio, true);
        });

        // beep when the mic opens
        function beep() {
            var ctx = audio();
            if (!ctx) { return; }
            try {
                if (ctx.resume) { ctx.resume(); }
                var tone = ctx.createOscillator();
                var volume = ctx.createGain();
                tone.frequency.value = 880;
                volume.gain.value = 0.08;
                tone.connect(volume);
                volume.connect(ctx.destination);
                tone.start();
                tone.stop(ctx.currentTime + 0.15);
            } catch (e) { /* no tone, still listening */ }
        }

        // ---- listening -------------------------------------------------------

        function setListening(on) {
            mic.classList.toggle('on', on);
            mic.setAttribute('aria-pressed', on ? 'true' : 'false');
            mic.querySelector('span').textContent = on ? mic.dataset.stop : mic.dataset.start;
        }

        // done(text, otherGuesses, failed), text null if nothing heard
        function listen(kind, done) {
            beep();
            trace('listening for ' + (kind === 'answer' ? 'an answer' : 'a request'));
            // wait for the beep to finish
            setTimeout(function () {
                if (useBrowser) { listenInBrowser(kind, done); } else { listenByRecording(kind, done); }
            }, 250);
        }

        function listenInBrowser(kind, done) {
            var timing = TIMING[kind];
            var rec = new Recognition();
            var phrases = [];
            var unfinished = '';
            var wanted = true;
            var active = false;
            var failed = false;
            var abandoned = false;
            var ended = false;
            var switchToRecording = false;
            var quietTimer = null;
            var longestTimer = null;
            var startedAt = Date.now();

            rec.lang = language.value;
            rec.continuous = true;
            rec.interimResults = true;
            rec.maxAlternatives = GUESSES;

            function sentence(k) {
                return phrases.map(function (g) { return g[Math.min(k, g.length - 1)]; })
                    .join(' ').replace(/\s+/g, ' ').trim();
            }
            function stopSoon(ms) {
                clearTimeout(quietTimer);
                quietTimer = setTimeout(stop, ms);
            }
            function stop() {
                wanted = false;
                clearTimeout(quietTimer);
                if (active) {
                    try { rec.stop(); } catch (e) { finish(); }
                } else {
                    try { rec.abort(); } catch (e) { /* never started */ }
                    finish();
                }
            }
            function finish() {
                if (ended) { return; }
                ended = true;
                clearTimeout(quietTimer);
                clearTimeout(longestTimer);
                stopListening = abandonListening = null;
                setListening(false);
                if (abandoned) { return; }
                if (switchToRecording) {
                    useBrowser = false;
                    trace('built-in recognition does not work here, recording from now on');
                    warm();
                    listen(kind, done);
                    return;
                }
                var text = sentence(0) || unfinished.trim();
                trace('heard: ' + (text || '(nothing)'));
                if (!text) { done(null, [], failed); return; }
                var seen = {};
                var others = [];
                seen[text] = true;
                for (var k = 1; k < GUESSES; k++) {
                    var s = sentence(k);
                    if (s && !seen[s]) { seen[s] = true; others.push(s); }
                }
                done(text, others, false);
            }

            rec.onstart = function () { active = true; };
            rec.onresult = function (e) {
                unfinished = '';
                for (var i = e.resultIndex; i < e.results.length; i++) {
                    var r = e.results[i];
                    if (r.isFinal) {
                        var g = [];
                        for (var a = 0; a < r.length; a++) {
                            if (r[a].transcript.trim()) { g.push(r[a].transcript.trim()); }
                        }
                        if (g.length) { phrases.push(g); }
                    } else {
                        unfinished += r[0].transcript;
                    }
                }
                var sofar = (sentence(0) + ' ' + unfinished).trim();
                if (kind === 'request') { box.value = sofar; }
                if (kind === 'answer' && ONLY_YES.test(sofar)) {
                    stopSoon(YES_SETTLES);
                } else if (kind === 'answer' && ONLY_NO.test(sofar)) {
                    stopSoon(NO_SETTLES);
                } else {
                    stopSoon(timing.quietAfter);
                }
            };
            rec.onerror = function (e) {
                trace('recognition error: ' + e.error);
                if (e.error === 'no-speech' || e.error === 'aborted') {
                    return;   // these only end the session, handled below
                }
                // other errors just fail again on restart
                wanted = false;
                failed = true;
                if (e.error === 'audio-capture') {
                    return;   // no microphone at all: recording can't help
                }
                if (canRecord) {
                    // safari with dictation off, unsupported language, chrome offline etc -> record instead
                    switchToRecording = true;
                } else {
                    show(e.error === 'not-allowed' ? 'denied' : 'unsupported');
                }
            };
            rec.onend = function () {
                active = false;
                if (wanted && Date.now() - startedAt < LONGEST) {
                    // chrome stops after a pause, restart
                    try { rec.start(); return; } catch (e) { /* fall through */ }
                }
                finish();
            };

            stopListening = stop;
            abandonListening = function () { abandoned = true; stop(); };
            setListening(true);
            try {
                rec.start();
            } catch (err) {
                trace('recognition would not start: ' + err);
                failed = true;
                switchToRecording = canRecord;
                finish();
                return;
            }
            stopSoon(timing.quietBefore);
            longestTimer = setTimeout(stop, LONGEST);
        }

        var stream = null;
        function microphone(ok, fail) {
            if (stream && stream.active) { ok(stream); return; }
            navigator.mediaDevices.getUserMedia({ audio: true }).then(function (s) {
                stream = s;
                ok(s);
            }, fail);
        }

        function recordingType() {
            var types = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4', 'audio/webm'];
            for (var i = 0; i < types.length; i++) {
                if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(types[i])) { return types[i]; }
            }
            return '';
        }

        function extension(type) {
            if (type.indexOf('ogg') >= 0) { return '.ogg'; }
            if (type.indexOf('mp4') >= 0) { return '.mp4'; }
            return '.webm';
        }

        function listenByRecording(kind, done) {
            var timing = TIMING[kind];
            microphone(function (s) {
                var type = recordingType();
                var recorder = type ? new MediaRecorder(s, { mimeType: type }) : new MediaRecorder(s);
                var chunks = [];
                var spoke = false;
                var abandoned = false;
                var startedAt = Date.now();
                var lastLoud = startedAt;

                // level meter for silence detection. has to reuse the tap-unlocked context or iOS gives silence
                var ctx = audio();
                var source = null;
                var analyser = null;
                var samples = null;
                if (ctx) {
                    try {
                        if (ctx.resume) { ctx.resume(); }
                        analyser = ctx.createAnalyser();
                        analyser.fftSize = 1024;
                        source = ctx.createMediaStreamSource(s);
                        source.connect(analyser);
                        samples = new Uint8Array(analyser.fftSize);
                    } catch (e) { analyser = null; }
                }

                var meter = setInterval(function () {
                    var now = Date.now();
                    if (analyser && (!ctx.state || ctx.state === 'running')) {
                        analyser.getByteTimeDomainData(samples);
                        var sum = 0;
                        for (var i = 0; i < samples.length; i++) {
                            var x = (samples[i] - 128) / 128;
                            sum += x * x;
                        }
                        if (Math.sqrt(sum / samples.length) > 0.035) {
                            spoke = true;
                            lastLoud = now;
                        }
                        if (spoke ? now - lastLoud > timing.quietAfter : now - startedAt > timing.quietBefore) { stop(); }
                    } else {
                        // no level available, wait for Stop / the time limit
                        spoke = true;
                        lastLoud = now;
                    }
                    if (now - startedAt > LONGEST) { stop(); }
                }, 100);

                function stop() {
                    clearInterval(meter);
                    if (recorder.state !== 'inactive') { recorder.stop(); }
                }

                recorder.ondataavailable = function (e) {
                    if (e.data && e.data.size) { chunks.push(e.data); }
                };
                recorder.onstop = function () {
                    stopListening = abandonListening = null;
                    setListening(false);
                    if (source) { try { source.disconnect(); } catch (e) { /* already gone */ } }
                    if (abandoned) { return; }
                    if (!spoke || !chunks.length) { trace('heard: (nothing)'); done(null, [], false); return; }

                    show('thinking');
                    var blob = new Blob(chunks, { type: recorder.mimeType || type || 'audio/webm' });
                    var data = new FormData();
                    data.append('audio', blob, 'speech' + extension(blob.type));
                    data.append('lang', language.value.slice(0, 2));
                    fetch(form.dataset.transcribe, { method: 'POST', body: data, credentials: 'same-origin' })
                        .then(function (r) {
                            return r.json().then(function (j) { return { code: r.status, body: j }; });
                        })
                        .then(function (res) {
                            if (res.code === 503) { show('unavailable'); done(null, [], true); return; }
                            if (res.code !== 200) { show('failed'); done(null, [], true); return; }
                            var text = (res.body.text || '').trim();
                            trace('server heard: ' + (text || '(nothing)'));
                            if (kind === 'request' && text) { box.value = text; }
                            done(text || null, [], false);
                        })
                        .catch(function () { show('failed'); done(null, [], true); });
                };

                stopListening = stop;
                abandonListening = function () { abandoned = true; stop(); };
                setListening(true);
                recorder.start(250);
            }, function () {
                show('denied');
                done(null, [], true);
            });
        }

        // ---- the conversation ------------------------------------------------

        function send(extra) {
            generation++;
            show('thinking');
            var body = { turns: turns, guesses: guesses, slot_id: slotId };
            for (var key in extra) {
                if (Object.prototype.hasOwnProperty.call(extra, key)) { body[key] = extra[key]; }
            }
            trace('sending ' + turns.length + ' turn(s)' + (body.decision ? ', decision ' + body.decision : ''));
            fetch(form.dataset.step, {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            })
                .then(function (r) {
                    if (!r.ok) { throw new Error('step ' + r.status); }
                    return r.json();
                })
                .then(showStep)
                .catch(function (err) { trace('step failed: ' + err); show('failed'); });
        }

        function showStep(step) {
            var mine = ++generation;
            lastStep = step;
            slotId = step.slot_id || null;
            result.innerHTML = step.html;
            // voice registration summary panel
            var side = document.getElementById('voice-side');
            if (step.side && side) { side.innerHTML = step.side; }
            if (form.hasAttribute('data-clear')) { box.value = ''; }
            wire();
            status.textContent = step.say;
            retries = step.repeat ? retries + 1 : 0;
            trace('step ' + step.stage + ' (understood by ' + (step.source || 'parser') + '), then ' + (step.listen || 'wait'));

            speak(step.say, function (spoken) {
                if (mine !== generation) { trace('moved on while speaking, not listening'); return; }
                if (step.url) {
                    setTimeout(function () { window.location.href = step.url; }, spoken ? 1500 : 6000);
                    return;
                }
                if (!step.listen) { return; }
                if (!canListen || retries > MAX_RETRIES) { show('buttons'); return; }
                if (step.listen === 'answer') { hearAnswer(true); } else { hearRequest(); }
            });
        }

        function hearRequest() {
            if (synth) { synth.cancel(); }
            var mine = ++generation;
            turns = [];
            guesses = [];
            slotId = null;
            show('listening');
            listen('request', function (text, others, failed) {
                if (mine !== generation) { return; }
                if (failed) { show('failed'); return; }
                if (!text) { show('nospeech'); return; }
                box.value = text;
                turns = [text];
                guesses = others;
                send({});
            });
        }

        // mayRetry: mic is sometimes still busy right after speaking
        function hearAnswer(mayRetry) {
            var mine = ++generation;
            show('answer');
            listen('answer', function (text, others, failed) {
                if (mine !== generation) { return; }
                if (failed) {
                    if (mayRetry) { setTimeout(function () { if (mine === generation) { hearAnswer(false); } }, 700); }
                    else { show('buttons'); }
                    return;
                }
                if (!text) {
                    retries++;
                    if (retries > MAX_RETRIES || !lastStep) { show('buttons'); return; }
                    status.textContent = lastStep.say;
                    speak(lastStep.say, function () { if (mine === generation) { hearAnswer(true); } });
                    return;
                }
                turns.push(text);
                send({});
            });
        }

        function quiet() {
            generation++;
            if (abandonListening) { abandonListening(); }
            if (synth) { synth.cancel(); }
        }

        function awaitingAnswer() {
            return !!(lastStep && lastStep.listen === 'answer' && turns.length);
        }

        // result html is replaced every turn, so delegate
        function wire() {
            var i;
            var hiddenUntilScript = result.querySelectorAll('[data-js]');
            for (i = 0; i < hiddenUntilScript.length; i++) { hiddenUntilScript[i].hidden = false; }

            var replay = result.querySelector('[data-replay]');
            if (replay) {
                replay.hidden = !voiceFor(VOICE_LANGS[pageLang] || 'en-IN');
                replay.addEventListener('click', function () {
                    quiet();
                    var mine = generation;
                    if (lastStep) {
                        speak(lastStep.say, function () {
                            if (mine === generation && awaitingAnswer() && canListen) { hearAnswer(true); }
                        });
                    }
                });
            }

            var decisions = result.querySelectorAll('[data-decision]');
            for (i = 0; i < decisions.length; i++) {
                decisions[i].addEventListener('click', function () {
                    quiet();
                    var crop = result.querySelector('[name="crop_type"]');
                    var qty = result.querySelector('[name="estimated_quantity"]');
                    send({
                        decision: this.dataset.decision,
                        crop: crop ? crop.value : null,
                        quantity: qty ? qty.value : null
                    });
                });
            }

            var answers = result.querySelectorAll('[data-answer]');
            for (i = 0; i < answers.length; i++) {
                answers[i].addEventListener('click', function () {
                    quiet();
                    turns.push(this.dataset.answer);
                    send({});
                });
            }

            var qtyDone = result.querySelector('[data-quantity-done]');
            var qtyBox = result.querySelector('#voice-quantity');
            if (qtyDone && qtyBox) {
                qtyDone.addEventListener('click', function () {
                    if (!qtyBox.value) { qtyBox.focus(); return; }
                    quiet();
                    turns.push(qtyBox.value + ' quintal');
                    send({});
                });
            }
        }

        // result already in the page (no-js post)
        var existing = result.querySelector('[data-say]');
        if (existing) {
            lastStep = { say: existing.dataset.say,
                         listen: existing.dataset.listen || (result.querySelector('[data-decision]') ? 'answer' : null) };
            slotId = existing.dataset.slot || null;
            turns = box.value.trim() ? [box.value.trim()] : [];
            wire();
        }

        // voice registration starts by asking, needs a tap before it can speak
        var start = form.querySelector('[data-voice-start]');
        if (start && lastStep && lastStep.say) {
            start.hidden = false;
            start.addEventListener('click', function () {
                quiet();
                retries = 0;
                start.hidden = true;
                var mine = generation;
                status.textContent = lastStep.say;
                speak(lastStep.say, function () {
                    if (mine === generation && canListen && lastStep.listen) { hearAnswer(true); }
                });
            });
        }

        mic.addEventListener('click', function () {
            if (stopListening) { stopListening(); return; }
            quiet();
            retries = 0;
            if (awaitingAnswer()) { hearAnswer(true); } else { hearRequest(); }
        });

        form.addEventListener('submit', function (e) {
            if (!box.value.trim()) { return; }
            e.preventDefault();
            quiet();
            turns = [box.value.trim()];
            guesses = [];
            slotId = null;
            retries = 0;
            send({});
        });
    });
})();
