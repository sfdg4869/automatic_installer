import React, { useState } from 'react';
import axios from 'axios';
import { LayoutGrid, Network } from 'lucide-react';
import FormPage from './FormPage.jsx';
import DiagramPage from './DiagramPage.jsx';
import './index.css';

const API_BASE = import.meta.env.VITE_API_BASE_URL
  ? `${import.meta.env.VITE_API_BASE_URL}/api`
  : 'http://127.0.0.1:5050/api';

const BASE_COMPONENTS = [
  {
    key: 'rts',
    agentType: 'daemon',
    label: 'RTS',
    extraFields: [
      { key: 'CONF_NAME', label: 'Config Name', placeholder: 'mxg' },
      { key: 'MXG_HOME', label: 'MXG Home', placeholder: '/home/MaxGauge' },
      { key: 'GATHER_IP', label: 'Gather IP', placeholder: '10.20.132.40' },
      { key: 'GATHER_PORT', label: 'Gather Port', placeholder: '7001' },
      { key: 'RTS_PORT', label: 'RTS Port', placeholder: '5080' },
      { key: 'SYS_PASS', label: 'Sys Pass Type', placeholder: '1' },
    ],
  },
  {
    key: 'pjs',
    agentType: 'pjs',
    label: 'PlatformJS',
    extraFields: [
      { key: 'GATHER_IP', label: 'Gather IP', placeholder: '10.20.132.40' },
      { key: 'GATHER_PORT', label: 'Gather Port', placeholder: '37000' },
      { key: 'PJS_PORT', label: 'Service Port', placeholder: '38080' },
      { key: 'DATABASE_TYPE', label: 'DB Type', type: 'select', options: ['oracle', 'postgres'] },
      { key: 'DATABASE_USER', label: 'DB User', placeholder: 'maxgauge' },
      { key: 'DATABASE_PASSWORD', label: 'DB Password', type: 'password', placeholder: '' },
      { key: 'DATABASE_NAME', label: 'DB Name', placeholder: 'jp_repo', pgOnly: true },
      { key: 'DATABASE_PORT', label: 'DB Port', placeholder: '5432', pgOnly: true },
    ],
  },
  {
    key: 'dgm',
    agentType: 'dgm',
    label: 'DataGather_M',
    extraFields: [
      { key: 'GATHER_PORT', label: 'Gather Port', placeholder: '7000' },
      { key: 'SLAVE_GATHER_LIST', label: 'Slave Gather List', placeholder: '127.0.0.1:7001' },
      { key: 'DATABASE_TYPE', label: 'DB Type', type: 'select', options: ['oracle', 'postgres'] },
      { key: 'DATABASE_IP', label: 'DB IP', placeholder: '10.20.132.101' },
      { key: 'DATABASE_PORT', label: 'DB Port', placeholder: '1521' },
      { key: 'DATABASE_SID', label: 'DB SID / Name', placeholder: 'oracle19' },
      { key: 'DATABASE_USER', label: 'DB User', placeholder: 'TEST_2507' },
      { key: 'DATABASE_PASSWORD', label: 'DB Password', type: 'password', placeholder: '' },
      { key: 'TABLESPACE', label: 'Tablespace', placeholder: 'TS_2507_TEST', oracleOnly: true },
      { key: 'INDEX_TABLESPACE', label: 'Index Tablespace', placeholder: 'TS_2507_TEST', oracleOnly: true },
    ],
  },
];

const DGS_DEF = {
  agentType: 'dgs',
  extraFields: [
    { key: 'DG_NAME', label: 'DG Name', placeholder: 'DGServer_S2' },
    { key: 'GATHER_PORT', label: 'Gather Port', placeholder: '7002' },
    { key: 'OBS1_KEYWORD2', label: 'OBS1 Keyword2', placeholder: 'keyword' },
  ],
};

