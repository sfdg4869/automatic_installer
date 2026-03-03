import tarfile
import tempfile
from pathlib import Path


def extract_tar(tar_path: Path) -> Path:
    if not tar_path.is_file():
        raise FileNotFoundError(f"tar file not found: {tar_path}")

    temp_dir = Path(tempfile.mkdtemp(prefix="auto_installer_"))
    with tarfile.open(tar_path) as tar:
        tar.extractall(path=temp_dir)
    return temp_dir
