import React, { useMemo, useRef, useState } from 'react';
import axios from 'axios';
import {
  CheckCircle2,
  Layers,
  Loader2,
  Play,
  RotateCcw,
  Terminal,
  Upload,
  X,
  XCircle,
} from 'lucide-react';
import PatchSection from './PatchSection.jsx';

const API_BASE = import.meta.env.VITE_API_BASE_URL
  ? `${import.meta.env.VITE_API_BASE_URL}/api`
  : 'http://127.0.0.1:5050/api';

const OS_OPTIONS = [
  { value: 'auto', label: 'Auto Detect' },
  { value: 'linux', label: 'Linux' },
  { value: 'hp', label: 'HP-UX' },
  { value: 'aix', label: 'AIX' },
  { value: 'sunos', label: 'SunOS' },
];

const VIRTUAL_DGS1_COMP = {
  key: 'dgs1',
  agentType: 'dgs',
  label: 'DataGather_S1',
  extraFields: [],
};

const BASE_CANVAS_HEIGHT = 820;
const DGS_GAP = 104;

const STATIC_NODES = {
  oracle: { x: 125, y: 178, w: 150, h: 86 },
  rts: { x: 96, y: 318, w: 220, h: 72 },
  obsd: { x: 80, y: 482, w: 128, h: 58 },
  sndf: { x: 130, y: 570, w: 150, h: 58 },
  file: { x: 270, y: 482, w: 120, h: 58 },
  pjs: { x: 472, y: 165, w: 375, h: 72 },
  dgm: { x: 472, y: 338, w: 375, h: 72 },
  dgs1: { x: 472, y: 500, w: 375, h: 92 },
  repo: { x: 575, y: 615, w: 170, h: 72 },
  rtm: { x: 955, y: 170, w: 240, h: 86 },
  pa: { x: 955, y: 338, w: 240, h: 86 },
};

function getNodeLayout(dgsInstances) {
  const extra = {};
  dgsInstances.forEach((d, index) => {
    extra[d.key] = {
      x: STATIC_NODES.dgs1.x,
      y: STATIC_NODES.dgs1.y + DGS_GAP * (index + 1),
      w: STATIC_NODES.dgs1.w,
      h: STATIC_NODES.dgs1.h,
    };
  });

  const totalExtra = dgsInstances.length * DGS_GAP;
  return {
    ...STATIC_NODES,
    ...extra,
    storage: {
      x: 470,
      y: STATIC_NODES.repo.y + totalExtra - 25,
      w: 380,
      h: 128,
    },
    repo: {
      ...STATIC_NODES.repo,
      y: STATIC_NODES.repo.y + totalExtra,
    },
    canvasHeight: BASE_CANVAS_HEIGHT + totalExtra,
  };
}

function statusColor(state) {
  if (state?.status === 'success') return '#26b98a';
  if (state?.status === 'error') return '#ff5362';
  if (state?.status === 'installing') return '#f59e0b';
  if (state?.uploadedPath) return '#4ea5ff';
  return '#d9e6f2';
}

function hostSubtitle(state, fallback = 'Click to configure') {
  return state?.host || fallback;
}

function extraSubtitle(id, state) {
  const extra = state?.extraFields || {};
  if (id === 'rts' && extra.CONF_NAME) return `conf: ${extra.CONF_NAME}`;
  if (id === 'pjs' && extra.PJS_PORT) return `svc: ${extra.PJS_PORT}`;
  if (id === 'dgm' && extra.GATHER_PORT) return `port: ${extra.GATHER_PORT}`;
  if (id === 'dgs1' && extra.GATHER_PORT) return `port: ${extra.GATHER_PORT}`;
  if (id.startsWith('dgs_') && extra.DG_NAME) return `name: ${extra.DG_NAME}`;
  return '';
}

