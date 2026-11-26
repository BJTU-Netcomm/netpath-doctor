const $ = (id) => document.getElementById(id);
let selectedFile = null;
let previewUrl = null;
let busy = false;
let lastResult = null;
let settings = null;
let completedTools = 0;

function setPhase(active) {
  const phases = ['phaseInput', 'phaseReason', 'phaseObserve', 'phaseResult'];
  const current = phases.indexOf(active);
  phases.forEach((id, index) => {
    $(id).classList.toggle('current', index === current);
    $(id).classList.toggle('done', index < current);
    if (index === current) $(id).setAttribute('aria-current', 'step');
    else $(id).removeAttribute('aria-current');
  });
}
function setSession(state, label, detail) {
  $('sessionState').textContent = label;
  $('sessionState').parentElement.dataset.state = state;
  $('sessionDetail').textContent = detail;
  $('traceMode').textContent = {running:'RUNNING', complete:'COMPLETE', error:'ATTENTION', ready:'STANDBY', checking:'CHECKING'}[state] || 'STANDBY';
}
function observeProgress(event) {
  if (event.event === 'progress') {
    const turn = event.message.match(/第\s*(\d+)\s*轮/);
    if (turn) { $('modelTurns').textContent = turn[1]; setPhase('phaseReason'); }
  }
  if (event.event === 'tool_start') {
    setPhase('phaseObserve');
    document.querySelectorAll('.router-node').forEach((node) => node.classList.toggle('observing', node.id === `router${event.device}`));
  }
  if (event.event === 'tool_result') {
    completedTools += 1;
    $('toolCount').textContent = String(completedTools);
    $('toolDetail').textContent = `已接收 ${completedTools} 次设备观察结果`;
    document.querySelectorAll('.router-node').forEach((node) => node.classList.remove('observing'));
  }
}

