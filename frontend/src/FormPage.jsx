import React, { useState, useRef } from 'react';
import { Upload, Play, Loader2, CheckCircle2, XCircle, Terminal, RotateCcw, Plus, Trash2 } from 'lucide-react';
import axios from 'axios';
import PatchSection from './PatchSection.jsx';

const API_BASE = import.meta.env.VITE_API_BASE_URL
  ? `${import.meta.env.VITE_API_BASE_URL}/api`
  : 'http://127.0.0.1:5050/api';

const OS_OPTIONS = [
  { value: 'auto', label: 'Auto' },
  { value: 'linux', label: 'Linux' },
  { value: 'hp', label: 'HP-UX' },
  { value: 'aix', label: 'AIX' },
  { value: 'sunos', label: 'SunOS' },
];

function UploadArea({ state, onFileChange, disabled }) {
  const ref = useRef(null);

  const handleDrop = (e) => {
    e.preventDefault();
    if (disabled) return;
    const file = e.dataTransfer.files[0];
    if (file) onFileChange(file);
  };

  return (
    <div
      className={`upload-area${disabled ? ' upload-disabled' : ''}${state.uploadedPath ? ' upload-done' : ''}`}
      onClick={() => !disabled && ref.current?.click()}
      onDragOver={(e) => e.preventDefault()}
      onDrop={handleDrop}
    >
      <input ref={ref} type="file" accept=".tar,.gz,.tgz" onChange={(e) => { if (e.target.files[0]) onFileChange(e.target.files[0]); e.target.value = ''; }} style={{ display: 'none' }} disabled={disabled} />
      {state.uploading ? (
        <><Loader2 size={15} className="spinner" /> 업로드 중...</>
      ) : state.uploadedPath ? (
        <><CheckCircle2 size={15} style={{ color: 'var(--success-color)' }} /> {state.filename}</>
      ) : state.uploadError ? (
        <><XCircle size={15} style={{ color: 'var(--error-color)' }} /> 업로드 실패 — 다시 시도</>
      ) : (
        <><Upload size={15} /> tar 파일 업로드 / 드래그</>
      )}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div className="field-row">
      <label className="field-label">{label}</label>
      {children}
    </div>
  );
}

