function externalImportPayload(extra = {}) {
  const type = document.getElementById('external-db-type')?.value || 'firebird';
  const organizationId = document.getElementById('external-import-context')?.dataset.organizationId || '';
  return {
    database_type: type,
    database_path: document.getElementById('external-db-path')?.value || '',
    user: document.getElementById('external-db-user')?.value || (type === 'firebird' ? 'SYSDBA' : ''),
    password: document.getElementById('external-db-password')?.value || '',
    charset: document.getElementById('external-db-charset')?.value || (type === 'firebird' ? 'WIN1252' : 'utf-8-sig'),
    host: document.getElementById('external-db-host')?.value || '',
    port: document.getElementById('external-db-port')?.value || '',
    database: document.getElementById('external-db-name')?.value || '',
    profile: document.getElementById('external-profile')?.value || 'auto',
    delimiter: document.getElementById('external-delimiter')?.value || ',',
    sheet: document.getElementById('external-sheet')?.value || '',
    organization_id: organizationId,
    ...extra,
  };
}

function updateExternalSourceFields() {
  const type = document.getElementById('external-db-type')?.value || 'firebird';
  const network = ['mysql', 'mariadb'].includes(type);
  const files = ['csv', 'xlsx', 'zip'].includes(type);
  document.querySelectorAll('.external-connection-fields').forEach((el) => { el.hidden = !network; });
  document.querySelectorAll('.external-file-fields').forEach((el) => { el.hidden = !files; });
  const pathLabel = document.getElementById('external-path-label');
  const userLabel = document.getElementById('external-user-label');
  const path = document.getElementById('external-db-path');
  const user = document.getElementById('external-db-user');
  if (network) {
    if (pathLabel) pathLabel.textContent = 'Caminho local opcional (não usado na conexão)';
    if (userLabel) userLabel.textContent = 'Usuário do banco';
    if (path) path.placeholder = 'Opcional';
    if (user && user.value === 'SYSDBA') user.value = '';
  } else {
    if (pathLabel) pathLabel.textContent = 'Caminho do arquivo no servidor';
    if (userLabel) userLabel.textContent = 'Usuário';
    if (path) path.placeholder = type === 'firebird' ? 'C:\\Origem\\Banco.fdb' : '/dados/exportacao.csv';
    if (user && !user.value) user.value = type === 'firebird' ? 'SYSDBA' : '';
  }
  const charset = document.getElementById('external-db-charset');
  if (charset && !charset.value) charset.value = type === 'firebird' ? 'WIN1252' : 'utf-8-sig';
}

function setExternalStatus(message, tone = 'blue') {
  const el = document.getElementById('external-status');
  if (!el) return;
  el.textContent = message;
  el.className = `note-block note-${tone === 'red' ?'amber' : tone}`;
}

let externalUploadPromise = null;
async function ensureExternalUpload() {
  const file = document.getElementById('external-db-file')?.files?.[0];
  if (!file) return true;
  const path = document.getElementById('external-db-path')?.value || '';
  if (path.includes('/import_uploads/')) return true;
  if (externalUploadPromise) return externalUploadPromise;
  externalUploadPromise = (async () => {
    const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
    const form = new FormData();
    form.append('file', file);
    const organizationId = document.getElementById('external-import-context')?.dataset.organizationId || '';
    if (organizationId) form.append('organization_id', organizationId);
    const response = await fetch('/api/importacao/bancos/upload', {
      method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrf }, body: form,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.success) throw new Error(data.erro || 'Falha ao enviar o arquivo.');
    const input = document.getElementById('external-db-path');
    if (input) input.value = data.database_path;
    setExternalStatus(`Arquivo ${data.filename} enviado.`, 'green');
    return true;
  })().catch((error) => {
    externalUploadPromise = null;
    throw error;
  });
  return externalUploadPromise;
}

async function externalApi(method, url, payload) {
  try {
    if (method !== 'GET') await ensureExternalUpload();
    return await apiCall(method, url, payload);
  } catch (error) {
    return { ok: false, status: 400, data: { erro: error.message || 'Falha na operação.' } };
  }
}