function DiagramLinks({ layout, dgsInstances }) {
  const dgs1 = layout.dgs1;
  const repo = layout.repo;
  const canvasHeight = layout.canvasHeight;

  return (
    <svg className="preview-links" viewBox={`0 0 1280 ${canvasHeight}`} preserveAspectRatio="none">
      <defs>
        <marker id="greenArrow" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto">
          <path d="M0,0 L10,5 L0,10 Z" fill="#42d6ac" />
        </marker>
        <marker id="blueArrow" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto">
          <path d="M0,0 L10,5 L0,10 Z" fill="#4ea5ff" />
        </marker>
        <marker id="redArrow" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto">
          <path d="M0,0 L10,5 L0,10 Z" fill="#ff5362" />
        </marker>
        <marker id="purpleArrow" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto">
          <path d="M0,0 L10,5 L0,10 Z" fill="#9487ff" />
        </marker>
        <marker id="grayArrow" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto">
          <path d="M0,0 L10,5 L0,10 Z" fill="rgba(230,230,230,.68)" />
        </marker>
      </defs>

      <path className="green-line" d="M275 220 C340 215,395 190,472 190" />
      <path className="green-line" d="M200 264 L200 318" />
      <path className="green-line" d="M316 352 C370 284,395 205,472 190" />
      <path className="blue-line" d="M275 220 C335 250,395 305,472 371" />

      <path className="gray-line" d="M160 384 L160 482" />
      <path className="gray-line" d="M160 540 L160 570" />
      <path className="gray-line" d="M318 482 C305 445,294 405,290 384" />
      <path className="gray-line" d="M250 570 C280 545,300 515,318 482" />

      <path className="blue-line dash" d="M280 600 C345 575,400 535,472 532" />
      <path className="blue-line dash" d="M316 384 C368 440,413 500,472 532" />

      {dgsInstances.map((d, index) => {
        const topY = index === 0 ? dgs1.y + dgs1.h / 2 : layout[dgsInstances[index - 1].key].y + 32;
        const current = layout[d.key];
        return (
          <g key={d.key}>
            <path
              className="blue-line dash"
              d={`M660 ${topY} L660 ${current.y + 14}`}
            />
          </g>
        );
      })}

      <path className="red-line" d="M660 500 L660 404" />
      <path className="red-line" d="M660 338 L660 231" />
      <path className="red-line" d={`M660 ${dgs1.y + dgs1.h} L660 ${repo.y}`} />
      <path className="purple-line" d={`M745 ${repo.y + 10} C765 ${repo.y - 145},790 320,820 231`} />

      <path className="green-line" d="M847 198 C885 198,920 204,955 213" />
      <path className="red-line" d="M847 182 C885 182,920 182,955 182" />
      <path className="purple-line" d="M847 216 C890 260,920 315,955 381" />
    </svg>
  );
}

function StaticNode({ className, children }) {
  return <div className={className}>{children}</div>;
}

function InteractiveNode({ id, label, state, selected, layout, onSelect }) {
  const subtitle = hostSubtitle(state);
  const detail = extraSubtitle(id, state);
  const style = {
    left: `${layout.x}px`,
    top: `${layout.y}px`,
    width: `${layout.w}px`,
    height: `${layout.h}px`,
  };

  return (
    <button
      type="button"
      className={`preview-node preview-node--interactive${selected ? ' is-selected' : ''}`}
      style={style}
      onClick={() => onSelect(id)}
    >
      <span className="preview-node__title">{label}</span>
      <span className="preview-node__sub">{subtitle}</span>
      {detail ? <span className="preview-node__meta">{detail}</span> : null}
      <span className="preview-node__status" style={{ background: statusColor(state) }} />
    </button>
  );
}

