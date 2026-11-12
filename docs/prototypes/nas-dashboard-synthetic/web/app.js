import {createPoller} from './poller.js';

const STATUS_LABELS = Object.freeze({
  unknown: '未知', job_completed: '任务已结束', running: '任务运行中', failed: '记录失败',
  differences: '发现差异', matched_snapshot: '快照内一致', matched_sample: '抽样一致', passed_sample: '抽样通过',
});
const REASON_LABELS = Object.freeze({
  invalid_receipt: '未取得有效合成回执', transport_error: '读取失败，当前状态未知',
  chronology_warning: '回执时间无法确认先后', clock_invalid: '页面时钟无效',
  policy_invalid: '有效期配置无效', missing_observed_at: '缺少观测时间',
  future_observation: '观测时间超出允许时钟偏差', cadence_unconfirmed: '采集节奏未确认',
  expired: '历史观测已过期', incomplete_evidence: '证据不足，不能判断',
});
const SCOPE_LABELS = Object.freeze({
  unknown: '未知', reported_snapshot: '声明的快照内', sample: '仅抽样', all_in_snapshot: '声明快照内全量',
});
const JOB_LABELS = Object.freeze({unknown:'未知',running:'运行中（历史记录）',success:'任务成功（历史记录）',failed:'任务失败（历史记录）'});
const RESTORE_LABELS = Object.freeze({unknown:'未知',passed:'通过（历史记录）',failed:'失败（历史记录）'});

function text(document, id, value) {
  const node = document.getElementById(id);
  const next = value ?? '未知';
  if (node.textContent !== next) node.textContent = next;
}
const number = value => value === null || value === undefined ? '未知' : value.toLocaleString('zh-CN');

function renderDashboard(document, view, meta) {
  for (const [key, item] of Object.entries(view.items)) {
    const status = document.getElementById(`${key}-status`);
    status.textContent = STATUS_LABELS[item.currentStatus] ?? '未知';
    status.className = `metric-value ${item.currentStatus}`;
    text(document, `${key}-reason`, REASON_LABELS[item.reason] ?? '仅在本项声明范围内判断');
    text(document, `${key}-time`, item.observedAt);
  }
  const job = view.items.last_attempt.historical;
  const inventory = view.items.inventory_check.historical;
  const content = view.items.content_check.historical;
  const restore = view.items.restore_check.historical;
  text(document, 'job-result', JOB_LABELS[job?.result] ?? '未知');
  text(document, 'job-started', job?.started_at);
  text(document, 'job-completed', job?.completed_at);
  text(document, 'job-errors', number(job?.error_count));
  text(document, 'inventory-scope', SCOPE_LABELS[inventory?.scope] ?? '未知');
  text(document, 'inventory-checked', number(inventory?.checked_objects));
  text(document, 'inventory-missing', number(inventory?.missing_objects));
  text(document, 'inventory-mismatches', number(inventory?.size_mismatches));
  text(document, 'content-scope', SCOPE_LABELS[content?.scope] ?? '未知');
  text(document, 'content-checked', number(content?.checked_objects));
  text(document, 'content-mismatches', number(content?.hash_mismatches));
  text(document, 'restore-scope', SCOPE_LABELS[restore?.scope] ?? '未知');
  text(document, 'restore-result', RESTORE_LABELS[restore?.result] ?? '未知');
  text(document, 'restore-checked', number(restore?.checked_objects));
  text(document, 'receipt-generated', view.generatedAt);
  text(document, 'page-read-time', meta.lastSuccessfulReadAt);

  let summary = '已加载合成回执 · 当前性未知（采集节奏未确认）';
  if (meta.warning) summary = '回执时间倒退或无法比较 · 当前状态未知';
  else if (meta.lastError) summary = '读取失败 · 当前状态未知，历史记录不代表当前通过';
  else if (view.loadError) summary = meta.loading ? '正在读取合成回执 · 当前状态未知' : '尚未取得有效合成回执 · 当前状态未知';
  text(document, 'live-status', summary);
  text(document, 'last-fetch-state', meta.loading ? '正在读取同源示例文件…'
    : meta.lastError ? '上次读取失败，保留已有历史证据'
      : meta.warning ? '未采用时间无法确认的新回执' : '页面轮询示例，不是 NAS 实时采集');
  const warning = document.getElementById('transport-warning');
  warning.hidden = !meta.warning;
  text(document, 'transport-warning', meta.warning === 'E_OLDER_RECEIPT'
    ? '收到较旧的回执，未覆盖已有历史记录。当前状态未知。'
    : meta.warning ? '回执时间或同时间证据无法确定先后，未覆盖已有历史记录。当前状态未知。' : '');
  document.getElementById('refresh').disabled = meta.loading;
  document.getElementById('auto-refresh').checked = meta.autoRefresh;
}

// Injection is for DOM/network/timer boundary tests, not a production data adapter.
export function mountDashboard({document = globalThis.document, window = globalThis.window, controllerOptions = {}} = {}) {
  const controller = createPoller({...controllerOptions, render: (view, meta) => renderDashboard(document, view, meta)});
  document.getElementById('refresh').addEventListener('click', () => controller.refresh());
  document.getElementById('auto-refresh').addEventListener('change', event => controller.setAutoRefresh(event.target.checked));
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') controller.visibilityReturn();
  });
  window.addEventListener('pagehide', () => controller.stop());
  window.addEventListener('pageshow', () => controller.start());
  controller.start();
  return controller;
}

if (typeof document !== 'undefined' && typeof window !== 'undefined') mountDashboard();
