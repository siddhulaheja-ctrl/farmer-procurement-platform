/* The weighbridge form. Works out the net weight and suggests a grade from
   the moisture and foreign matter as they are typed, the same way core.py
   does, and asks for a reason only when the grade picked differs. */
(function () {
    var form = document.getElementById('weigh-form');
    if (!form) { return; }
    var FACTOR = { A: 1, FAQ: 1, B: 0.94, Rejected: 0 };
    var msp = parseFloat(form.getAttribute('data-msp'));
    var limit = parseFloat(form.getAttribute('data-limit'));
    var faq = parseFloat(form.getAttribute('data-faq'));
    var bLimit = parseFloat(form.getAttribute('data-b'));
    var grade = form.querySelector('#quality_grade');
    var noteField = document.getElementById('grade-note-field');
    var note = document.getElementById('grade_note');
    var hint = document.getElementById('suggested');
    var touched = false;
    var suggested = null;

    function num(id) { return parseFloat(form.querySelector('#' + id).value); }
    function out(name, text) { form.querySelector('[data-out="' + name + '"]').textContent = text; }
    function rupees(v) { return '₹' + Math.round(v).toLocaleString('en-IN'); }

    function suggest(m, f) {
        if (isNaN(m) || isNaN(f)) { return null; }
        if (m > limit + 2 || f > bLimit) { return 'Rejected'; }
        if (m > limit || f > faq) { return 'B'; }
        if (m <= limit - 1.5 && f <= 0.25) { return 'A'; }
        return 'FAQ';
    }

    function update() {
        var net = Math.max(0, num('gross_weight') - (num('bags') || 0) * (num('bag_weight_kg') || 0) / 100);
        suggested = suggest(num('moisture'), num('foreign_matter'));
        if (suggested) {
            hint.textContent = 'Readings suggest grade ' + suggested + '.';
            if (!touched) { grade.value = suggested; }
        }
        var differs = suggested && grade.value !== suggested;
        noteField.hidden = !differs;
        note.required = !!differs;
        var rate = msp * (FACTOR[grade.value] === undefined ? 1 : FACTOR[grade.value]);
        out('net', isNaN(net) ? '—' : net.toFixed(2));
        out('rate', rupees(rate));
        out('amount', isNaN(net) ? '—' : rupees(rate * net));
    }

    form.addEventListener('input', update);
    grade.addEventListener('change', function () { touched = true; update(); });
    update();
})();
