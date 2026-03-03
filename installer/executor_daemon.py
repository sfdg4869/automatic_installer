import os
import platform
import shutil
import subprocess
from pathlib import Path


def detect_runtime_os() -> str:
    system = platform.system().lower()
    if "windows" in system:
        return "windows"
    if "linux" in system:
        return "linux"
    raise RuntimeError(f"Unsupported runtime OS: {platform.system()}")


def find_install_script(extracted_dir: Path, runtime_os: str, preferred_script: str | None) -> Path:
    if preferred_script:
        match = _find_by_name(extracted_dir, preferred_script)
        if match:
            return match
        raise FileNotFoundError(f"Preferred installer script not found: {preferred_script}")

    if runtime_os == "linux":
        candidates = ("install.sh", "setup.sh")
    elif runtime_os == "windows":
        candidates = ("install.bat", "setup.bat", "install.ps1", "setup.ps1")
    else:
        raise RuntimeError(f"Unsupported runtime OS: {runtime_os}")

    for name in candidates:
        match = _find_by_name(extracted_dir, name)
        if match:
            return match

    raise FileNotFoundError(
        f"No installer script found in {extracted_dir}. Tried: {', '.join(candidates)}"
    )


def _find_by_name(root: Path, name: str) -> Path | None:
    lowered = name.lower()
    for path in root.rglob("*"):
        if path.is_file() and path.name.lower() == lowered:
            return path
    return None


def run_install_script(
    script_path: Path,
    runtime_os: str,
    host: str,
    port: int,
    install_path: str,
    extra_vars: dict[str, str],
    extracted_dir: Path | None = None,
    tar_path: Path | None = None,
) -> int:
    if host and host not in ("localhost", "127.0.0.1", "0.0.0.0"):
        return _run_remote_install(script_path, runtime_os, host, port, install_path, extra_vars, extracted_dir, tar_path)

    env = os.environ.copy()
    env.update(
        {
            "INSTALL_HOST": host,
            "INSTALL_PORT": str(port),
            "INSTALL_PATH": install_path,
        }
    )
    env.update(extra_vars)

    command = _build_command(script_path=script_path, runtime_os=runtime_os)
    completed = subprocess.run(command, cwd=script_path.parent, env=env, check=False)
    return completed.returncode


def _run_remote_install(script_path: Path, runtime_os: str, host: str, port: int, install_path: str, extra_vars: dict[str, str], extracted_dir: Path | None, tar_path: Path | None) -> int:
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
        
    print("[SSH] Detecting Remote OS...")
    stdin, stdout, stderr = ssh.exec_command("uname -s")
    remote_os_uname = stdout.read().decode('utf-8', errors='ignore').strip().lower()
    print(f"  => Remote OS: {remote_os_uname}")

    if "linux" in remote_os_uname:
        from installer.executor_daemon_linux import run_linux_install
        return run_linux_install(script_path, remote_os_uname, host, port, install_path, extra_vars, extracted_dir, tar_path)
    else:
        from installer.executor_daemon_unix import run_unix_install
        return run_unix_install(script_path, remote_os_uname, host, port, install_path, extra_vars, extracted_dir, tar_path)


def _build_command(script_path: Path, runtime_os: str) -> list[str]:
    suffix = script_path.suffix.lower()
    script = str(script_path)

    if runtime_os == "linux":
        if suffix == ".sh":
            return ["bash", script]
        raise RuntimeError(f"Unsupported script for linux: {script_path.name}")

    if runtime_os == "windows":
        if suffix == ".bat":
            return ["cmd", "/c", script]
        if suffix == ".ps1":
            powershell = shutil.which("pwsh") or shutil.which("powershell")
            if not powershell:
                raise RuntimeError("PowerShell executable not found for .ps1 script.")
            return [powershell, "-ExecutionPolicy", "Bypass", "-File", script]
        raise RuntimeError(f"Unsupported script for windows: {script_path.name}")

    raise RuntimeError(f"Unsupported runtime OS: {runtime_os}")
