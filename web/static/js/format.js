/* 展示层共用的格式化工具与类别配色。 */

// AAMI 五分类的固定顺序，与模型输出索引一致，不要随意调整
export const CLASS_ORDER = ['N', 'S', 'V', 'F', 'Q'];

// 与后端 config.CLASS_NAMES_ZH 对应；仅用于无法拿到后端 classes 时的兜底
export const CLASS_NAME_FALLBACK = {
  N: '正常搏动',
  S: '室上性早搏',
  V: '室性早搏',
  F: '融合搏动',
  Q: '未分类/起搏搏动',
};

export const CLASS_COLOR = {
  N: '#059669',
  S: '#d97706',
  V: '#dc2626',
  F: '#7c3aed',
  Q: '#64748b',
};

export function pct(v, digits = 1) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return (v * 100).toFixed(digits) + '%';
}

export function num(v, digits = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return Number(v).toFixed(digits);
}

export function int(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return String(Math.round(v));
}

/**
 * 相对时间。优先用后端给的 created_at_ts（带时区的 epoch），
 * 它不受服务器时区设置影响；没有时才退回解析本地时间字符串。
 */
export function relTime(item) {
  let ms = null;
  if (item && item.created_at_ts) {
    ms = item.created_at_ts * 1000;
  } else if (item && item.created_at) {
    const t = Date.parse(item.created_at.replace(' ', 'T'));
    if (!Number.isNaN(t)) ms = t;
  }
  if (ms === null) return item?.created_at || '—';

  const diff = (Date.now() - ms) / 1000;
  if (diff < 0) return '刚刚';
  if (diff < 60) return '刚刚';
  if (diff < 3600) return Math.floor(diff / 60) + ' 分钟前';
  if (diff < 86400) return Math.floor(diff / 3600) + ' 小时前';
  if (diff < 86400 * 30) return Math.floor(diff / 86400) + ' 天前';
  return item.created_at;
}

/** 风险等级 -> 样式类名 */
export function riskClass(code) {
  if (code === 'high') return 'high';
  if (code === 'medium') return 'medium';
  return 'low';
}