const mkInitial = () => ({
  uploadedPath: null,
  filename: null,
  uploading: false,
  uploadError: null,
  host: '',
  port: '22',
  osChoice: 'auto',
  sshUser: '',
  sshPassword: '',
  installPath: '',
  dgmInstallPath: '',
  extraFields: {},
  installUpdater: false,
  status: 'idle',
  log: '',
  patchUploadedPath: null,
  patchFilename: null,
  patchUploading: false,
  patchUploadError: null,
  patchSuffix: '',
  patchStatus: 'idle',
  patchLog: '',
  patchOpen: false,
  patchJobId: null,
  patchComponentKey: null,
  patchEntries: [],
  patchedFilenames: [],
  rollbackBackups: null,
  rollbackSelectedDate: {},
  rollbackStatus: 'idle',
  rollbackLog: '',
  rollbackSource: null,
  rollbackJob: null,
  rollbackJobs: [],
});

export default function App() {
  const [page, setPage] = useState('diagram');
  const [dgsInstances, setDgsInstances] = useState([]);
  const [states, setStates] = useState(() => ({
    ...Object.fromEntries(BASE_COMPONENTS.map((c) => [c.key, mkInitial()])),
    dgs1: mkInitial(),
  }));

  const allComponents = [
    ...BASE_COMPONENTS,
    ...dgsInstances.map((d) => ({ ...DGS_DEF, key: d.key, label: d.label })),
  ];

  const addDgs = () => {
    const nextIdx = dgsInstances.length > 0 ? Math.max(...dgsInstances.map((d) => d.idx)) + 1 : 2;
    const key = `dgs_${nextIdx}`;
    setDgsInstances((prev) => [...prev, { key, label: `DataGather_S${nextIdx}`, idx: nextIdx }]);
    setStates((prev) => ({
      ...prev,
      [key]: { ...mkInitial(), extraFields: { DG_NAME: `DGServer_S${nextIdx}` } },
    }));
  };

  const removeDgs = (key) => {
    setDgsInstances((prev) => prev.filter((d) => d.key !== key));
    setStates((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const update = (key, patch) => {
    setStates((prev) => ({ ...prev, [key]: { ...prev[key], ...patch } }));
  };

  const handleInstall = async (compDef) => {
    const state = states[compDef.key];
    update(compDef.key, { status: 'installing', log: '' });

    const selectDefaults = {};
    compDef.extraFields
      .filter((f) => f.type === 'select')
      .forEach((f) => {
        selectDefaults[f.key] = f.options[0];
      });

    const extraVars = {
      SSH_USER: state.sshUser,
      SSH_PASSWORD: state.sshPassword,
      ...selectDefaults,
      ...state.extraFields,
    };

    const installPath = compDef.agentType === 'daemon'
      ? (state.extraFields.MXG_HOME || state.installPath || '')
      : state.installPath;

    try {
      const res = await axios.post(`${API_BASE}/install`, {
        agent_type: compDef.agentType,
        tar_path: state.uploadedPath,
        host: state.host,
        port: parseInt(state.port, 10) || 22,
        os_choice: state.osChoice,
        install_path: installPath,
        extra_vars: extraVars,
        install_updater: compDef.agentType === 'daemon' ? (state.installUpdater || false) : false,
      });
      const log = res.data.log || '';
      update(compDef.key, { status: 'success', log });
      return log;
    } catch (err) {
      const errLog = err.response?.data?.log || '';
      const errMsg = err.response?.data?.message || err.message;
      const fullLog = (errLog ? `${errLog}\n` : '') + `\n[FATAL] ${errMsg}`;
      update(compDef.key, { status: 'error', log: fullLog });
      return fullLog;
    }
  };

  const handlePatch = async (compDef) => {
    const stateKey = compDef.key;
    const state = states[stateKey];
    if (!state.patchUploadedPath) return;

    update(stateKey, {
      patchStatus: 'patching',
      patchLog: '',
      patchJobId: null,
      patchComponentKey: null,
      patchEntries: [],
    });

    let searchRoot = '';
    if (compDef.agentType === 'daemon') {
      const mxgHome = state.extraFields.MXG_HOME || '';
      const confName = state.extraFields.CONF_NAME || '';
      searchRoot = confName ? `${mxgHome}/${confName}` : mxgHome;
    } else {
      searchRoot = state.installPath || '';
    }

    try {
      const res = await axios.post(`${API_BASE}/patch`, {
        archive_path: state.patchUploadedPath,
        host: state.host,
        port: parseInt(state.port, 10) || 22,
        ssh_user: state.sshUser,
        ssh_password: state.sshPassword,
        search_root: searchRoot,
        backup_suffix: state.patchSuffix.trim() || null,
        component_key: compDef.key,
        component_label: compDef.label,
        agent_type: compDef.agentType,
      });
      update(stateKey, {
        patchStatus: res.data.status === 'success' ? 'success' : 'error',
        patchLog: res.data.log || '',
        patchJobId: res.data.job_id || null,
        patchComponentKey: compDef.key,
        patchEntries: res.data.patched_entries || [],
        patchedFilenames: res.data.patched_filenames || [],
      });
    } catch (err) {
      const errLog = err.response?.data?.log || '';
      const errMsg = err.response?.data?.message || err.message;
      update(stateKey, {
        patchStatus: 'error',
        patchLog: (errLog ? `${errLog}\n` : '') + `\n[FATAL] ${errMsg}`,
      });
    }
  };

  const getSearchRoot = (compDef) => {
    const state = states[compDef.key];
    if (compDef.agentType === 'daemon') {
      const mxgHome = state.extraFields?.MXG_HOME || '';
      const confName = state.extraFields?.CONF_NAME || '';
      if (!mxgHome) return '';
      return confName ? `${mxgHome}/${confName}` : mxgHome;
    }
    return state.installPath || '';
  };

  const handleRollbackList = async (compDef, jobId = null) => {
    const stateKey = compDef.key;
    const state = states[stateKey];
    const searchRoot = getSearchRoot(compDef);
    if (!searchRoot) return;

    update(stateKey, {
      rollbackStatus: 'loading',
      rollbackLog: '',
      rollbackBackups: null,
      rollbackSource: null,
      rollbackJob: null,
      rollbackJobs: [],
    });
    try {
      const filenames = (state.patchEntries || []).map((entry) => entry.filename).filter(Boolean);
      const fallbackFilenames = filenames.length > 0 ? filenames : (state.patchedFilenames || []);
      const recentJobId = jobId || (state.patchComponentKey === compDef.key ? state.patchJobId : null);
      const res = await axios.post(`${API_BASE}/rollback/list`, {
        host: state.host,
        port: parseInt(state.port, 10) || 22,
        ssh_user: state.sshUser,
        ssh_password: state.sshPassword,
        search_root: searchRoot,
        filenames: fallbackFilenames,
        component_key: compDef.key,
        job_id: recentJobId,
        use_recent_history: true,
        history_limit: 10,
      });
      const backups = res.data.backups || {};
      const defaultDates = {};
      Object.entries(backups).forEach(([fileName, entries]) => {
        if (entries.length > 0) defaultDates[fileName] = entries[entries.length - 1].date;
      });
      update(stateKey, {
        rollbackStatus: 'idle',
        rollbackBackups: backups,
        rollbackSelectedDate: defaultDates,
        rollbackLog: res.data.log || '',
        rollbackSource: res.data.source || null,
        rollbackJob: res.data.history_job || null,
        rollbackJobs: res.data.history_jobs || [],
      });
    } catch (err) {
      const errLog = err.response?.data?.log || '';
      const errMsg = err.response?.data?.message || err.message;
      update(stateKey, {
        rollbackStatus: 'error',
        rollbackLog: (errLog ? `${errLog}\n` : '') + `\n[FATAL] ${errMsg}`,
      });
    }
  };

  const handleRollback = async (compDef) => {
    const stateKey = compDef.key;
    const state = states[stateKey];
    if (!state.rollbackBackups) return;

    const rollbackTargets = [];
    Object.entries(state.rollbackBackups).forEach(([fileName, entries]) => {
      const selectedDate = state.rollbackSelectedDate[fileName];
      const entry = entries.find((e) => e.date === selectedDate);
      if (entry) {
        rollbackTargets.push({
          backup_path: entry.backup_path,
          original_path: entry.original_path,
        });
      }
    });

    if (!rollbackTargets.length) return;

    update(stateKey, { rollbackStatus: 'running', rollbackLog: '' });
    try {
      const res = await axios.post(`${API_BASE}/rollback/run`, {
        host: state.host,
        port: parseInt(state.port, 10) || 22,
        ssh_user: state.sshUser,
        ssh_password: state.sshPassword,
        rollback_targets: rollbackTargets,
      });
      update(stateKey, {
        rollbackStatus: res.data.status === 'success' ? 'success' : 'error',
        rollbackLog: res.data.log || '',
      });
    } catch (err) {
      const errLog = err.response?.data?.log || '';
      const errMsg = err.response?.data?.message || err.message;
      update(stateKey, {
        rollbackStatus: 'error',
        rollbackLog: (errLog ? `${errLog}\n` : '') + `\n[FATAL] ${errMsg}`,
      });
    }
  };

  const handleAddDgs = async (compDef, instanceIdx) => {
    const state = states[compDef.key];
    update(compDef.key, { status: 'installing', log: '' });
    try {
      const res = await axios.post(`${API_BASE}/add_dgs`, {
        host: state.host,
        port: parseInt(state.port, 10) || 22,
        ssh_user: state.sshUser,
        ssh_password: state.sshPassword,
        s1_install_path: state.installPath,
        instance_num: instanceIdx,
        dg_name: state.extraFields?.DG_NAME || '',
        gather_port: state.extraFields?.GATHER_PORT || '',
        obs1_keyword2: state.extraFields?.OBS1_KEYWORD2 || '',
        dgm_install_path: state.dgmInstallPath || states.dgm?.installPath || '',
      });
      update(compDef.key, { status: 'success', log: res.data.log || '' });
    } catch (err) {
      const errLog = err.response?.data?.log || '';
      const errMsg = err.response?.data?.message || err.message;
      update(compDef.key, { status: 'error', log: (errLog ? `${errLog}\n` : '') + `\n[FATAL] ${errMsg}` });
    }
  };

  const handleInstallAll = async () => {
    const order = ['rts', 'dgm', 'pjs', ...dgsInstances.map((d) => d.key)];
    for (const key of order) {
      const compDef = allComponents.find((c) => c.key === key);
      const state = states[key];
      if (!state || !compDef) continue;

      const dgsInst = dgsInstances.find((d) => d.key === key);
      if (dgsInst) {
        const ready = state.host && state.sshUser && state.sshPassword && state.installPath &&
          state.extraFields?.DG_NAME && state.extraFields?.GATHER_PORT && state.extraFields?.OBS1_KEYWORD2;
        if (!ready) continue;
        await handleAddDgs(compDef, dgsInst.idx);
      } else {
        if (!state.uploadedPath || !state.host || !state.sshUser || !state.sshPassword) continue;
        await handleInstall(compDef);
      }
    }
  };

  return (
    <div className="page">
      <header className="top-header">
        <img src="/logo.png" alt="MaxGauge" style={{ height: '36px', objectFit: 'contain' }} />
        <div style={{ flex: 1 }}>
          <h1 className="top-title">MaxGauge Installer</h1>
          <p className="top-sub">Upload a package, connect to the target server, and run install or patch from one place.</p>
        </div>
        <nav className="page-nav">
          <button className={`nav-btn${page === 'diagram' ? ' nav-btn--active' : ''}`} onClick={() => setPage('diagram')}>
            <Network size={15} /> Diagram View
          </button>
          <button className={`nav-btn${page === 'form' ? ' nav-btn--active' : ''}`} onClick={() => setPage('form')}>
            <LayoutGrid size={15} /> Form View
          </button>
        </nav>
      </header>

      {page === 'form' ? (
        <FormPage
          components={allComponents}
          dgsInstances={dgsInstances}
          addDgs={addDgs}
          removeDgs={removeDgs}
          states={states}
          update={update}
          onInstall={handleInstall}
          onAddDgs={handleAddDgs}
          onPatch={handlePatch}
          onInstallAll={handleInstallAll}
          onRollbackList={handleRollbackList}
          onRollback={handleRollback}
        />
      ) : (
        <DiagramPage
          components={allComponents}
          dgsInstances={dgsInstances}
          addDgs={addDgs}
          removeDgs={removeDgs}
          states={states}
          update={update}
          onInstall={handleInstall}
          onAddDgs={handleAddDgs}
          onPatch={handlePatch}
          onInstallAll={handleInstallAll}
          onRollbackList={handleRollbackList}
          onRollback={handleRollback}
        />
      )}
    </div>
  );
}
