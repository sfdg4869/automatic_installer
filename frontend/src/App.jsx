import React, { useState } from 'react';
import axios from 'axios';
import { Bot, Terminal, Play, Loader2, CheckCircle2, XCircle, HelpCircle } from 'lucide-react';
import './index.css';

const API_BASE = 'http://127.0.0.1:5050/api';

function App() {
  const [prompt, setPrompt] = useState('"C:\\Users\\jungkyungsoo\\Desktop\\MFO\\rts.5.5.1.26.24110576.package\\rts.5.5.1.26.24110576.package\\rts.5.5.1.26.24110576.package\\rts.5.5.1.26.linux.x86_64.numa.19000.pkg.tar.gz" 파일로 리눅스(hp) 10.20.132.101 서버에 10022 포트로 설치해. 추가 변수로는 SSH_USER=MaxGauge, SSH_PASSWORD=12Sqecd34!, CONF_NAME=mxg, MXG_HOME=/home/MaxGauge, GATHER_IP=10.20.132.40, GATHER_PORT=17001, SYS_PASS=1 이 6가지만 필수로 지정해줘. 나머지 설정 중에 RTS_PORT=25031, MXG_USER=maxgauge, MXG_PASS=maxgauge 로 기본값을 덮어씌워서 설치해!');
  const [status, setStatus] = useState('idle'); // idle, parsing, installing, success, error
  const [logs, setLogs] = useState('');
  const [message, setMessage] = useState('');
  const [activeTab, setActiveTab] = useState('daemon');

  const handleInstall = async () => {
    if (!prompt.trim()) return;

    setLogs('');
    setMessage('');

    try {
      // 1. Parse via Gemini
      setStatus('parsing');
      setLogs(prev => prev + '> Sending prompt to Gemini AI for analysis...\n');

      const parseRes = await axios.post(`${API_BASE}/parse`, { prompt });
      const config = parseRes.data;

      setLogs(prev => prev + '> Extracted Configuration:\n' + JSON.stringify(config, null, 2) + '\n\n');
      setLogs(prev => prev + '> Starting automated installation process...\n');

      // 2. Install
      setStatus('installing');

      const installRes = await axios.post(`${API_BASE}/install`, config);

      setLogs(prev => prev + installRes.data.log + '\n');
      setMessage(installRes.data.message);
      setStatus('success');

    } catch (err) {
      console.error("AXIOS ERROR DETAILED:", err);
      const errMessage = err.response?.data?.message || err.response?.data?.error || err.message;
      const errLog = err.response?.data?.log || '';

      if (errLog) {
        setLogs(prev => prev + errLog + '\n');
      }
      setLogs(prev => prev + `\n[FATAL] Error occurred: ${errMessage}\n`);
      setMessage(`Installation Failed: ${errMessage}`);
      setStatus('error');
    }
  };

  return (
    <div className="app-container">
      <header className="header" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ textAlign: 'center' }}>
          <h1 style={{ margin: 0, paddingBottom: '5px' }}>설치 자동화</h1>
          <p style={{ margin: 0, opacity: 0.8, fontSize: '0.9rem', marginBottom: '20px' }}>Installation Assistant</p>
        </div>
        <img src="/logo.png" alt="MaxGauge Logo" style={{ height: '50px', objectFit: 'contain', display: 'block' }} />
      </header>

      <div className="glass-panel">
        <div className="input-section">
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 500, color: 'var(--text-main)' }}>
            <Bot size={20} className="pulse" style={{ color: 'var(--accent-color)' }} />
            Prompt 입력
          </label>
          <div className="textarea-wrapper">
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="e.g., Desktop의 app.tar 파일을 리눅스로 /opt/myapp 에 설치해. 포트는 8080..."
              disabled={status === 'parsing' || status === 'installing'}
            />
          </div>
          <button
            className="submit-btn"
            onClick={handleInstall}
            disabled={status === 'parsing' || status === 'installing' || !prompt.trim()}
          >
            {status === 'idle' || status === 'success' || status === 'error' ? (
              <><Play size={20} /> Execute Install</>
            ) : (
              <><Loader2 size={20} className="spinner" /> {status === 'parsing' ? 'Analyzing...' : 'Installing...'}</>
            )}
          </button>
        </div>

        {status !== 'idle' && (
          <div className={`status-badge status-${status}`}>
            {status === 'parsing' && <>AI Engine is parsing instruction...</>}
            {status === 'installing' && <>Running installation scripts...</>}
            {status === 'success' && <><CheckCircle2 size={16} style={{ marginRight: '0.5rem' }} /> {message || 'Success'}</>}
            {status === 'error' && <><XCircle size={16} style={{ marginRight: '0.5rem' }} /> {message || 'Error occurred'}</>}
          </div>
        )}

        {(logs || status !== 'idle') && (
          <div className="log-terminal">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem', color: 'var(--text-muted)' }}>
              <Terminal size={16} />
              <span style={{ fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: '1px' }}>Terminal Output</span>
            </div>
            {logs || 'Ready...'}
          </div>
        )}
      </div>

      <div className="help-panel">
        <div className="help-panel-tab">
          <HelpCircle size={24} />
        </div>
        <h3 style={{ margin: '0 0 10px 0', color: 'var(--accent-color)', fontSize: '1.2rem' }}>💡 프롬프트 작성 템플릿</h3>

        <div style={{ display: 'flex', gap: '10px', marginBottom: '15px' }}>
          <button
            onClick={() => setActiveTab('daemon')}
            style={{ padding: '6px 16px', borderRadius: '4px', border: '1px solid var(--border-color)', background: activeTab === 'daemon' ? 'var(--accent-color)' : 'transparent', color: activeTab === 'daemon' ? '#fff' : 'var(--text-main)', cursor: 'pointer', fontWeight: 'bold' }}
          >
            Daemon
          </button>
          <button
            onClick={() => setActiveTab('pjs')}
            style={{ padding: '6px 16px', borderRadius: '4px', border: '1px solid var(--border-color)', background: activeTab === 'pjs' ? 'var(--accent-color)' : 'transparent', color: activeTab === 'pjs' ? '#fff' : 'var(--text-main)', cursor: 'pointer', fontWeight: 'bold' }}
          >
            PJS
          </button>
          <button
            onClick={() => setActiveTab('dg')}
            style={{ padding: '6px 16px', borderRadius: '4px', border: '1px solid var(--border-color)', background: activeTab === 'dg' ? 'var(--accent-color)' : 'transparent', color: activeTab === 'dg' ? '#fff' : 'var(--text-main)', cursor: 'pointer', fontWeight: 'bold' }}
          >
            DataGather
          </button>
        </div>

        <p style={{ margin: 0, fontSize: '0.95rem', lineHeight: '1.6', wordBreak: 'keep-all', color: 'var(--text-main)', opacity: 0.9 }}>
          다음 양식을 복사해서 <span style={{ color: '#fff', fontWeight: 'bold' }}>&lt;형광펜 부분&gt;</span>을 자신의 환경에 맞게 고쳐서 사용하세요!
        </p>
        <div style={{ marginTop: '15px', padding: '12px', background: 'rgba(0,0,0,0.4)', borderRadius: '8px', border: '1px solid var(--border-color)', fontSize: '0.85rem', lineHeight: '1.5', fontFamily: 'monospace' }}>
          {activeTab === 'daemon' && (
            <>
              <span style={{ color: '#58a6ff' }}>"&lt;내PC의 tar파일 전체경로&gt;"</span> 파일로 <span style={{ color: '#58a6ff' }}>&lt;설치할 OS&gt;</span> <span style={{ color: '#58a6ff' }}>&lt;서버IP&gt;</span> 서버에 <span style={{ color: '#58a6ff' }}>&lt;SSH포트&gt;</span> 포트로 설치해.<br /><br />
              추가 변수로는 <br />
              SSH_USER=<span style={{ color: '#3fb950' }}>&lt;계정명&gt;</span>, <br />
              SSH_PASSWORD=<span style={{ color: '#3fb950' }}>&lt;비밀번호&gt;</span>, <br />
              CONF_NAME=<span style={{ color: '#3fb950' }}>&lt;폴더명: 예)mxg&gt;</span>, <br />
              MXG_HOME=<span style={{ color: '#3fb950' }}>&lt;설치경로: 예)/home/MaxGauge&gt;</span>, <br />
              GATHER_IP=<span style={{ color: '#3fb950' }}>&lt;데이터수집IP&gt;</span>, <br />
              GATHER_PORT=<span style={{ color: '#3fb950' }}>&lt;데이터수집포트: 예) 7001&gt;</span>, <br />
              SYS_PASS=<span style={{ color: '#3fb950' }}>&lt;패스워드타입: 예) 1&gt;</span> <br />
              이 7가지만 필수로 지정해줘. 나머지는 기본값으로 해줘!
            </>
          )}

          {activeTab === 'pjs' && (
            <>
              "<span style={{ color: '#58a6ff' }}>&lt;내PC의 tar파일 전체경로&gt;</span>" 파일을 <span style={{ color: '#58a6ff' }}>&lt;설치할 OS&gt;</span> <span style={{ color: '#58a6ff' }}>&lt;서버IP&gt;</span> 서버에 지정하고 <span style={{ color: '#58a6ff' }}>&lt;SSH포트&gt;</span> 포트야.<br /><br />
              추가 변수로는 <br />
              SSH_USER=<span style={{ color: '#3fb950' }}>&lt;계정명&gt;</span>, <br />
              SSH_PASSWORD=<span style={{ color: '#3fb950' }}>&lt;비밀번호&gt;</span>, <br />
              설치 경로는 <span style={{ color: '#3fb950' }}>&lt;설치경로: 예)/home/MaxGauge&gt;</span> 로 지정하고, <br />
              DataGather IP=<span style={{ color: '#3fb950' }}>&lt;데이터수집IP&gt;</span>, <br />
              DataGather Port=<span style={{ color: '#3fb950' }}>&lt;데이터수집포트: 예) 37000&gt;</span>, <br />
              Database Type=<span style={{ color: '#3fb950' }}>&lt;DB타입: 예) oracle&gt;</span>, <br />
              DB 유저=<span style={{ color: '#3fb950' }}>&lt;DB계정명&gt;</span>, <br />
              DB 패스워드=<span style={{ color: '#3fb950' }}>&lt;DB비밀번호&gt;</span>, <br />
              SID=<span style={{ color: '#3fb950' }}>&lt;DB명&gt;</span>, <br />
              PJS Service port=<span style={{ color: '#3fb950' }}>&lt;서비스포트: 예) 38080&gt;</span> <br />
              으로 세팅해!
            </>
          )}

          {activeTab === 'dg' && (
            <>
              <span style={{ color: '#58a6ff' }}>&lt;내PC의 tar파일 전체경로&gt;</span> 파일을 서버 <span style={{ color: '#58a6ff' }}>&lt;서버IP&gt;</span>의 <span style={{ color: '#58a6ff' }}>&lt;SSH포트&gt;</span>번 포트에 접속해서 <br />
              <span style={{ color: '#3fb950' }}>&lt;설치경로: 예)/home/MaxGauge/my_test/test_&gt;</span> 경로에 DG_M(마스터) 모드로 설치해줘.<br /><br />
              서버 접속 계정은 <br />
              SSH_USER=<span style={{ color: '#3fb950' }}>&lt;계정명&gt;</span> 이고 <br />
              SSH_PASSWORD=<span style={{ color: '#3fb950' }}>&lt;비밀번호&gt;</span> 야. <br /><br />
              설치할 OS는 <span style={{ color: '#58a6ff' }}>&lt;설치할 OS&gt;</span>로 선택하고, <br />
              데이터베이스 정보는 다음과 같아.<br />
              database_type=<span style={{ color: '#3fb950' }}>&lt;DB타입: 예) oracle&gt;</span><br />
              database_ip=<span style={{ color: '#3fb950' }}>&lt;DB IP&gt;</span><br />
              database_port=<span style={{ color: '#3fb950' }}>&lt;DB포트&gt;</span><br />
              database_sid=<span style={{ color: '#3fb950' }}>&lt;DB명&gt;</span><br />
              database_user=<span style={{ color: '#3fb950' }}>&lt;DB계정명&gt;</span><br />
              database_password=<span style={{ color: '#3fb950' }}>&lt;DB비밀번호&gt;</span><br />
              tablespace=<span style={{ color: '#3fb950' }}>&lt;테이블스페이스&gt;</span><br />
              index_tablespace=<span style={{ color: '#3fb950' }}>&lt;인덱스테이블스페이스&gt;</span><br />
              gather_port=<span style={{ color: '#3fb950' }}>&lt;수집포트: 예) 7000&gt;</span> 이고,<br />
              slave_gather_list=<span style={{ color: '#3fb950' }}>&lt;슬레이브수집기목록: 예) 10.20.132.101:7001&gt;</span> 로 설정해서 설치 진행해줘.
            </>
          )}
        </div>
      </div>
    </div >
  );
}

export default App;
