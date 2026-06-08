import os
import re
from typing import Optional

from openai import OpenAI
from pydantic import BaseModel, Field


class InstallConfigSchema(BaseModel):
    tar_path: Optional[str] = Field(
        description="The path to the tar file. If it refers to a real world concept like 'Desktop', it should be represented as '~/Desktop/filename.tar'.",
        default=None,
    )
    os_choice: Optional[str] = Field(
        description="The target operating system. Supported values: 'auto', 'linux', 'unix', 'windows'. If user mentions hp, hp-ux, aix, sunos, map it to 'linux' or 'unix'.",
        default="auto",
    )
    host: Optional[str] = Field(
        description="The server host/IP string.", default=None
    )
    port: Optional[int] = Field(
        description="The server port integer.", default=None
    )
    install_path: Optional[str] = Field(
        description="The installation directory path.", default=None
    )
    script_name: Optional[str] = Field(
        description="The specific installation script name (e.g., 'install.sh', 'setup.bat').",
        default=None,
    )
    extra_vars_list: list[str] = Field(
        description="Extra environment variables to pass during installation. Must be a list of strings in the format 'KEY=VALUE'.",
        default_factory=list,
    )


def build_system_instruction() -> str:
    return (
        "You are a specialized AI assistant perfectly configured for parsing **PJS (PlatformJS)** installation commands.\n"
        "Your mission is to extract the fields required ONLY for a PJS installation from the user's natural language input. "
        "For any missing information, leave the field as null/None, except for os_choice which defaults to 'auto' and extra_vars which defaults to {}.\n"
        "Pay special attention to these PJS-specific extra variables. Extract and map them into extra_vars_list EXACTLY as 'KEY=VALUE':\n"
        "- DG_IP: DataGather IP (DG_M executing environment IP)\n"
        "- DG_PORT: DataGather Port (port allocated to DG_M)\n"
        "- DB_TYPE: Database Type (e.g. REPO DB)\n"
        "- DB_IP: Database Server IP (REPO DB environment IP)\n"
        "- DB_PORT: Database Port (REPO DB listener port)\n"
        "- DB_NAME: Database name (ORACLE=SID, PG=DB Name)\n"
        "- DB_USER: Database User\n"
        "- DB_PASSWORD: Database Password\n"
        "- PJS_PORT: Service port (PJS port)\n"
        "- SSH_USER: The SSH username for server access\n"
        "- SSH_PASSWORD: The SSH password for server access\n"
        "- SSH_PORT: The SSH port for server access"
    )


def parse_install_prompt(user_prompt: str) -> InstallConfigSchema:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set.")

    client = OpenAI(api_key=api_key)
    models_to_try = ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]
    last_error = None

    for model_name in models_to_try:
        try:
            print(f"[AI] Requesting OpenAI using model: {model_name}...")
            response = client.beta.chat.completions.parse(
                model=model_name,
                messages=[
                    {"role": "system", "content": build_system_instruction()},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=InstallConfigSchema,
                temperature=0.0,
            )
            print(f"[AI] Successfully received response from {model_name}!")

            result = response.choices[0].message.parsed
            if result is None:
                return InstallConfigSchema()

            # Additional fallback to force SSH extraction if AI missed it
            missing_ssh_user = True
            missing_ssh_pass = True
            for ev in result.extra_vars_list:
                if ev.upper().startswith("SSH_USER="): missing_ssh_user = False
                if ev.upper().startswith("SSH_PASSWORD="): missing_ssh_pass = False

            if missing_ssh_user:
                m = re.search(r'SSH_USER=([a-zA-Z0-9_.-]+)', user_prompt, re.IGNORECASE)
                if m: result.extra_vars_list.append(f"SSH_USER={m.group(1)}")
            if missing_ssh_pass:
                m = re.search(r'SSH_PASSWORD=([^\s,;]+)', user_prompt, re.IGNORECASE)
                if m: result.extra_vars_list.append(f"SSH_PASSWORD={m.group(1)}")

            return result
        except Exception as e:
            error_msg = str(e)
            if "503" in error_msg or "429" in error_msg or "404" in error_msg:
                last_error = e
                continue
            raise e

    if last_error:
        raise last_error
    return InstallConfigSchema()
