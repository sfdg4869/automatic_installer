import os
from typing import Optional

from google import genai
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
        "You are a specialized AI assistant perfectly configured for parsing **MaxGauge Daemon (Agent)** installation commands.\n"
        "Your mission is to extract the fields required ONLY for a Daemon installation from the user's natural language input. "
        "For any missing information, leave the field as null/None, except for os_choice which defaults to 'auto' and extra_vars which defaults to {}.\n"
        "Pay special attention to:\n"
        "- tar_path: translate natural language like '바탕화면의 app.tar' to '~/Desktop/app.tar' or similar appropriate paths.\n"
        "- extra_vars_list: extract MaxGauge Daemon specific environment variables (e.g., DB_OWNER, MXG_HOME, CONF_NAME, IPC_KEY) into a list of strings formatted exactly as 'KEY=VALUE'."
    )


def parse_install_prompt(user_prompt: str) -> InstallConfigSchema:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is not set.")

    client = genai.Client()
    models_to_try = ["gemini-flash-latest", "gemini-3-flash-preview", "gemini-2.5-flash", "gemini-1.5-flash-8b"]
    last_error = None

    for model_name in models_to_try:
        try:
            print(f"[AI] Requesting Gemini using model: {model_name}...")
            response = client.models.generate_content(
                model=model_name,
                contents=user_prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": InstallConfigSchema,
                    "system_instruction": build_system_instruction(),
                    "temperature": 0.0,
                },
            )
            print(f"[AI] Successfully received response from {model_name}!")
            
            if not response.text:
                return InstallConfigSchema()

            return InstallConfigSchema.model_validate_json(response.text)
        except Exception as e:
            error_msg = str(e)
            if "503" in error_msg or "429" in error_msg:
                last_error = e
                continue
            raise e

    if last_error:
        raise last_error
    return InstallConfigSchema()
