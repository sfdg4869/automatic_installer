# Automatic Installer (tar-based)

This project provides a Python interactive installer that:

1. receives install values from terminal prompts
2. detects target OS (or uses selected OS)
3. extracts a tar file
4. finds and runs an install script automatically

## Requirements

- Python 3.10+
- Linux: `bash`
- Windows: `cmd` (for `.bat`) or PowerShell (for `.ps1`)
## Run (Web UI Mode - Recommended)

```bash
# 1. Create and activate a Virtual Environment
python -m venv venv

# Windows (CMD):
venv\Scripts\activate
# Windows (PowerShell):
venv\Scripts\Activate.ps1
# Mac/Linux:
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set your API key in your environment
export GEMINI_API_KEY="your-api-key"

# 4. Terminal 1: Start Flask Backend (port 5000)
python server.py

# 5. Terminal 2: Start React Frontend (port 5173)
cd frontend
npm run dev
```

## Run (CLI Mode)

```bash
# Set your API key in your environment
export GEMINI_API_KEY="your-api-key"

python installer.py
```

## Prompt inputs (CLI)

When prompted, you can type your installation instructions in natural language.
**Example**: *"Desktop의 app.tar 파일을 리눅스로 /opt/myapp 에 설치해. 포트는 8080, DB_USER=root 도 추가해줘."*

If you leave it empty and press Enter, it falls back to manual prompts:

- Path to tar file
- Target OS: `auto` / `linux` / `windows`
- Server host
- Server port
- Install path
- Installer script name (optional)
- Extra vars (optional): `KEY=VALUE,KEY2=VALUE2`

## Script discovery

- Linux default names: `install.sh`, `setup.sh`
- Windows default names: `install.bat`, `setup.bat`, `install.ps1`, `setup.ps1`
- If you enter an installer script name, that name is used first.

## Environment variables passed to installer script

- `INSTALL_HOST`
- `INSTALL_PORT`
- `INSTALL_PATH`
- plus any extra vars you provided

## Example

If your script needs DB info:

```
Extra vars: DB_HOST=10.10.1.3,DB_PORT=5432,DB_USER=app
```

Then the installer script can read them from environment variables.