function DiagramCanvas({ states, selected, onSelect, dgsInstances }) {
  const layout = useMemo(() => getNodeLayout(dgsInstances), [dgsInstances]);

  return (
    <div className="preview-canvas-shell">
      <div className="preview-canvas" style={{ height: `${layout.canvasHeight}px` }}>
        <h2 className="preview-title">MaxGauge Architecture</h2>
        <div className="preview-subtitle">Collection, AP server, and web client flow</div>

        <div className="preview-legend">
          <span><i className="dot" style={{ background: '#42d6ac' }} />Transfer</span>
          <span><i className="dot" style={{ background: '#4ea5ff' }} />Install / Auto create</span>
          <span><i className="dot" style={{ background: '#ff5362' }} />Reference</span>
          <span><i className="dot" style={{ background: '#9487ff' }} />Web query</span>
        </div>

        <div className="preview-layer left-layer"><div className="preview-layer-title">Data Collection Layer</div></div>
        <div className="preview-layer mid-layer"><div className="preview-layer-title">MaxGauge AP Server Layer</div></div>
        <div className="preview-layer right-layer"><div className="preview-layer-title">Web Client Layer</div></div>

        <DiagramLinks layout={layout} dgsInstances={dgsInstances} />

        <StaticNode className="preview-oracle">Oracle</StaticNode>

        <InteractiveNode id="rts" label="RTS" state={states.rts} selected={selected === 'rts'} layout={layout.rts} onSelect={onSelect} />
        <StaticNode className="preview-node preview-node--static preview-node--obsd">OBSD</StaticNode>
        <StaticNode className="preview-node preview-node--static preview-node--sndf">SNDF</StaticNode>
        <StaticNode className="preview-node preview-node--file">File</StaticNode>

        <InteractiveNode id="pjs" label="PlatformJS" state={states.pjs} selected={selected === 'pjs'} layout={layout.pjs} onSelect={onSelect} />
        <InteractiveNode id="dgm" label="DataGather_M" state={states.dgm} selected={selected === 'dgm'} layout={layout.dgm} onSelect={onSelect} />
        <InteractiveNode id="dgs1" label="DataGather_S1" state={states.dgm} selected={selected === 'dgs1'} layout={layout.dgs1} onSelect={onSelect} />

        {dgsInstances.map((d) => (
          <InteractiveNode
            key={d.key}
            id={d.key}
            label={d.label}
            state={states[d.key]}
            selected={selected === d.key}
            layout={layout[d.key]}
            onSelect={onSelect}
          />
        ))}

        <div
          className="preview-storage-layer"
          style={{
            left: `${layout.storage.x}px`,
            top: `${layout.storage.y}px`,
            width: `${layout.storage.w}px`,
            height: `${layout.storage.h}px`,
          }}
        >
          <div className="preview-storage-title">Data Storage Layer</div>
        </div>
        <div
          className="preview-node preview-node--repo"
          style={{
            left: `${layout.repo.x}px`,
            top: `${layout.repo.y}px`,
            width: `${layout.repo.w}px`,
            height: `${layout.repo.h}px`,
          }}
        >
          Repository
        </div>

        <StaticNode className="preview-node preview-node--green preview-node--rtm">Real-time Monitor</StaticNode>
        <StaticNode className="preview-node preview-node--purple preview-node--pa">Performance Analyzer</StaticNode>

        <div className="preview-note">Best captured around 90-100% zoom in browser or docs.</div>
      </div>
    </div>
  );
}

