from dataclasses import dataclass
from pathlib import Path
import os
from installer.agent_daemon import parse_install_prompt



@dataclass
class InstallConfig:
    tar_path: Path
    os_choice: str
    host: str
    port: int
    install_path: str
    script_name: str | None
    extra_vars: dict[str, str]


def _ask_non_empty(message: str) -> str:
    while True:
        value = input(message).strip()
        if value:
            return value
        print("[WARN] Value cannot be empty.")


def _ask_port(message: str) -> int:
    while True:
        raw = input(message).strip()
        try:
            value = int(raw)
            if 1 <= value <= 65535:
                return value
        except ValueError:
            pass
        print("[WARN] Enter a valid port (1-65535).")


def _ask_os_choice() -> str:
    while True:
        raw = input("Target OS [auto/linux/windows]: ").strip().lower() or "auto"
        if raw in {"auto", "linux", "windows"}:
            return raw
        print("[WARN] Supported values: auto, linux, windows")


def _parse_extra_vars(raw: str) -> dict[str, str]:
    if not raw.strip():
        return {}

    result: dict[str, str] = {}
    pairs = [item.strip() for item in raw.split(",") if item.strip()]
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"Invalid pair: '{pair}', expected KEY=VALUE")
        key, value = pair.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError("Empty key is not allowed in extra vars.")
        result[key] = value.strip()
    return result


def prompt_install_config() -> InstallConfig:
    print("--------------------------------------------------")
    print("You can type naturally to skip manual prompts!")
    print("Example: 'Desktop의 app.tar 파일을 리눅스로 /opt/myapp 에 설치해. 포트는 8080, DB_USER=root 도 추가해줘.'")
    print("Or press Enter to use the standard manual prompts.")
    print("--------------------------------------------------")
    
    natural_prompt = input("Natural Language Instruction (optional): ").strip()
    
    parsed = None
    if natural_prompt:
        try:
            print("[INFO] Passing instruction to Gemini AI...")
            parsed = parse_install_prompt(natural_prompt)
            print("[INFO] AI Parsing successful!")
        except Exception as e:
            print(f"[WARN] Failed to parse with AI: {e}")
            print("[INFO] Falling back to manual prompts.")
            parsed = None

    # Helper function to ask if missing from parsed
    def ask_if_missing(attr_name, default_asker, *args):
        if parsed is not None and getattr(parsed, attr_name) is not None:
            val = getattr(parsed, attr_name)
            print(f"> {attr_name} set to: {val}")
            return val
        return default_asker(*args)

    # 1. tar_path
    if parsed is not None and parsed.tar_path:
        tar_path = Path(parsed.tar_path).expanduser()
        print(f"> tar_path set to: {tar_path}")
        if not tar_path.is_file():
            print("[WARN] AI parsed tar file not found. Please enter a valid path manually.")
            tar_path = None
    else:
        tar_path = None

    while not tar_path:
        tar_raw = _ask_non_empty("Path to tar file: ")
        t = Path(tar_raw).expanduser()
        if t.is_file():
            tar_path = t
            break
        print("[WARN] tar file not found. Please enter a valid path.")

    # 2. os_choice
    if parsed is not None and parsed.os_choice:
        os_choice = parsed.os_choice.lower()
        if os_choice not in {"auto", "linux", "windows"}:
            os_choice = None
        else:
            print(f"> os_choice set to: {os_choice}")
    else:
        os_choice = None
    
    if not os_choice:
        os_choice = _ask_os_choice()

    # 3. host & port & install_path
    host = ask_if_missing("host", _ask_non_empty, "Server host: ")
    port = ask_if_missing("port", _ask_port, "Server port: ")
    install_path = ask_if_missing("install_path", _ask_non_empty, "Install path: ")

    # 4. script_name
    script_name = None
    if parsed is not None and parsed.script_name:
         script_name = parsed.script_name
         print(f"> script_name set to: {script_name}")
    else:
         script_name_raw = input("Installer script name (optional): ").strip()
         script_name = script_name_raw or None

    # 5. extra_vars
    extra_vars = {}
    if parsed is not None and parsed.extra_vars:
        extra_vars = parsed.extra_vars
        print(f"> extra_vars set to: {extra_vars}")
    else:
        while True:
            extra_raw = input("Extra vars (KEY=VALUE, comma-separated, optional): ").strip()
            try:
                extra_vars = _parse_extra_vars(extra_raw)
                break
            except ValueError as exc:
                print(f"[WARN] {exc}")

    return InstallConfig(
        tar_path=tar_path,
        os_choice=os_choice,
        host=host,
        port=port,
        install_path=install_path,
        script_name=script_name,
        extra_vars=extra_vars,
    )
