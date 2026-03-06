from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import io
import sys
import contextlib
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from installer.agent_daemon import parse_install_prompt
from installer.archive import extract_tar
from installer.executor_daemon import detect_runtime_os, find_install_script, run_install_script
from installer.prompt import InstallConfig

app = Flask(__name__)
# Enable CORS for the React frontend
CORS(app)

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
            from installer.router import route_prompt
            agent_type = route_prompt(tar_path.name, extra_vars)
            print(f"[ROUTER] Installation resolved to agent target: {agent_type}")
            
            if agent_type in ("pjs", "dgm", "dgs"):
                script_path = None
            else:
                # 3. Find Script for Daemon/Normal installs
                script_path = find_install_script(
                    extracted_dir=extracted_dir,
                    runtime_os=runtime_os,
                    preferred_script=data.get('script_name'),
                )
                print(f"[INFO] Installer script found: {script_path}")

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


if __name__ == '__main__':
    # Check for API Key but don't crash, just warn so the UI can handle it or the user can set it later
    if not os.environ.get("GEMINI_API_KEY"):
        print("WARNING: GEMINI_API_KEY environment variable is not set. NL parsing will fail. Please check your .env file.")
    print("Starting Flask Backend on port 5050...")
    app.run(host='0.0.0.0', port=5050, debug=True, use_reloader=False)