function now() { return new Date().toLocaleTimeString('zh-CN', { hour12: false }); }
function addTrace(message, state = '') {
  const line = document.createElement('div'); line.className = `trace-line ${state}`;
  const time = document.createElement('span'); time.className = 'trace-time'; time.textContent = now();
  const dot = document.createElement('span'); dot.className = 'trace-dot';
  const text = document.createElement('span'); text.textContent = message;
  line.append(time, dot, text); $('traceLog').append(line); $('traceLog').scrollTop = $('traceLog').scrollHeight;
}
function setBusy(value) {
  busy = value;
  for (const id of ['diagnoseButton', 'question', 'imageInput', 'removeFile', 'openSettings', 'diagnosisKind', 'sourceDevice', 'targetIp', 'checkEnsp', 'faultType', 'injectFault', 'recoverFault']) $(id).disabled = value;
  updateFaultControls();
  $('spinner').classList.toggle('hidden', !value);
  document.body.dataset.running = String(value);
  $('traceMode').classList.toggle('live', value);
}
function setFile(file) {
  if (!file || busy) return;
  if ($('diagnosisKind').value === 'live') { addTrace('截图分析请先切换到“材料分析”入口', 'error'); return; }
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type)) { addTrace('仅支持 PNG、JPG、WEBP 图片', 'error'); return; }
  if (file.size > 5 * 1024 * 1024) { addTrace('截图不能超过 5 MB', 'error'); return; }
  selectedFile = file;
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = URL.createObjectURL(file);
  $('imagePreview').src = previewUrl; $('imagePreview').classList.remove('hidden');
  $('fileName').textContent = `${file.name} · ${(file.size / 1024).toFixed(0)} KB`;
  $('filePreview').classList.remove('hidden');
}
function removeFile() {
  selectedFile = null; $('imageInput').value = '';
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = null; $('imagePreview').removeAttribute('src');
  $('imagePreview').classList.add('hidden'); $('filePreview').classList.add('hidden');
}
$('dropzone').addEventListener('click', (event) => { if (!busy && !event.target.closest('button')) $('imageInput').click(); });
$('dropzone').addEventListener('keydown', (event) => { if (!busy && ['Enter', ' '].includes(event.key)) { event.preventDefault(); $('imageInput').click(); } });
$('imageInput').addEventListener('change', () => setFile($('imageInput').files[0]));
for (const name of ['dragenter', 'dragover']) $('dropzone').addEventListener(name, (event) => { event.preventDefault(); if (!busy) $('dropzone').classList.add('drag'); });
for (const name of ['dragleave', 'drop']) $('dropzone').addEventListener(name, (event) => { event.preventDefault(); $('dropzone').classList.remove('drag'); });
$('dropzone').addEventListener('drop', (event) => setFile(event.dataTransfer.files[0]));
$('removeFile').addEventListener('click', (event) => { event.stopPropagation(); removeFile(); });
document.addEventListener('paste', (event) => {
  if ($('settingsDialog').open) return;
  const image = [...(event.clipboardData?.items || [])].find((item) => item.type.startsWith('image/'));
  if (image) { event.preventDefault(); setFile(image.getAsFile()); }
});
function fileAsDataUrl(file) { return new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = () => reject(new Error('截图读取失败')); reader.readAsDataURL(file); }); }
function fillList(id, values, emptyText = '未提取到明确内容') {
  $(id).replaceChildren();
  (values.length ? values : [emptyText]).forEach((value) => { const item = document.createElement('li'); item.textContent = value; $(id).append(item); });
}
function renderResult(result) {
  lastResult = result;
  setPhase('phaseResult');
  $('elapsedTime').textContent = (result.elapsed_ms / 1000).toFixed(1);
  const insufficient = result.diagnosis?.diagnosis_status === 'NEED_MORE_DATA';
  setSession(insufficient ? 'error' : 'complete', insufficient ? '待补充证据' : '诊断已完成', result.execution_mode === 'ai_live_console' ? '已保存工具轨迹与设备原始回显' : '输入材料分析完成 · 未探测设备');
  if (result.execution_mode === 'ai_live_console') {
    $('modelTurns').textContent = String(result.turns ?? '—');
    $('toolCount').textContent = String(result.command_trace.length);
    $('toolDetail').textContent = `成功 ${result.command_trace.filter((item) => item.success).length} / ${result.command_trace.length} 次实际观察`;
  }
  if (result.execution_mode === 'ai_live_console') { renderLiveResult(result); return; }
  $('resultTitle').textContent = result.title; $('resultSummary').textContent = result.summary;
  $('limitations').textContent = `${result.limitations} 本入口仅分析输入材料，未执行实时设备探测。`;
  fillList('factsList', result.observed_facts); fillList('checksList', result.next_checks, '请补充现场信息');
  $('causesList').replaceChildren();
  const causes = result.likely_causes.length ? result.likely_causes : [{cause: '信息不足', reason: '请补充现场证据。'}];
  causes.forEach((cause) => { const card = document.createElement('div'); card.className = 'cause-card'; const title = document.createElement('strong'); title.textContent = cause.cause; const detail = document.createElement('small'); detail.textContent = cause.reason; card.append(title, detail); $('causesList').append(card); });
  $('resultBadge').textContent = result.execution_mode === 'demo' ? 'LOCAL DEMO · 示例结果' : 'BAILIAN API · 模型返回';
  $('resultMeta').textContent = `模型：${result.model} · 耗时：${(result.elapsed_ms / 1000).toFixed(1)} 秒 · 设备操作：0`;
  $('resultPanel').classList.remove('hidden'); $('resultPanel').scrollIntoView({behavior: 'smooth', block: 'start'});
}
function renderLiveResult(report) {
  const diagnosis = report.diagnosis;
  const status = diagnosis.diagnosis_status;
  const names = {INTERFACE_DOWN:'接口关闭 / 链路异常', ROUTE_MISSING:'路由缺失', ARP_UNRESOLVED:'ARP 解析失败', NEXT_HOP_UNREACHABLE:'下一跳不可达'};
  const normal = status === 'NORMAL'; const complete = status === 'COMPLETED';
  const targetPings = report.command_trace.filter((item) => item.action === 'RUN_PING' && item.device === report.source_device && item.command === `ping ${report.target_ip}` && item.success);
  const lossRecorded = targetPings.some((item) => item.facts.packet_loss > 0);
  $('resultTitle').textContent = normal ? (lossRecorded ? '目标可达（含丢包记录）' : '本次连通性探测正常') : complete ? (names[diagnosis.fault_type] || diagnosis.fault_type) : '证据不足，暂不能定位';
  $('resultSummary').textContent = normal ? `${report.source_device} 到 ${report.target_ip} 的本次探测可达。` : complete ? `故障设备：${diagnosis.fault_device}；接口：${diagnosis.fault_interface || '不适用'}。结论通过现有 Harness 的证据校验。` : '已保留实际观察和错误信息；不会把连接失败或证据缺失当作确定故障。';
  if (targetPings.length) $('resultSummary').textContent += ` 目标 ping 丢包率记录：${targetPings.map((item) => item.facts.packet_loss + '%').join(' → ')}。`;
  fillList('factsList', diagnosis.evidence || [], '未获得足够设备事实');
  $('causesList').replaceChildren();
  const card = document.createElement('div'); card.className = 'cause-card';
  card.textContent = normal ? '当前探测未确认网络故障；这不代表所有设备与业务均正常。' : complete ? `${diagnosis.fault_type} · ${diagnosis.fault_device}${diagnosis.fault_interface ? ' / ' + diagnosis.fault_interface : ''}` : '需要补充信息后继续检查。';
  $('causesList').append(card);
  const checks = normal ? ['如问题间歇出现，请在故障发生时再次诊断', '可更换目标 IP 检查其他业务路径'] : complete ? ['展开工具回显核对设备事实', '由实验负责人决定恢复操作，恢复后再次诊断'] : ['确认三台设备已启动且 Console 可响应', '查看工具错误，检查目标 IP 与拓扑配置'];
  fillList('checksList', checks);
  $('limitations').textContent = '此结果来自本次 eNSP 实时只读观察。诊断期间未写配置。若通过工作台注入了故障，故障会保留到点击恢复。' + (report.error ? ` 本次执行状态：${report.error}。` : '');
  $('resultBadge').textContent = normal ? 'LIVE · 本次探测正常' : complete ? 'LIVE · 已定位' : 'LIVE · 待补充证据';
  const successes = report.command_trace.filter((item) => item.success).length;
  $('resultMeta').textContent = `模型：${report.model} · ${(report.elapsed_ms / 1000).toFixed(1)}s · 只读检查：${report.command_trace.length}（成功 ${successes}）· 配置写入：0`;
  $('resultPanel').classList.remove('hidden'); $('resultPanel').scrollIntoView({behavior:'smooth', block:'start'});
}
function addToolCard(record) {
  $('toolPanel').classList.remove('hidden');
  const detail = document.createElement('details'); detail.className = 'tool-card'; detail.open = true;
  const title = document.createElement('summary'); title.textContent = `${record.success ? '✓' : '✕'} ${record.device} > ${record.command}`;
  const facts = document.createElement('div'); facts.className = 'tool-facts'; facts.textContent = record.success ? JSON.stringify(record.facts || {}) : record.error || '未收到有效结果';
  const raw = document.createElement('pre'); raw.textContent = (record.raw_output || '（未取得设备原始回显）').replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, '').replace(/---- More ----\s*/g, '');
  const reference = document.createElement('small'); reference.textContent = record.raw_ref ? `证据来源：${record.raw_ref}` : '来源：本次 Console 请求';
  detail.append(title, facts, raw, reference); $('toolCards').append(detail);
}
function updateDiagnosisKind() {
  const live = $('diagnosisKind').value === 'live';
  $('liveControls').classList.toggle('hidden', !live); $('dropzone').classList.toggle('hidden', live);
  $('question').placeholder = live ? '例如：检查 R1 到目标是否可达；如有故障，请依据实际回显定位。' : '描述看到的现象，或上传截图分析。';
  $('inputNote').textContent = live ? '◈ 诊断只读设备；演示故障仅限预设实验配置，可一键恢复。' : '◈ 材料会发送给百炼分析；此模式不探测设备，请勿提交凭据。';
  if (live) removeFile();
}
function updateFaultControls() {
  if (!$('faultStatus')) return;
  const active = settings?.active_fault;
  const live = $('diagnosisKind').value === 'live';
  if (active) $('faultType').value = active;
  $('faultStatus').textContent = active
    ? `当前保留故障：${active === 'INTERFACE_DOWN' ? 'R2 → R3 接口关闭' : 'R2 目标路由缺失'}。完成演示后请恢复。`
    : '基线连通且设备状态匹配时才会注入。';
  $('injectFault').disabled = busy || !live || Boolean(active);
  $('recoverFault').disabled = busy || !live;
  $('faultType').disabled = busy || !live;
}
$('diagnosisKind').addEventListener('change', updateDiagnosisKind);
$('injectFault').addEventListener('click', () => runFaultAction('inject'));
$('recoverFault').addEventListener('click', () => runFaultAction('recover'));
async function runFaultAction(action) {
  if (busy || $('diagnosisKind').value !== 'live') return;
  if (!settings?.ensp) { addTrace('当前后端尚未支持故障注入，请重启到新版诊断台', 'error'); return; }
  const faultType = $('faultType').value;
  const isInject = action === 'inject';
  setBusy(true);
  setSession('checking', isInject ? '正在注入故障' : '正在恢复故障', '仅操作预设的 R2 实验接口或静态路由');
  $('faultStatus').textContent = isInject ? '正在检查基线并验证设备回显…' : '正在执行恢复并验证设备回显…';
  addTrace(`${isInject ? '开始注入' : '开始恢复'} ${faultType}`, 'active');
  try {
    const payload = await jsonRequest('/api/fault', {action, fault_type: faultType});
    settings.active_fault = payload.active_fault;
    const result = payload.result;
    addTrace(result.message, 'done');
    $('toolCards').replaceChildren();
    if (result.baseline) addToolCard({device:'R1', command:result.baseline.command, success:result.baseline.success, facts:result.baseline.facts, raw_output:result.baseline.raw_output, error:result.baseline.error});
    const check = result.verification?.check;
    if (check) addToolCard({device:'R2', command:check.command, success:check.success, facts:check.facts, raw_output:check.raw_output, error:check.error});
    $('traceFooter').textContent = isInject ? 'FAULT INJECTED · VERIFIED' : 'FAULT RECOVERED · VERIFIED';
    setSession('complete', isInject ? '故障已注入' : '故障已恢复', result.message);
  } catch (error) {
    addTrace(error.message, 'error');
    $('traceFooter').textContent = 'FAULT ACTION NEEDS ATTENTION';
    setSession('error', '故障操作未完成', error.message);
    await refreshHealth().catch(() => {});
  } finally {
    setBusy(false);
  }
}
$('checkEnsp').addEventListener('click', async () => {
  if (!settings?.ensp) { addTrace('当前后端为旧版，请使用新版诊断台地址或重启本地服务', 'error'); return; }
  if (busy) return; setBusy(true);
  setSession('checking', '设备连接检测', '正在读取三台设备的接口摘要');
  $('enspStatus').textContent = '正在等待设备回显…'; addTrace('开始检查 R1 / R2 / R3 的 Console CLI', 'active');
  try {
    const result = await jsonRequest('/api/ensp/preflight', {});
    $('toolCards').replaceChildren();
    result.devices.forEach((device) => {
      addTrace(`${device.device}：${device.ready ? '已收到真实接口摘要' : device.error}`, device.ready ? 'done' : 'error');
      const node = $(`router${device.device}`); if (node) { node.classList.toggle('ready', device.ready); node.title = device.ready ? 'Console CLI 已响应' : 'Console 未就绪'; }
      addToolCard({device:device.device, command:'display ip interface brief', success:device.ready, raw_output:device.raw_output, error:device.error});
    });
    $('enspStatus').textContent = result.ready ? '3 台 Console CLI 均已响应' : '部分设备未就绪，查看日志';
    $('traceFooter').textContent = result.ready ? 'ENSP CLI READY' : 'ENSP CHECK INCOMPLETE';
    setSession(result.ready ? 'ready' : 'error', result.ready ? '设备连接就绪' : '设备连接异常', `Console 响应 ${result.devices.filter((device) => device.ready).length} / ${result.devices.length} · 尚未验证业务状态`);
  } catch (error) { $('enspStatus').textContent = error.message; addTrace(error.message, 'error'); setSession('error', '连接检测失败', '请查看执行轨迹中的错误信息'); }
  finally { setBusy(false); }
});
async function jsonRequest(path, body) {
  const response = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  const payload = await response.json();
  if (!response.ok || !payload.ok) throw new Error(payload.error || '请求失败');
  return payload;
}
async function refreshHealth() {
  const response = await fetch('/api/health'); if (!response.ok) throw new Error('本地服务连接失败');
  settings = await response.json();
  $('serviceStatus').textContent = settings.mode === 'demo' ? 'DEMO · 固定示例' : (settings.provider_verified ? `API 已验证 · ${settings.model}` : settings.provider_configured ? `API 已配置 · ${settings.model}` : 'API 待配置');
  updateFaultControls();
  return settings;
}
function showSettings() {
  if (!settings || busy) return;
  $('configMode').value = settings.mode; $('configBaseUrl').value = settings.base_url;
  $('configModel').value = settings.model; $('configVisionModel').value = settings.vision_model;
  $('configApiKey').value = ''; $('configMessage').textContent = settings.provider_configured ? '密钥已配置；留空可继续使用。' : '尚未配置密钥。';
  $('settingsDialog').showModal();
}
async function saveSettings(check) {
  if (!$('settingsForm').reportValidity()) return;
  $('saveSettings').disabled = true; $('checkProvider').disabled = true;
  $('configMessage').textContent = check ? '应用设置并发送连接测试请求…' : '正在应用…';
  try {
    await jsonRequest('/api/config', {mode: $('configMode').value, base_url: $('configBaseUrl').value, model: $('configModel').value, vision_model: $('configVisionModel').value, api_key: $('configApiKey').value, persist: $('configPersist').checked});
    $('configApiKey').value = '';
    if (check) {
      const result = await jsonRequest('/api/check-provider', {});
      $('configMessage').textContent = `连接成功 · ${result.model} · ${(result.elapsed_ms / 1000).toFixed(1)}s。${result.message}`;
      addTrace('API 连接测试成功，模型接口已响应', 'done');
    } else $('configMessage').textContent = '设置已应用。可以关闭此窗口开始诊断。';
  } catch (error) { $('configMessage').textContent = error.message; }
  finally { $('saveSettings').disabled = false; $('checkProvider').disabled = false; await refreshHealth().catch(() => {}); }
}
$('openSettings').addEventListener('click', showSettings);
$('closeSettings').addEventListener('click', () => { $('configApiKey').value = ''; $('settingsDialog').close(); });
$('settingsDialog').addEventListener('close', () => { $('configApiKey').value = ''; });
$('settingsForm').addEventListener('submit', (event) => { event.preventDefault(); saveSettings(false); });
$('checkProvider').addEventListener('click', () => saveSettings(true));
async function runDiagnosis() {
  if (busy) return;
  const question = $('question').value.trim();
  const live = $('diagnosisKind').value === 'live';
  if (live && !settings?.ensp) { addTrace('当前后端为旧版，尚未支持网页实时诊断；请打开新版服务地址', 'error'); return; }
  if (!live && !question && !selectedFile) { addTrace('请输入问题或上传截图', 'error'); $('question').focus(); return; }
  if (live && settings?.mode !== 'api') { addTrace('实时诊断需要切换到真实 API 模式', 'error'); showSettings(); return; }
  if (live && !/^(?:\d{1,3}\.){3}\d{1,3}$/.test($('targetIp').value.trim())) { addTrace('请输入合法目标 IPv4 地址', 'error'); $('targetIp').focus(); return; }
  if (settings?.mode === 'api' && !settings.provider_configured) { addTrace('请先在 API 设置中填写密钥', 'error'); showSettings(); return; }
  setBusy(true); $('resultPanel').classList.add('hidden'); lastResult = null;
  completedTools = 0; $('modelTurns').textContent = '—'; $('toolCount').textContent = '0'; $('elapsedTime').textContent = '0.0';
  $('toolDetail').textContent = live ? '等待实际设备观察结果' : '材料分析模式 · 不调用设备';
  setSession('running', '诊断执行中', live ? 'LLM Agent 正在调度只读诊断工具' : '模型正在分析输入材料'); setPhase('phaseInput');
  $('toolCards').replaceChildren(); $('toolPanel').classList.add('hidden');
  $('traceLog').replaceChildren(); addTrace('正在准备诊断请求…', 'active');
  const started = Date.now();
  const timer = setInterval(() => { $('traceFooter').textContent = `运行中 · ${Math.round((Date.now() - started) / 1000)}s`; if (!lastResult) $('elapsedTime').textContent = ((Date.now() - started) / 1000).toFixed(1); }, 1000);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), live ? 540000 : 330000);
  let receivedResult = false;
  try {
    const body = {question, stream: true};
    if (live) { body.diagnosis_kind = 'live'; body.source_device = $('sourceDevice').value; body.target_ip = $('targetIp').value.trim(); }
    if (selectedFile) { body.image_name = selectedFile.name; body.image_data = await fileAsDataUrl(selectedFile); }
    const response = await fetch('/api/diagnose', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body), signal: controller.signal});
    if (!response.ok) { const payload = await response.json(); throw new Error(payload.error || '诊断请求失败'); }
    const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = '';
    function eventLine(line) {
      if (!line.trim()) return;
      const event = JSON.parse(line);
      observeProgress(event);
      if (event.event === 'progress') addTrace(event.message, 'active');
      if (event.event === 'tool_start') addTrace(`正在执行 ${event.device} > ${event.command}`, 'active');
      if (event.event === 'tool_result') { addToolCard(event); addTrace(`${event.device} ${event.success ? '回显已解析：' + JSON.stringify(event.facts) : '检查失败：' + event.error}`, event.success ? 'done' : 'error'); }
      if (event.event === 'agent_action' && !event.trace.result.success) addTrace(`动作校验未通过：${event.trace.result.error}`, 'error');
      if (event.event === 'error') throw new Error(event.error);
      if (event.event === 'result') {
        receivedResult = true;
        (event.result.observed_facts || event.result.diagnosis?.evidence || []).slice(0, 2).forEach((fact) => addTrace(`发现：${fact}`, 'done'));
        addTrace(event.result.diagnosis?.diagnosis_status === 'NEED_MORE_DATA' ? '本轮结束：证据不足，已保留观察记录' : event.result.execution_mode === 'demo' ? '本地示例生成完成' : '模型诊断完成，结果已展示', 'done');
        renderResult(event.result);
      }
    }
    while (true) {
      const {done, value} = await reader.read();
      buffer += decoder.decode(value, {stream: !done});
      const lines = buffer.split('\n'); buffer = lines.pop(); lines.forEach(eventLine);
      if (done) break;
    }
    if (buffer.trim()) eventLine(buffer);
    if (!receivedResult) throw new Error('响应中断，未收到完整诊断结果，请重试');
    $('traceFooter').textContent = 'DIAGNOSIS COMPLETE';
  } catch (error) {
    addTrace(error.name === 'AbortError' ? '请求超时，请检查 API 状态后重试' : error.message, 'error');
    $('traceFooter').textContent = 'REQUEST FAILED';
    setSession('error', '执行未完成', '本轮未收到完整诊断，请检查错误记录');
    $('elapsedTime').textContent = ((Date.now() - started) / 1000).toFixed(1);
  } finally { clearInterval(timer); clearTimeout(timeout); setBusy(false); document.querySelectorAll('.router-node').forEach((node) => node.classList.remove('observing')); }
}
$('diagnoseButton').addEventListener('click', runDiagnosis);
$('question').addEventListener('keydown', (event) => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') runDiagnosis(); });
$('downloadResult').addEventListener('click', () => {
  if (!lastResult) return;
  const blob = new Blob([JSON.stringify(lastResult, null, 2)], {type: 'application/json'});
  const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = `netpath-diagnosis-${Date.now()}.json`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
refreshHealth().then(() => { addTrace(settings.mode === 'demo' ? '当前为本地示例模式，可在 API 设置切换' : settings.provider_configured ? '百炼配置已载入，可以开始诊断' : '请打开右上角 API 设置，配置百炼接口', 'done'); }).catch((error) => { $('serviceStatus').textContent = 'LOCAL SERVER OFFLINE'; addTrace(error.message, 'error'); });
updateDiagnosisKind();