function DgsCopyPanel({ compDef, state, onChange, onAddDgs }) {
  const isInstalling = state.status === 'installing';
  const canCreate = state.host && state.sshUser && state.sshPassword && state.installPath &&
    state.extraFields?.DG_NAME && state.extraFields?.GATHER_PORT && state.extraFields?.OBS1_KEYWORD2 &&
    !isInstalling;

  return (
    <>
      <div className="dgs-copy-info">Create a new DataGather_S by copying from the S1 install path.</div>
      <div className="diag-fields">
        <div className="diag-field">
          <label>Server IP</label>
          <input type="text" value={state.host} onChange={(e) => onChange({ host: e.target.value })} placeholder="10.20.132.101" disabled={isInstalling} />
        </div>
        <div className="diag-grid-2">
          <div className="diag-field">
            <label>SSH Port</label>
            <input type="number" value={state.port} onChange={(e) => onChange({ port: e.target.value })} placeholder="22" disabled={isInstalling} />
          </div>
          <div className="diag-field">
            <label>OS</label>
            <select value={state.osChoice} onChange={(e) => onChange({ osChoice: e.target.value })} disabled={isInstalling}>
              {OS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
        </div>
        <div className="diag-field">
          <label>SSH User</label>
          <input type="text" value={state.sshUser} onChange={(e) => onChange({ sshUser: e.target.value })} placeholder="MaxGauge" disabled={isInstalling} />
        </div>
        <div className="diag-field">
          <label>SSH Password</label>
          <input type="password" value={state.sshPassword} onChange={(e) => onChange({ sshPassword: e.target.value })} placeholder="password" disabled={isInstalling} />
        </div>
        <div className="diag-field">
          <label>S1 Install Path</label>
          <input type="text" value={state.installPath} onChange={(e) => onChange({ installPath: e.target.value })} placeholder="/home/MaxGauge" disabled={isInstalling} />
        </div>
        <div className="diag-field">
          <label>DGM Install Path</label>
          <input type="text" value={state.dgmInstallPath || ''} onChange={(e) => onChange({ dgmInstallPath: e.target.value })} placeholder="/home/MaxGauge" disabled={isInstalling} />
        </div>
        {compDef.extraFields.map((f) => (
          <div className="diag-field" key={f.key}>
            <label>{f.label}</label>
            <input
              type="text"
              value={state.extraFields?.[f.key] || ''}
              onChange={(e) => onChange({ extraFields: { ...state.extraFields, [f.key]: e.target.value } })}
              placeholder={f.placeholder}
              disabled={isInstalling}
            />
          </div>
        ))}
      </div>

      <button className="install-btn" style={{ marginTop: '12px' }} onClick={onAddDgs} disabled={!canCreate}>
        {isInstalling ? <><Loader2 size={14} className="spinner" /> Creating...</> : <><Play size={14} /> Create Instance</>}
      </button>

      {state.status === 'success' && <div className="card-msg success-msg" style={{ marginTop: '8px' }}><CheckCircle2 size={13} /> Creation completed</div>}
      {state.status === 'error' && <div className="card-msg error-msg" style={{ marginTop: '8px' }}><XCircle size={13} /> Creation failed</div>}

      {state.log && (
        <div style={{ marginTop: '12px' }}>
          <div className="diag-log-label"><Terminal size={12} /> Log</div>
          <pre className="log-content" style={{ maxHeight: '180px', fontSize: '0.75rem' }}>{state.log}</pre>
        </div>
      )}
    </>
  );
}

function DgsS1PatchPanel({ state, onChange }) {
  const isBusy = state.status === 'installing' || state.patchStatus === 'patching' || state.rollbackStatus === 'loading' || state.rollbackStatus === 'running';

  return (
    <>
      <div className="dgs-copy-info">
        DataGather_S1 can be patched independently. Enter only the minimum server information needed for patch and rollback.
      </div>
      <div className="diag-fields">
        <div className="diag-field">
          <label>Server IP</label>
          <input type="text" value={state.host} onChange={(e) => onChange({ host: e.target.value })} placeholder="10.20.132.101" disabled={isBusy} />
        </div>
        <div className="diag-grid-2">
          <div className="diag-field">
            <label>SSH Port</label>
            <input type="number" value={state.port} onChange={(e) => onChange({ port: e.target.value })} placeholder="22" disabled={isBusy} />
          </div>
          <div className="diag-field">
            <label>OS</label>
            <select value={state.osChoice} onChange={(e) => onChange({ osChoice: e.target.value })} disabled={isBusy}>
              {OS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
        </div>
        <div className="diag-field">
          <label>SSH User</label>
          <input type="text" value={state.sshUser} onChange={(e) => onChange({ sshUser: e.target.value })} placeholder="MaxGauge" disabled={isBusy} />
        </div>
        <div className="diag-field">
          <label>SSH Password</label>
          <input type="password" value={state.sshPassword} onChange={(e) => onChange({ sshPassword: e.target.value })} placeholder="password" disabled={isBusy} />
        </div>
        <div className="diag-field">
          <label>S1 Install Path</label>
          <input type="text" value={state.installPath} onChange={(e) => onChange({ installPath: e.target.value })} placeholder="/home/MaxGauge" disabled={isBusy} />
        </div>
      </div>
    </>
  );
}

function ConfigPanel({ compDef, state, onChange, onInstall, onAddDgs, isDgsCopy, onPatch, onRollbackList, onRollback, onClose }) {
  const fileRef = useRef(null);
  const [tab, setTab] = useState('install');
  const isInstalling = state.status === 'installing';
  const canInstall = state.uploadedPath && state.host && state.sshUser && state.sshPassword && !isInstalling;
  const isAutoDgsS1 = compDef.key === 'dgs1';

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

  return (
    <div className="diag-panel diag-panel--preview">
      <div className="diag-panel-header">
        <div>
          <div className="diag-panel-comp-name">{compDef.label}</div>
          <div className="diag-panel-comp-type">
            {isDgsCopy ? 'Copy from S1' : `${compDef.agentType.toUpperCase()} install settings`}
          </div>
        </div>
        <div style={{ display: 'flex', gap: '6px' }}>
          {(state.status === 'success' || state.status === 'error') && (
            <button className="icon-btn" title="Reset" onClick={() => onChange({ status: 'idle', log: '' })}>
              <RotateCcw size={15} />
            </button>
          )}
          <button className="icon-btn" onClick={onClose}><X size={16} /></button>
        </div>
      </div>

      <div className="panel-tabs">
        <button className={`panel-tab${tab === 'install' ? ' panel-tab--active' : ''}`} onClick={() => setTab('install')}>Install</button>
        <button className={`panel-tab${tab === 'patch' ? ' panel-tab--active' : ''}`} onClick={() => setTab('patch')}>Patch</button>
      </div>

      {tab === 'install' ? (
        isDgsCopy ? (
          <DgsCopyPanel compDef={compDef} state={state} onChange={onChange} onAddDgs={onAddDgs} />
        ) : isAutoDgsS1 ? (
          <DgsS1PatchPanel state={state} onChange={onChange} />
        ) : (
          <>
            <div
              className={`diag-upload${state.uploadedPath ? ' diag-upload-done' : ''}${state.uploading ? ' diag-upload-busy' : ''}`}
              onClick={() => !isInstalling && fileRef.current?.click()}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (!isInstalling && e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
              }}
            >
              <input
                ref={fileRef}
                type="file"
                accept=".tar,.gz,.tgz"
                style={{ display: 'none' }}
                disabled={isInstalling}
                onChange={(e) => {
                  if (e.target.files[0]) handleFile(e.target.files[0]);
                  e.target.value = '';
                }}
              />
              {state.uploading ? (
                <><Loader2 size={16} className="spinner" /><span>Uploading package...</span></>
              ) : state.uploadedPath ? (
                <><CheckCircle2 size={16} style={{ color: 'var(--success-color)' }} /><span style={{ wordBreak: 'break-all' }}>{state.filename}</span></>
              ) : (
                <><Upload size={16} /><span>Select or drop a tar package</span></>
              )}
            </div>

            {state.uploadError && <div className="diag-error-text">{state.uploadError}</div>}

            <div className="diag-fields">
              <div className="diag-field">
                <label>Server IP</label>
                <input type="text" value={state.host} onChange={(e) => onChange({ host: e.target.value })} placeholder="10.20.132.101" disabled={isInstalling} />
              </div>
              <div className="diag-grid-2">
                <div className="diag-field">
                  <label>SSH Port</label>
                  <input type="number" value={state.port} onChange={(e) => onChange({ port: e.target.value })} placeholder="22" disabled={isInstalling} />
                </div>
                <div className="diag-field">
                  <label>OS</label>
                  <select value={state.osChoice} onChange={(e) => onChange({ osChoice: e.target.value })} disabled={isInstalling}>
                    {OS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>
              </div>
              <div className="diag-field">
                <label>SSH User</label>
                <input type="text" value={state.sshUser} onChange={(e) => onChange({ sshUser: e.target.value })} placeholder="MaxGauge" disabled={isInstalling} />
              </div>
              <div className="diag-field">
                <label>SSH Password</label>
                <input type="password" value={state.sshPassword} onChange={(e) => onChange({ sshPassword: e.target.value })} placeholder="password" disabled={isInstalling} />
              </div>
              {compDef.agentType !== 'daemon' && (
                <div className="diag-field">
                  <label>Install Path</label>
                  <input type="text" value={state.installPath} onChange={(e) => onChange({ installPath: e.target.value })} placeholder="/home/MaxGauge" disabled={isInstalling} />
                </div>
              )}
              {compDef.extraFields.map((f) => {
                const dbType = state.extraFields.DATABASE_TYPE || 'oracle';
                if (f.oracleOnly && dbType !== 'oracle') return null;
                if (f.pgOnly && dbType !== 'postgres') return null;
                return (
                  <div className="diag-field" key={f.key}>
                    <label>{f.label}</label>
                    {f.type === 'select' ? (
                      <select
                        value={state.extraFields[f.key] || f.options[0]}
                        onChange={(e) => onChange({ extraFields: { ...state.extraFields, [f.key]: e.target.value } })}
                        disabled={isInstalling}
                      >
                        {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
                      </select>
                    ) : (
                      <input
                        type={f.type || 'text'}
                        value={state.extraFields[f.key] || ''}
                        onChange={(e) => onChange({ extraFields: { ...state.extraFields, [f.key]: e.target.value } })}
                        placeholder={f.placeholder}
                        disabled={isInstalling}
                      />
                    )}
                  </div>
                );
              })}
            </div>

            <button className="install-btn" style={{ marginTop: '12px' }} onClick={onInstall} disabled={!canInstall}>
              {isInstalling ? <><Loader2 size={14} className="spinner" /> Installing...</> : <><Play size={14} /> Run Install</>}
            </button>

            {state.status === 'success' && <div className="card-msg success-msg" style={{ marginTop: '8px' }}><CheckCircle2 size={13} /> Install completed</div>}
            {state.status === 'error' && <div className="card-msg error-msg" style={{ marginTop: '8px' }}><XCircle size={13} /> Install failed</div>}

            {state.log && (
              <div style={{ marginTop: '12px' }}>
                <div className="diag-log-label"><Terminal size={12} /> Install log</div>
                <pre className="log-content" style={{ maxHeight: '180px', fontSize: '0.75rem' }}>{state.log}</pre>
              </div>
            )}
          </>
        )
      ) : (
        <PatchSection compDef={compDef} state={state} onChange={onChange} onPatch={onPatch} onRollbackList={onRollbackList} onRollback={onRollback} />
      )}
    </div>
  );
}

const BATCH_KEYS_FIXED = ['rts', 'dgm', 'pjs'];

function isComponentReady(comp, states) {
  const state = states[comp.key];
  if (!state) return false;
  if (comp.key.startsWith('dgs_')) {
    return !!(
      state.host &&
      state.sshUser &&
      state.sshPassword &&
      state.installPath &&
      state.extraFields?.DG_NAME &&
      state.extraFields?.GATHER_PORT &&
      state.extraFields?.OBS1_KEYWORD2
    );
  }
  return !!(state.uploadedPath && state.host && state.sshUser && state.sshPassword);
}

function BatchInstallBar({ components, states, onInstallAll }) {
  const targets = components.filter((c) => BATCH_KEYS_FIXED.includes(c.key) || c.key.startsWith('dgs_'));
  const isAnyInstalling = targets.some((c) => states[c.key]?.status === 'installing');
  const readyCount = targets.filter((c) => isComponentReady(c, states)).length;

  return (
    <div className="batch-bar batch-bar--preview">
      <div className="batch-chips">
        {targets.map((comp) => {
          const state = states[comp.key];
          const ready = isComponentReady(comp, states);
          const currentStatus = state.status;
          return (
            <div
              key={comp.key}
              className={`batch-chip${currentStatus === 'installing' ? ' batch-chip--installing' : currentStatus === 'success' ? ' batch-chip--success' : currentStatus === 'error' ? ' batch-chip--error' : ready ? ' batch-chip--ready' : ''}`}
            >
              {currentStatus === 'installing' && <Loader2 size={11} className="spinner" />}
              {currentStatus === 'success' && <CheckCircle2 size={11} />}
              {currentStatus === 'error' && <XCircle size={11} />}
              <span>{comp.label}</span>
            </div>
          );
        })}
      </div>
      <div className="batch-bar__action">
        <span className="batch-bar__count">{readyCount}/{targets.length} ready</span>
        <button className="install-btn" style={{ margin: 0, whiteSpace: 'nowrap' }} onClick={onInstallAll} disabled={isAnyInstalling || readyCount === 0}>
          {isAnyInstalling ? <><Loader2 size={14} className="spinner" /> Installing...</> : <><Layers size={14} /> Install Ready Items</>}
        </button>
      </div>
    </div>
  );
}

export default function DiagramPage({ components, dgsInstances, addDgs, removeDgs, states, update, onInstall, onAddDgs, onPatch, onInstallAll, onRollbackList, onRollback }) {
  const [selected, setSelected] = useState(null);
  const compDefs = {
    ...Object.fromEntries(components.map((c) => [c.key, c])),
    dgs1: VIRTUAL_DGS1_COMP,
  };
  const selectedDgsInst = selected ? dgsInstances.find((d) => d.key === selected) : null;
  const isDgsCopy = !!selectedDgsInst;

  const handleInstall = async () => {
    if (!selected) return;
    await onInstall(compDefs[selected]);
  };

  const handleAddDgs = async () => {
    if (!selectedDgsInst) return;
    await onAddDgs(compDefs[selected], selectedDgsInst.idx);
  };

  const handlePatch = async () => {
    if (!selected) return;
    await onPatch(compDefs[selected]);
  };

  const handleRollbackList = async (jobId = null) => {
    if (!selected) return;
    await onRollbackList(compDefs[selected], jobId);
  };

  const handleRollback = async () => {
    if (!selected) return;
    await onRollback(compDefs[selected]);
  };

  return (
    <>
      <BatchInstallBar components={components} states={states} onInstallAll={onInstallAll} />

      <div className="dgs-controls dgs-controls--preview">
        <button className="dgs-add-btn" onClick={addDgs}>+ Add DataGather_S</button>
        {dgsInstances.length > 0 && (
          <button
            className="dgs-remove-btn"
            onClick={() => {
              const last = dgsInstances[dgsInstances.length - 1];
              if (selected === last.key) setSelected(null);
              removeDgs(last.key);
            }}
          >
            Remove Last
          </button>
        )}
      </div>

      <div className={`diag-layout diag-layout--preview${selected ? ' diag-layout--open' : ''}`}>
        <div className="diag-svg-area diag-svg-area--preview">
          <DiagramCanvas states={states} selected={selected} onSelect={setSelected} dgsInstances={dgsInstances} />
        </div>

        {selected && (
          <ConfigPanel
            compDef={compDefs[selected]}
            state={states[selected]}
            onChange={(patch) => update(selected, patch)}
            onInstall={handleInstall}
            onAddDgs={handleAddDgs}
            isDgsCopy={isDgsCopy}
            onPatch={handlePatch}
            onRollbackList={handleRollbackList}
            onRollback={handleRollback}
            onClose={() => setSelected(null)}
          />
        )}
      </div>
    </>
  );
}
