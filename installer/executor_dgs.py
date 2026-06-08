import sys


def run_dgs_add(
    host: str,
    port: int,
    ssh_user: str,
    ssh_password: str,
    s1_install_path: str,
    instance_num: int,
    dg_name: str,
    gather_port: str,
    obs1_keyword2: str,
    dgm_install_path: str,
) -> int:
    try:
        import paramiko
    except ImportError:
        print("[ERROR] 'paramiko' is missing. Please run: pip install paramiko")
        return -1

    script = f"""
set -e

echo "[STEP 1] Copy DataGather_S{instance_num}"
S1_DIR=$(find "{s1_install_path}" -maxdepth 3 -type d -name "DGServer_S1" 2>/dev/null | head -n 1)
if [ -z "$S1_DIR" ]; then
    echo "[ERROR] Could not find DGServer_S1 under: {s1_install_path}"
    exit 1
fi
echo "  S1 path: $S1_DIR"

S_BASE=$(dirname "$S1_DIR")
S_NEW="$S_BASE/DGServer_S{instance_num}"

if [ -d "$S_NEW" ]; then
    echo "  [ERROR] Target directory already exists: $S_NEW"
    echo "  Existing DataGather_S{instance_num} will not be deleted. Aborting."
    exit 1
fi

cp -r "$S1_DIR" "$S_NEW"
echo "  Copy complete: $S_NEW"

echo "[STEP 2] Update .mxgrc DG_NAME"
MXGRC="$S_NEW/.mxgrc"
if [ -f "$MXGRC" ]; then
    sed -i "s|^DG_NAME=.*|DG_NAME={dg_name}|g" "$MXGRC"
    echo "  DG_NAME={dg_name}"
else
    echo "  [WARN] .mxgrc file not found, skipping"
fi

echo "[STEP 3] Update conf/DGServer.xml gather_port"
DGXML="$S_NEW/conf/DGServer.xml"
if [ -f "$DGXML" ]; then
    sed -i "s|<gather_port>.*</gather_port>|<gather_port>{gather_port}</gather_port>|g" "$DGXML"
    echo "  gather_port={gather_port}"
else
    echo "  [WARN] conf/DGServer.xml file not found, skipping"
fi

echo "[STEP 4] Update conf/DG/common_linux.conf obs1_keyword2"
CONF="$S_NEW/conf/DG/common_linux.conf"
if [ -f "$CONF" ]; then
    rm -f "${{CONF}}.swp" "${{CONF}}.swn" 2>/dev/null || true
    sed -i "s|^obs1_keyword2=.*|obs1_keyword2={obs1_keyword2}|g" "$CONF"
    echo "  obs1_keyword2={obs1_keyword2}"
else
    echo "  [WARN] conf/DG/common_linux.conf file not found, skipping"
fi

echo "[STEP 5] Update DataGather_M slave_gather_list"
DGM_DIR=$(find "{dgm_install_path}" -maxdepth 3 -type d -name "DGServer_M" 2>/dev/null | head -n 1)
if [ -n "$DGM_DIR" ]; then
    DGM_XML="$DGM_DIR/conf/DGServer.xml"
    if [ -f "$DGM_XML" ]; then
        if grep -q "{host}:{gather_port}" "$DGM_XML"; then
            echo "  {host}:{gather_port} already exists in slave_gather_list, skipping"
        else
            sed -i "s|</slave_gather_list>|,{host}:{gather_port}</slave_gather_list>|g" "$DGM_XML"
            echo "  Added {host}:{gather_port} to DGM slave_gather_list"
        fi
    else
        echo "  [WARN] DGM conf/DGServer.xml file not found, skipping"
    fi
else
    echo "  [WARN] Could not find DGServer_M under: {dgm_install_path}"
fi

echo "[DONE] DataGather_S{instance_num} creation complete"
"""

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(host, port=port, username=ssh_user, password=ssh_password, timeout=30)
        _, stdout, stderr = client.exec_command(script)
        out = stdout.read().decode(errors="replace")
        err = stderr.read().decode(errors="replace")
        exit_code = stdout.channel.recv_exit_status()
        if out:
            print(out)
        if err:
            print(err, file=sys.stderr)
        return exit_code
    except Exception as e:
        print(f"[ERROR] SSH connection failed: {e}")
        return -1
    finally:
        client.close()
