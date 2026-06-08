import os
import time
from pathlib import Path

def run_linux_install(script_path: Path, runtime_os: str, host: str, port: int, install_path: str, extra_vars: dict[str, str], extracted_dir: Path, tar_path: Path, install_updater: bool = False) -> int:
    try:
        import paramiko
    except ImportError:
        print("[ERROR] 'paramiko' is missing. Please run: pip install paramiko")
        return -1
        
    user = None
    password = None

    # Priority 1: Strict keys
    for k, v in extra_vars.items():
        kl = k.lower()
        if kl in ("ssh_user", "ssh user", "ssh-user"): user = v
        if kl in ("ssh_password", "ssh password", "ssh-password"): password = v

    # Priority 2: Loose keys, but avoid DB credentials
    if not user or not password:
        for k, v in extra_vars.items():
            kl = k.lower()
            vl = str(v).lower()
            if not user and ("id" in kl or "user" in kl or "계정" in kl or "유저" in kl) and "db" not in kl and "ssh" not in kl:
                if vl not in ("postgres", "oracle", "tibero", "mysql"): user = v
            if not password and ("pw" in kl or "pass" in kl or "비번" in kl or "패스워드" in kl) and "db" not in kl and "ssh" not in kl:
                if vl not in ("postgres", "oracle", "tibero", "mysql"): password = v

    user = user or "root"
    password = password or ""
            
    port = int(port) if port else 22
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"[SSH] Connecting to {host}:{port} as {user}...")
    try:
        ssh.connect(host, port=port, username=user, password=password, timeout=10)
    except Exception as e:
        print(f"[SSH ERROR] Connection failed: {e}")
        return -1
        
    print("[SSH] Running Oracle Auto-Discovery (Linux)...")
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
        try:
            print("[SSH] Attempting to auto-discover IPC_KEY via oradebug...")
            db_owner = extra_vars.get("DB_OWNER", "oracle")
            sh_cmd = f"export ORACLE_HOME={extra_vars['ORACLE_HOME']}; export ORACLE_SID={extra_vars['ORACLE_SID']}; export PATH=$ORACLE_HOME/bin:$PATH; "
            
            # Create a sql script to run oradebug commands
            sql_script = "oradebug setmypid\noradebug ipc\noradebug tracefile_name\nexit\n"
            ssh.exec_command(f"echo '{sql_script}' > /tmp/get_ipc.sql")
            ssh.exec_command(f"chmod 777 /tmp/get_ipc.sql")
            
            # Execute sqlplus to get trace file path directly (since maxgauge has dba group)
            stdin, stdout, stderr = ssh.exec_command(sh_cmd + "sqlplus -S '/ as sysdba' @/tmp/get_ipc.sql")
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
            print(f"  => [WARNING] Auto-discover IPC_KEY failed: {e}")

    # Find Listener Port and IP (from tnslsnr or lsnrctl)
    if not extra_vars.get("LISTENER_IP_PORT"):
        lsnr_found = False
        if extra_vars.get("ORACLE_HOME"):
            # Try lsnrctl status without su
            cmd = f"sh -c 'export ORACLE_HOME={extra_vars['ORACLE_HOME']}; export PATH=$ORACLE_HOME/bin:$PATH; lsnrctl status 2>/dev/null'"
            stdin, stdout, stderr = ssh.exec_command(cmd)
            lsnr_out = stdout.read().decode('utf-8', errors='ignore')
            
            match = re.search(r'\(ADDRESS=\(PROTOCOL=tcp\)\(HOST=([^)]+)\)\(PORT=([0-9]+)\)\)', lsnr_out, re.IGNORECASE)
            if match:
                host_ip = match.group(1).strip()
                port_num = match.group(2).strip()
                # hostname(비IP)이면 SSH 연결 대상 IP로 대체
                if not re.match(r'^\d+\.\d+\.\d+\.\d+$', host_ip):
                    host_ip = host
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
            stdin, stdout, stderr = ssh.exec_command("netstat -tlnp 2>/dev/null | grep tnslsnr | head -n 1")
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
        
    if script_path is not None:
        # Standard installer: script exists locally, calculate remote path
        if extracted_dir:
            rel_script = script_path.relative_to(extracted_dir).as_posix()

            target_home = extra_vars.get("MXG_HOME")
            conf_name = extra_vars.get("CONF_NAME", "")

            if target_home:
                if conf_name and not target_home.endswith(conf_name):
                    final_target = f"{target_home.rstrip('/')}/{conf_name}"
                else:
                    final_target = target_home

                extra_vars["MXG_HOME"] = final_target

                top_dir = rel_script.split('/')[0] if '/' in rel_script else ""
                if top_dir:
                    print(f"[SSH] Moving extracted folder (including hidden files) to {final_target}...")
                    stdin, stdout, stderr = ssh.exec_command(f"mkdir -p {final_target} && cp -a {remote_base}/{top_dir}/. {final_target}/")
                    stdout.channel.recv_exit_status()
                    part = rel_script[len(top_dir)+1:]
                    remote_script_path = f"{final_target}/{part}"
                else:
                    stdin, stdout, stderr = ssh.exec_command(f"mkdir -p {final_target} && cp -a {remote_base}/. {final_target}/")
                    stdout.channel.recv_exit_status()
                    remote_script_path = f"{final_target}/{rel_script}"
            else:
                remote_script_path = f"{remote_base}/{rel_script}"
        else:
            remote_script_path = f"{remote_base}/{script_path.name}"
    else:
        # Package-type tar: auto-select matching .pkg.tar.gz on remote server
        print("[SSH] Package-type tar detected — auto-selecting platform package on remote server...")
        stdin, stdout, stderr = ssh.exec_command("uname -m")
        remote_arch = stdout.read().decode('utf-8', errors='ignore').strip() or "x86_64"

        oracle_ver_hint = ""
        oracle_home = extra_vars.get("ORACLE_HOME", "")
        if oracle_home:
            m = re.search(r'/(\d+)\.\d+', oracle_home)
            if m:
                oracle_ver_hint = m.group(1)

        select_cmd = f"""
set -e
ARCH="{remote_arch}"
BASE="{remote_base}"
PKG_LIST=$(find "$BASE" -name "*.linux.$ARCH.*.pkg.tar.gz" 2>/dev/null | sort)
SELECTED=""
if [ -n "{oracle_ver_hint}" ]; then
    SELECTED=$(echo "$PKG_LIST" | grep "\\.{oracle_ver_hint}[0-9]*\\.pkg\\.tar\\.gz" | head -1)
fi
[ -z "$SELECTED" ] && SELECTED=$(echo "$PKG_LIST" | head -1)
if [ -z "$SELECTED" ]; then
    echo "PKG_ERROR:No matching package found for linux/$ARCH"
    exit 1
fi
echo "PKG_SELECTED:$SELECTED"
PKG_DIR="$BASE/pkg_extracted"
mkdir -p "$PKG_DIR"
cd "$PKG_DIR"
tar -xzf "$SELECTED" 2>/dev/null || gzip -dc "$SELECTED" | tar -xf -
INSTALL_SH=$(find "$PKG_DIR" -name "install.sh" | head -1)
if [ -z "$INSTALL_SH" ]; then
    echo "PKG_ERROR:No install.sh found in package $SELECTED"
    exit 1
fi
echo "PKG_SCRIPT:$INSTALL_SH"
"""
        stdin, stdout, stderr = ssh.exec_command(select_cmd)
        pkg_out = stdout.read().decode('utf-8', errors='ignore')
        print(f"[SSH] Package selection output:\n{pkg_out.strip()}")

        if "PKG_ERROR" in pkg_out:
            err = next((l for l in pkg_out.splitlines() if "PKG_ERROR" in l), "Unknown error")
            print(f"[SSH ERROR] {err}")
            return -1

        remote_script_path = None
        for line in pkg_out.splitlines():
            if line.startswith("PKG_SCRIPT:"):
                remote_script_path = line[len("PKG_SCRIPT:"):].strip()
                break

        if not remote_script_path:
            print("[SSH ERROR] Could not determine remote install script path from package")
            return -1

        print(f"[SSH] Selected install script: {remote_script_path}")

        # install.sh 실행 전 패키지 파일을 MXG_HOME으로 복사
        mxg_home_val = extra_vars.get("MXG_HOME", "")
        conf_name_val = extra_vars.get("CONF_NAME", "")
        if mxg_home_val:
            if conf_name_val and not mxg_home_val.endswith("/" + conf_name_val):
                final_mxg = f"{mxg_home_val.rstrip('/')}/{conf_name_val}"
            else:
                final_mxg = mxg_home_val
            extra_vars["MXG_HOME"] = final_mxg

            pkg_extracted_dir = f"{remote_base}/pkg_extracted"
            rel_in_pkg = remote_script_path[len(pkg_extracted_dir):].lstrip("/")
            pkg_top_dir = rel_in_pkg.split("/")[0]
            rel_install_script = "/".join(rel_in_pkg.split("/")[1:])

            print(f"[SSH] Copying package contents to MXG_HOME: {final_mxg}...")
            stdin, stdout, stderr = ssh.exec_command(
                f"mkdir -p '{final_mxg}' && cp -a '{pkg_extracted_dir}/{pkg_top_dir}/.' '{final_mxg}/'"
            )
            if stdout.channel.recv_exit_status() != 0:
                print(f"[SSH ERROR] Failed to copy package to MXG_HOME: {stderr.read().decode('utf-8', errors='ignore')}")
                return -1

            remote_script_path = f"{final_mxg}/{rel_install_script}"
            print(f"[SSH] Install script in MXG_HOME: {remote_script_path}")

    print(f"[SSH] Handing over logic. Executing INTERACTIVE remote script: {remote_script_path}")
    
    conf_name_for_mxgrc = extra_vars.get("CONF_NAME", "")
    target_home_for_mxgrc = extra_vars.get("MXG_HOME", "")
    
    if target_home_for_mxgrc and conf_name_for_mxgrc and target_home_for_mxgrc.endswith("/" + conf_name_for_mxgrc):
         target_home_for_mxgrc = target_home_for_mxgrc[:-len("/" + conf_name_for_mxgrc)]
         
    if target_home_for_mxgrc:
        print(f"[SSH] Updating MXG_HOME and CONF_NAME in .mxgrc BEFORE install...")
        final_target_val = extra_vars.get("MXG_HOME", target_home_for_mxgrc)
        # Use a more robust sed pattern that handles both 'NAME=' and 'export NAME='
        update_mxgrc_sh = f"""
        for MXG_FILE in "{final_target_val}/.mxgrc" "{target_home_for_mxgrc}/.mxgrc"; do
            if [ -f "$MXG_FILE" ]; then
                echo "[SSH] Found .mxgrc at $MXG_FILE, updating MXG_HOME and CONF_NAME..."
                # 1. Handle MXG_HOME
                sed -i 's|^MXG_HOME=.*|MXG_HOME={target_home_for_mxgrc}/{conf_name_for_mxgrc}|g' "$MXG_FILE"
                sed -i 's|^export MXG_HOME=.*|export MXG_HOME={target_home_for_mxgrc}/{conf_name_for_mxgrc}|g' "$MXG_FILE"
                # 2. Handle CONF_NAME
                sed -i 's|^CONF_NAME=.*|CONF_NAME={conf_name_for_mxgrc}|g' "$MXG_FILE"
                sed -i 's|^export CONF_NAME=.*|export CONF_NAME={conf_name_for_mxgrc}|g' "$MXG_FILE"
            fi
        done
        """
        stdin, stdout, stderr = ssh.exec_command(update_mxgrc_sh)
        stdout.channel.recv_exit_status()
        
        source_mxgrc_path = final_target_val
        source_mxgrc_alt = target_home_for_mxgrc

    # ── Updater: set MXG_UPDATER_ENABLED=1 in mxgrc before installation ──
    if install_updater and target_home_for_mxgrc and conf_name_for_mxgrc:
        mxgrc_path = f"{target_home_for_mxgrc}/{conf_name_for_mxgrc}/mxgrc"
        print(f"[SSH] [Updater] Enabling MXG_UPDATER_ENABLED=1 in {mxgrc_path}...")
        update_cmd = f"""
if [ -f "{mxgrc_path}" ]; then
    if grep -q 'MXG_UPDATER_ENABLED' "{mxgrc_path}"; then
        sed -i 's/^export MXG_UPDATER_ENABLED=.*/export MXG_UPDATER_ENABLED=1/g' "{mxgrc_path}"
        sed -i 's/^MXG_UPDATER_ENABLED=.*/MXG_UPDATER_ENABLED=1/g' "{mxgrc_path}"
        echo "[Updater] MXG_UPDATER_ENABLED set to 1"
    else
        echo "export MXG_UPDATER_ENABLED=1" >> "{mxgrc_path}"
        echo "[Updater] MXG_UPDATER_ENABLED=1 appended to mxgrc"
    fi
else
    echo "[Updater][WARNING] mxgrc not found at {mxgrc_path} — skipping"
fi
"""
        stdin, stdout, stderr = ssh.exec_command(update_cmd)
        out = stdout.read().decode('utf-8', errors='ignore').strip()
        print(f"  => {out}")
        stdout.channel.recv_exit_status()

    channel = ssh.invoke_shell()
    channel.resize_pty(width=200, height=50)
    
    # === Linux Original Logic (No sleep, single command) ===
    import posixpath
    script_dir = posixpath.dirname(remote_script_path)
    script_name = posixpath.basename(remote_script_path)
    
    exports = []
    if install_path:
        exports.append(f"export INSTALL_PATH='{install_path}'")
        
    # 1. Define internal keys to skip exporting (keep essential ones like ORACLE_HOME)
    internal_keys = {"SSH_USER", "SSH_PASSWORD", "SSH_PASS", "VERSION", "IPC_KEY"}
    
    for k, v in extra_vars.items():
        if k.upper() in internal_keys or k in internal_keys:
            continue
        exports.append(f"export {k}='{v}'")
        
    ex_str = " ; ".join(exports)
    
    # 2. Update .mxgrc if paths are provided
    if target_home_for_mxgrc:
        channel.send("set -a\n")
        time.sleep(0.2)
        # Load existing .mxgrc if it exists
        channel.send(f"test -f {source_mxgrc_path}/.mxgrc && . {source_mxgrc_path}/.mxgrc\n")
        time.sleep(0.1)
        channel.send(f"test -f {source_mxgrc_alt}/.mxgrc && . {source_mxgrc_alt}/.mxgrc\n")
        time.sleep(0.2)
        
        # Override with our specific variables
        channel.send(f"export MXG_HOME='{target_home_for_mxgrc}/{conf_name_for_mxgrc}'\n")
        channel.send(f"export CONF_NAME='{conf_name_for_mxgrc}'\n")
        channel.send("set +a\n")
        time.sleep(0.2)
        
    # Oracle discovery environment
    if extra_vars.get("ORACLE_HOME"):
        channel.send(f"export PATH=$PATH:{extra_vars['ORACLE_HOME']}/bin\n")
        time.sleep(0.1)
    
    # Send the main exports
    if ex_str:
        channel.send(f"{ex_str}\n")
        time.sleep(0.2)

    channel.send(f"cd {script_dir}\n")
    time.sleep(0.2)
    channel.send(f"chmod +x ./{script_name}\n")
    time.sleep(0.5)
    
    # Determine remote OS for script execution
    # This part assumes 'remote_os_uname' is available, which is not in the original code.
    # For now, I'll assume 'runtime_os' from function arguments can be used as a proxy or
    # that 'remote_os_uname' would be defined elsewhere. If not, this will cause an error.
    # Assuming 'runtime_os' is the intended variable for OS type check.
    # Send the execution command
    channel.send("\n")
    time.sleep(0.5)
    if "hp-ux" in runtime_os.lower():
        channel.send(f"ksh ./{script_name} ; exit $?\n")
    else:
        channel.send(f"./{script_name} ; exit $?\n")
    
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
            # 쉘 종료로 소켓이 닫힌 경우 로그로 성공 여부 판단
            if "End Install.sh" in buffer or "End install.sh" in buffer:
                print("[SSH] Install script completed — treating as success despite socket close.")
                exit_status = 0
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
                else:
                    for num, key in matches:
                        if key != "0x00000000":
                            selected = num
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
                ans = ""
                # 프롬프트에서 표시된 옵션 파싱: LISTENER INFO: [ opt1|opt2|... ]
                opts_match = re.search(r'LISTENER INFO:\s*\[\s*([^\]]+)\s*\]', buffer)
                if opts_match:
                    opts = [o.strip() for o in opts_match.group(1).split('|') if o.strip()]
                    # x.x.x.x:port 형식의 옵션 우선 선택
                    ip_port_opts = [o for o in opts if re.match(r'^\d+\.\d+\.\d+\.\d+:\d+$', o)]
                    if ip_port_opts:
                        matching = [o for o in ip_port_opts if o.startswith(f"{host}:")]
                        ans = matching[0] if matching else ip_port_opts[0]
                if not ans:
                    stored = extra_vars.get("LISTENER_IP_PORT", "")
                    if stored and re.match(r'^\d+\.\d+\.\d+\.\d+:\d+$', stored):
                        ans = stored
                    elif stored and ":" in stored:
                        ans = f"{host}:{stored.split(':')[-1]}"
                if not ans:
                    ans = f"{host}:1521"
                channel.send(ans + "\n")
                buffer = ""
            elif "RTS TCP Port number" in buffer and "]" in buffer and buffer.strip().endswith("]"):
                channel.send(extra_vars.get("RTS_PORT", "5080") + "\n")
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
                channel.send("2\n") # 2 is Linux
                buffer = ""
            elif "run run_by_sys ?" in buffer and buffer.strip().endswith("]"):
                channel.send("y\n")
                buffer = ""
            elif install_updater and (
                buffer.strip().endswith("(y/n)") or
                buffer.strip().endswith("[y/n]") or
                (buffer.strip().endswith("]") and "?" in buffer.split("\n")[-3:])
            ):
                # Updater 활성화 시 처리되지 않은 yes/no 프롬프트는 모두 y로 응답
                print(f"[Updater] Auto-answering unmatched prompt with 'y'")
                channel.send("y\n")
                buffer = ""

        if channel.exit_status_ready() and not channel.recv_ready():
            exit_status = channel.recv_exit_status()
            break
        else:
            time.sleep(0.1)
            
    print(f"\n[SSH] ✅ Remote installation (Linux) finished with code: {exit_status}")
    
    print(f"[SSH] Cleaning up remote temporary files...")
    stdin, stdout, stderr = ssh.exec_command(f"rm -rf {remote_base}")
    stdout.channel.recv_exit_status()
    ssh.close()
    return exit_status
