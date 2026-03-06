import os
import posixpath
import re
import time
from pathlib import Path

def run_dgm_install(script_path: Path | None, runtime_os: str, host: str, port: int, install_path: str, extra_vars: dict[str, str], extracted_dir: Path | None, tar_path: Path | None) -> int:
    try:
        import paramiko
    except ImportError:
        print("[ERROR] 'paramiko' is missing. Please run: pip install paramiko")
        return -1
        
    user = extra_vars.get("SSH_USER", "root")
    password = extra_vars.get("SSH_PASSWORD", "")
    
    # Fallback to strict matches if explicit ones are not found, making sure to ignore DB variables
    if not password:
        for k, v in extra_vars.items():
            kl = k.lower()
            if kl in ("pw", "password", "pass", "ssh_pass"):
                password = v
                break
    
    if user == "root":
        for k, v in extra_vars.items():
            kl = k.lower()
            if kl in ("id", "user", "ssh_user", "username"):
                user = v
                break
            
    port = int(port) if port else 22
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"[SSH] Connecting to {host}:{port} as {user}...")
    try:
        ssh.connect(host, port=port, username=user, password=password, timeout=10)
    except Exception as e:
        print(f"[SSH ERROR] Connection failed: {e}")
        return -1
        
    print(f"[SSH] Connected! Uploading '{tar_path.name}' to remote server...")
    remote_base = install_path if install_path else "/tmp/auto_installer_dgm"
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
        print(f"[SSH ERROR] Fast SCP Upload failed: {e}")
        return -1
        
    print(f"[SSH] Extracting on remote server: {host} into {remote_base}...")
    if tar_path.name.endswith('.gz') or tar_path.name.endswith('.tgz'):
        stdin, stdout, stderr = ssh.exec_command(f"cd {remote_base} && tar -zxf '{tar_path.name}'")
    else:
        stdin, stdout, stderr = ssh.exec_command(f"cd {remote_base} && tar -xf '{tar_path.name}'")
    
    exit_status = stdout.channel.recv_exit_status()
    if exit_status != 0:
        err_msg = stderr.read().decode('utf-8', errors='ignore')
        print(f"[SSH ERROR] Remote extraction failed:\n{err_msg}")
        return exit_status
        
    print(f"[SSH] Extraction complete. Configuring DGServer_M...")
    
    # Map OS typing
    os_type_map = {
        "linux": "linux64",
        "linux32": "linux32",
        "linux64": "linux64",
        "aix": "aix",
        "hp": "hpia",
        "hppa": "hppa",
        "sun32": "sun32",
        "sun": "sun64"
    }
    input_os = runtime_os.lower()
    os_type_val = os_type_map.get(input_os, "linux64")
    
    # Fallback to get any value from extra_vars
    def gv(*keys, default):
        for k in keys:
            if k in extra_vars and extra_vars[k]:
                return extra_vars[k]
        for ek, ev in extra_vars.items():
            for k in keys:
                if k.lower() in ek.lower():
                    return ev
        return default
    
    # Parse configs from extra_vars
    g_port = gv("gather_port", "Gather Port", default="7000")
    s_list = gv("slave_gather_list", "Slave Gather List", default="127.0.0.1:7001")
    
    # Extract Slave port (e.g. from 127.0.0.1:7001 -> 7001) or get from extra_vars
    s_port = gv("slave_gather_port", "Slave Port", default=s_list.split(":")[-1] if ":" in s_list else "7001")
    
    db_type = gv("database_type", "Database Type", "DB_TYPE", default="oracle")
    db_ip = gv("database_ip", "DB_IP", "Database IP", "Database Server", default="127.0.0.1")
    
    # Set different defaults if postgres
    db_type_lower = db_type.lower().strip()
    is_pg = "postgres" in db_type_lower or db_type_lower == "pg"
    db_port = gv("database_port", "DB_PORT", "Database Port", default="5432" if is_pg else "1521")
    db_sid = gv("database_sid", "DB_NAME", "Database Name", "Database SID", default="postgres" if is_pg else "MFO")
    
    db_user = gv("database_user", "DB_USER", "Database User", default="postgres")
    db_pw = gv("database_password", "DB_PASSWORD", "Database Password", default="postgres")
    tb = gv("tablespace", "Tablespace", default="tablespace_name")
    i_tb = gv("index_tablespace", "Index Tablespace", default="tablespace_name")

    modify_cmd = f"""
# M_DIR Configuration
M_DIR=$(find "{remote_base}" -maxdepth 2 -type d -name "DGServer_M" | head -n 1)
if [ -n "$M_DIR" ]; then
    cd "$M_DIR"
    MXGH="$(pwd)"
    sed -i "s|^MXG_HOME=.*|MXG_HOME=$MXGH|g" .mxgrc
    sed -i "s|^OS_TYPE=.*|OS_TYPE={os_type_val}|g" .mxgrc

    CONF="conf/DGServer.xml"
    if [ -f "$CONF" ]; then
      sed -i "s|<gather_port>.*</gather_port>|<gather_port>{g_port}</gather_port>|g" "$CONF"
      sed -i "s|<slave_gather_list>.*</slave_gather_list>|<slave_gather_list>{s_list}</slave_gather_list>|g" "$CONF"
      sed -i "s|<database_type>.*</database_type>|<database_type>{db_type}</database_type>|g" "$CONF"
      sed -i "s|<database_ip>.*</database_ip>|<database_ip>{db_ip}</database_ip>|g" "$CONF"
      sed -i "s|<database_port>.*</database_port>|<database_port>{db_port}</database_port>|g" "$CONF"
      sed -i "s|<database_sid[^>]*>.*</database_sid>|<database_sid service=\\"false\\">{db_sid}</database_sid>|g" "$CONF"
      sed -i "s|<database_user[^>]*>.*</database_user>|<database_user>{db_user}</database_user>|g" "$CONF"
      sed -i "s|<database_password[^>]*>.*</database_password>|<database_password encrypted=\\"false\\">{db_pw}</database_password>|g" "$CONF"
      sed -i "s|<tablespace>.*</tablespace>|<tablespace>{tb}</tablespace>|g" "$CONF"
      sed -i "s|<index_tablespace>.*</index_tablespace>|<index_tablespace>{i_tb}</index_tablespace>|g" "$CONF"
    fi
else
    echo "DGServer_M directory not found!"
    exit 1
fi

# S1_DIR Configuration
S_DIR=$(find "{remote_base}" -maxdepth 2 -type d -name "DGServer_S1" | head -n 1)
if [ -n "$S_DIR" ]; then
    cd "$S_DIR"
    MXGH="$(pwd)"
    sed -i "s|^MXG_HOME=.*|MXG_HOME=$MXGH|g" .mxgrc
    sed -i "s|^OS_TYPE=.*|OS_TYPE={os_type_val}|g" .mxgrc

    CONF="conf/DGServer.xml"
    if [ -f "$CONF" ]; then
      sed -i "s|<gather_port>.*</gather_port>|<gather_port>{s_port}</gather_port>|g" "$CONF"
      sed -i "s|<slave_gather_list>.*</slave_gather_list>|<slave_gather_list>{s_list}</slave_gather_list>|g" "$CONF"
      sed -i "s|<database_type>.*</database_type>|<database_type>{db_type}</database_type>|g" "$CONF"
      sed -i "s|<database_ip[^>]*>.*</database_ip>|<database_ip>{db_ip}</database_ip>|g" "$CONF"
      sed -i "s|<database_port[^>]*>.*</database_port>|<database_port>{db_port}</database_port>|g" "$CONF"
      sed -i "s|<database_sid[^>]*>.*</database_sid>|<database_sid service=\\"false\\">{db_sid}</database_sid>|g" "$CONF"
      sed -i "s|<database_user[^>]*>.*</database_user>|<database_user>{db_user}</database_user>|g" "$CONF"
      sed -i "s|<database_password[^>]*>.*</database_password>|<database_password encrypted=\\"false\\">{db_pw}</database_password>|g" "$CONF"
      sed -i "s|<tablespace>.*</tablespace>|<tablespace>{tb}</tablespace>|g" "$CONF"
      sed -i "s|<index_tablespace>.*</index_tablespace>|<index_tablespace>{i_tb}</index_tablespace>|g" "$CONF"
    fi
else
    echo "DGServer_S1 directory not found, skipping..."
fi
"""
    print("[SSH] Modifying .mxgrc and conf/DGServer.xml for BOTH DGServer_M and DGServer_S1...")
    stdin, stdout, stderr = ssh.exec_command(modify_cmd)
    exit_status = stdout.channel.recv_exit_status()
    if exit_status != 0:
        print("[SSH WARNING] Configuration file modification encountered an issue:")
        print(stderr.read().decode('utf-8', errors='ignore'))
        
    print(f"[SSH] Starting interactive installation via dgsctl...")
    channel = ssh.invoke_shell()
    channel.resize_pty(width=200, height=50)
    
    channel.send(f"M_DIR=$(find \"{remote_base}\" -maxdepth 2 -type d -name \"DGServer_M\" | head -n 1)\n")
    time.sleep(0.5)
    channel.send(f"cd \"$M_DIR\"\n")
    time.sleep(0.5)
    channel.send(". ./.mxgrc\n")
    time.sleep(0.5)
    channel.send("cd bin\n")
    time.sleep(0.5)
    channel.send("./dgsctl\n")
    
    buffer = ""
    last_processed_len = 0
    menu_state = 0 # 0: main, 1: install menu
    
    while True:
        try:
            if channel.recv_ready():
                data = channel.recv(4096).decode('utf-8', errors='ignore')
                print(data, end="", flush=True)
                buffer += data
                
                if not channel.recv_ready():
                    time.sleep(0.5)
                    if not channel.recv_ready() and len(buffer) > last_processed_len:
                        current_view = buffer[last_processed_len:]
                        
                        if "[5] install" in current_view.lower() or ("install" in current_view.lower() and "[5]" in current_view):
                            if menu_state == 0:
                                print("\n[AI Macro] Detected Main Menu. Pressing '5' (install)...", flush=True)
                                channel.send("5\n")
                                menu_state = 1
                            elif menu_state == 3:
                                # Sometimes the big menu reprints, sometimes it doesn't.
                                pass 
                            last_processed_len = len(buffer)
                            
                        elif "dgsctl>" in current_view.lower() and menu_state == 3:
                            print("\n[AI Macro] Detected returned DGSCTL prompt. Pressing '8' (quit)...", flush=True)
                            channel.send("8\n")
                            menu_state = 4
                            time.sleep(0.5)
                            channel.send("exit\n")
                            last_processed_len = len(buffer)
                            
                        elif "Install Menu" in current_view and "Exit" in current_view and "Install Repository" in current_view:
                            if menu_state == 1:
                                print("\n[AI Macro] Detected Install Menu. Pressing '1' (Install Repository)...", flush=True)
                                channel.send("1\n")
                                menu_state = 2
                            elif menu_state == 2:
                                print("\n[AI Macro] Installation finished, returned to Install Menu. Pressing '0' (Exit)...", flush=True)
                                channel.send("0\n")
                                menu_state = 3
                            last_processed_len = len(buffer)
                            
                        elif "change index" in current_view.lower() and "(y/n)" in current_view.lower():
                            print("\n[AI Macro] Answering 'Y' to change index question...", flush=True)
                            channel.send("Y\n")
                            last_processed_len = len(buffer)
                            
                        elif "Press Any Key" in current_view.title() or "Press Enter" in current_view.title():
                            channel.send("\n")
                            last_processed_len = len(buffer)

        except Exception as e:
            print(f"\n[SSH ERROR] Channel closed or read error: {e}")
            break

        if channel.exit_status_ready() and not channel.recv_ready():
            break
        else:
            time.sleep(0.1)
            
    print(f"\n[SSH] ✅ Remote DGM installation finished.")
    ssh.close()
    return 0
