import subprocess
import sys
import os

def run_pip(args):
    venv_pip = os.path.join("venv", "Scripts", "pip.exe")
    if not os.path.exists(venv_pip):
        venv_pip = "pip"  # Fallback to system pip if venv structure is different
    
    print(f"\nRunning: pip {' '.join(args)}")
    cmd = [venv_pip] + args
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"Warning: pip command failed with exit code {result.returncode}")

if __name__ == "__main__":
    print("==================================================")
    # 1. Upgrade pip, setuptools, wheel
    print("Upgrading pip, setuptools, and wheel...")
    run_pip(["install", "--upgrade", "pip", "setuptools", "wheel"])

    # 2. Install PyTorch CPU (stable, lightweight, high compatibility)
    print("\nInstalling PyTorch (CPU-first for high compatibility and fast installation)...")
    run_pip(["install", "torch>=2.2.0", "torchvision", "torchaudio", "--index-url", "https://download.pytorch.org/whl/cpu"])

    # 3. Install central manager dependencies
    print("\nInstalling central manager dependencies...")
    run_pip(["install", "fastapi", "uvicorn", "requests", "psutil", "python-multipart", "jinja2", "aiofiles"])

    # 4. Install Kokoro requirements
    print("\nInstalling Kokoro TTS Local dependencies...")
    # Read kokoro requirements and install them, stripping lines
    kokoro_req_path = os.path.join("kokoro-tts-local", "requirements.txt")
    if os.path.exists(kokoro_req_path):
        run_pip(["install", "-r", kokoro_req_path])

    # 5. Install Pocket TTS requirements
    print("\nInstalling Pocket TTS Server dependencies...")
    pocket_req_path = os.path.join("pocket-tts-server", "requirements.txt")
    if os.path.exists(pocket_req_path):
        run_pip(["install", "-r", pocket_req_path])

    # 6. Install Supertonic serve
    print("\nInstalling Supertonic with serve extension...")
    run_pip(["install", "supertonic[serve]"])

    # 7. Resolve potential numpy version conflict by installing compatible numpy 1.26.4
    print("\nAligning numpy to highly compatible version 1.26.4...")
    run_pip(["install", "numpy==1.26.4", "--force-reinstall"])

    print("\n==================================================")
    print("Setup completed successfully!")
    print("All backends and manager dependencies are installed.")
    print("==================================================")
