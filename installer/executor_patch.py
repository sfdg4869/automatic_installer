import tarfile
import zipfile
import tempfile
import shutil
from datetime import datetime
from pathlib import Path


def _prepare_patch_files(archive_path: Path) -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="auto_patch_"))
    name = archive_path.name.lower()

    if name.endswith(".tar.gz") or name.endswith(".tgz") or name.endswith(".tar"):
        with tarfile.open(archive_path) as tar:
            tar.extractall(temp_dir)
    elif name.endswith(".zip"):
        with zipfile.ZipFile(archive_path) as z:
            z.extractall(temp_dir)
    elif name.endswith(".jar"):
        shutil.copy2(archive_path, temp_dir / archive_path.name)
    else:
        raise ValueError(f"Unsupported archive format: {archive_path.name}")

    return temp_dir


def run_patch(
    archive_path: Path,
    host: str,
    port: int,
    ssh_user: str,
    ssh_password: str,
    search_root: str,
    backup_suffix: str | None = None,
) -> tuple[int, list[dict], str]:
    try:
        import paramiko
    except ImportError:
        print("[ERROR] 'paramiko' is missing. Please run: pip install paramiko")
        return -1

    # 1. Extract archive locally to get the file list
    print(f"[Patch] Preparing patch input: {archive_path.name}")
    try:
        temp_dir = _prepare_patch_files(archive_path)
    except Exception as e:
        print(f"[Patch][ERROR] Failed to prepare patch input: {e}")
        return -1, [], ""

    patch_files = [f for f in temp_dir.rglob("*") if f.is_file()]
    if not patch_files:
        print("[Patch][ERROR] No files found in archive.")
        return -1, [], ""

    print(f"[Patch] {len(patch_files)} file(s) found in archive:")
    for f in patch_files:
        print(f"  - {f.name}")

    # 2. SSH connect
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"[Patch] Connecting to {host}:{port} as {ssh_user}...")
    try:
        ssh.connect(host, port=int(port), username=ssh_user, password=ssh_password, timeout=10)
    except Exception as e:
        print(f"[Patch][SSH ERROR] Connection failed: {e}")
        return -1, [], ""

    suffix = backup_suffix.strip() if backup_suffix and backup_suffix.strip() else f"bak{datetime.now().strftime('%y%m%d')}"
    overall_ok = True
    patched_entries = []

    try:
        from scp import SCPClient
        transport = ssh.get_transport()
        transport.window_size = 2147483647
        transport.packetizer.REKEY_BYTES = pow(2, 40)
        transport.packetizer.REKEY_PACKETS = pow(2, 40)
    except ImportError:
        print("[ERROR] 'scp' is missing. Please run: pip install scp")
        ssh.close()
        return -1, [], suffix

    for local_file in patch_files:
        filename = local_file.name
        print(f"\n[Patch] ── {filename} ──")

        # 3. Find matching file on remote server
        stdin, stdout, stderr = ssh.exec_command(
            f"find '{search_root}' -name '{filename}' -type f 2>/dev/null"
        )
        found_raw = stdout.read().decode("utf-8", errors="ignore").strip()
        stdout.channel.recv_exit_status()

        found_paths = [p for p in found_raw.splitlines() if p.strip()]
        if not found_paths:
            print(f"  [WARNING] '{filename}' not found under '{search_root}' — skipping")
            continue

        print(f"  Found {len(found_paths)} match(es):")
        for p in found_paths:
            print(f"    {p}")

        # 4. Upload new file to /tmp on remote
        remote_tmp = f"/tmp/_patch_{filename}"
        print(f"  Uploading to remote /tmp...")
        try:
            with SCPClient(transport) as scp:
                scp.put(str(local_file), remote_tmp)
        except Exception as e:
            print(f"  [ERROR] Upload failed: {e}")
            overall_ok = False
            continue

        # 5. Backup old file and replace with new one
        for remote_path in found_paths:
            backup_path = f"{remote_path}_{suffix}"
            print(f"  Backing up  : {remote_path}")
            print(f"          → {backup_path}")

            # Backup
            stdin, stdout, stderr = ssh.exec_command(f"mv '{remote_path}' '{backup_path}'")
            rc = stdout.channel.recv_exit_status()
            if rc != 0:
                err = stderr.read().decode("utf-8", errors="ignore").strip()
                print(f"  [ERROR] Backup failed (rc={rc}): {err}")
                overall_ok = False
                continue

            # Copy new file preserving permissions from backup
            stdin, stdout, stderr = ssh.exec_command(
                f"cp '{remote_tmp}' '{remote_path}'"
                f" && chmod --reference='{backup_path}' '{remote_path}' 2>/dev/null || true"
            )
            rc = stdout.channel.recv_exit_status()
            if rc != 0:
                err = stderr.read().decode("utf-8", errors="ignore").strip()
                print(f"  [ERROR] Replace failed (rc={rc}): {err}")
                overall_ok = False
            else:
                print(f"  Replaced OK : {remote_path}")
                patched_entries.append({
                    "filename": filename,
                    "original_path": remote_path,
                    "backup_path": backup_path,
                    "display_name": _display_name(remote_path),
                })

        # Cleanup remote tmp file
        ssh.exec_command(f"rm -f '{remote_tmp}'")

    ssh.close()

    if overall_ok:
        print("\n[Patch] All files patched successfully.")
        return 0, patched_entries, suffix
    else:
        print("\n[Patch] Completed with some errors.")
        return 1, patched_entries, suffix


def _display_name(original_path: str) -> str:
    path_segments = original_path.strip("/").split("/")
    if len(path_segments) >= 2:
        return "/".join(path_segments[-2:])
    return path_segments[-1] if path_segments else original_path
