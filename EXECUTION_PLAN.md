# MaxGauge Automatic Installer - Execution Plan

## 개요
이 문서는 MaxGauge 자동 설치기(Automatic Installer)가 원격 서버(Linux, Unix, AIX, HP-UX, SunOS)에 접근하여 대화형 프롬프트 없이 스크립트를 전자동으로 설치하는 전체 과정을 구체화한 마스터 플랜입니다.

---

## 단계별 실행 프로세스

### 1. 프롬프트 AI 파싱기 (Natural Language Processing)
- **개념**: 사용자의 자연어 입력을 받아 정형화된 설치 설정값(`InstallConfigSchema`)을 도출합니다.
- **주요 로직**:
  - `agent.py` 내의 Google Gemini AI 모델(기본: `gemini-flash-latest`)을 호출.
  - Rate Limiting(503, 429) 에러 발생 시 백업 모델(`gemini-3-flash-preview` 등)로 Fallback.
  - 자연어 속성에서 서버 IP/포트, 필수 환경변수(`SSH_USER`, `MXG_HOME`, `CONF_NAME` 등) 및 `tar` 파일 경로를 JSON으로 변환.

### 2. 원격 서버 접속 파이프라인 (SSH Connection)
- **개념**: `paramiko` 라이브러리를 통해 타겟 서버에 SSH 접속을 진행합니다.
- **주요 로직**:
  - `executor.py`에서 전달받은 `SSH_USER` 및 `SSH_PASSWORD`를 활용하여 세션 오픈.
  - 접속 실패시 에러 반환 및 타임아웃 룰 적용.

### 3. OS 및 오라클 인스턴스 자동 탐지 (Auto-Discovery)
- **개념**: 타겟 서버의 OS 종류와 환경 변수, 실행 중인 오라클의 메타데이터를 수집합니다.
- **주요 로직**:
  - `uname -s` 로 리눅스 및 각종 유닉스(HP-UX, AIX, SunOS) 변종 판별.
  - `ps -ef | grep ora_pmon` 및 `.tar.gz` 파일명의 힌트(예: 19000, 11204)를 조합하여 정밀 추출:
    1. **오라클 버전**
    2. 데이터베이스 소유 계정 (**DB_OWNER**)
    3. 프로세스 모니터 이름 (**PMON_NAME**)
    4. 인스턴스 이름 (**ORACLE_SID**)
  - `/etc/oratab` (또는 `/var/opt/oracle/oratab`) 텍스트 파싱 및 `su - oracle -c 'echo $ORACLE_HOME'` 구문으로 오라클 홈 경로 자동 획득.

### 4. IPC Key & DB 네트워크 수집 (Network & IPC Discovery)
- **개념**: 오라클 공유 메모리(SGA) 접근 키와 리스너 소켓 정보를 탈취(수집)합니다.
- **주요 로직**:
  - 1차: `sqlplus` 로 `oradebug` 유틸리티를 호출해 트레이스(TRC) 파일에서 **IPC_KEY** 추출.
  - 2차: `oradebug`가 실패하거나 추출이 거부되었을 시(AIX 등 환경변수 미비), 백업 플랜으로 오라클 내장 도구인 `sysresv`를 실행하여 정규식(Regex)으로 100% 정답 **IPC_KEY** 획득.
  - `lsnrctl status` 명령 또는 `listener.ora` 파일 파싱과 `netstat` 분석 알고리즘으로 **LISTENER_IP_PORT** 정보 저장.

### 5. 아카이브 고속 전송 및 완전 추출 (Transfer & Extraction)
- **개념**: 수백 MB의 설치 패키지를 원격 서버에 올리고 압축을 해제합니다.
- **주요 로직**:
  - `SCPClient`의 FAST SCP 모드로 `/tmp/auto_installer_remote/` 위치로 업로드.
  - **유닉스 호환성 극대화**: Solaris 등 구버전 계열의 tar 한계를 극복하기 위해 파이프(`|`) 오류를 차단하고, `gunzip`을 먼저 분리 실행 후 순정 `tar -xf`로 해제.
  - 추출된 폴더를 안전하게 사용자 타겟 경로(`MXG_HOME`)로 이동하기 전, 서버의 OS 결벽성(mkdir -p 버그) 우회를 위해 `mkdir` 및 `cp -R` 기법을 교차 결합하여 디스크 권한 에러를 완벽 차단.
  - 스크립트 실행 전 `ls -l` 검문소를 배치하여 127(Command Not Found) 에러 발생 요인 원천 봉쇄.

### 6. 인터랙티브 대화형 쉘 강제 구동 (Interactive Shell Execution)
- **개념**: 사용자가 직접 콘솔 창에 엔터를 치는 것처럼 응답을 에뮬레이션합니다.
- **주요 로직**:
  - 대상 서버의 OS에 맞춰 쉘(`invoke_shell`)을 오픈 (HP-UX/AIX: `ksh`, 그 외: `sh`).
  - 정규표현식(`re`)을 사용하여 끝없이 내려오는 원격 콘솔의 텍스트 버퍼를 감시.
  - "Enter Database owner:", "Enter Maxgauge conf name:", "Select ipc key:" 등의 프롬프트 질문이 등장하면 3~4단계에서 획득한 오라클 속성 정답들을 1초의 딜레이만 두고 즉각 채워 넣음.

### 7. 설치 완료 및 사후 처리
- **개념**: 정상 설치 플래그 점검 및 임시 잔여물 포맷.
- **주요 로직**:
  - `channel.recv_exit_status()`로 최종 스크립트 실행 Exit Code 점검.
  - 설치 성공 시 `[SSH] ✅ Remote installation finished` 로깅 후 Python API에 JSON 반환.
  - 사용 중 생성한 `.sql` 및 `/tmp/` 폴더 찌꺼기를 백그라운드에서 완전히 삭제.
