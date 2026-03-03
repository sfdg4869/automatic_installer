from installer.archive import extract_tar
from installer.executor_daemon import detect_runtime_os, find_install_script, run_install_script
from installer.prompt import prompt_install_config


def main() -> int:
    print("=== Automatic Installer ===")
    config = prompt_install_config()

    runtime_os = detect_runtime_os() if config.os_choice == "auto" else config.os_choice
    print(f"[INFO] Runtime OS: {runtime_os}")

    extracted_dir = extract_tar(config.tar_path)
    print(f"[INFO] Extracted to: {extracted_dir}")

    script_path = find_install_script(
        extracted_dir=extracted_dir,
        runtime_os=runtime_os,
        preferred_script=config.script_name,
    )
    print(f"[INFO] Installer script: {script_path}")

    exit_code = run_install_script(
        script_path=script_path,
        runtime_os=runtime_os,
        host=config.host,
        port=config.port,
        install_path=config.install_path,
        extra_vars=config.extra_vars,
        extracted_dir=extracted_dir,
        tar_path=config.tar_path,
    )
    if exit_code != 0:
        print(f"[ERROR] Install script failed with exit code: {exit_code}")
        return exit_code

    print("[INFO] Installation completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