function printExternalImport(data) {
  const out = document.getElementById('external-output');
  if (!out) return;
  const compact = data?.schema ?{
    success: data.success,
    dry_run: data.dry_run,
    connection: data.connection,
    selected_tables: data.selected_tables,
    counts: data.counts,
    detected_entities: data.schema.detected_entities,
    mapped_fields: data.mapped_fields,
    ignored_fields: data.ignored_fields,
    invalid_records: data.invalid_records,
    probable_duplicates: data.probable_duplicates,
    examples: data.examples,
    manual_confirmation: data.manual_confirmation,
    schema_table_count: data.schema.table_count,
  } : data;
  out.textContent = JSON.stringify(compact, null, 2);
}

async function externalTest() {
  setExternalStatus('Testando conexão...', 'sky');
  const r = await externalApi('POST', '/api/importacao/bancos/test', externalImportPayload());
  printExternalImport(r.data);
  if (r.ok && r.data?.success) setExternalStatus(`Conexão OK. Tabelas encontradas: ${r.data.table_count}.`, 'green');
  else setExternalStatus(r.data?.erro || 'Falha ao testar conexão.', 'red');
}

async function externalSchema() {
  setExternalStatus('Analisando estrutura...', 'sky');
  const r = await externalApi('POST', '/api/importacao/bancos/schema', externalImportPayload());
  printExternalImport(r.data);
  if (r.ok && r.data?.success) setExternalStatus(`Estrutura analisada. Tabelas encontradas: ${r.data.schema?.table_count || 0}.`, 'green');
  else setExternalStatus(r.data?.erro || 'Falha ao analisar a estrutura.', 'red');
}

async function externalMapping() {
  setExternalStatus('Carregando mapeamento...', 'sky');
  const r = await externalApi('POST', '/api/importacao/bancos/mapping', externalImportPayload());
  printExternalImport(r.data);
  if (r.ok && r.data?.success) setExternalStatus('Mapeamento carregado.', 'green');
  else setExternalStatus(r.data?.erro || 'Falha ao carregar mapeamento.', 'red');
}

async function externalLogs() {
  setExternalStatus('Carregando logs técnicos...', 'sky');
  const organizationId = document.getElementById('external-import-context')?.dataset.organizationId || '';
  const query = organizationId ? `?organization_id=${encodeURIComponent(organizationId)}` : '';
  const r = await apiCall('GET', `/api/importacao/bancos/logs${query}`);
  printExternalImport(r.data);
  if (r.ok && r.data?.success) setExternalStatus(`Logs encontrados: ${r.data.logs?.length || 0}.`, 'green');
  else setExternalStatus(r.data?.erro || 'Falha ao carregar logs.', 'red');
}

async function externalPreview() {
  setExternalStatus('Gerando prévia sem gravar dados...', 'sky');
  const r = await externalApi('POST', '/api/importacao/bancos/preview', externalImportPayload());
  printExternalImport(r.data);
  const btn = document.getElementById('external-commit-btn');
  if (r.ok && r.data?.success) {
    setExternalStatus('Prévia gerada. Revise duplicados, inválidos e confirmações manuais antes da gravação.', 'green');
    if (btn) btn.disabled = false;
  } else {
    setExternalStatus(r.data?.erro || 'Falha ao gerar a prévia.', 'red');
    if (btn) btn.disabled = true;
  }
}

async function externalCommit() {
  if (!confirm('Confirmar importação real no MySQL? Essa ação cria dados novos e não salva a senha de origem.')) return;
  setExternalStatus('Importando dados confirmados...', 'sky');
  const r = await externalApi('POST', '/api/importacao/bancos/commit', externalImportPayload({ confirm: true }));
  printExternalImport(r.data);
  if (r.ok && r.data?.success) setExternalStatus('Importação concluída. Confira o log técnico em instance/import_logs.', 'green');
  else setExternalStatus(r.data?.erro || 'Falha ao importar.', 'red');
}

document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-action]');
  if (!el) return;
  const action = el.getAttribute('data-action');
  if (action === 'external-test') return externalTest();
  if (action === 'external-schema') return externalSchema();
  if (action === 'external-mapping') return externalMapping();
  if (action === 'external-logs') return externalLogs();
  if (action === 'external-preview') return externalPreview();
  if (action === 'external-commit') return externalCommit();
});

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('external-db-type')?.addEventListener('change', updateExternalSourceFields);
  updateExternalSourceFields();
});
