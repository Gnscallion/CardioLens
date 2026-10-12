/* 后端接口封装。
 *
 * 统一把各种失败形态归一成带中文提示的 Error：
 *   - 网络不通
 *   - 非 JSON 响应（例如反代返回了 HTML 错误页）
 *   - 后端约定的 { ok: false, error: "..." }
 */

async function parse(res) {
  const text = await res.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    // 收到非 JSON（常见于反向代理自己吐出的错误页），
    // 与其让 JSON.parse 抛一句看不懂的错，不如给出可判断的说明。
    throw new Error(
      res.ok
        ? '服务器返回了无法解析的内容'
        : `服务器返回 ${res.status}（响应不是 JSON，可能是反向代理的错误页）`
    );
  }
}

async function request(method, url, body, signal) {
  let res;
  try {
    res = await fetch(url, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: 'same-origin',   // 带上会话 Cookie
      signal,
    });
  } catch (err) {
    if (err && err.name === 'AbortError') throw err;
    throw new Error('网络连接失败，请检查网络后重试');
  }

  const data = await parse(res);
  if (!res.ok || data.ok === false) {
    throw new Error(data.error || `请求失败（HTTP ${res.status}）`);
  }
  return data;
}

export const api = {
  get: (url, signal) => request('GET', url, undefined, signal),
  post: (url, body, signal) => request('POST', url, body ?? {}, signal),
  del: (url, signal) => request('DELETE', url, undefined, signal),

  bootstrap: (signal) => request('GET', '/api/bootstrap', undefined, signal),
  status: () => request('GET', '/api/status'),
  records: () => request('GET', '/api/records'),

  /** 波形预览。参数是原始值，由后端负责校验与回退对齐。 */
  preview: (recordId, start, duration, signal) =>
    request(
      'GET',
      `/api/preview?record_id=${encodeURIComponent(recordId)}` +
        `&start=${encodeURIComponent(start)}&duration=${encodeURIComponent(duration)}`,
      undefined,
      signal
    ),

  analyze: (params, signal) => request('POST', '/api/analyze', params, signal),

  historyList: () => request('GET', '/api/history'),
  historyDetail: (id) => request('GET', `/api/history/${id}`),
  historyDelete: (id) => request('DELETE', `/api/history/${id}`),
  historyClear: () => request('POST', '/api/history/clear', {}),
};
