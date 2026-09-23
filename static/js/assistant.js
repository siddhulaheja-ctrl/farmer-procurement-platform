/* help chat widget. answers come from /help/chat (assistant.py),
   history kept in sessionStorage for the tab. */
(function () {
    var STORE = 'ks-help-chat';
    var KEEP = 12;
    var VOICE_LANGS = { hi: 'hi-IN', bn: 'bn-IN', en: 'en-IN' };

    function load() {
        try {
            var saved = JSON.parse(sessionStorage.getItem(STORE) || '[]');
            return Array.isArray(saved) ? saved : [];
        } catch (e) { return []; }
    }
    function save(list) {
        try { sessionStorage.setItem(STORE, JSON.stringify(list.slice(-KEEP))); } catch (e) { /* private mode */ }
    }

    document.addEventListener('DOMContentLoaded', function () {
        var root = document.getElementById('assistant');
        if (!root || !window.fetch || !window.JSON) { return; }
        root.hidden = false;

        var launch = root.querySelector('.assistant-launch');
        var panel = root.querySelector('.assistant-panel');
        var log = root.querySelector('.ap-log');
        var chips = root.querySelector('.ap-chips');
        var form = root.querySelector('.ap-form');
        var input = form.querySelector('input');
        var sendButton = form.querySelector('.ap-send');
        var mic = form.querySelector('.ap-mic');
        var pageLang = document.documentElement.lang;
        var history = load();
        var busy = false;
        var talking = null;     // held so chrome doesn't drop the utterance mid-sentence

        function add(role, text, link) {
            var msg = document.createElement('div');
            msg.className = 'ap-msg ' + (role === 'user' ? 'me' : 'bot');
            var words = document.createElement('p');
            words.textContent = text;
            msg.appendChild(words);
            if (link && link.href) {
                var a = document.createElement('a');
                a.className = 'ap-link';
                a.href = link.href;
                a.textContent = link.label + ' →';
                msg.appendChild(a);
            }
            log.appendChild(msg);
            log.scrollTop = log.scrollHeight;
            return msg;
        }

        function showChips(list) {
            chips.innerHTML = '';
            for (var i = 0; i < list.length; i++) {
                var b = document.createElement('button');
                b.type = 'button';
                b.textContent = list[i];
                chips.appendChild(b);
            }
            chips.hidden = !list.length;
        }
        chips.addEventListener('click', function (e) {
            if (e.target.tagName === 'BUTTON') { ask(e.target.textContent, false); }
        });

        for (var n = 0; n < history.length; n++) { add(history[n].role, history[n].text, history[n].link); }
        if (history.length) { chips.hidden = true; }

        function openPanel() {
            panel.hidden = false;
            launch.setAttribute('aria-expanded', 'true');
            root.classList.add('open');
            log.scrollTop = log.scrollHeight;
            input.focus();
        }
        function closePanel() {
            panel.hidden = true;
            launch.setAttribute('aria-expanded', 'false');
            root.classList.remove('open');
            if (window.speechSynthesis) { window.speechSynthesis.cancel(); }
            launch.focus();
        }
        launch.addEventListener('click', function () { if (panel.hidden) { openPanel(); } else { closePanel(); } });
        root.querySelector('.ap-close').addEventListener('click', closePanel);
        root.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && !panel.hidden) { closePanel(); }
        });

        function voiceFor(tag) {
            var synth = window.speechSynthesis;
            if (!synth) { return null; }
            var voices = synth.getVoices();
            for (var i = 0; i < voices.length; i++) {
                if (voices[i].lang.replace('_', '-') === tag) { return voices[i]; }
            }
            for (var j = 0; j < voices.length; j++) {
                if (voices[j].lang.slice(0, 2) === tag.slice(0, 2)) { return voices[j]; }
            }
            return null;
        }
        if (window.speechSynthesis) { window.speechSynthesis.getVoices(); }

        function speak(text) {
            var voice = voiceFor(VOICE_LANGS[pageLang] || 'en-IN');
            if (!voice) { return; }     // an english voice reading hindi is worse than nothing
            window.speechSynthesis.cancel();
            talking = new SpeechSynthesisUtterance(text);
            talking.voice = voice;
            talking.lang = voice.lang;
            talking.rate = 0.95;
            window.speechSynthesis.speak(talking);
        }

        function ask(text, spoken) {
            text = (text || '').trim();
            if (!text || busy) { return; }
            busy = true;
            sendButton.disabled = true;
            add('user', text);
            history.push({ role: 'user', text: text });
            save(history);
            input.value = '';
            chips.hidden = true;
            var waiting = add('bot', root.getAttribute('data-thinking'));
            waiting.classList.add('waiting');

            fetch(root.getAttribute('data-url'), {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ messages: history.map(function (m) { return { role: m.role, text: m.text }; }) })
            })
                .then(function (r) {
                    if (!r.ok) { throw new Error('chat ' + r.status); }
                    return r.json();
                })
                .then(function (answer) {
                    log.removeChild(waiting);
                    add('bot', answer.reply, answer.link);
                    history.push({ role: 'assistant', text: answer.reply, link: answer.link });
                    save(history);
                    showChips(answer.suggestions || []);
                    if (spoken) { speak(answer.reply); }
                })
                .catch(function () {
                    if (waiting.parentNode) { log.removeChild(waiting); }
                    add('bot', root.getAttribute('data-offline'));
                })
                .then(function () {
                    busy = false;
                    sendButton.disabled = false;
                });
        }

        form.addEventListener('submit', function (e) {
            e.preventDefault();
            ask(input.value, false);
        });

        var Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (Recognition) {
            var listening = null;
            mic.hidden = false;
            mic.addEventListener('click', function () {
                if (listening) { listening.stop(); return; }
                var rec = new Recognition();
                var said = '';
                var chosen = null;
                try { chosen = localStorage.getItem('ks-mic-lang'); } catch (e) { /* private mode */ }
                rec.lang = chosen || (pageLang === 'bn' ? 'bn-IN' : 'hi-IN');
                rec.interimResults = true;
                rec.onresult = function (e) {
                    said = '';
                    for (var i = 0; i < e.results.length; i++) { said += e.results[i][0].transcript; }
                    input.value = said;
                };
                rec.onend = function () {
                    listening = null;
                    mic.classList.remove('on');
                    if (said.trim()) { ask(said, true); }
                };
                rec.onerror = function () { /* onend follows */ };
                try {
                    rec.start();
                    listening = rec;
                    mic.classList.add('on');
                } catch (err) {
                    listening = null;
                }
            });
        }
    });
})();
