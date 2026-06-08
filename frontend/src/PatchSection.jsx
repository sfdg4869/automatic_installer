import React, { useRef } from 'react';
import axios from 'axios';
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Loader2,
  RefreshCw,
  RotateCcw,
  Terminal,
  Upload,
  Wrench,
  XCircle,
} from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE_URL
  ? `${import.meta.env.VITE_API_BASE_URL}/api`
  : 'http://127.0.0.1:5050/api';

function getSearchRoot(compDef, state) {
  if (compDef.agentType === 'daemon') {
    const mxgHome = state.extraFields?.MXG_HOME || '';
    const confName = state.extraFields?.CONF_NAME || '';
    if (!mxgHome) return '';
    return confName ? `${mxgHome}/${confName}` : mxgHome;
  }
  return state.installPath || '';
}

function patchStatusLabel(status) {
  if (status === 'patching') return 'Running';
  if (status === 'success') return 'Done';
  if (status === 'error') return 'Error';
  return '';
}

export default function PatchSection({ compDef, state, onChange, onPatch, onRollbackList, onRollback }) {
  const fileRef = useRef(null);
  const isPatching = state.patchStatus === 'patching';
  const searchRoot = getSearchRoot(compDef, state);
  const canPatch = state.patchUploadedPath && state.host && state.sshUser && state.sshPassword && searchRoot && !isPatching;

  const isRollbackLoading = state.rollbackStatus === 'loading';
  const isRollbackRunning = state.rollbackStatus === 'running';
  const canRollbackList = state.host && state.sshUser && state.sshPassword && searchRoot && !isRollbackLoading && !isRollbackRunning;
  const canRollback = state.rollbackBackups && Object.keys(state.rollbackBackups).length > 0 && !isRollbackRunning;
  const recentJobs = state.rollbackJobs || [];

  const handleHistoryChange = async (jobId) => {
    onChange({
      rollbackJob: recentJobs.find((job) => job.job_id === jobId) || null,
      rollbackBackups: null,
      rollbackSelectedDate: {},
    });
    await onRollbackList(jobId);
  };

  const handleFile = async (file) => {
    onChange({ patchUploading: true, patchUploadError: null, patchFilename: file.name });
    const fd = new FormData();
    fd.append('file', file);
    try {
      const res = await axios.post(`${API_BASE}/upload`, fd);
      onChange({ patchUploading: false, patchUploadedPath: res.data.uploaded_path, patchFilename: res.data.filename });
    } catch (err) {
      onChange({ patchUploading: false, patchUploadError: err.response?.data?.error || err.message });
    }
  };

  const statusColor = state.patchStatus === 'success'
    ? 'var(--success-color)'
    : state.patchStatus === 'error'
      ? 'var(--error-color)'
      : state.patchStatus === 'patching'
        ? '#d29922'
        : 'var(--border-color)';

  return (
    <div className="patch-section">
      <button
        className="patch-toggle"
        onClick={() => onChange({ patchOpen: !state.patchOpen })}
        style={{ borderColor: state.patchOpen ? 'var(--accent-color)' : undefined }}
      >
        <Wrench size={13} />
        <span>Patch</span>
        {state.patchStatus !== 'idle' && (
          <span className="patch-status-badge" style={{ background: statusColor }}>
            {patchStatusLabel(state.patchStatus)}
          </span>
        )}
        {state.patchOpen
          ? <ChevronUp size={13} style={{ marginLeft: 'auto' }} />
          : <ChevronDown size={13} style={{ marginLeft: 'auto' }} />}
      </button>

      {state.patchOpen && (
        <div className="patch-body">
          <div className="patch-root-info">
            <span className="patch-root-label">Search Root</span>
            <code className="patch-root-path">{searchRoot || '(enter MXG_HOME or Install Path first)'}</code>
          </div>

          <div
            className={`upload-area${state.patchUploadedPath ? ' upload-done' : ''}${state.patchUploading ? ' upload-disabled' : ''}`}
            onClick={() => !isPatching && fileRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              if (!isPatching && e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
            }}
          >
            <input
              ref={fileRef}
              type="file"
              accept=".tar,.gz,.tgz,.zip,.jar"
              style={{ display: 'none' }}
              disabled={isPatching}
              onChange={(e) => {
                if (e.target.files[0]) handleFile(e.target.files[0]);
                e.target.value = '';
              }}
            />
            {state.patchUploading ? (
              <><Loader2 size={14} className="spinner" /> Uploading...</>
            ) : state.patchUploadedPath ? (
              <><CheckCircle2 size={14} style={{ color: 'var(--success-color)' }} /> {state.patchFilename}</>
            ) : (
              <><Upload size={14} /> Upload patch file (tar / zip / jar)</>
            )}
          </div>

          {state.patchUploadError && (
            <div style={{ color: 'var(--error-color)', fontSize: '0.72rem' }}>{state.patchUploadError}</div>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
            <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
              Backup suffix (leave blank to auto-generate a date-based suffix)
            </label>
            <input
              type="text"
              value={state.patchSuffix || ''}
              onChange={(e) => onChange({ patchSuffix: e.target.value })}
              placeholder={(() => {
                const d = new Date();
                return `bak${String(d.getFullYear()).slice(2)}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
              })()}
              disabled={isPatching}
              style={{ fontSize: '0.8rem', padding: '4px 8px' }}
            />
          </div>

          <button className="install-btn" style={{ background: canPatch ? '#b45309' : undefined }} onClick={onPatch} disabled={!canPatch}>
            {isPatching ? <><Loader2 size={13} className="spinner" /> Running patch...</> : <><Wrench size={13} /> Run Patch</>}
          </button>

          {state.patchStatus === 'success' && (
            <div className="card-msg success-msg"><CheckCircle2 size={12} /> Patch completed</div>
          )}
          {state.patchStatus === 'error' && (
            <div className="card-msg error-msg"><XCircle size={12} /> Patch failed</div>
          )}

          {state.patchLog && (
            <div>
              <div className="diag-log-label" style={{ marginTop: '8px' }}>
                <Terminal size={11} /> Patch log
              </div>
              <pre className="log-content" style={{ maxHeight: '160px', fontSize: '0.75rem' }}>{state.patchLog}</pre>
            </div>
          )}

          <div style={{ borderTop: '1px solid var(--border-color)', marginTop: '10px', paddingTop: '10px' }}>
            <div className="diag-log-label" style={{ marginBottom: '6px' }}>
              <RotateCcw size={11} /> Rollback
            </div>

            <button
              className="install-btn"
              style={{ background: canRollbackList ? '#374151' : undefined, marginBottom: '6px' }}
              onClick={() => onRollbackList()}
              disabled={!canRollbackList}
            >
              {isRollbackLoading ? <><Loader2 size={13} className="spinner" /> Loading recent patch job...</> : <><RefreshCw size={13} /> Load Recent Patch Job</>}
            </button>

            {state.rollbackSource === 'history' && state.rollbackJob && (
              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: '6px' }}>
                Loaded from recent patch job {state.rollbackJob.job_id}
              </div>
            )}

            {recentJobs.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginBottom: '8px' }}>
                <label style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Recent patch jobs</label>
                <select
                  value={state.rollbackJob?.job_id || ''}
                  onChange={(e) => handleHistoryChange(e.target.value)}
                  disabled={isRollbackLoading || isRollbackRunning}
                  style={{ width: '100%', fontSize: '0.78rem', padding: '6px 8px', background: 'rgba(13, 17, 23, 0.6)', color: 'var(--text-main)', border: '1px solid var(--border-color)', borderRadius: '4px' }}
                >
                  {recentJobs.map((job) => (
                    <option key={job.job_id} value={job.job_id}>
                      {`${job.created_at} | ${job.archive_name || job.component_label} | ${job.backup_suffix}`}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {state.rollbackSource === 'scan' && (
              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: '6px' }}>
                Recent patch history was not found, so remote backup scan fallback was used.
              </div>
            )}

            {state.rollbackBackups && Object.keys(state.rollbackBackups).length === 0 && (
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '6px' }}>No backup files found.</div>
            )}

            {state.rollbackBackups && Object.keys(state.rollbackBackups).length > 0 && (
              <div style={{ marginBottom: '8px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {Object.entries(state.rollbackBackups).map(([origPath, entries]) => {
                  const displayName = entries[0]?.display_name || origPath.split('/').pop();
                  return (
                    <div key={origPath} style={{ background: 'rgba(13, 17, 23, 0.6)', border: '1px solid var(--border-color)', borderRadius: '6px', padding: '6px 8px' }}>
                      <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: '4px', wordBreak: 'break-all' }} title={origPath}>
                        {displayName}
                      </div>
                      <select
                        style={{ width: '100%', fontSize: '0.78rem', padding: '3px 6px', background: 'rgba(13, 17, 23, 0.6)', color: 'var(--text-main)', border: '1px solid var(--border-color)', borderRadius: '4px' }}
                        value={state.rollbackSelectedDate?.[origPath] || ''}
                        onChange={(e) => onChange({ rollbackSelectedDate: { ...state.rollbackSelectedDate, [origPath]: e.target.value } })}
                        disabled={isRollbackRunning}
                      >
                        {entries.map((entry) => (
                          <option key={entry.date} value={entry.date}>{entry.label}</option>
                        ))}
                      </select>
                    </div>
                  );
                })}
              </div>
            )}

            {state.rollbackBackups && Object.keys(state.rollbackBackups).length > 0 && (
              <button className="install-btn" style={{ background: canRollback ? '#7c3aed' : undefined }} onClick={() => onRollback()} disabled={!canRollback}>
                {isRollbackRunning ? <><Loader2 size={13} className="spinner" /> Rolling back...</> : <><RotateCcw size={13} /> Run Rollback</>}
              </button>
            )}

            {state.rollbackStatus === 'success' && (
              <div className="card-msg success-msg"><CheckCircle2 size={12} /> Rollback completed</div>
            )}
            {state.rollbackStatus === 'error' && (
              <div className="card-msg error-msg"><XCircle size={12} /> Rollback failed</div>
            )}

            {state.rollbackLog && (
              <div>
                <div className="diag-log-label" style={{ marginTop: '8px' }}>
                  <Terminal size={11} /> Rollback log
                </div>
                <pre className="log-content" style={{ maxHeight: '160px', fontSize: '0.75rem' }}>{state.rollbackLog}</pre>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
