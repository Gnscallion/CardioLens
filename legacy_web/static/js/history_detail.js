/* 历史报告详情页：渲染已保存的分析结果 */
(function () {
  'use strict';

  const D = JSON.parse(document.getElementById('payload-data').textContent);
  const ORDER = ['N', 'S', 'V', 'F', 'Q'];
  const NAME = {}, DESC = {};
  D.classes.forEach(c => { NAME[c.code] = c.name; DESC[c.code] = c.desc; });

  const $ = id => document.getElementById(id);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const pct = x => (x * 100).toFixed(1) + '%';

  const s = D.summary;
  let selected = 0;

  /* 分布 */
  $('stackBox').innerHTML = ORDER.map(c => {
    const v = s.counts[c] || 0;
    if (!v) return '';
    return '<span style="width:' + (v / s.n_beats * 100).toFixed(2) +
           '%;background:var(--c-' + c + ')" title="' + c + ': ' + v + '">' +
           (v / s.n_beats > 0.09 ? v : '') + '</span>';
  }).join('');

  $('distBox').innerHTML = ORDER.map(c => {
    const v = s.counts[c] || 0;
    return '<div class="prob-row">' +
      '<span class="lbl"><span class="badge badge-' + c + '">' + c + '</span> ' + esc(NAME[c]) + '</span>' +
      '<span class="bar"><i style="width:' + (v / s.n_beats * 100).toFixed(1) +
        '%;background:var(--c-' + c + ')"></i></span>' +
      '<span class="val">' + v + ' 搏</span></div>';
  }).join('');

  /* 明细表 */
  $('beatRows').innerHTML = D.beats.map(b =>
    '<tr data-i="' + (b.index - 1) + '">' +
      '<td class="mono">' + b.index + '</td>' +
      '<td class="mono">' + b.time_sec.toFixed(2) + ' s</td>' +
      '<td><span class="badge badge-' + b.pred + '">' + b.pred + ' ' + esc(b.pred_name) + '</span></td>' +
      '<td class="num">' + pct(b.confidence) + '</td>' +
      '<td><span class="badge badge-' + b.expert + '">' + b.expert + '</span></td>' +
      '<td>' + (b.agree ? '<span class="badge badge-ok">一致</span>'
                        : '<span class="badge badge-warn">不一致</span>') + '</td>' +
    '</tr>'
  ).join('');

  /* 图例 */
  $('resLegend').innerHTML = ORDER.filter(c => s.counts[c] > 0).map(c =>
    '<span class="item"><i class="dot" style="background:var(--c-' + c + ')"></i>' +
    c + ' ' + esc(NAME[c]) + ' <span class="mono muted">' + s.counts[c] + '</span></span>'
  ).join('') + (D.beats[0] && D.beats[0].cam
    ? '<span class="item"><i class="dot" style="background:#f59e0b"></i>Grad-CAM 关注区间</span>' : '');

  function drawStrip() {
    ECGWave.renderStrip($('resCanvas'), {
      signal: D.signal, fs: D.fs, beats: D.beats, selected: selected,
      showCam: !!(D.beats[0] && D.beats[0].cam), height: 340,
      onSelect: i => { selected = i; drawStrip(); drawBeat(i); highlight(i); },
      onHover: (i, ev) => {
        const tip = $('resTip');
        if (i < 0) { tip.style.display = 'none'; return; }
        const b = D.beats[i];
        tip.innerHTML = '第 ' + b.index + ' 搏 · ' + b.time_sec.toFixed(2) + ' s<br>' +
          '<span style="color:' + ECGWave.CLASS_COLOR[b.pred] + '">' + b.pred + ' ' +
          esc(b.pred_name) + '</span> · 置信度 ' + pct(b.confidence);
        tip.style.display = 'block';
        const box = $('resCanvas').parentElement.getBoundingClientRect();
        tip.style.left = Math.min(ev.clientX - box.left + 12, box.width - 190) + 'px';
        tip.style.top = (ev.clientY - box.top - 10) + 'px';
      }
    });
  }

  function highlight(i) {
    const rows = document.querySelectorAll('#beatRows tr');
    rows.forEach(r => r.classList.remove('sel'));
    if (rows[i]) { rows[i].classList.add('sel'); rows[i].scrollIntoView({ block: 'nearest' }); }
  }

  function drawBeat(i) {
    const b = D.beats[i];
    if (!b) return;
    $('beatNav').textContent = '第 ' + b.index + ' / ' + D.beats.length + ' 搏';

    const raw = D.signal.slice(b.sample - 90, b.sample + 162);
    if (raw.length === 252) {
      ECGWave.renderBeat($('beatCanvas'), {
        beat: raw, cam: b.cam || null, classes: D.classes,
        predIdx: ORDER.indexOf(b.pred), height: 190
      });
    }

    $('beatInfo').innerHTML =
      '<div class="flex-between" style="margin-bottom:12px">' +
        '<span class="badge badge-' + b.pred + '" style="font-size:.9rem;padding:5px 14px">' +
          b.pred + ' · ' + esc(b.pred_name) + '</span>' +
        (b.agree ? '<span class="badge badge-ok">与专家标注一致</span>'
                 : '<span class="badge badge-warn">专家标注为 ' + b.expert + '</span>') +
      '</div>' +
      '<p class="small muted">' + esc(DESC[b.pred] || '') + '</p>' +
      (window.ECGRhythm ? ECGRhythm.render(b) : '') +
      ORDER.map(c =>
        '<div class="prob-row">' +
          '<span class="lbl"><span class="badge badge-' + c + '">' + c + '</span></span>' +
          '<span class="bar"><i style="width:' + (b.probs[c] * 100).toFixed(1) +
            '%;background:var(--c-' + c + ')"></i></span>' +
          '<span class="val">' + (b.probs[c] * 100).toFixed(1) + '%</span></div>'
      ).join('');
  }

  document.querySelectorAll('#beatRows tr').forEach(r => {
    r.addEventListener('click', () => {
      selected = Number(r.dataset.i);
      drawStrip(); drawBeat(selected); highlight(selected);
    });
  });

  const delBtn = $('delBtn');
  if (delBtn) delBtn.addEventListener('click', async () => {
    if (!confirm('确定要删除该报告吗？该操作不可恢复。')) return;
    try {
      const res = await fetch('/api/history/' + delBtn.dataset.id, { method: 'DELETE' });
      const j = await res.json();
      if (!res.ok || j.ok === false) throw new Error(j.error || '删除失败');
      location.href = '/history';
    } catch (e) {
      alert(e.message);
    }
  });

  drawStrip();
  drawBeat(selected);
  highlight(selected);

  let rt;
  window.addEventListener('resize', () => {
    clearTimeout(rt);
    rt = setTimeout(() => { drawStrip(); drawBeat(selected); }, 180);
  });
})();
