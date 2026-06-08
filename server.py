from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import io
import sys
import contextlib
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from installer.archive import extract_tar
from installer.executor_daemon import detect_runtime_os, find_install_script, run_install_script
from installer.patch_history import find_recent_patch_job, history_job_to_backups, list_recent_patch_jobs, save_patch_job, save_rollback_logs
from installer.prompt import InstallConfig

app = Flask(__name__)
CORS(app)

UPLOAD_DIR = Path("/tmp/auto_installer_uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_EXTENSIONS = {".tar", ".gz", ".tgz", ".zip", ".jar"}

@app.route('/')
def index():
    return """
    <html>
        <body style="font-family: sans-serif; text-align: center; padding-top: 50px;">
            <h2>API Server is Running! 🚀</h2>
            <p>This is the backend server. The Web UI is running on a different port.</p>
            <p>Please open <b><a href="http://localhost:5173">http://localhost:5173</a></b> to view the interface.</p>
        </body>
    </html>
    """

import traceback

@app.route('/api/upload', methods=['POST', 'OPTIONS'])
def api_upload():
    if request.method == 'OPTIONS':
        return '', 200

    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400

    filename = secure_filename(file.filename)
    suffix = Path(filename).suffix.lower()
    # Accept .tar, .gz, .tgz (also catches .tar.gz via .gz suffix)
    if suffix not in ALLOWED_EXTENSIONS:
        return jsonify({"error": f"Unsupported file type: {suffix}"}), 400

    save_path = UPLOAD_DIR / filename
    file.save(str(save_path))
    return jsonify({"uploaded_path": str(save_path), "filename": filename})


@app.route('/api/parse', methods=['POST', 'OPTIONS'])
def api_parse():
    if request.method == 'OPTIONS':
        return '', 200
        
    data = request.json
    if not data or 'prompt' not in data:
        return jsonify({"error": "No prompt provided"}), 400
    
    natural_prompt = data.get('prompt')
    try:
        from installer.router import route_prompt
        agent_type = route_prompt(natural_prompt)
        print(f"[ROUTER] Natural Prompt resolved to agent target: {agent_type}")
        
        if agent_type == "pjs":
            from installer.agent_pjs import parse_install_prompt
        elif agent_type == "dgm":
            from installer.agent_dgm import parse_install_prompt
        elif agent_type == "dgs":
            from installer.agent_dgs import parse_install_prompt
        else:
            from installer.agent_daemon import parse_install_prompt
            
        parsed_schema = parse_install_prompt(natural_prompt)
        parsed_dict = parsed_schema.model_dump()
        
        # Convert list of 'KEY=VALUE' back to dictionary to avoid Gemini schema errors
        extra_vars = {}
        for ev in parsed_dict.get('extra_vars_list', []):
            if '=' in ev:
                k, v = ev.split('=', 1)
                extra_vars[k.strip()] = v.strip()
                
        # Super Fallback: Some agents drop SSH credentials, pull them directly if missing
        import re
        if "SSH_USER" not in extra_vars:
            m = re.search(r'SSH_USER=([a-zA-Z0-9_.-]+)', natural_prompt, re.IGNORECASE)
            if m: extra_vars["SSH_USER"] = m.group(1)
            
        if "SSH_PASSWORD" not in extra_vars:
            m = re.search(r'SSH_PASSWORD=([^\s,;]+)', natural_prompt, re.IGNORECASE)
            if m: extra_vars["SSH_PASSWORD"] = m.group(1)
            
        if "SSH_PORT" not in extra_vars and not parsed_dict.get('port'):
            m = re.search(r'SSH_PORT=(\d+)', natural_prompt, re.IGNORECASE)
            if m: parsed_dict['port'] = int(m.group(1))

        # Synchronize back just for display if needed
        parsed_dict['extra_vars_list'] = [f"{k}={v}" for k, v in extra_vars.items()]

        parsed_dict['extra_vars'] = extra_vars
        
        return jsonify(parsed_dict)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/install', methods=['POST', 'OPTIONS'])
def api_install():
    if request.method == 'OPTIONS':
        return '', 200
        
    data = request.json
    if not data:
        return jsonify({"error": "No payload provided"}), 400
    
    # We capture stdout/stderr to return via the API instead of raw terminal output
    output_capture = io.StringIO()
    
    class TeeTextIO:
        def __init__(self, stream1, stream2):
            self.stream1 = stream1
            self.stream2 = stream2
        def write(self, data):
            self.stream1.write(data)
            self.stream2.write(data)
            self.stream1.flush()
            self.stream2.flush()
        def flush(self):
            self.stream1.flush()
            self.stream2.flush()
            
    tee_stream = TeeTextIO(output_capture, sys.__stdout__)
    exit_code = -1
    
    with contextlib.redirect_stdout(tee_stream), contextlib.redirect_stderr(tee_stream):
        try:
            # 1. Expand paths, map missing values
            tar_raw = data.get('tar_path')
            if not tar_raw:
                print("[ERROR] No tar_path provided.")
                return jsonify({"status": "error", "message": "No tar_path provided", "log": output_capture.getvalue()}), 400
                
            tar_path = Path(tar_raw).expanduser()
            if not tar_path.is_file():
                print(f"[ERROR] tar file not found at: {tar_path}")
                return jsonify({"status": "error", "message": f"tar file not found at: {tar_path}", "log": output_capture.getvalue()}), 400
            
            os_choice = data.get('os_choice')
            if not os_choice or os_choice == "auto":
                runtime_os = detect_runtime_os()
                # 로컬이 Windows라도 원격 호스트 대상 설치는 Linux 스크립트를 사용
                remote_host = data.get('host') or ""
                if runtime_os == "windows" and remote_host and remote_host not in ("localhost", "127.0.0.1", "0.0.0.0"):
                    runtime_os = "linux"
            else:
                runtime_os = os_choice.lower()
                if "hp" in runtime_os or "aix" in runtime_os or "sunos" in runtime_os or "unix" in runtime_os:
                    runtime_os = "linux"  # we treat all unixes as linux for the local extraction/script finding phase
            
            print(f"[INFO] Runtime OS: {runtime_os}")
            
            # 2. Extract tar
            try:
                extracted_dir = extract_tar(tar_path)
                print(f"[INFO] Extracted to: {extracted_dir}")
            except Exception as e:
                print(f"[ERROR] Extraction failed: {e}")
                return jsonify({"status": "error", "message": f"Extraction failed: {e}", "log": output_capture.getvalue()}), 500

            extra_vars = data.get('extra_vars') or {}
            # agent_type can be supplied directly from the form UI; fall back to router for legacy NL flow
            agent_type = data.get('agent_type') or None
            if not agent_type:
                from installer.router import route_prompt
                agent_type = route_prompt(tar_path.name, extra_vars)
            print(f"[ROUTER] Installation resolved to agent target: {agent_type}")
            
            if agent_type in ("pjs", "dgm", "dgs"):
                script_path = None
            else:
                # 3. Find Script for Daemon/Normal installs
                remote_host_val = data.get('host') or ""
                is_remote_host = bool(remote_host_val and remote_host_val not in ("localhost", "127.0.0.1", "0.0.0.0"))
                try:
                    script_path = find_install_script(
                        extracted_dir=extracted_dir,
                        runtime_os=runtime_os,
                        preferred_script=data.get('script_name'),
                    )
                    print(f"[INFO] Installer script found: {script_path}")
                except FileNotFoundError as e:
                    if is_remote_host:
                        print(f"[INFO] No local install script (package-type tar), will auto-select on remote: {e}")
                        script_path = None
                    else:
                        raise

            # 4. Run Script
            if agent_type == "pjs":
                from installer.executor_pjs import run_pjs_install
                exit_code = run_pjs_install(
                    script_path=script_path,
                    runtime_os=runtime_os,
                    host=data.get('host') or "",
                    port=data.get('port') or 0,
                    install_path=data.get('install_path') or "",
                    extra_vars=extra_vars,
                    extracted_dir=extracted_dir,
                    tar_path=tar_path,
                )
            elif agent_type == "dgm":
                from installer.executor_dgm import run_dgm_install
                exit_code = run_dgm_install(
                    script_path=script_path,
                    runtime_os=runtime_os,
                    host=data.get('host') or "",
                    port=data.get('port') or 0,
                    install_path=data.get('install_path') or "",
                    extra_vars=extra_vars,
                    extracted_dir=extracted_dir,
                    tar_path=tar_path,
                )
            else:
                exit_code = run_install_script(
                    script_path=script_path,
                    runtime_os=runtime_os,
                    host=data.get('host') or "",
                    port=data.get('port') or 0,
                    install_path=data.get('install_path') or "",
                    extra_vars=extra_vars,
                    extracted_dir=extracted_dir,
                    tar_path=tar_path,
                    install_updater=bool(data.get('install_updater', False)),
                )
            
            if exit_code != 0:
                print(f"[ERROR] Install script failed with exit code: {exit_code}")
                return jsonify({"status": "error", "message": f"Install script failed with exit code {exit_code}", "log": output_capture.getvalue()}), 500
                
            print("[INFO] Installation completed successfully.")
            return jsonify({
                "status": "success", 
                "message": "Installation successful.", 
                "log": output_capture.getvalue()
            })
            
        except Exception as e:
            print(f"[ERROR] Unexpected error during installation: {e}")
            return jsonify({"status": "error", "message": str(e), "log": output_capture.getvalue()}), 500


@app.route('/api/add_dgs', methods=['POST', 'OPTIONS'])
def api_add_dgs():
    if request.method == 'OPTIONS':
        return '', 200

    data = request.json
    if not data:
        return jsonify({"error": "No payload provided"}), 400

    output_capture = io.StringIO()

    class TeeTextIO:
        def __init__(self, s1, s2):
            self.s1, self.s2 = s1, s2
        def write(self, d):
            self.s1.write(d); self.s2.write(d); self.s1.flush(); self.s2.flush()
        def flush(self):
            self.s1.flush(); self.s2.flush()

    tee = TeeTextIO(output_capture, sys.__stdout__)

    with contextlib.redirect_stdout(tee), contextlib.redirect_stderr(tee):
        try:
            required = ['host', 'ssh_user', 'ssh_password', 's1_install_path',
                        'instance_num', 'dg_name', 'gather_port', 'obs1_keyword2']
            missing = [k for k in required if not data.get(k)]
            if missing:
                return jsonify({"status": "error", "message": f"필수 항목 누락: {missing}", "log": ""}), 400

            from installer.executor_dgs import run_dgs_add
            exit_code = run_dgs_add(
                host=data['host'],
                port=int(data.get('port') or 22),
                ssh_user=data['ssh_user'],
                ssh_password=data['ssh_password'],
                s1_install_path=data['s1_install_path'],
                instance_num=int(data['instance_num']),
                dg_name=data['dg_name'],
                gather_port=data['gather_port'],
                obs1_keyword2=data['obs1_keyword2'],
                dgm_install_path=data['dgm_install_path'],
            )

            if exit_code != 0:
                return jsonify({"status": "error", "message": f"생성 실패 (exit {exit_code})", "log": output_capture.getvalue()}), 500

            return jsonify({"status": "success", "message": "DataGather_S 생성 완료", "log": output_capture.getvalue()})

        except Exception as e:
            print(f"[ERROR] {e}")
            return jsonify({"status": "error", "message": str(e), "log": output_capture.getvalue()}), 500


@app.route('/api/patch', methods=['POST', 'OPTIONS'])
def api_patch():
    if request.method == 'OPTIONS':
        return '', 200

    data = request.json
    if not data:
        return jsonify({"error": "No payload provided"}), 400

    output_capture = io.StringIO()

    class TeeTextIO:
        def __init__(self, s1, s2):
            self.s1, self.s2 = s1, s2
        def write(self, d):
            self.s1.write(d); self.s2.write(d); self.s1.flush(); self.s2.flush()
        def flush(self):
            self.s1.flush(); self.s2.flush()

    tee = TeeTextIO(output_capture, sys.__stdout__)

    with contextlib.redirect_stdout(tee), contextlib.redirect_stderr(tee):
        try:
            archive_raw = data.get('archive_path')
            if not archive_raw:
                return jsonify({"status": "error", "message": "No archive_path provided", "log": ""}), 400

            archive_path = Path(archive_raw)
            if not archive_path.is_file():
                return jsonify({"status": "error", "message": f"Archive not found: {archive_path}", "log": ""}), 400

            search_root = data.get('search_root', '').strip()
            if not search_root:
                return jsonify({"status": "error", "message": "No search_root provided", "log": ""}), 400

            ssh_user = data.get('ssh_user', '')
            ssh_password = data.get('ssh_password', '')
            host = data.get('host', '')
            port = int(data.get('port') or 22)

            from installer.executor_patch import run_patch
            exit_code, patched_entries, used_suffix = run_patch(
                archive_path=archive_path,
                host=host,
                port=port,
                ssh_user=ssh_user,
                ssh_password=ssh_password,
                search_root=search_root,
                backup_suffix=data.get('backup_suffix') or None,
            )

            status = "success" if exit_code == 0 else "error"
            msg = "패치 완료" if exit_code == 0 else f"패치 중 오류 발생 (exit code {exit_code})"
            patched_filenames = sorted({entry.get("filename", "") for entry in patched_entries if entry.get("filename")})
            history_job = save_patch_job(
                component_key=data.get('component_key') or data.get('agent_type') or 'unknown',
                component_label=data.get('component_label') or data.get('component_key') or data.get('agent_type') or 'Unknown',
                agent_type=data.get('agent_type') or '',
                host=host,
                port=port,
                search_root=search_root,
                archive_name=archive_path.name,
                backup_suffix=used_suffix,
                status=status,
                patched_entries=patched_entries,
            )
            return jsonify({
                "status": status,
                "message": msg,
                "log": output_capture.getvalue(),
                "patched_filenames": patched_filenames,
                "patched_entries": patched_entries,
                "backup_suffix": used_suffix,
                "job_id": history_job.get("job_id") if history_job else None,
            })

        except Exception as e:
            traceback.print_exc()
            return jsonify({"status": "error", "message": str(e), "log": output_capture.getvalue()}), 500


@app.route('/api/rollback/list', methods=['POST', 'OPTIONS'])
def api_rollback_list():
    if request.method == 'OPTIONS':
        return '', 200

    data = request.json
    if not data:
        return jsonify({"error": "No payload provided"}), 400

    output_capture = io.StringIO()

    class TeeTextIO:
        def __init__(self, s1, s2):
            self.s1, self.s2 = s1, s2
        def write(self, d):
            self.s1.write(d); self.s2.write(d); self.s1.flush(); self.s2.flush()
        def flush(self):
            self.s1.flush(); self.s2.flush()

    tee = TeeTextIO(output_capture, sys.__stdout__)

    with contextlib.redirect_stdout(tee), contextlib.redirect_stderr(tee):
        try:
            search_root = data.get('search_root', '').strip()
            if not search_root:
                return jsonify({"status": "error", "message": "No search_root provided", "log": ""}), 400

            host = data.get('host', '')
            port = int(data.get('port') or 22)
            component_key = data.get('component_key') or None
            job_id = data.get('job_id') or None
            use_recent_history = bool(data.get('use_recent_history'))

            history_job = None
            history_jobs = []
            if use_recent_history or job_id:
                history_job = find_recent_patch_job(
                    host=host,
                    port=port,
                    search_root=search_root,
                    component_key=component_key,
                    job_id=job_id,
                )
                history_jobs = list_recent_patch_jobs(
                    host=host,
                    port=port,
                    search_root=search_root,
                    component_key=component_key,
                    limit=int(data.get('history_limit') or 10),
                )

            if history_job:
                backups = history_job_to_backups(history_job)
                print(f"[Rollback] Loaded recent patch history job: {history_job.get('job_id')}")
                return jsonify({
                    "status": "success",
                    "backups": backups,
                    "log": output_capture.getvalue(),
                    "source": "history",
                    "history_jobs": [
                        {
                            "job_id": job.get("job_id"),
                            "created_at": job.get("created_at"),
                            "component_key": job.get("component_key"),
                            "component_label": job.get("component_label"),
                            "backup_suffix": job.get("backup_suffix"),
                            "status": job.get("status"),
                            "archive_name": job.get("archive_name"),
                        }
                        for job in history_jobs
                    ],
                    "history_job": {
                        "job_id": history_job.get("job_id"),
                        "created_at": history_job.get("created_at"),
                        "component_key": history_job.get("component_key"),
                        "component_label": history_job.get("component_label"),
                        "backup_suffix": history_job.get("backup_suffix"),
                        "status": history_job.get("status"),
                    },
                })

            from installer.executor_rollback import list_backups
            backups = list_backups(
                host=host,
                port=port,
                ssh_user=data.get('ssh_user', ''),
                ssh_password=data.get('ssh_password', ''),
                search_root=search_root,
                filenames=data.get('filenames') or [],
            )
            return jsonify({
                "status": "success",
                "backups": backups,
                "log": output_capture.getvalue(),
                "source": "scan",
                "history_jobs": [],
                "history_job": None,
            })
        except Exception as e:
            traceback.print_exc()
            return jsonify({"status": "error", "message": str(e), "log": output_capture.getvalue()}), 500


@app.route('/api/rollback/run', methods=['POST', 'OPTIONS'])
def api_rollback_run():
    if request.method == 'OPTIONS':
        return '', 200

    data = request.json
    if not data:
        return jsonify({"error": "No payload provided"}), 400

    output_capture = io.StringIO()

    class TeeTextIO:
        def __init__(self, s1, s2):
            self.s1, self.s2 = s1, s2
        def write(self, d):
            self.s1.write(d); self.s2.write(d); self.s1.flush(); self.s2.flush()
        def flush(self):
            self.s1.flush(); self.s2.flush()

    tee = TeeTextIO(output_capture, sys.__stdout__)

    with contextlib.redirect_stdout(tee), contextlib.redirect_stderr(tee):
        try:
            rollback_targets = data.get('rollback_targets', [])
            if not rollback_targets:
                return jsonify({"status": "error", "message": "No rollback_targets provided", "log": ""}), 400

            from installer.executor_rollback import run_rollback
            exit_code = run_rollback(
                host=data.get('host', ''),
                port=int(data.get('port') or 22),
                ssh_user=data.get('ssh_user', ''),
                ssh_password=data.get('ssh_password', ''),
                rollback_targets=rollback_targets,
            )
            status = "success" if exit_code == 0 else "error"
            msg = "롤백 완료" if exit_code == 0 else f"롤백 중 오류 발생 (exit code {exit_code})"
            save_rollback_logs(
                component_key=data.get('component_key'),
                component_label=data.get('component_label'),
                host=data.get('host', ''),
                port=int(data.get('port') or 22),
                search_root=data.get('search_root'),
                job_id=data.get('job_id'),
                rollback_targets=rollback_targets,
                status=status,
            )
            return jsonify({"status": status, "message": msg, "log": output_capture.getvalue()})
        except Exception as e:
            traceback.print_exc()
            return jsonify({"status": "error", "message": str(e), "log": output_capture.getvalue()}), 500


if __name__ == '__main__':
    # Check for API Key but don't crash, just warn so the UI can handle it or the user can set it later
    if not os.environ.get("GEMINI_API_KEY"):
        print("WARNING: GEMINI_API_KEY environment variable is not set. NL parsing will fail. Please check your .env file.")
    print("Starting Flask Backend on port 5050...")
    app.run(host='0.0.0.0', port=5050, debug=True, use_reloader=False)
