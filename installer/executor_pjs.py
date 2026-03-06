import os
import posixpath
import re
import time
from pathlib import Path

def run_pjs_install(script_path: Path | None, runtime_os: str, host: str, port: int, install_path: str, extra_vars: dict[str, str], extracted_dir: Path | None, tar_path: Path | None) -> int:
    try:
        import paramiko
    except ImportError:
        print("[ERROR] 'paramiko' is missing. Please run: pip install paramiko")
        return -1
        
    user = None
    password = None

    # First, try strict keys
    for k, v in extra_vars.items():
        k_lower = k.lower()
        if k_lower in ("ssh_user", "ssh user", "ssh-user"):
            user = v
        if k_lower in ("ssh_password", "ssh password", "ssh-password"):
            password = v

    # Fallback to loose keys, but strictly avoiding DB credentials
    if not user:
        for k, v in extra_vars.items():
            k_lower = k.lower()
            v_lower = str(v).lower()
            if ("id" in k_lower or "user" in k_lower or "계정" in k_lower or "유저" in k_lower) and "db" not in k_lower and "database" not in k_lower and "ssh" not in k_lower:
                if v_lower not in ("postgres", "oracle", "tibero", "mysql"):
                    user = v
                    break
    if not password:
        for k, v in extra_vars.items():
            k_lower = k.lower()
            v_lower = str(v).lower()
            if ("pw" in k_lower or "pass" in k_lower or "비번" in k_lower or "패스워드" in k_lower) and "db" not in k_lower and "database" not in k_lower and "ssh" not in k_lower:
                if v_lower not in ("postgres", "oracle", "tibero", "mysql"):
                    password = v
                    break
    user = user or "root"
            
    port = int(port) if port else 22
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"[SSH] Connecting to {host}:{port} as {user}...")
    try:
        ssh.connect(host, port=port, username=user, password=password, timeout=10)
    except Exception as e:
        print(f"[SSH ERROR] Connection failed: {e}")
        return -1
        
    print("[SSH] Running Auto-Discovery for missing PJS settings...")
    
    def exists_in_vars(*keys):
        for k in keys:
            for ek, ev in extra_vars.items():
                if k.lower() in ek.lower() and ev:
                    return True
        return False
    
    # 1. DB_IP Auto Discovery (default to install target host)
    if not exists_in_vars("db_ip", "database ip", "database server"):
        extra_vars["DB_IP"] = host
        print(f"  => Auto-discovered DB_IP (Target Host): {extra_vars['DB_IP']}")

    # 2. DB_NAME (SID) Auto Discovery via ps -ef (Oracle)
    if not exists_in_vars("db_name", "database name", "sid", "database_sid"):
        stdin, stdout, stderr = ssh.exec_command("ps -ef | grep ora_pmon | grep -v grep")
        pmon_lines = stdout.read().decode('utf-8', errors='ignore').strip().split('\n')
        if pmon_lines and pmon_lines[0]:
            match = re.search(r'(ora_pmon_[^\s]+)', pmon_lines[0])
            if match:
                extra_vars["DB_NAME"] = match.group(1).replace("ora_pmon_", "")
                print(f"  => Auto-discovered DB_NAME (SID) via pmon: {extra_vars['DB_NAME']}")

    # 3. DB_PORT (Listener Port) Auto Discovery via netstat (Oracle)
    if not exists_in_vars("db_port", "database port"):
        stdin, stdout, stderr = ssh.exec_command("netstat -tlnp 2>/dev/null | grep tnslsnr | head -n 1")
        lsnr_line = stdout.read().decode('utf-8', errors='ignore').strip()
        if lsnr_line:
            port_match = re.search(r':(\d+)\s', lsnr_line)
            if not port_match:
                port_match = re.search(r'\d+\.\d+\.\d+\.\d+:(\d+)', lsnr_line)
            if port_match:
                extra_vars["DB_PORT"] = port_match.group(1)
                print(f"  => Auto-discovered DB_PORT via netstat tnslsnr: {extra_vars['DB_PORT']}")

        
    print(f"[SSH] Connected! Uploading '{tar_path.name}' to remote server...")
    remote_base = install_path if install_path else "/tmp/auto_installer_pjs"
    ssh.exec_command(f"mkdir -p {remote_base}")
    
    try:
        from scp import SCPClient
        
        transport = ssh.get_transport()
        transport.window_size = 2147483647
        transport.packetizer.REKEY_BYTES = pow(2, 40)
        transport.packetizer.REKEY_PACKETS = pow(2, 40)
        
        def progress(filename, size, sent):
            pass 
            
        with SCPClient(transport, progress=progress) as scp_client:
            remote_tar = f"{remote_base}/{tar_path.name}"
            scp_client.put(str(tar_path), remote_tar)
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[SSH ERROR] Fast SCP Upload failed: {e}")
        return -1
        
    print(f"[SSH] Extracting on remote server: {host} into {remote_base}...")
    if tar_path.name.endswith('.gz'):
        fallback_cmd = (
            f"cd {remote_base} && "
            "export PATH=$PATH:/usr/local/bin:/usr/contrib/bin:/opt/iexpress/gzip/bin:/opt/freeware/bin && "
            f"( gzip -dc '{tar_path.name}' 2>/dev/null | tar -xf - || "
            f"gunzip -c '{tar_path.name}' 2>/dev/null | tar -xf - || "
            f"tar -zxf '{tar_path.name}' 2>/dev/null )"
        )
        stdin, stdout, stderr = ssh.exec_command(fallback_cmd)
    else:
        stdin, stdout, stderr = ssh.exec_command(f"cd {remote_base} && tar -xf '{tar_path.name}'")
    
    exit_status = stdout.channel.recv_exit_status()
    if exit_status != 0:
        print(f"[SSH ERROR] Remote extraction failed:\n{stderr.read().decode('utf-8', errors='ignore')}")
        return exit_status
        
    print(f"[SSH] Extraction complete. Executing configuration.sh...")
    
    channel = ssh.invoke_shell()
    channel.resize_pty(width=200, height=50)
    
    exports = []
    skip_keys = {"SSH_USER", "SSH_PASSWORD", "SSH_PASS"}
    for k, v in extra_vars.items():
        if k in skip_keys:
            continue
        exports.append(f"export {k}='{v}'")
        
    ex_str = " ; ".join(exports)

    if ex_str:
        channel.send(f"{ex_str}\n")
        time.sleep(0.2)

    channel.send(f"cd {remote_base}\n")
    time.sleep(0.2)
    # The extracted folder might have a subfolder. Find configuration.sh
    channel.send(f"CONF_SCRIPT=$(find . -name 'configuration.sh' | head -n 1)\n")
    time.sleep(0.2)
    # Execute the script and mark exit status
    cmd = "if [ -n \"$CONF_SCRIPT\" ]; then cd \"$(dirname \"$CONF_SCRIPT\")\"; chmod +x configuration.sh; ./configuration.sh; else echo 'configuration.sh not found'; fi; echo EXIT_MARKER_$?\n"
    channel.send(cmd)
    
    buffer = ""
    exit_status = -1
    last_processed_len = 0
    
    def gv(*keys, default=""):
        for k in keys:
            if k in extra_vars and extra_vars[k]:
                return extra_vars[k]
        for ek, ev in extra_vars.items():
            for k in keys:
                if k.lower() in ek.lower():
                    return ev
        return default
    
    while True:
        try:
            if channel.recv_ready():
                data = channel.recv(4096).decode('utf-8', errors='ignore')
                print(data, end="", flush=True)
                buffer += data
                
                # Check if it's waiting for input (no new data after sleep-check)
                if not channel.recv_ready():
                    time.sleep(0.5) # Wait a bit to ensure full prompt is printed
                    if not channel.recv_ready() and len(buffer) > last_processed_len:
                        current_view = buffer[last_processed_len:]
                        
                        if "Select Number :" in current_view:
                            if "Repository DB Type" in current_view:
                                db_type = gv("db_type", "database type", "database_type", default="").lower()
                                if "oracle" in db_type:
                                    print("\n[AI Macro] Pressing '2' (Oracle) for DB Type...", flush=True)
                                    channel.send("2\n")
                                else:
                                    print("\n[AI Macro] Pressing '1' (PostgreSQL) for DB Type...", flush=True)
                                    channel.send("1\n")
                            # 2. Main Menu
                            elif "Configurations" in current_view and "Exit" in current_view:
                                menu_appearances = buffer.count("Select Number :")
                                if menu_appearances == 1:
                                    print("\n[AI Macro] Pressing '1' (Configurations)...", flush=True)
                                    channel.send("1\n")
                                else:
                                    print("\n[AI Macro] Pressing '0' (Exit)...", flush=True)
                                    channel.send("0\n")
                            else:
                                print("\n[AI Macro] Unknown Select Number menu, pressing Enter...", flush=True)
                                channel.send("\n")
                            last_processed_len = len(buffer)
                            
                        elif "Input Text :" in current_view:
                            # It's a configuration step
                            step_match = re.search(r'Step\s+\d+\.\s+(.*?)\s*\[', current_view)
                            if step_match:
                                question = step_match.group(1).strip().lower()
                                answer = ""
                                
                                # Exact PJS mappings using case-insensitive check
                                if "datagather ip" in question: answer = gv("dg_ip", "datagather ip", "datagather_ip")
                                elif "datagather port" in question: answer = gv("dg_port", "datagather port", "datagather_port")
                                elif "database server" in question or "database ip" in question or "db ip" in question: answer = gv("db_ip", "database server", "database ip", "database_ip")
                                elif "database port" in question or "db port" in question: answer = gv("db_port", "database port", "database_port")
                                elif "database name" in question or "db name" in question or "sid" in question: answer = gv("db_name", "database name", "database_name", "sid", "database sid", "database_sid")
                                elif "database user" in question or "db user" in question: answer = gv("db_user", "database user", "database_user")
                                elif "password" in question or "db password" in question: answer = gv("db_password", "database password", "database_password", "db_pass", "db password")
                                elif "service port" in question or "pjs port" in question: answer = gv("pjs_port", "service port", "service_port", "pjs port", "pjs_port")
                                
                                # Remove aggressive fallback scanning which causes incorrect answers
                                if answer:
                                    print(f"\n[AI Macro] Answering '{question}' with: {answer}", flush=True)
                                    channel.send(f"{answer}\n")
                                else:
                                    print(f"\n[AI Macro] No answer found for '{question}', pressing Enter (Default)", flush=True)
                                    channel.send("\n")
                            else:
                                print(f"\n[AI Macro] Unrecognized Input Text prompt, pressing Enter", flush=True)
                                channel.send("\n")
                                
                            last_processed_len = len(buffer)
                            
                        elif "press enter to continue" in current_view.lower() or "press any key to continue" in current_view.lower():
                            print("\n[AI Macro] Pressing Enter to continue...", flush=True)
                            channel.send("\n")
                            last_processed_len = len(buffer)
                            
        except Exception as e:
            print(f"\n[SSH] Channel closed or read error: {e}")
            break
            
        m = re.search(r'EXIT_MARKER_(\d+)', buffer)
        if m:
            exit_status = int(m.group(1))
            break
        
        if channel.exit_status_ready() and not channel.recv_ready():
            exit_status = channel.recv_exit_status()
            break
        else:
            time.sleep(0.1)
            
    print(f"\n[SSH] ✅ Remote PJS installation finished with raw code: {exit_status}")
    if exit_status == 1 and "### Saved ###" in buffer:
        print("[SSH] Tollerating exit code 1 as success since configuration was saved.")
        exit_status = 0
    ssh.close()
    return exit_status
