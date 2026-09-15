/* The registration stepper, and land record rows.

   Without script the registration form is one long page and posts as it is.
   With it the same fieldsets become steps: one on screen at a time, Next
   checks that step's fields, and the last step shows everything back before
   Register.

   Step 1 looks a Farmer ID up (/register/lookup) and fills in what the
   registry holds. The full Aadhaar and account numbers never come to the page,
   only their last digits - the server takes them from the registry when the
   form arrives.

   Land rows work on any page with [data-lands]: add one, remove one. */
(function () {
    function one(sel, root) { return (root || document).querySelector(sel); }
    function all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
    function digits(value) { return String(value || '').replace(/\D/g, ''); }
    function esc(text) {
        var d = document.createElement('div');
        d.textContent = text == null ? '' : String(text);
        return d.innerHTML;
    }
    function mask(value) {
        var s = digits(value);
        if (s.length <= 4) { return s; }
        var dots = '';
        for (var i = 0; i < s.length - 4; i++) { dots += '•'; }
        return dots + s.slice(-4);
    }

    // ---- villages: the list follows the district ---------------------------

    function shown(el) {
        if (el.tagName === 'SELECT') { return el.value ? el.options[el.selectedIndex].text.trim() : ''; }
        return el.value.trim();
    }

    function catalogue(select) {
        if (!select._villages) {
            var list = {};
            all('optgroup', select).forEach(function (group) {
                list[group.getAttribute('data-district')] = all('option', group).map(function (o) { return [o.value, o.textContent]; });
            });
            select._villages = list;
        }
        return select._villages;
    }

    function districtNow() {
        var d = one('#district');
        return d ? d.value : '';
    }

    // only the chosen district's villages. a saved village that is on no list
    // at all stays, so an old record still shows what it holds
    function setVillages(select, district, value) {
        var list = catalogue(select);
        if (value === undefined) { value = select.value; }
        var listed = false, anywhere = false;
        Object.keys(list).forEach(function (d) {
            list[d].forEach(function (v) { if (v[0] === value) { anywhere = true; } });
        });
        select.innerHTML = '';
        select.appendChild(new Option(select.getAttribute(district ? 'data-pick' : 'data-first'), ''));
        (list[district] || []).forEach(function (v) {
            var o = new Option(v[1], v[0]);
            if (v[0] === value) { o.selected = true; listed = true; }
            select.appendChild(o);
        });
        if (value && !anywhere) { select.appendChild(new Option(value, value, true, true)); listed = true; }
        if (!listed) { select.value = ''; }
        select.disabled = !district;
    }

    function refreshVillages() {
        var district = districtNow();
        all('select[data-village]').forEach(function (select) { setVillages(select, district); });
    }

    function setupVillages() {
        var district = one('#district');
        if (!district || !one('select[data-village]')) { return; }
        district.addEventListener('change', refreshVillages);
        refreshVillages();
    }

    // ---- land rows ---------------------------------------------------------

    var rowNumber = 1000;

    function setupLands(box) {
        var holder = box.parentNode;
        var template = one('template[data-land-template]', holder);
        if (!template) { return; }
        var foot = one('.land-foot', holder);
        if (foot) {
            foot.hidden = false;
            var add = one('[data-add-land]', foot);
            if (add) {
                add.addEventListener('click', function () {
                    var row = addRow(box, {});
                    var first = one('input', row);
                    if (first) { first.focus(); }
                });
            }
        }
        wireRows(box);
    }

    function addRow(box, land, before) {
        var template = one('template[data-land-template]', box.parentNode);
        var wrap = document.createElement('div');
        wrap.innerHTML = template.innerHTML.replace(/__N__/g, String(++rowNumber));
        var row = wrap.querySelector('.land-row');
        box.insertBefore(row, before || null);
        one('[name="land_record_id"]', row).value = land.land_record_id || '';
        setVillages(one('[name="land_village"]', row), districtNow(), land.village || '');
        one('[name="land_area"]', row).value = land.area_acres == null ? '' : land.area_acres;
        one('[name="land_source"]', row).value = land.source || 'manual';
        if (land.source === 'registry') {
            row.classList.add('from-registry');
            one('[name="land_record_id"]', row).readOnly = true;
            var badge = document.createElement('span');
            badge.className = 'badge green';
            badge.textContent = box.getAttribute('data-registry-label') || '';
            one('.land-side', row).insertBefore(badge, one('.land-side', row).firstChild);
        }
        wireRows(box);
        return row;
    }

    function clearRow(row) {
        all('input', row).forEach(function (input) {
            if (input.type === 'hidden') { input.value = 'manual'; } else { input.value = ''; input.readOnly = false; }
        });
        all('select', row).forEach(function (select) { select.value = ''; });
        row.classList.remove('from-registry');
        var badge = one('.badge', row);
        if (badge) { badge.parentNode.removeChild(badge); }
    }

    function wireRows(box) {
        all('.land-row', box).forEach(function (row) {
            var button = one('[data-remove-land]', row);
            if (!button || button.getAttribute('data-wired')) { return; }
            button.setAttribute('data-wired', '1');
            button.hidden = false;
            button.addEventListener('click', function () {
                if (all('.land-row', box).length > 1) { row.parentNode.removeChild(row); } else { clearRow(row); }
            });
        });
    }

    // ---- the stepper -------------------------------------------------------

    function setupStepper(form) {
        var steps = all('.reg-step', form);
        var heads = all('.stepper-head li', form);
        var back = one('[data-back]', form);
        var next = one('[data-next]', form);
        var submitRow = one('.step-submit', form);
        var review = one('[data-review]', form);
        var idInput = one('#agristack_id', form);
        var lookupButton = one('[data-lookup-btn]', form);
        var useRegistry = one('#use_registry', form);
        var result = one('#registry-result', form);
        var registryBox = one('[data-registry-box]', form);
        var manualBox = one('[data-manual-box]', form);
        var landsBox = one('[data-lands]', form);
        var fetchedId = useRegistry.value === '1' ? digits(idInput.value) : '';
        var current = 0;
        if (!steps.length) { return; }

        form.classList.add('is-stepper');
        all('[data-js]', form).forEach(function (el) { el.hidden = false; });

        function show(i) {
            current = Math.max(0, Math.min(steps.length - 1, i));
            steps.forEach(function (step, k) { step.classList.toggle('current', k === current); });
            heads.forEach(function (head, k) {
                head.classList.toggle('done', k < current);
                head.classList.toggle('current', k === current);
                if (k === current) { head.setAttribute('aria-current', 'step'); } else { head.removeAttribute('aria-current'); }
            });
            back.hidden = current === 0;
            next.hidden = current === steps.length - 1;
            submitRow.classList.toggle('show', current === steps.length - 1);
            if (current === steps.length - 1) { buildReview(); }
        }

        function goTo(i) {
            show(i);
            var header = one('.topbar');
            var top = form.getBoundingClientRect().top + window.pageYOffset - (header ? header.offsetHeight : 0) - 16;
            if (window.pageYOffset > top) { window.scrollTo(0, top); }
            var heading = one('h3', steps[current]);
            if (heading) {
                heading.setAttribute('tabindex', '-1');
                heading.focus({ preventScroll: true });
            }
        }

        function stepValid(k) {
            var fields = all('input, select, textarea', steps[k]).filter(function (el) {
                return !el.disabled && el.type !== 'hidden' && el.offsetParent !== null;
            });
            for (var i = 0; i < fields.length; i++) {
                if (!fields[i].checkValidity()) { fields[i].reportValidity(); return false; }
            }
            return true;
        }

        // ---- the Farmer ID

        function note(kind, text, title) {
            result.innerHTML = text ? '<div class="notice ' + kind + ' small">' + (title ? '<h3>' + esc(title) + '</h3>' : '') +
                '<p>' + esc(text) + '</p></div>' : '';
        }

        function useManualBank() {
            useRegistry.value = '';
            registryBox.hidden = true;
            manualBox.hidden = false;
        }

        function clearRegistry() {
            useManualBank();
            fetchedId = '';
            all('.land-row.from-registry', landsBox).forEach(function (row) {
                if (all('.land-row', landsBox).length > 1) { row.parentNode.removeChild(row); } else { clearRow(row); }
            });
        }

        function fill(res) {
            var f = res.farmer;
            fetchedId = f.farmer_id;
            idInput.value = f.farmer_id;
            useRegistry.value = '1';
            one('#name', form).value = f.name;
            one('#district', form).value = f.district;
            refreshVillages();
            setVillages(one('#village', form), f.district, f.village);
            all('[data-fill]', registryBox).forEach(function (el) { el.textContent = f[el.getAttribute('data-fill')] || ''; });
            registryBox.hidden = false;
            manualBox.hidden = true;
            // the registry's parcels first, then anything typed that it didn't have
            all('.land-row.from-registry', landsBox).forEach(function (row) { row.parentNode.removeChild(row); });
            var known = {};
            f.lands.forEach(function (land) { known[land.land_record_id] = true; });
            all('.land-row', landsBox).forEach(function (row) {
                var id = one('[name="land_record_id"]', row).value.trim().toUpperCase();
                if (known[id]) { row.parentNode.removeChild(row); }
            });
            var first = one('.land-row', landsBox);
            f.lands.forEach(function (land) {
                addRow(landsBox, { land_record_id: land.land_record_id, village: land.village,
                                   area_acres: land.area_acres, source: 'registry' }, first);
            });
            if (!all('.land-row', landsBox).some(function (row) { return !one('[name="land_record_id"]', row).value; })) {
                addRow(landsBox, {});
            }
            note('success', form.getAttribute('data-found'), f.name + ' · ' + res.shown.village + ', ' + res.shown.district);
        }

        function lookup(then) {
            var code = digits(idInput.value);
            if (code.length !== 11) {
                note('error', form.getAttribute('data-notfound'));
                idInput.focus();
                then(false);
                return;
            }
            note('info', form.getAttribute('data-checking'));
            lookupButton.disabled = true;
            fetch(form.getAttribute('data-lookup') + '?farmer_id=' + encodeURIComponent(code), { credentials: 'same-origin' })
                .then(function (r) { return r.json(); })
                .then(function (res) {
                    lookupButton.disabled = false;
                    if (!res.found) {
                        clearRegistry();
                        note('error', res.message || form.getAttribute('data-notfound'));
                        then(false);
                        return;
                    }
                    fill(res);
                    then(true);
                })
                .catch(function () {
                    lookupButton.disabled = false;
                    note('error', form.getAttribute('data-failed'));
                    then(false);
                });
        }

        lookupButton.addEventListener('click', function (e) {
            e.preventDefault();
            lookup(function (found) { if (found) { goTo(1); } });
        });
        idInput.addEventListener('input', function () {
            if (fetchedId && digits(idInput.value) !== fetchedId) {
                clearRegistry();
                note('', '');
            }
        });
        var manualButton = one('[data-manual]', form);
        if (manualButton) {
            manualButton.addEventListener('click', function () {
                useManualBank();
                var first = one('input', manualBox);
                if (first) { first.focus(); }
            });
        }

        // ---- moving between steps

        next.addEventListener('click', function () {
            if (!stepValid(current)) { return; }
            if (current === 0) {
                var code = digits(idInput.value);
                if (code && useRegistry.value !== '1') {
                    lookup(function (found) { if (found) { goTo(1); } });
                    return;
                }
                if (!code) { clearRegistry(); note('', ''); }
            }
            goTo(current + 1);
        });
        back.addEventListener('click', function () { goTo(current - 1); });

        form.addEventListener('keydown', function (e) {
            var el = e.target;
            if (e.key !== 'Enter' || el.tagName === 'TEXTAREA' || el.tagName === 'BUTTON') { return; }
            if (current < steps.length - 1) {
                e.preventDefault();
                if (el === idInput) { lookupButton.click(); } else { next.click(); }
            }
        });

        form.addEventListener('submit', function (e) {
            // a submit from anywhere but the last step moves on instead
            if (current < steps.length - 1 && !(e.submitter && e.submitter.hasAttribute('data-lookup-btn'))) {
                e.preventDefault();
                next.click();
            }
        });

        // ---- the last step: everything back once more

        function labelFor(id) {
            var label = one('label[for="' + id + '"]', form);
            return label ? label.textContent.replace('*', '').trim() : id;
        }

        function buildReview() {
            var rows = [];
            function add(label, value, step) { rows.push([label, value, step]); }
            var none = review.getAttribute('data-none');
            add(review.getAttribute('data-l-farmer-id'), digits(idInput.value) || none, 0);
            ['name', 'phone_number', 'village'].forEach(function (id) {
                add(labelFor(id), shown(one('#' + id, form)) || none, 1);
            });
            var district = one('#district', form);
            add(labelFor('district'), district.value ? district.options[district.selectedIndex].text : none, 1);
            if (useRegistry.value === '1') {
                all('dt', registryBox).forEach(function (dt) { add(dt.textContent.trim(), dt.nextElementSibling.textContent.trim(), 2); });
            } else {
                add(labelFor('aadhaar_number'), mask(one('#aadhaar_number', form).value) || none, 2);
                add(labelFor('bank_account'), mask(one('#bank_account', form).value) || none, 2);
                add(labelFor('ifsc_code'), one('#ifsc_code', form).value.trim().toUpperCase() || none, 2);
                add(labelFor('bank_name_on_account'), one('#bank_name_on_account', form).value.trim() || one('#name', form).value.trim() || none, 2);
            }
            var landLabel = review.getAttribute('data-l-land');
            var count = 0;
            all('.land-row', landsBox).forEach(function (row) {
                var id = one('[name="land_record_id"]', row).value.trim().toUpperCase();
                if (!id) { return; }
                count++;
                var parts = [id];
                var village = shown(one('[name="land_village"]', row));
                var area = one('[name="land_area"]', row).value.trim();
                if (village) { parts.push(village); }
                if (area) { parts.push(area + ' ' + review.getAttribute('data-acres')); }
                add(landLabel + ' ' + count, parts.join(' · '), 3);
            });
            if (!count) { add(landLabel, none, 3); }

            var html = '<dl class="kv review-list">';
            rows.forEach(function (r) {
                html += '<dt>' + esc(r[0]) + '</dt><dd><span>' + esc(r[1]) + '</span>' +
                    '<button type="button" class="review-edit" data-goto="' + r[2] + '">' + esc(review.getAttribute('data-edit')) + '</button></dd>';
            });
            review.innerHTML = html + '</dl>';
            all('[data-goto]', review).forEach(function (button) {
                button.addEventListener('click', function () { goTo(parseInt(button.getAttribute('data-goto'), 10)); });
            });
        }

        show((parseInt(form.getAttribute('data-start'), 10) || 1) - 1);
    }

    document.addEventListener('DOMContentLoaded', function () {
        setupVillages();
        all('[data-lands]').forEach(setupLands);
        var form = one('form[data-stepper]');
        if (form) { setupStepper(form); }
    });
})();
