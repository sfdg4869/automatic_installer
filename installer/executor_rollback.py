import re
from datetime import datetime


def list_backups(host: str, port: int, ssh_user: str, ssh_password: str, search_root: str, filenames: list = None) -> dict:
    try:
        import paramiko
    except ImportError:
        print("[ERROR] 'paramiko' is missing. Please run: pip install paramiko")
        return {}

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"[Rollback] Connecting to {host}:{port} as {ssh_user}...")
    try:
        ssh.connect(host, port=int(port), username=ssh_user, password=ssh_password, timeout=10)
    except Exception as e:
        print(f"[Rollback][SSH ERROR] Connection failed: {e}")
        return {}

    print(f"[Rollback] Searching for backups under: {search_root}")
    if filenames:
        name_conditions = " -o ".join(f"-name '{f}_bak*'" for f in filenames)
        cmd = f"find '{search_root}' \\( {name_conditions} \\) -type f 2>/dev/null"
    else:
        cmd = f"find '{search_root}' -name '*_bak*' -type f 2>/dev/null"

    stdin, stdout, stderr = ssh.exec_command(cmd)
    raw = stdout.read().decode("utf-8", errors="ignore").strip()
    stdout.channel.recv_exit_status()
    ssh.close()

    result = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue

        parts = line.rsplit("/", 1)
        dir_part = parts[0] if len(parts) == 2 else ""
        fname_part = parts[-1]
        match = re.search(r"_bak(.+)$", fname_part)
        if not match:
            continue

        suffix_str = match.group(1)
        original_filename = fname_part[:match.start()]
        original_path = f"{dir_part}/{original_filename}" if dir_part else original_filename

        path_segments = original_path.strip("/").split("/")
        display_name = "/".join(path_segments[-2:]) if len(path_segments) >= 2 else original_filename

        date_match = re.match(r"^(\d{2})(\d{2})(\d{2})$", suffix_str)
        if date_match:
            label = f"20{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
        else:
            label = suffix_str

        result.setdefault(original_path, []).append({
            "date": suffix_str,
            "label": label,
            "backup_path": line,
            "original_path": original_path,
            "display_name": display_name,
        })

    for original_path in result:
        result[original_path].sort(key=lambda entry: entry["date"])

    if result:
        print(f"[Rollback] Found backups for {len(result)} file(s):")
        for orig_path, entries in result.items():
            print(f"  {orig_path}: {[entry['label'] for entry in entries]}")
    else:
        print("[Rollback] No backup files found.")

    return result


def run_rollback(host: str, port: int, ssh_user: str, ssh_password: str, rollback_targets: list) -> int:
    try:
        import paramiko
    except ImportError:
        print("[ERROR] 'paramiko' is missing. Please run: pip install paramiko")
        return -1

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"[Rollback] Connecting to {host}:{port} as {ssh_user}...")
    try:
        ssh.connect(host, port=int(port), username=ssh_user, password=ssh_password, timeout=10)
    except Exception as e:
        print(f"[Rollback][SSH ERROR] Connection failed: {e}")
        return -1

    overall_ok = True

    for target in rollback_targets:
        backup_path = target.get("backup_path", "")
        original_path = target.get("original_path", "")
        if not backup_path or not original_path:
            print(f"[Rollback][WARNING] Skipping invalid target: {target}")
            continue

        filename = original_path.split("/")[-1]
        rollback_suffix = datetime.now().strftime("%y%m%d_%H%M%S")
        current_backup_path = f"{original_path}_bak_rollback_{rollback_suffix}"
        target["preserved_current_path"] = current_backup_path

        print(f"\n[Rollback] -- {filename} --")
        print(f"  Preserving current file as: {current_backup_path}")
        print(f"  Restoring from: {backup_path}")
        print(f"  Restoring to  : {original_path}")

        cmd = (
            f"mv '{original_path}' '{current_backup_path}'"
            f" && cp '{backup_path}' '{original_path}'"
        )
        stdin, stdout, stderr = ssh.exec_command(cmd)
        rc = stdout.channel.recv_exit_status()
        if rc != 0:
            err = stderr.read().decode("utf-8", errors="ignore").strip()
            print(f"  [ERROR] Rollback failed (rc={rc}): {err}")
            target["preserved_current_path"] = None
            overall_ok = False
        else:
            print(f"  Preserved current file: {current_backup_path}")
            print(f"  Restored OK: {original_path}")

    ssh.close()

    if overall_ok:
        print("\n[Rollback] All files restored successfully.")
        return 0

    print("\n[Rollback] Completed with some errors.")
    return 1