function ComponentCard({ compDef, state, onChange, onInstall, onPatch, onRollbackList, onRollback, onReset, onShowLog, onRemove }) {
  const [tab, setTab] = useState('install');
  const isInstalling = state.status === 'installing';
  const canInstall = state.uploadedPath && state.host && state.sshUser && state.sshPassword && !isInstalling;

  const handleFile = async (file) => {
    onChange({ uploading: true, uploadError: null, filename: file.name });
    const fd = new FormData();
    fd.append('file', file);
    try {
      const res = await axios.post(`${API_BASE}/upload`, fd);
      onChange({ uploading: false, uploadedPath: res.data.uploaded_path, filename: res.data.filename });
    } catch (err) {
      onChange({ uploading: false, uploadError: err.response?.data?.error || err.message });
    }
  };

  const statusColor = state.status === 'success' ? 'var(--success-color)' : state.status === 'error' ? 'var(--error-color)' : state.status === 'installing' ? '#d29922' : 'var(--border-color)';

  return (
    <div className="comp-card" style={{ borderColor: statusColor }}>
      <div className="comp-card-header">
        <span className="comp-label">{compDef.label}</span>
        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
          {state.log && (
            <button className="icon-btn" title="로그 보기" onClick={onShowLog}><Terminal size={14} /></button>
          )}
          {(state.status === 'success' || state.status === 'error') && (
            <button className="icon-btn" title="초기화" onClick={onReset}><RotateCcw size={14} /></button>
          )}
          {onRemove && (
            <button className="icon-btn" title="제거" onClick={onRemove} style={{ color: 'var(--error-color)' }}><Trash2 size={14} /></button>
          )}
          <div className="status-dot" style={{ background: statusColor }} />
        </div>
      </div>

      {/* ── 설치 / 패치 탭 ── */}
      <div className="panel-tabs">
        <button className={`panel-tab${tab === 'install' ? ' panel-tab--active' : ''}`} onClick={() => setTab('install')}>설치</button>
        <button className={`panel-tab${tab === 'patch'   ? ' panel-tab--active' : ''}`} onClick={() => setTab('patch')}>패치</button>
      </div>

      {tab === 'install' && (
        <>
          <UploadArea state={state} onFileChange={handleFile} disabled={isInstalling} />

          <div className="fields">
            <Field label="Server IP">
              <input type="text" value={state.host} onChange={e => onChange({ host: e.target.value })} placeholder="10.20.132.101" disabled={isInstalling} />
            </Field>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px' }}>
              <Field label="SSH Port">
                <input type="number" value={state.port} onChange={e => onChange({ port: e.target.value })} placeholder="22" disabled={isInstalling} />
              </Field>
              <Field label="OS">
                <select value={state.osChoice} onChange={e => onChange({ osChoice: e.target.value })} disabled={isInstalling}>
                  {OS_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </Field>
            </div>
            <Field label="SSH User">
              <input type="text" value={state.sshUser} onChange={e => onChange({ sshUser: e.target.value })} placeholder="MaxGauge" disabled={isInstalling} />
            </Field>
            <Field label="SSH Password">
              <input type="password" value={state.sshPassword} onChange={e => onChange({ sshPassword: e.target.value })} placeholder="••••••••" disabled={isInstalling} />
            </Field>
            {compDef.agentType !== 'daemon' && (
              <Field label="Install Path">
                <input type="text" value={state.installPath} onChange={e => onChange({ installPath: e.target.value })} placeholder="/home/MaxGauge" disabled={isInstalling} />
              </Field>
            )}
            {compDef.extraFields.map(f => {
              const dbType = state.extraFields['DATABASE_TYPE'] || 'oracle';
              if (f.oracleOnly && dbType !== 'oracle') return null;
              if (f.pgOnly    && dbType !== 'postgres') return null;
              return (
                <Field key={f.key} label={f.label}>
                  {f.type === 'select' ? (
                    <select
                      value={state.extraFields[f.key] || f.options[0]}
                      onChange={e => onChange({ extraFields: { ...state.extraFields, [f.key]: e.target.value } })}
                      disabled={isInstalling}
                    >
                      {f.options.map(o => <option key={o} value={o}>{o}</option>)}
                    </select>
                  ) : (
                    <input
                      type={f.type || 'text'}
                      value={state.extraFields[f.key] || ''}
                      onChange={e => onChange({ extraFields: { ...state.extraFields, [f.key]: e.target.value } })}
                      placeholder={f.placeholder}
                      disabled={isInstalling}
                    />
                  )}
                </Field>
              );
            })}

            {compDef.agentType === 'daemon' && (
              <div className="updater-section">
                <label className="updater-checkbox-label">
                  <input
                    type="checkbox"
                    checked={state.installUpdater || false}
                    onChange={e => onChange({ installUpdater: e.target.checked })}
                    disabled={isInstalling}
                  />
                  <span>업데이터 설치</span>
                </label>
                {state.installUpdater && (
                  <p className="updater-hint">
                    설치 전 <code>{state.extraFields['MXG_HOME'] || '$MXG_HOME'}/{state.extraFields['CONF_NAME'] || '$CONF_NAME'}/mxgrc</code>의
                    <code> MXG_UPDATER_ENABLED</code> 값을 <strong>1</strong>로 변경합니다.
                  </p>
                )}
              </div>
            )}
          </div>

          <button className="install-btn" onClick={onInstall} disabled={!canInstall}>
            {isInstalling ? <><Loader2 size={14} className="spinner" /> 설치 중...</> : <><Play size={14} /> 설치 실행</>}
          </button>

          {state.status === 'success' && <div className="card-msg success-msg"><CheckCircle2 size={13} /> 설치 완료</div>}
          {state.status === 'error'   && <div className="card-msg error-msg"><XCircle size={13} /> 설치 실패</div>}
        </>
      )}

      {tab === 'patch' && (
        <PatchSection compDef={compDef} state={state} onChange={onChange} onPatch={onPatch} onRollbackList={onRollbackList} onRollback={onRollback} />
      )}
    </div>
  );
}

function DgsS1Card({ compDef, state, onChange, onInstall, dgmState, onReset, onShowLog }) {
  const isInstalling = state.status === 'installing';
  const dgmReady = dgmState?.host && dgmState?.sshUser && dgmState?.sshPassword;
  const canInstall = state.uploadedPath && state.installPath && dgmReady && !isInstalling;

  const handleFile = async (file) => {
    onChange({ uploading: true, uploadError: null, filename: file.name });
    const fd = new FormData();
    fd.append('file', file);
    try {
      const res = await axios.post(`${API_BASE}/upload`, fd);
      onChange({ uploading: false, uploadedPath: res.data.uploaded_path, filename: res.data.filename });
    } catch (err) {
      onChange({ uploading: false, uploadError: err.response?.data?.error || err.message });
    }
  };

  const statusColor = state.status === 'success' ? 'var(--success-color)'
    : state.status === 'error' ? 'var(--error-color)'
    : state.status === 'installing' ? '#d29922'
    : 'var(--border-color)';

  return (
    <div className="comp-card" style={{ borderColor: statusColor }}>
      <div className="comp-card-header">
        <span className="comp-label">{compDef.label}</span>
        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
          {state.log && <button className="icon-btn" title="로그 보기" onClick={onShowLog}><Terminal size={14} /></button>}
          {(state.status === 'success' || state.status === 'error') && (
            <button className="icon-btn" title="초기화" onClick={onReset}><RotateCcw size={14} /></button>
          )}
          <div className="status-dot" style={{ background: statusColor }} />
        </div>
      </div>
      <div className="dgs-copy-info">
        DGM과 동일한 서버에 설치합니다
        {dgmState?.host ? ` — ${dgmState.host}` : ' (DGM 서버 정보를 먼저 입력하세요)'}
      </div>
      <UploadArea state={state} onFileChange={handleFile} disabled={isInstalling} />
      <div className="fields" style={{ marginTop: '8px' }}>
        <Field label="Install Path">
          <input type="text" value={state.installPath} onChange={e => onChange({ installPath: e.target.value })} placeholder="/home/MaxGauge" disabled={isInstalling} />
        </Field>
        {compDef.extraFields.map(f => (
          <Field key={f.key} label={f.label}>
            <input type="text" value={state.extraFields?.[f.key] || ''}
              onChange={e => onChange({ extraFields: { ...state.extraFields, [f.key]: e.target.value } })}
              placeholder={f.placeholder} disabled={isInstalling} />
          </Field>
        ))}
      </div>
      <button className="install-btn" onClick={onInstall} disabled={!canInstall}>
        {isInstalling ? <><Loader2 size={14} className="spinner" /> 설치 중...</> : <><Play size={14} /> 설치 실행</>}
      </button>
      {state.status === 'success' && <div className="card-msg success-msg"><CheckCircle2 size={13} /> 설치 완료</div>}
      {state.status === 'error'   && <div className="card-msg error-msg"><XCircle size={13} /> 설치 실패</div>}
    </div>
  );
}

function DgsCopyCard({ compDef, state, onChange, onAddDgs, onReset, onShowLog, onRemove }) {
  const isInstalling = state.status === 'installing';
  const canCreate = state.host && state.sshUser && state.sshPassword && state.installPath &&
    state.extraFields?.DG_NAME && state.extraFields?.GATHER_PORT && state.extraFields?.OBS1_KEYWORD2 &&
    !isInstalling;

  const statusColor = state.status === 'success' ? 'var(--success-color)'
    : state.status === 'error' ? 'var(--error-color)'
    : state.status === 'installing' ? '#d29922'
    : 'var(--border-color)';

  return (
    <div className="comp-card" style={{ borderColor: statusColor }}>
      <div className="comp-card-header">
        <span className="comp-label">{compDef.label}</span>
        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
          {state.log && <button className="icon-btn" title="로그 보기" onClick={onShowLog}><Terminal size={14} /></button>}
          {(state.status === 'success' || state.status === 'error') && (
            <button className="icon-btn" title="초기화" onClick={onReset}><RotateCcw size={14} /></button>
          )}
          {onRemove && (
            <button className="icon-btn" title="제거" onClick={onRemove} style={{ color: 'var(--error-color)' }}><Trash2 size={14} /></button>
          )}
          <div className="status-dot" style={{ background: statusColor }} />
        </div>
      </div>

      <div className="dgs-copy-info">S1이 설치된 경로를 입력하면 복사본으로 생성됩니다</div>

      <div className="fields" style={{ marginTop: '8px' }}>
        <Field label="Server IP">
          <input type="text" value={state.host} onChange={e => onChange({ host: e.target.value })} placeholder="10.20.132.101" disabled={isInstalling} />
        </Field>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px' }}>
          <Field label="SSH Port">
            <input type="number" value={state.port} onChange={e => onChange({ port: e.target.value })} placeholder="22" disabled={isInstalling} />
          </Field>
          <Field label="OS">
            <select value={state.osChoice} onChange={e => onChange({ osChoice: e.target.value })} disabled={isInstalling}>
              {[{value:'auto',label:'Auto'},{value:'linux',label:'Linux'},{value:'hp',label:'HP-UX'},{value:'aix',label:'AIX'},{value:'sunos',label:'SunOS'}].map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </Field>
        </div>
        <Field label="SSH User">
          <input type="text" value={state.sshUser} onChange={e => onChange({ sshUser: e.target.value })} placeholder="MaxGauge" disabled={isInstalling} />
        </Field>
        <Field label="SSH Password">
          <input type="password" value={state.sshPassword} onChange={e => onChange({ sshPassword: e.target.value })} placeholder="••••••••" disabled={isInstalling} />
        </Field>
        <Field label="S1 Install Path">
          <input type="text" value={state.installPath} onChange={e => onChange({ installPath: e.target.value })} placeholder="/home/MaxGauge" disabled={isInstalling} />
        </Field>
        <Field label="DGM Install Path">
          <input type="text" value={state.dgmInstallPath || ''} onChange={e => onChange({ dgmInstallPath: e.target.value })} placeholder="/home/MaxGauge" disabled={isInstalling} />
        </Field>
        {compDef.extraFields.map(f => (
          <Field key={f.key} label={f.label}>
            <input type="text" value={state.extraFields?.[f.key] || ''}
              onChange={e => onChange({ extraFields: { ...state.extraFields, [f.key]: e.target.value } })}
              placeholder={f.placeholder} disabled={isInstalling} />
          </Field>
        ))}
      </div>

      <button className="install-btn" onClick={onAddDgs} disabled={!canCreate}>
        {isInstalling ? <><Loader2 size={14} className="spinner" /> 생성 중...</> : <><Play size={14} /> 생성 실행</>}
      </button>

      {state.status === 'success' && <div className="card-msg success-msg"><CheckCircle2 size={13} /> 생성 완료</div>}
      {state.status === 'error'   && <div className="card-msg error-msg"><XCircle size={13} /> 생성 실패</div>}
    </div>
  );
}

const BATCH_KEYS_FIXED = ['rts', 'dgm', 'pjs'];

function isComponentReady(comp, states) {
  const s = states[comp.key];
  if (!s) return false;
  if (comp.key.startsWith('dgs_'))
    return !!(s.host && s.sshUser && s.sshPassword && s.installPath
      && s.extraFields?.DG_NAME && s.extraFields?.GATHER_PORT && s.extraFields?.OBS1_KEYWORD2);
  return !!(s.uploadedPath && s.host && s.sshUser && s.sshPassword);
}

function BatchInstallBar({ components, states, onInstallAll }) {
  const targets = components.filter(c => BATCH_KEYS_FIXED.includes(c.key) || c.key.startsWith('dgs_'));
  const isAnyInstalling = targets.some(c => states[c.key]?.status === 'installing');
  const readyCount = targets.filter(c => isComponentReady(c, states)).length;

  return (
    <div className="batch-bar">
      <div className="batch-chips">
        {targets.map(comp => {
          const s = states[comp.key];
          const ready = isComponentReady(comp, states);
          const st = s.status;
          return (
            <div key={comp.key} className={`batch-chip${st === 'installing' ? ' batch-chip--installing' : st === 'success' ? ' batch-chip--success' : st === 'error' ? ' batch-chip--error' : ready ? ' batch-chip--ready' : ''}`}>
              {st === 'installing' && <Loader2 size={11} className="spinner" />}
              {st === 'success'    && <CheckCircle2 size={11} />}
              {st === 'error'      && <XCircle size={11} />}
              <span>{comp.label}</span>
            </div>
          );
        })}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
          {readyCount}/{targets.length} 준비됨
        </span>
        <button
          className="install-btn"
          style={{ margin: 0, whiteSpace: 'nowrap' }}
          onClick={onInstallAll}
          disabled={isAnyInstalling || readyCount === 0}
        >
          {isAnyInstalling
            ? <><Loader2 size={14} className="spinner" /> 설치 중...</>
            : <><Play size={14} /> 순차 설치 실행</>}
        </button>
      </div>
    </div>
  );
}

export default function FormPage({ components, dgsInstances, addDgs, removeDgs, states, update, onInstall, onAddDgs, onPatch, onInstallAll, onRollbackList, onRollback }) {
  const [logPanel, setLogPanel] = useState({ key: null, text: '' });

  const handleInstall = async (compDef) => {
    const log = await onInstall(compDef, (text) => setLogPanel({ key: compDef.key, text }));
    setLogPanel({ key: compDef.key, text: log });
  };

  const compMap = Object.fromEntries(components.map(c => [c.key, c]));
  const rts = compMap['rts'];
  const pjs = compMap['pjs'];
  const dgm = compMap['dgm'];

  return (
    <>
      <BatchInstallBar components={components} states={states} onInstallAll={onInstallAll} />
      <div className="arch-layout">
        <section className="layer-section">
          <div className="layer-badge">Data Collection Layer</div>
          <ComponentCard compDef={rts} state={states.rts} onChange={p => update('rts', p)} onInstall={() => handleInstall(rts)} onPatch={() => onPatch(rts)} onRollbackList={() => onRollbackList(rts)} onRollback={() => onRollback(rts)} onReset={() => update('rts', { status: 'idle', log: '' })} onShowLog={() => setLogPanel({ key: 'rts', text: states.rts.log })} />
        </section>

        <section className="layer-section layer-section-ap">
          <div className="layer-badge">MaxGauge AP Server Layer</div>
          <div className="ap-grid">
            {[pjs, dgm].map(comp => (
              <ComponentCard key={comp.key} compDef={comp} state={states[comp.key]} onChange={p => update(comp.key, p)} onInstall={() => handleInstall(comp)} onPatch={() => onPatch(comp)} onRollbackList={() => onRollbackList(comp)} onRollback={() => onRollback(comp)} onReset={() => update(comp.key, { status: 'idle', log: '' })} onShowLog={() => setLogPanel({ key: comp.key, text: states[comp.key].log })} />
            ))}
            {dgsInstances.map(d => {
              const comp = compMap[d.key];
              if (!comp || !states[d.key]) return null;
              return (
                <DgsCopyCard
                  key={d.key}
                  compDef={comp}
                  state={states[d.key]}
                  onChange={p => update(d.key, p)}
                  onAddDgs={() => onAddDgs(comp, d.idx)}
                  onReset={() => update(d.key, { status: 'idle', log: '' })}
                  onShowLog={() => setLogPanel({ key: d.key, text: states[d.key].log })}
                  onRemove={() => removeDgs(d.key)}
                />
              );
            })}
          </div>
          <button className="dgs-add-btn" onClick={addDgs} style={{ marginTop: '10px' }}>
            <Plus size={13} /> DataGather_S 추가
          </button>
        </section>
      </div>

      {logPanel.key && (
        <div className="log-panel">
          <div className="log-panel-header">
            <Terminal size={15} />
            <span>{components.find(c => c.key === logPanel.key)?.label} — 설치 로그</span>
            <button className="icon-btn" onClick={() => setLogPanel({ key: null, text: '' })} style={{ marginLeft: 'auto' }}><XCircle size={15} /></button>
          </div>
          <pre className="log-content">{logPanel.text || 'Ready...'}</pre>
        </div>
      )}
    </>
  );
}
