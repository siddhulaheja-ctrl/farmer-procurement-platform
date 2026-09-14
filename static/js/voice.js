/* Book by speaking, as a conversation.

   1. The farmer taps the mic and says what they want.
   2. The words go to the server (voicebook.py), which picks a slot and sends
      back what to say: "Rudrapur, tomorrow, 8 to 10 in the morning, wheat,
      20 quintals. Shall I book it? Say yes or no."
   3. The page says it out loud and listens for the answer. Yes books it and
      reads out the token, no stops, a correction ("no, 30 quintals") gets a
      new suggestion, and a missing crop or quantity is asked for.
   Big buttons do the same for anyone who would rather tap.

   Listening: Chrome, Edge and Safari have speech recognition built in. Other
   browsers record the audio and the server writes out the words
   (speech_to_text.py). Add ?stt=server to the address to force that path in
   Chrome when testing it.

   Speaking: speechSynthesis works in every current browser, but only when the
   device has a voice for the page language. Without one, the words stay on
   screen and the buttons still work.

   The page never reloads mid-conversation: browsers only let a page speak
   after the farmer has tapped something on that same page.

   Open the browser console to follow a conversation: every step logs a
   "[voice]" line. */
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

    // an answer that is only a yes or only a no doesn't need the full pause.
    // yes stops quickest; no waits a little longer, because "nahi, tees
    // quintal" is how people correct us and must not be cut off
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

        // the server model takes a few seconds to load; start now, not on the first sentence
        if (canListen && !useBrowser && form.dataset.warm) {
            fetch(form.dataset.warm, { method: 'POST', credentials: 'same-origin' }).catch(function () {});
        }

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

        // chrome forgets to fire onend for an utterance nothing else refers to,
        // which left the page waiting and the mic closed. keep hold of it here
        var talking = null;

        function speak(text, then) {
            var voice = voiceFor(VOICE_LANGS[pageLang] || 'en-IN');
            if (!text || !voice) {
                // an english voice reading hindi is worse than silence
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

            // don't trust onend alone: also notice when the voice goes quiet
            watch = setInterval(function () {
                if (Date.now() - startedAt > 1000 && !synth.speaking && !synth.pending) { end('went quiet'); }
            }, 250);
            guard = setTimeout(function () { end('time limit'); }, 4000 + text.length * 120);
        }

        // a short tone when the microphone opens, so the farmer knows to talk
        var beeper = null;
        function beep() {
            var Context = window.AudioContext || window.webkitAudioContext;
            if (!Context) { return; }
            try {
                beeper = beeper || new Context();
                if (beeper.resume) { beeper.resume(); }
                var tone = beeper.createOscillator();
                var volume = beeper.createGain();
                tone.frequency.value = 880;
                volume.gain.value = 0.08;
                tone.connect(volume);
                volume.connect(beeper.destination);
                tone.start();
                tone.stop(beeper.currentTime + 0.15);
            } catch (e) { /* no tone, still listening */ }
        }

        // ---- listening -------------------------------------------------------

        function setListening(on) {
            mic.classList.toggle('on', on);
            mic.setAttribute('aria-pressed', on ? 'true' : 'false');
            mic.querySelector('span').textContent = on ? mic.dataset.stop : mic.dataset.start;
        }

        // done(text, otherGuesses, failed). text is null when nothing was heard
        function listen(kind, done) {
            beep();
            trace('listening for ' + (kind === 'answer' ? 'an answer' : 'a request'));
            // wait out the tone, or the recogniser hears it
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
                if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
                    failed = true;
                    wanted = false;
                    show('denied');
                } else if (e.error === 'network' || e.error === 'audio-capture') {
                    failed = true;
                    wanted = false;
                }
                // no-speech and aborted only end the session, handled below
            };
            rec.onend = function () {
                active = false;
                if (wanted && Date.now() - startedAt < LONGEST) {
                    // chrome ends the session after a pause: carry on listening
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

                // how loud it is, to notice when the farmer has stopped talking
                var Context = window.AudioContext || window.webkitAudioContext;
                var ctx = Context ? new Context() : null;
                var analyser = null;
                var samples = null;
                if (ctx) {
                    analyser = ctx.createAnalyser();
                    analyser.fftSize = 1024;
                    ctx.createMediaStreamSource(s).connect(analyser);
                    samples = new Uint8Array(analyser.fftSize);
                }

                var meter = setInterval(function () {
                    var now = Date.now();
                    if (analyser) {
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
                        spoke = true;   // can't measure it: record until Stop or the limit
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
                    if (ctx && ctx.close) { ctx.close(); }
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
            wire();
            status.textContent = step.say;
            retries = step.repeat ? retries + 1 : 0;
            trace('step ' + step.stage + ' (understood by ' + (step.source || 'parser') + '), then ' + (step.listen || 'wait'));

            speak(step.say, function (spoken) {
                if (mine !== generation) { trace('moved on while speaking, not listening'); return; }
                if (step.url) {
                    // give the token a moment on screen when it couldn't be read out
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

        // mayRetry: straight after our own voice the microphone is sometimes
        // still busy, so one failed start is tried again
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
                    // silence: ask again, then leave it to the buttons
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

        // a question is waiting for an answer, so the mic should hear a reply, not a new request
        function awaitingAnswer() {
            return !!(lastStep && lastStep.listen === 'answer' && turns.length);
        }

        // buttons inside the result, which is replaced after every turn
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

        // a page that arrived with a result already in it (typed, script-free post)
        var existing = result.querySelector('[data-say]');
        if (existing) {
            lastStep = { say: existing.dataset.say, listen: result.querySelector('[data-decision]') ? 'answer' : null };
            slotId = existing.dataset.slot || null;
            turns = box.value.trim() ? [box.value.trim()] : [];
            wire();
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
