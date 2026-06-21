function cplusPayload(extra = {}) {
  return {
    database_path: document.getElementById('cplus-path')?.value || '',
    user: document.getElementById('cplus-user')?.value || 'SYSDBA',
    password: document.getElementById('cplus-password')?.value || '',
    charset: document.getElementById('cplus-charset')?.value || 'WIN1252',
    ...extra,
  };
}

function setCplusStatus(message, tone = 'blue') {
  const el = document.getElementById('cplus-status');
  if (!el) return;
  el.textContent = message;
  el.className = `note-block note-${tone === 'red' ? 'amber' : tone}`;
}

function printCplus(data) {
  const out = document.getElementById('cplus-output');
  if (!out) return;
  const compact = data?.schema ? {
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

async function cplusTest() {
  setCplusStatus('Testando conexao...', 'sky');
  const r = await apiCall('POST', '/api/importacao/cplus/test', cplusPayload());
  printCplus(r.data);
  if (r.ok && r.data?.success) setCplusStatus(`Conexao OK. Tabelas encontradas: ${r.data.table_count}.`, 'green');
  else setCplusStatus(r.data?.erro || 'Falha ao testar conexao.', 'red');
}

async function cplusPreview() {
  setCplusStatus('Gerando preview sem gravar dados...', 'sky');
  const r = await apiCall('POST', '/api/importacao/cplus/preview', cplusPayload());
  printCplus(r.data);
  const btn = document.getElementById('cplus-commit-btn');
  if (r.ok && r.data?.success) {
    setCplusStatus('Preview gerado. Revise duplicados, invalidos e confirmacoes manuais antes do commit.', 'green');
    if (btn) btn.disabled = false;
  } else {
    setCplusStatus(r.data?.erro || 'Falha ao gerar preview.', 'red');
    if (btn) btn.disabled = true;
  }
}

async function cplusCommit() {
  if (!confirm('Confirmar importacao real no MySQL? Essa acao cria dados novos e nao salva a senha Firebird.')) return;
  setCplusStatus('Importando dados confirmados...', 'sky');
  const r = await apiCall('POST', '/api/importacao/cplus/commit', cplusPayload({ confirm: true }));
  printCplus(r.data);
  if (r.ok && r.data?.success) setCplusStatus('Importacao concluida. Confira o log tecnico em instance/import_logs.', 'green');
  else setCplusStatus(r.data?.erro || 'Falha ao importar.', 'red');
}

document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-action]');
  if (!el) return;
  const action = el.getAttribute('data-action');
  if (action === 'cplus-test') return cplusTest();
  if (action === 'cplus-preview') return cplusPreview();
  if (action === 'cplus-commit') return cplusCommit();
});
