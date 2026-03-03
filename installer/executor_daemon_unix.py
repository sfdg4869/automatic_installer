import os
from pathlib import Path

def run_unix_install(script_path: Path, runtime_os: str, host: str, port: int, install_path: str, extra_vars: dict[str, str], extracted_dir: Path, tar_path: Path) -> int:
    try:
        import paramiko
    except ImportError:
        print("[ERROR] 'paramiko' is missing. Please run: pip install paramiko")
        return -1
        
    user = extra_vars.get("SSH_USER", "root")
    password = ""
    for k, v in extra_vars.items():
        if "pw" in k.lower() or "password" in k.lower():
            password = v
        if "id" == k.lower() or "user" in k.lower() or "ssh_user" == k.lower():
            user = v
            
    port = int(port) if port else 22
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"[SSH] Connecting to {host}:{port} as {user}...")
    try:
        ssh.connect(host, port=port, username=user, password=password, timeout=10)
    except Exception as e:
        print(f"[SSH ERROR] Connection failed: {e}")
        return -1
        
    print("[SSH] Running Oracle Auto-Discovery & OS Detection (Unix)...")
    stdin, stdout, stderr = ssh.exec_command("uname -s")
    remote_os_uname = stdout.read().decode('utf-8', errors='ignore').strip().lower()
    print(f"  => Remote OS detected: {remote_os_uname}")

    import re
    # Extract Oracle version from tar file name (e.g. 11204, 19300)
    oracle_version_hint = ""
    match_ver = re.search(r'\.(1[0-9]{3,4})\.', tar_path.name)
    if match_ver:
        oracle_version_hint = match_ver.group(1)
        print(f"  => Deduced Oracle Version Hint from tar: {oracle_version_hint}")
        
    # Find DB Owner and PMON
    stdin, stdout, stderr = ssh.exec_command("ps -ef | grep ora_pmon | grep -v grep")
    pmon_lines = stdout.read().decode('utf-8', errors='ignore').strip().split('\n')
    
    selected_pmon_line = ""
    if pmon_lines and pmon_lines[0]:
        if oracle_version_hint:
            for line in pmon_lines:
                if oracle_version_hint in line:
                    selected_pmon_line = line
                    break
        
        if not selected_pmon_line:
            selected_pmon_line = pmon_lines[0]
            
    if selected_pmon_line and not extra_vars.get("DB_OWNER"):
        extra_vars["DB_OWNER"] = selected_pmon_line.split()[0]
        print(f"  => Auto-discovered DB_OWNER: {extra_vars['DB_OWNER']}")
        
    if selected_pmon_line and not extra_vars.get("PMON_NAME"):
        match = re.search(r'(ora_pmon_[^\s]+)', selected_pmon_line)
        if match:
            extra_vars["PMON_NAME"] = match.group(1)
            print(f"  => Auto-discovered PMON_NAME: {extra_vars['PMON_NAME']}")

    if extra_vars.get("PMON_NAME") and not extra_vars.get("ORACLE_SID"):
        extra_vars["ORACLE_SID"] = extra_vars["PMON_NAME"].replace("ora_pmon_", "")
        print(f"  => Auto-deduced ORACLE_SID: {extra_vars['ORACLE_SID']}")

    if not extra_vars.get("CONF_NAME") and extra_vars.get("ORACLE_SID"):
        extra_vars["CONF_NAME"] = extra_vars["ORACLE_SID"]
        print(f"  => Auto-deduced CONF_NAME: {extra_vars['CONF_NAME']}")

    if extra_vars.get("ORACLE_SID"):
        # Try oratab first
        stdin, stdout, stderr = ssh.exec_command(f"cat /etc/oratab /var/opt/oracle/oratab 2>/dev/null | grep '^{extra_vars.get('ORACLE_SID')}:' | cut -d: -f2 | head -n 1")
        out2 = stdout.read().decode('utf-8', errors='ignore').strip()
        if out2 and "/" in out2:
            extra_vars["ORACLE_HOME"] = out2
            print(f"  => Auto-discovered ORACLE_HOME via oratab: {extra_vars['ORACLE_HOME']}")
            
    if extra_vars.get("DB_OWNER") and not extra_vars.get("ORACLE_HOME"):
        # Prevent hang with < /dev/null if it prompts for a password
        stdin, stdout, stderr = ssh.exec_command(f"su - {extra_vars['DB_OWNER']} -c 'echo $ORACLE_HOME' < /dev/null")
        out = stdout.read().decode('utf-8', errors='ignore').strip()
        if out and "/" in out and not "Password:" in out:
            extra_vars["ORACLE_HOME"] = out.split('\n')[-1].strip()
            print(f"  => Auto-discovered ORACLE_HOME via su: {extra_vars['ORACLE_HOME']}")
        
        if not extra_vars.get("ORACLE_HOME"):
            print("  => [WARNING] ORACLE_HOME could not be auto-discovered. The install script might fail.")

    # Find IPC_KEY via oradebug always (to override any old pasted values)
    if extra_vars.get("ORACLE_HOME") and extra_vars.get("ORACLE_SID"):
        old_ipc = extra_vars.get("IPC_KEY", "")
        extra_vars["IPC_KEY"] = ""  # Clear it so we don't use a wrong pasted value if discovery fails
        try:
            print(f"[SSH] Attempting to auto-discover IPC_KEY via oradebug (old value was '{old_ipc}')...")
            sh_cmd = f"source ~/.profile 2>/dev/null || . ~/.profile 2>/dev/null; export ORACLE_HOME={extra_vars['ORACLE_HOME']}; export ORACLE_SID={extra_vars['ORACLE_SID']}; export PATH=$ORACLE_HOME/bin:$PATH; "
            
            # Create a sql script to run oradebug commands (using simple echo to avoid EOF issues)
            ssh.exec_command("echo 'oradebug setmypid' > /tmp/get_ipc.sql; echo 'oradebug ipc' >> /tmp/get_ipc.sql; echo 'oradebug tracefile_name' >> /tmp/get_ipc.sql; echo 'exit' >> /tmp/get_ipc.sql")
            ssh.exec_command("chmod 777 /tmp/get_ipc.sql")
            
            # Execute sqlplus to get trace file path directly (capture stderr too)
            stdin, stdout, stderr = ssh.exec_command(sh_cmd + "sqlplus -S '/ as sysdba' @/tmp/get_ipc.sql 2>&1")
            sql_out = stdout.read().decode('utf-8', errors='ignore').strip()
            
            # Look for trace file path
            trace_match = re.search(r'(/.*\.trc)', sql_out, re.IGNORECASE)
            if trace_match:
                trace_file = trace_match.group(1).strip()
                
                # Check trace file for IPC key directly
                read_trace_cmd = f"cat {trace_file} | grep -v '0x00000000' | grep 'skgm overhead!'"
                stdin, stdout, stderr = ssh.exec_command(read_trace_cmd)
                trace_out = stdout.read().decode('utf-8', errors='ignore')
                
                ipc_match = re.search(r'shmid:\s*(0x[0-9a-fA-F]+)', trace_out, re.IGNORECASE)
                if ipc_match:
                    extra_vars["IPC_KEY"] = ipc_match.group(1).lstrip("0x").lstrip("0X")
                    print(f"  => Auto-discovered IPC_KEY: {extra_vars['IPC_KEY']}")
                else:
                    print(f"  => [DEBUG] Found trace_file={trace_file}, but couldn't find IPC_KEY inside it. trace_out: {trace_out[:200]}")
            else:
                print(f"  => [DEBUG] Failed to find trace file path in sql_out. sql_out: {sql_out}")
                    
            ssh.exec_command(f"rm -f /tmp/get_ipc.sql")
        except Exception as e:
            print(f"  => [WARNING] Auto-discover IPC_KEY failed via oradebug: {e}")

        # Fallback to sysresv if oradebug failed
        if not extra_vars.get("IPC_KEY"):
            try:
                print(f"[SSH] Attempting to auto-discover IPC_KEY via sysresv...")
                sh_cmd = f"source ~/.profile 2>/dev/null || . ~/.profile 2>/dev/null; export ORACLE_HOME={extra_vars['ORACLE_HOME']}; export ORACLE_SID={extra_vars['ORACLE_SID']}; export PATH=$ORACLE_HOME/bin:$PATH; "
                stdin, stdout, stderr = ssh.exec_command(sh_cmd + "sysresv")
                sysresv_out = stdout.read().decode('utf-8', errors='ignore')
                
                # regex to grab anything that looks like a hex key after an ID
                sysresv_matches = re.findall(r'(\d+)\s+(0x[0-9a-fA-F]+)', sysresv_out, re.IGNORECASE)
                if sysresv_matches:
                    for _id, key in sysresv_matches:
                        if key.lower() != "0x00000000" and key.lower() != "0x0":
                            extra_vars["IPC_KEY"] = key.lstrip("0x").lstrip("0X")
                    print(f"  => Auto-discovered IPC_KEY via sysresv: {extra_vars['IPC_KEY']}")
                else:
                    print(f"  => [DEBUG] sysresv didn't return keys. output: {sysresv_out[:300]}")
            except Exception as e:
                print(f"  => [WARNING] Auto-discover IPC_KEY failed via sysresv: {e}")

    # Find Listener Port and IP (from tnslsnr or lsnrctl)
    if not extra_vars.get("LISTENER_IP_PORT"):
        lsnr_found = False
        if extra_vars.get("ORACLE_HOME"):
            # Try lsnrctl status without su (often works if world-executable)
            cmd = f"sh -c 'export ORACLE_HOME={extra_vars['ORACLE_HOME']}; export PATH=$ORACLE_HOME/bin:$PATH; lsnrctl status 2>/dev/null'"
            stdin, stdout, stderr = ssh.exec_command(cmd)
            lsnr_out = stdout.read().decode('utf-8', errors='ignore')
            
            match = re.search(r'\(ADDRESS=\(PROTOCOL=tcp\)\(HOST=([^)]+)\)\(PORT=([0-9]+)\)\)', lsnr_out, re.IGNORECASE)
            if match:
                host_ip = match.group(1).strip()
                port_num = match.group(2).strip()
                extra_vars["LISTENER_IP_PORT"] = f"{host_ip}:{port_num}"
                print(f"  => Auto-discovered LISTENER via lsnrctl: {extra_vars['LISTENER_IP_PORT']}")
                lsnr_found = True

            # If failed, try reading listener.ora
            if not lsnr_found:
                cmd = f"cat {extra_vars['ORACLE_HOME']}/network/admin/listener.ora 2>/dev/null"
                stdin, stdout, stderr = ssh.exec_command(cmd)
                ora_out = stdout.read().decode('utf-8', errors='ignore')
                
                # Match (PORT = 1722)
                port_match = re.search(r'\(PORT\s*=\s*([0-9]+)\)', ora_out, re.IGNORECASE)
                host_match = re.search(r'\(HOST\s*=\s*([^)]+)\)', ora_out, re.IGNORECASE)
                if port_match:
                    port_num = port_match.group(1).strip()
                    host_ip = host_match.group(1).strip() if host_match else host
                    extra_vars["LISTENER_IP_PORT"] = f"{host_ip}:{port_num}"
                    print(f"  => Auto-discovered LISTENER via listener.ora: {extra_vars['LISTENER_IP_PORT']}")
                    lsnr_found = True
                
        if not lsnr_found:
            stdin, stdout, stderr = ssh.exec_command("netstat -an | grep LISTEN | grep tnslsnr | head -n 1")
            lsnr_line = stdout.read().decode('utf-8', errors='ignore').strip()
            if lsnr_line:
                match = re.search(r'\d+\.\d+\.\d+\.\d+:\d+', lsnr_line)
                if match:
                    extra_vars["LISTENER_IP_PORT"] = match.group(0)
                    print(f"  => Auto-discovered LISTENER via netstat: {extra_vars['LISTENER_IP_PORT']}")
        
    print(f"[SSH] Connected! Uploading original tar format '{tar_path.name}' to remote server using FAST SCP Mode...")
    remote_base = "/tmp/auto_installer_remote"
    ssh.exec_command(f"rm -rf {remote_base} && mkdir -p {remote_base}")
    
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
        
    print(f"[SSH] Extracting on remote server: {host}...")
    if tar_path.name.endswith('.gz'):
        tar_no_gz = tar_path.name.replace('.gz', '')
        fallback_cmd = (
            f"cd '{remote_base}' && "
            "export PATH=/usr/gnu/bin:/usr/sfw/bin:/usr/local/bin:/usr/contrib/bin:/opt/iexpress/gzip/bin:/opt/freeware/bin:$PATH && "
            f"gunzip -f '{tar_path.name}' && tar -xf '{tar_no_gz}'"
        )
        stdin, stdout, stderr = ssh.exec_command(fallback_cmd)
    else:
        stdin, stdout, stderr = ssh.exec_command(f"cd '{remote_base}' && tar -xf '{tar_path.name}'")
    
    exit_status = stdout.channel.recv_exit_status()
    if exit_status != 0:
        print(f"[SSH ERROR] Remote extraction failed:\n{stderr.read().decode('utf-8', errors='ignore')}")
        # Keep going in case it partially succeeded or it's a non-fatal GNU tar warning
        
    if extracted_dir:
        rel_script = script_path.relative_to(extracted_dir).as_posix()
        
        target_home = extra_vars.get("MXG_HOME", "").strip()
        conf_name = extra_vars.get("CONF_NAME", "").strip()
        
        if target_home:
            if conf_name and not target_home.endswith(conf_name):
                final_target = f"{target_home.rstrip('/')}/{conf_name}"
            else:
                final_target = target_home
            
            extra_vars["MXG_HOME"] = final_target

            top_dir = rel_script.split('/')[0] if '/' in rel_script else ""
            if top_dir:
                print(f"[SSH] Copying extracted folder to {final_target}...")
                parent_dir = "/".join(final_target.split("/")[:-1])
                # Solaris strict permission bug workaround: try normal mkdir first which doesn't check root traversal, then fallback to mkdir -p
                mv_cmd = f"([ -d '{final_target}' ] || mkdir '{final_target}' 2>/dev/null || mkdir -p '{final_target}') && cp -R {remote_base}/{top_dir}/* '{final_target}/'"
                stdin, stdout, stderr = ssh.exec_command(mv_cmd)
                mv_st = stdout.channel.recv_exit_status()
                if mv_st != 0:
                    print(f"  => [DEBUG] CP failed. cmd: {mv_cmd} | stderr: {stderr.read().decode('utf-8', errors='ignore')}")
                    # Extra debug to prove why Permission Denied happens
                    stdin, stdout, _ = ssh.exec_command(f"id; ls -ld '{parent_dir}' 2>/dev/null || ls -ld $(dirname '{parent_dir}') 2>/dev/null")
                    print(f"  => [DEBUG] OS context: {stdout.read().decode('utf-8').strip()}")
                part = rel_script[len(top_dir)+1:] 
                remote_script_path = f"{final_target}/{part}"
            else:
                cp_cmd = f"([ -d '{final_target}' ] || mkdir '{final_target}' 2>/dev/null || mkdir -p '{final_target}') && cp -R '{remote_base}'/* '{final_target}/'"
                stdin, stdout, stderr = ssh.exec_command(cp_cmd)
                cp_st = stdout.channel.recv_exit_status()
                if cp_st != 0:
                    print(f"  => [DEBUG] CP-* failed. cmd: {cp_cmd} | stderr: {stderr.read().decode('utf-8', errors='ignore')}")
                remote_script_path = f"{final_target}/{rel_script}"
        else:
            remote_script_path = f"{remote_base}/{rel_script}"
    else:
        remote_script_path = f"{remote_base}/{script_path.name}"
        
    # Validation step to save tears
    stdin, stdout, stderr = ssh.exec_command(f"ls -l '{remote_script_path}'")
    if stdout.channel.recv_exit_status() != 0:
        print(f"\n[SSH ERROR] Critical! Script file {remote_script_path} NOT FOUND on remote server.")
        stdin, stdout, _ = ssh.exec_command(f"ls -la '{final_target}' 2>/dev/null")
        print(f"[DEBUG] {final_target} contents:\n{stdout.read().decode('utf-8')[:500]}")

        
    print(f"[SSH] Handing over logic. Executing INTERACTIVE remote script: {remote_script_path}")
    
    conf_name_for_mxgrc = extra_vars.get("CONF_NAME", "")
    target_home_for_mxgrc = extra_vars.get("MXG_HOME", "")
    
    source_cmd = ""
    if target_home_for_mxgrc and conf_name_for_mxgrc and target_home_for_mxgrc.endswith("/" + conf_name_for_mxgrc):
         target_home_for_mxgrc = target_home_for_mxgrc[:-len("/" + conf_name_for_mxgrc)]
         
    if target_home_for_mxgrc:
        print(f"[SSH] Updating MXG_HOME and CONF_NAME in .mxgrc BEFORE install...")
        final_target_val = extra_vars.get("MXG_HOME", target_home_for_mxgrc)
        update_mxgrc_sh = f"""
        for MXG_FILE in "{final_target_val}/.mxgrc" "{target_home_for_mxgrc}/.mxgrc"; do
            if [ -f "$MXG_FILE" ]; then
                echo "[SSH] Found .mxgrc at $MXG_FILE, updating..."
                sed 's!^MXG_HOME=.*!MXG_HOME={target_home_for_mxgrc}/{conf_name_for_mxgrc}!' "$MXG_FILE" > "$MXG_FILE.tmp1" && mv "$MXG_FILE.tmp1" "$MXG_FILE"
                sed 's!^CONF_NAME=.*!CONF_NAME={conf_name_for_mxgrc}!' "$MXG_FILE" > "$MXG_FILE.tmp2" && mv "$MXG_FILE.tmp2" "$MXG_FILE"
                sed 's!^export MXG_HOME=.*!export MXG_HOME={target_home_for_mxgrc}/{conf_name_for_mxgrc}!' "$MXG_FILE" > "$MXG_FILE.tmp3" && mv "$MXG_FILE.tmp3" "$MXG_FILE"
                sed 's!^export CONF_NAME=.*!export CONF_NAME={conf_name_for_mxgrc}!' "$MXG_FILE" > "$MXG_FILE.tmp4" && mv "$MXG_FILE.tmp4" "$MXG_FILE"
            fi
        done
        """
        stdin, stdout, stderr = ssh.exec_command(update_mxgrc_sh)
        stdout.channel.recv_exit_status()
        
        source_mxgrc_path = final_target_val
        source_mxgrc_alt = target_home_for_mxgrc
    
    channel = ssh.invoke_shell()
    channel.resize_pty(width=200, height=50)
    
    import time
    
    skip_keys = {"SSH_USER", "SSH_PASSWORD", "SSH_PASS"}
    
    if install_path:
        channel.send(f"export INSTALL_PATH='{install_path}'\n")
        time.sleep(0.2)
    
    for k, v in extra_vars.items():
        if k in skip_keys:
            continue
        channel.send(f"export {k}='{v}'\n")
        time.sleep(0.2)
    
    if target_home_for_mxgrc:
        channel.send("set -a\n")
        time.sleep(0.2)
        channel.send(f"test -f {source_mxgrc_path}/.mxgrc && . {source_mxgrc_path}/.mxgrc\n")
        time.sleep(0.2)
        channel.send(f"test -f {source_mxgrc_alt}/.mxgrc && . {source_mxgrc_alt}/.mxgrc\n")
        time.sleep(0.2)
        channel.send("set +a\n")
        time.sleep(0.2)
        
    if extra_vars.get("ORACLE_HOME"):
        channel.send(f"export PATH=$PATH:{extra_vars['ORACLE_HOME']}/bin\n")
        time.sleep(0.2)
    
    import posixpath
    script_dir = posixpath.dirname(remote_script_path).strip()
    script_name = posixpath.basename(remote_script_path).strip()
    
    channel.send(f"cd '{script_dir}'\n")
    time.sleep(0.5)
    channel.send(f"chmod +x './{script_name}'\n")
    time.sleep(0.5)
    
    if "hp-ux" in remote_os_uname.lower() or "aix" in remote_os_uname.lower():
        channel.send(f"ksh './{script_name}' ; exit $?\n")
    else:
        channel.send(f"sh './{script_name}' ; exit $?\n")
    
    buffer = ""
    exit_status = -1
    
    while True:
        try:
            if channel.recv_ready():
                data = channel.recv(4096).decode('utf-8', errors='ignore')
                print(data, end="", flush=True)
                buffer += data
        except Exception as e:
            print(f"\n[SSH] Channel closed or read error: {e}")
            break
            
        if channel.recv_ready() or buffer:
            if len(buffer) > 8192:
                buffer = buffer[-8192:]
                
            if "Enter Database owner:" in buffer and buffer.strip().endswith("]"):
                channel.send(extra_vars.get("DB_OWNER", "oracle") + "\n")
                buffer = ""
            elif "Enter Maxgauge conf name:" in buffer and buffer.strip().endswith("]"):
                channel.send(extra_vars.get("CONF_NAME", "") + "\n")
                buffer = ""
            elif "Select EXA type" in buffer and "3: Cloud" in buffer:
                channel.send(extra_vars.get("EXA_TYPE", "0") + "\n")
                buffer = ""
            elif "Select ipc key:" in buffer and buffer.rstrip().endswith(":"):
                target_key = extra_vars.get("IPC_KEY", "").strip()
                if target_key.startswith("0x") or target_key.startswith("0X"):
                    target_key = target_key[2:]
                    
                selected = "1"
                matches = re.findall(r"(\d+)\)\s+(0x[0-9a-fA-F]+)", buffer)
                if target_key:
                    for num, key in matches:
                        clean_key = key[2:] if key.startswith("0x") else key
                        if target_key.lower() == clean_key.lower():
                            selected = num
                            break
                channel.send(selected + "\n")
                buffer = ""
            elif "Select pmon process name:" in buffer and buffer.rstrip().endswith(":"):
                target_pmon = extra_vars.get("PMON_NAME", "")
                selected = "1"
                matches = re.findall(r"(\d+)\)\s+(ora_pmon_[^\s]+)", buffer)
                if target_pmon:
                    for num, name in matches:
                        if target_pmon.lower() in name.lower():
                            selected = num
                            break
                channel.send(selected + "\n")
                buffer = ""
            elif "LISTENER INFO:" in buffer and "]" in buffer and buffer.strip().endswith("]"):
                ans = extra_vars.get("LISTENER_IP_PORT", extra_vars.get("LISTENER_INFO", extra_vars.get("LISTENER_IP", "")))
                if not ans:
                    ans = f"{host}:1521"
                channel.send(ans + "\n")
                buffer = ""
            elif "RTS TCP Port number" in buffer and "]" in buffer and buffer.strip().endswith("]"):
                ans = extra_vars.get("RTS_PORT", extra_vars.get("TCP_PORT", "25081"))
                channel.send(ans + "\n")
                buffer = ""
            elif "DataGather IP Address" in buffer and "]" in buffer and buffer.strip().endswith("]"):
                channel.send(extra_vars.get("GATHER_IP", "127.0.0.1") + "\n")
                buffer = ""
            elif "DataGather Port number" in buffer and "]" in buffer and buffer.strip().endswith("]"):
                channel.send(extra_vars.get("GATHER_PORT", "7001") + "\n")
                buffer = ""
            elif "Oracle sys pass:" in buffer and buffer.rstrip().endswith(":"):
                channel.send(extra_vars.get("SYS_PASS", "1") + "\n")
                buffer = ""
            elif "Oracle maxgauge user:" in buffer and buffer.strip().endswith("]"):
                ans = extra_vars.get("MG_USER", extra_vars.get("MXG_USER", "maxgauge"))
                channel.send(ans + "\n")
                buffer = ""
            elif "Oracle maxgauge pass:" in buffer and buffer.rstrip().endswith(":"):
                ans = extra_vars.get("MG_PASS", extra_vars.get("MXG_PASS", "maxgauge"))
                channel.send(ans + "\n")
                buffer = ""
            elif "RTS version 5.42 or higher ?" in buffer and buffer.strip().endswith("(y/n)"):
                channel.send("y\n")
                buffer = ""
            elif "Default Tablespace for MaxGauge:" in buffer and buffer.strip().endswith("]"):
                channel.send(extra_vars.get("DEF_TS", "") + "\n")
                buffer = ""
            elif "Temporary Tablespace for MaxGauge:" in buffer and buffer.strip().endswith("]"):
                channel.send(extra_vars.get("TMP_TS", "") + "\n")
                buffer = ""
            elif "Create xm$ view in oracle sys account" in buffer and buffer.strip().endswith("]"):
                channel.send("yes\n")
                buffer = ""
            elif "Install expkg package ?" in buffer and buffer.strip().endswith("]"):
                channel.send("y\n")
                buffer = ""
            elif "Make env ?" in buffer and buffer.strip().endswith("]"):
                channel.send("y\n")
                buffer = ""
            elif "Make list.conf ?" in buffer and buffer.strip().endswith("]"):
                channel.send("y\n")
                buffer = ""
            elif "SQL file for list.conf:" in buffer and ".sql" in buffer:
                channel.send("\n")
                buffer = ""
            elif "Auto-Decteted Product type:" in buffer and buffer.strip().endswith("]"):
                channel.send("y\n")
                buffer = ""
            elif "enable_refresh_env_list_conf" in buffer and buffer.strip().endswith("]"):
                channel.send("\n")
                buffer = ""
            elif "ORACLE_SID" in buffer and buffer.strip().endswith("]:"):
                channel.send(extra_vars.get("CONF_NAME", "") + "\n")
                buffer = ""
            elif "ORACLE_HOME" in buffer and buffer.strip().endswith("]:"):
                channel.send("\n")
                buffer = ""
            elif "Press enter for next step." in buffer:
                channel.send("\n")
                buffer = ""
            elif "Make updater configuration files (updater.conf) ?" in buffer and buffer.strip().endswith("]"):
                channel.send("y\n")
                buffer = ""
            elif "Make updater log configuration files (updater_log.conf) ?" in buffer and buffer.strip().endswith("]"):
                channel.send("y\n")
                buffer = ""
            elif "Register updater to common.conf ?" in buffer and buffer.strip().endswith("]"):
                channel.send("y\n")
                buffer = ""
            elif "Is this correct?" in buffer:
                channel.send("y\n")
                buffer = ""
            elif "execute script process ?" in buffer and buffer.strip().endswith("]"):
                channel.send("y\n")
                buffer = ""
            elif "Make conf files (rts.conf) ?" in buffer and buffer.strip().endswith("]"):
                channel.send("y\n")
                buffer = ""
            elif "Select passwd File" in buffer and "]" in buffer and buffer.strip().endswith("]"):
                channel.send("1\n") # 1 is Unix
                buffer = ""
            elif "run run_by_sys ?" in buffer and buffer.strip().endswith("]"):
                channel.send("y\n")
                buffer = ""

        if channel.exit_status_ready() and not channel.recv_ready():
            exit_status = channel.recv_exit_status()
            break
        else:
            time.sleep(0.1)
            
    print(f"\n[SSH] ✅ Remote installation (Unix) finished with code: {exit_status}")
    
    print(f"[SSH] Cleaning up remote temporary files...")
    stdin, stdout, stderr = ssh.exec_command(f"rm -rf {remote_base}")
    stdout.channel.recv_exit_status()
    ssh.close()
    return exit_status
