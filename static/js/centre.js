/* Weather on a centre's slot page.

   Tapping a day in the forecast shows it hour by hour. Choosing a slot opens
   that day's weather under it, picks out the readings around the chosen time,
   sums them up in one line, and warns if rain is likely then.

   Everything is already in the page; this only shows and hides it. Without
   script the forecast and today's hours are still there. */
(function () {
    document.addEventListener('DOMContentLoaded', function () {
        var i;

        // ---- the forecast card: a day at a time, hour by hour
        var card = document.getElementById('centre-weather');
        if (card) {
            var dayCards = card.querySelectorAll('[data-pick-day]');
            var dayHours = card.querySelectorAll('.cw-day');
            var showDay = function (date) {
                for (var n = 0; n < dayCards.length; n++) {
                    var on = dayCards[n].getAttribute('data-pick-day') === date;
                    dayCards[n].classList.toggle('on', on);
                    dayCards[n].setAttribute('aria-pressed', on ? 'true' : 'false');
                }
                for (var m = 0; m < dayHours.length; m++) {
                    dayHours[m].hidden = dayHours[m].getAttribute('data-day') !== date;
                }
            };
            for (i = 0; i < dayCards.length; i++) {
                dayCards[i].addEventListener('click', function () { showDay(this.getAttribute('data-pick-day')); });
                dayCards[i].addEventListener('keydown', function (e) {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        showDay(this.getAttribute('data-pick-day'));
                    }
                });
            }
            var hint = card.querySelector('.cw-hint');
            if (hint) { hint.hidden = false; }
        }

        // ---- choosing a slot: that day's weather, under it
        var panels = document.querySelectorAll('.slot-weather');
        var radios = document.querySelectorAll('input[name="slot_id"][data-date]');

        function showSlot(radio) {
            var date = radio.getAttribute('data-date');
            var start = parseFloat(radio.getAttribute('data-start'));
            var end = parseFloat(radio.getAttribute('data-end'));
            var panel = null;
            for (var p = 0; p < panels.length; p++) {
                var mine = panels[p].getAttribute('data-day') === date;
                panels[p].hidden = !mine;
                if (mine) { panel = panels[p]; }
            }
            if (!panel) { return; }

            // readings are three hours apart, so take the ones within an hour
            // either side of the window
            var rows = panel.querySelectorAll('tr[data-hour]');
            var temps = [];
            var chance = 0;
            var rain = 0;
            var wet = false;
            for (var r = 0; r < rows.length; r++) {
                var hour = parseFloat(rows[r].getAttribute('data-hour'));
                var inSlot = hour >= start - 1 && hour <= end + 1;
                rows[r].classList.toggle('in-slot', inSlot);
                if (!inSlot) { continue; }
                temps.push(parseFloat(rows[r].getAttribute('data-temp')));
                chance = Math.max(chance, parseFloat(rows[r].getAttribute('data-chance')));
                rain += parseFloat(rows[r].getAttribute('data-rain'));
                wet = wet || rows[r].getAttribute('data-wet') === '1';
            }

            var windowText = panel.querySelector('[data-window]');
            if (windowText) { windowText.textContent = radio.getAttribute('data-window'); }
            var line = panel.querySelector('.sw-slot');
            var summary = panel.querySelector('[data-slot-summary]');
            if (line) { line.hidden = !temps.length; }
            if (summary && temps.length) {
                var low = Math.min.apply(null, temps);
                var high = Math.max.apply(null, temps);
                summary.textContent = (low === high ? low : low + '–' + high) + '°C · ' +
                    chance + '% ' + summary.getAttribute('data-chance') + ' · ' + rain.toFixed(1) + ' mm';
            }
            var warning = panel.querySelector('.sw-wet');
            if (warning) { warning.hidden = !wet; }
        }

        for (i = 0; i < radios.length; i++) {
            radios[i].addEventListener('change', function () { showSlot(this); });
            // a slot still ticked after coming back to the page
            if (radios[i].checked) { showSlot(radios[i]); }
        }
    });
})();
