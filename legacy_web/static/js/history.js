/* 历史记录页：删除单条 / 清空全部 */
(function () {
  'use strict';

  async function api(url, opts) {
    const res = await fetch(url, opts);
    let data;
    try { data = await res.json(); }
    catch (e) { throw new Error('服务器返回了非 JSON 响应（HTTP ' + res.status + '）'); }
    if (!res.ok || data.ok === false) throw new Error(data.error || ('请求失败（HTTP ' + res.status + '）'));
    return data;
  }

  function flash(message, kind) {
    const div = document.createElement('div');
    div.className = 'alert alert-' + (kind || 'ok');
    div.innerHTML = '<span>' + (kind === 'err' ? '⚠' : '✓') + '</span><div>' + message + '</div>';
    const main = document.querySelector('.page');
    main.insertBefore(div, main.firstChild);
    setTimeout(() => div.remove(), 5000);
  }

  document.addEventListener('click', async function (e) {
    const del = e.target.closest('.del');
    if (del) {
      const id = del.dataset.id;
      if (!confirm('确定要删除报告 #' + id + ' 吗？该操作不可恢复。')) return;
      del.disabled = true;
      del.textContent = '删除中…';
      try {
        await api('/api/history/' + id, { method: 'DELETE' });
        const row = del.closest('tr');
        row.style.transition = 'opacity .3s';
        row.style.opacity = '0';
        setTimeout(() => {
          row.remove();
          // 删掉最后一条后刷新，让「清空全部」按钮与统计数字同步更新
          if (!document.querySelectorAll('tbody tr').length) location.reload();
        }, 300);
        flash('已删除报告 #' + id + '。');
      } catch (err) {
        flash(err.message, 'err');
        del.disabled = false;
        del.textContent = '删除';
      }
      return;
    }

    if (e.target.id === 'clearBtn') {
      if (!confirm('确定要清空全部历史记录吗？该操作不可恢复。')) return;
      e.target.disabled = true;
      e.target.textContent = '清空中…';
      try {
        const r = await api('/api/history/clear', { method: 'POST' });
        flash('已清空 ' + r.deleted + ' 条历史记录。');
        setTimeout(() => location.reload(), 700);
      } catch (err) {
        flash(err.message, 'err');
        e.target.disabled = false;
        e.target.textContent = '清空全部记录';
      }
    }
  });
})();
