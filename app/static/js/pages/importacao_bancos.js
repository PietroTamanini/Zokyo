function externalImportPayload(extra = {}) {
  return {
    database_type: document.getElementById('external-db-type')?.value || 'firebird',
    database_path: document.getElementById('external-db-path')?.value || '',
    user: document.getElementById('external-db-user')?.value || 'SYSDBA',
    password: document.getElementById('external-db-password')?.value || '',
    charset: document.getElementById('external-db-charset')?.value || 'WIN1252',
    ...extra,
  };
}

function setExternalStatus(message, tone = 'blue') {
  const el = document.getElementById('external-status');
  if (!el) return;
  el.textContent = message;
  el.className = `note-block note-${tone === 'red' ?'amber' : tone}`;
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
  const r = await apiCall('POST', '/api/importacao/bancos/test', externalImportPayload());
  printExternalImport(r.data);
  if (r.ok && r.data?.success) setExternalStatus(`Conexão OK. Tabelas encontradas: ${r.data.table_count}.`, 'green');
  else setExternalStatus(r.data?.erro || 'Falha ao testar conexão.', 'red');
}

async function externalSchema() {
  setExternalStatus('Analisando estrutura...', 'sky');
  const r = await apiCall('POST', '/api/importacao/bancos/schema', externalImportPayload());
  printExternalImport(r.data);
  if (r.ok && r.data?.success) setExternalStatus(`Estrutura analisada. Tabelas encontradas: ${r.data.schema?.table_count || 0}.`, 'green');
  else setExternalStatus(r.data?.erro || 'Falha ao analisar a estrutura.', 'red');
}

async function externalMapping() {
  setExternalStatus('Carregando mapeamento...', 'sky');
  const r = await apiCall('POST', '/api/importacao/bancos/mapping', externalImportPayload());
  printExternalImport(r.data);
  if (r.ok && r.data?.success) setExternalStatus('Mapeamento carregado.', 'green');
  else setExternalStatus(r.data?.erro || 'Falha ao carregar mapeamento.', 'red');
}

async function externalLogs() {
  setExternalStatus('Carregando logs técnicos...', 'sky');
  const r = await apiCall('GET', '/api/importacao/bancos/logs');
  printExternalImport(r.data);
  if (r.ok && r.data?.success) setExternalStatus(`Logs encontrados: ${r.data.logs?.length || 0}.`, 'green');
  else setExternalStatus(r.data?.erro || 'Falha ao carregar logs.', 'red');
}

async function externalPreview() {
  setExternalStatus('Gerando prévia sem gravar dados...', 'sky');
  const r = await apiCall('POST', '/api/importacao/bancos/preview', externalImportPayload());
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
  const r = await apiCall('POST', '/api/importacao/bancos/commit', externalImportPayload({ confirm: true }));
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
