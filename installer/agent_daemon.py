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
    ssh_user: Optional[str] = Field(
        description="The SSH user to connect as.", default=None
    )
    ssh_password: Optional[str] = Field(
        description="The SSH password to use for connection.", default=None
    )
    extra_vars_list: list[str] = Field(
        description="Extra environment variables to pass during installation. Must be a list of strings in the format 'KEY=VALUE'.",
        default_factory=list,
    )


def build_system_instruction() -> str:
    return (
        "You are a specialized AI assistant perfectly configured for parsing **MaxGauge (Daemon/PJS/DGM)** installation commands.\n"
        "Your mission is to extract ALL required fields from the user's natural language input. "
        "For any missing information, leave the field as null/None, except for os_choice which defaults to 'auto' and extra_vars which defaults to {}.\n"
        "Pay special attention to:\n"
        "- tar_path: translate natural language like '바탕화면의 app.tar' to '~/Desktop/app.tar' or similar appropriate paths.\n"
        "- extra_vars_list: extract ALL environment variables (e.g., SSH_USER, SSH_PASSWORD, SSH_PORT, DB_TYPE, DB_USER, DB_PASSWORD, DB_NAME, SID, DG_IP, DG_PORT, PJS_PORT, DB_OWNER, MXG_HOME) into a list of strings formatted exactly as 'KEY=VALUE'."
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

            # AI often strips SSH_USER/PASSWORD, fallback regex to recover them
            if not result.ssh_user:
                m = re.search(r'SSH_USER=([a-zA-Z0-9_.-]+)', user_prompt, re.IGNORECASE)
                if m: result.ssh_user = m.group(1)
            if not result.ssh_password:
                m = re.search(r'SSH_PASSWORD=([^\s,;]+)', user_prompt, re.IGNORECASE)
                if m: result.ssh_password = m.group(1)
            if not result.port:
                m = re.search(r'SSH_PORT=(\d+)', user_prompt, re.IGNORECASE)
                if m: result.port = int(m.group(1))

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
