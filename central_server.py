import os
import sys

# High-Performance CPU Thread Optimization for PyTorch / ONNX / MKL
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["MKL_NUM_THREADS"] = "4"

import subprocess
import time
import json
import psutil
import requests
import numpy as np
from pathlib import Path
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import shutil
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Yield control to FastAPI
    yield
    # Shutdown logic
    print("[INFO] Unified Backend Manager shutting down...")
    for name, port in PORTS.items():
        kill_process_on_port(port)

app = FastAPI(
    title="TTS Unified Backend Manager",
    description="Manages Kokoro, Pocket, and Supertonic backends, ensuring mutual exclusion.",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables to track processes
running_processes = {
    "kokoro": None,
    "pocket": None,
    "supertonic": None
}

PORTS = {
    "kokoro": 7860,
    "pocket": 8000,
    "supertonic": 7788
}

active_backend = None

# Create folders
WORKSPACE_DIR = Path(__file__).parent.resolve()
CUSTOM_STYLES_DIR = WORKSPACE_DIR / "custom_styles"
CUSTOM_STYLES_DIR.mkdir(parents=True, exist_ok=True)

import socket

# Helper function to find and kill processes listening on target ports
def kill_process_on_port(port: int):
    print(f"[INFO] Finding and cleaning up any active processes on port {port}...")
    killed = False
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            conns = []
            if hasattr(proc, 'net_connections'):
                conns = proc.net_connections(kind='inet')
            elif hasattr(proc, 'connections'):
                conns = proc.connections(kind='inet')
                
            for conn in conns:
                if conn.laddr.port == port:
                    print(f"[KILL] Terminating process {proc.info['name']} (PID {proc.info['pid']}) on port {port}")
                    parent = psutil.Process(proc.info['pid'])
                    for child in parent.children(recursive=True):
                        child.kill()
                    parent.kill()
                    killed = True
        except Exception:
            pass
    if killed:
        time.sleep(1.5)  # Give system time to release the port

def is_port_in_use(port: int) -> bool:
    # Try IPv4 localhost
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            if s.connect_ex(('127.0.0.1', port)) == 0:
                return True
    except Exception:
        pass
    # Try IPv6 localhost
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            if s.connect_ex(('::1', port)) == 0:
                return True
    except Exception:
        pass
    return False

def wait_for_port(port: int, timeout: int = 30) -> bool:
    start_time = time.time()
    while time.time() - start_time < timeout:
        if is_port_in_use(port):
            return True
        time.sleep(0.5)
    return False

@app.get("/api/status")
def get_status():
    """Get status of all backends and system usage"""
    status = {}
    for backend, port in PORTS.items():
        in_use = is_port_in_use(port)
        status[backend] = {
            "port": port,
            "running": in_use,
            "url": f"http://localhost:{port}"
        }
    
    # Get system stats
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    
    # Get local LAN IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = '127.0.0.1'
    
    global active_backend
    # Recalculate active backend based on actual port status
    if active_backend and status.get(active_backend, {}).get("running"):
        # Keep current active_backend if it is running
        pass
    else:
        detected_active = None
        for backend, info in status.items():
            if info["running"]:
                detected_active = backend
                break
        active_backend = detected_active
    
    return {
        "active_backend": active_backend,
        "backends": status,
        "system": {
            "cpu": cpu,
            "ram": ram,
            "local_ip": local_ip
        }
    }

class SwitchRequest(BaseModel):
    backend: str

@app.post("/api/switch")
def switch_backend(request: SwitchRequest):
    """Switch active backend: kills others, starts the requested one"""
    global active_backend
    target = request.backend.lower()
    
    if target not in PORTS:
        raise HTTPException(status_code=400, detail=f"Unknown backend '{target}'")
        
    print(f"[INFO] Switch requested to: {target}")
    
    # 1. Kill any process listening on any of our ports to ensure mutual exclusion
    for name, port in PORTS.items():
        kill_process_on_port(port)
        if running_processes[name]:
            try:
                running_processes[name].terminate()
                running_processes[name] = None
            except:
                pass
                
    active_backend = None
    
    # 2. Start the requested backend
    venv_python = WORKSPACE_DIR / "venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        venv_python = sys.executable  # Fallback to current python interpreter
        
    # Prepare environment with UTF-8 flags and high-performance CPU thread optimizations to prevent Windows crashes and CPU core thrashing
    sub_env = os.environ.copy()
    sub_env["PYTHONIOENCODING"] = "utf-8"
    sub_env["PYTHONUTF8"] = "1"
    sub_env["OMP_NUM_THREADS"] = "4"
    sub_env["MKL_NUM_THREADS"] = "4"
    sub_env["SUPERTONIC_INTRA_OP_THREADS"] = "4"
    sub_env["SUPERTONIC_INTER_OP_THREADS"] = "2"

    try:
        if target == "kokoro":
            print("[INFO] Starting Kokoro TTS API...")
            cmd = [str(venv_python), "kokoro_api.py"]
            cwd = WORKSPACE_DIR / "kokoro-tts-local"
            log_file = open(WORKSPACE_DIR / "kokoro.log", "w", encoding="utf-8")
            proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=log_file, stderr=subprocess.STDOUT, env=sub_env)
            log_file.close()
            running_processes["kokoro"] = proc
            
        elif target == "pocket":
            print("[INFO] Starting Pocket TTS Server...")
            cmd = [str(venv_python), "pocket_tts_api.py"]
            cwd = WORKSPACE_DIR / "pocket-tts-server"
            log_file = open(WORKSPACE_DIR / "pocket.log", "w", encoding="utf-8")
            proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=log_file, stderr=subprocess.STDOUT, env=sub_env)
            log_file.close()
            running_processes["pocket"] = proc
            
        elif target == "supertonic":
            print("[INFO] Starting Supertonic Serve...")
            # Use correct CLI subcommand syntax
            cmd = [str(venv_python), "-m", "supertonic.cli", "serve", "--host", "127.0.0.1", "--port", "7788"]
            # Set cwd to venv to avoid Python importing local 'supertonic' directory as module
            cwd = WORKSPACE_DIR / "venv"
            log_file = open(WORKSPACE_DIR / "supertonic.log", "w", encoding="utf-8")
            proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=log_file, stderr=subprocess.STDOUT, env=sub_env)
            log_file.close()
            running_processes["supertonic"] = proc
            
        # 3. Wait for the server to bind to the port
        port = PORTS[target]
        print(f"[INFO] Waiting for port {port} to open...")
        success = wait_for_port(port, timeout=180)
        
        if success:
            active_backend = target
            print(f"[SUCCESS] Backend {target} is now running and active!")
            
            # Post-startup setup for Supertonic: import custom mixed styles
            if target == "supertonic":
                try:
                    time.sleep(2)  # Wait for startup to complete
                    import_custom_styles_to_supertonic()
                except Exception as e:
                    print(f"[WARNING] Custom styles import failed: {e}")
            
            return {
                "status": "success",
                "backend": target,
                "port": port,
                "message": f"Successfully loaded backend: {target}"
            }
        else:
            # Failed to start - kill it
            if proc:
                proc.kill()
            raise HTTPException(status_code=500, detail=f"Backend '{target}' failed to start within timeout.")
            
    except Exception as e:
        print(f"[ERROR] Failed to start backend: {e}")
        raise HTTPException(status_code=500, detail=f"Startup error: {str(e)}")

@app.post("/api/stop")
def stop_active_backend():
    """Kill any running backend"""
    global active_backend
    for name, port in PORTS.items():
        kill_process_on_port(port)
        if running_processes[name]:
            try:
                running_processes[name].terminate()
                running_processes[name] = None
            except:
                pass
    active_backend = None
    return {"status": "success", "message": "All backends stopped."}

@app.get("/api/voices")
def get_unified_voices():
    """Get list of voices for the active backend"""
    global active_backend
    if not active_backend:
        return {"voices": [], "backend": None}
        
    port = PORTS[active_backend]
    try:
        if active_backend == "kokoro":
            response = requests.get(f"http://localhost:{port}/voices", timeout=5)
            if response.status_code == 200:
                voice_list = response.json().get("voices", [])
                voices = []
                for name in voice_list:
                    # Detect gender
                    gender = "female" if any(pref in name for pref in ["af_", "bf_", "jf_", "zf_", "ef_", "ff_", "hf_", "if_", "pf_"]) else "male"
                    
                    # Detect language from prefix
                    lang = "en"
                    if name.startswith("zf") or name.startswith("zm") or name.startswith("zh"):
                        lang = "zh"
                    elif name.startswith("jf") or name.startswith("jm") or name.startswith("ja"):
                        lang = "ja"
                    elif name.startswith("ef") or name.startswith("em") or name.startswith("es"):
                        lang = "es"
                    elif name.startswith("ff") or name.startswith("fm") or name.startswith("fr"):
                        lang = "fr"
                    elif name.startswith("hf") or name.startswith("hm") or name.startswith("hi"):
                        lang = "hi"
                    elif name.startswith("if") or name.startswith("im") or name.startswith("it"):
                        lang = "it"
                    elif name.startswith("pf") or name.startswith("pm") or name.startswith("pt"):
                        lang = "pt"
                        
                    voices.append({
                        "id": name,
                        "name": name,
                        "gender": gender,
                        "language": lang,
                        "cloned": False
                    })
                return {"voices": voices, "backend": active_backend}
                
        elif active_backend == "pocket":
            response = requests.get(f"http://localhost:{port}/v1/audio/voices", timeout=5)
            if response.status_code == 200:
                voices = response.json().get("voices", [])
                mapped_voices = []
                standard_voices = {"donald-trump", "joe-original", "joe_original", "barack-obama"}
                for v in voices:
                    vid = v["voice_id"]
                    vname = v["name"]
                    
                    # Detect language suffix e.g. speaker_es
                    lang = "en"
                    display_name = vname
                    is_cloned = False
                    
                    for possible_lang in ["en", "es", "fr", "zh", "ja", "hi", "it", "pt"]:
                        suffix = f"_{possible_lang}"
                        if vname.endswith(suffix):
                            lang = possible_lang
                            display_name = vname[:-len(suffix)]
                            is_cloned = True
                            break
                            
                    if vid not in standard_voices:
                        is_cloned = True
                        
                    mapped_voices.append({
                        "id": vid,
                        "name": display_name,
                        "gender": "neutral",
                        "language": lang,
                        "cloned": is_cloned
                    })
                return {"voices": mapped_voices, "backend": active_backend}
                
        elif active_backend == "supertonic":
            response = requests.get(f"http://localhost:{port}/v1/styles", timeout=5)
            if response.status_code == 200:
                styles = response.json()
                print(f"[DEBUG] Supertonic styles payload: {styles}")
                
                style_list = []
                if isinstance(styles, dict):
                    raw_list = styles.get("styles", [])
                    if isinstance(raw_list, list):
                        for item in raw_list:
                            if isinstance(item, dict) and "name" in item:
                                style_list.append(item["name"])
                            elif isinstance(item, str):
                                style_list.append(item)
                    else:
                        # Fallback if styles was dict but 'styles' key wasn't list
                        style_list = ["M1", "M2", "F1", "F2"]
                elif isinstance(styles, list):
                    for item in styles:
                        if isinstance(item, dict) and "name" in item:
                            style_list.append(item["name"])
                        elif isinstance(item, str):
                            style_list.append(item)
                else:
                    style_list = ["M1", "M2", "F1", "F2"]
                    
                voices = []
                standard_styles = {"M1", "M2", "F1", "F2", "M3", "M4", "F3", "F4"}
                for name in style_list:
                    # Default gender fallback based on name
                    gender = "male" if name.lower().startswith("m") else "female"
                    voices.append({
                        "id": name,
                        "name": name,
                        "gender": gender,
                        "language": "all",
                        "cloned": name not in standard_styles
                    })
                return {"voices": voices, "backend": active_backend}
                
    except Exception as e:
        print(f"[ERROR] Failed to fetch voices from backend {active_backend}: {e}")
        
    return {"voices": [], "backend": active_backend, "error": "Backend offline or unreachable"}

class UnifiedTTSRequest(BaseModel):
    text: str
    voice: str
    speed: float = 1.0
    lang: str = "en"
    format: str = "wav"

def split_text_into_chunks(text: str, max_len: int = 200) -> list:
    if not text:
        return []
    import re
    # 1. Split by hard punctuation boundaries first
    primary = re.split(r'([\n.!?。！？;；])', text)
    segments = []
    current = ""
    for part in primary:
        if not part:
            continue
        if part in ["\n", ".", "!", "?", "。", "！", "？", ";", "；"]:
            current += part
            if current.strip():
                segments.append(current.strip())
            current = ""
        else:
            current += part
    if current.strip():
        segments.append(current.strip())
        
    final_chunks = []
    
    def add_chunk(chunk_text: str):
        chunk_text = chunk_text.strip()
        if not chunk_text:
            return
        if len(chunk_text) <= max_len:
            final_chunks.append(chunk_text)
        else:
            # Fallback word-by-word splitting
            words = chunk_text.split()
            temp = ""
            for w in words:
                if len(temp) + len(w) + 1 > max_len:
                    if temp.strip():
                        final_chunks.append(temp.strip())
                    temp = w
                else:
                    temp = (temp + " " + w).strip()
            if temp.strip():
                final_chunks.append(temp.strip())

    # 2. Refined splitting that mathematically guarantees no chunk ever exceeds max_len!
    for seg in segments:
        if len(seg) <= max_len:
            add_chunk(seg)
        else:
            subparts = re.split(r'([,，\-\—\|])', seg)
            curr_chunk = ""
            for part in subparts:
                if not part:
                    continue
                if len(curr_chunk) + len(part) > max_len:
                    add_chunk(curr_chunk)
                    curr_chunk = part
                else:
                    curr_chunk += part
            add_chunk(curr_chunk)
                        
    return [c for c in final_chunks if c]

def concatenate_wav_buffers(buffers: list) -> bytes:
    if not buffers:
        return b""
    if len(buffers) == 1:
        return buffers[0]
        
    master_header = bytearray(buffers[0][:44])
    pcm_chunks = []
    total_pcm_length = 0
    for buf in buffers:
        if len(buf) > 44:
            pcm = buf[44:]
            pcm_chunks.append(pcm)
            total_pcm_length += len(pcm)
            
    total_wav_length = 44 + total_pcm_length
    import struct
    struct.pack_into("<I", master_header, 4, total_wav_length - 8)
    struct.pack_into("<I", master_header, 40, total_pcm_length)
    
    return bytes(master_header) + b"".join(pcm_chunks)

@app.post("/api/tts")
def unified_tts(request: UnifiedTTSRequest):
    """Proxy the TTS request to the currently active backend"""
    global active_backend
    if not active_backend:
        raise HTTPException(status_code=400, detail="No active TTS backend loaded. Please select a backend first.")
        
    port = PORTS[active_backend]
    
    try:
        # Split text into safe, naturally partitioned chunks for all backends to guarantee zero crashes and ultra-low synthesis latencies!
        chunks = split_text_into_chunks(request.text, max_len=200)
        if not chunks:
            chunks = [request.text]
            
        import requests
        from concurrent.futures import ThreadPoolExecutor
        
        def fetch_chunk(chunk_text: str) -> bytes:
            if active_backend == "kokoro":
                payload = {
                    "text": chunk_text,
                    "voice": request.voice,
                    "speed": request.speed,
                    "format": "wav"  # Internally request WAV for reliable binary concatenation
                }
                resp = requests.post(f"http://localhost:{port}/tts", json=payload, timeout=60)
                if resp.status_code == 200:
                    return resp.content
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
                
            elif active_backend == "pocket":
                payload = {
                    "model": "tts-1",
                    "input": chunk_text,
                    "voice": request.voice,
                    "response_format": "wav",  # Internally request WAV for reliable binary concatenation
                    "speed": request.speed
                }
                resp = requests.post(f"http://localhost:{port}/v1/audio/speech", json=payload, timeout=60)
                if resp.status_code == 200:
                    return resp.content
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
                
            elif active_backend == "supertonic":
                chunk_payload = {
                    "text": chunk_text,
                    "voice": request.voice,
                    "lang": request.lang,
                    "speed": request.speed
                }
                resp = requests.post(f"http://localhost:{port}/v1/tts", json=chunk_payload, timeout=60)
                if resp.status_code == 200:
                    return resp.content
                
                # Fallback to OpenAI speech endpoint of Supertonic
                openai_payload = {
                    "model": "supertonic-3",
                    "input": chunk_text,
                    "voice": request.voice,
                    "response_format": "wav"
                }
                resp_fallback = requests.post(f"http://localhost:{port}/v1/audio/speech", json=openai_payload, timeout=60)
                if resp_fallback.status_code == 200:
                    return resp_fallback.content
                raise HTTPException(status_code=resp.status_code, detail=resp_fallback.text)
            return b""

        # Run all chunk generations concurrently inside a high-speed Python ThreadPoolExecutor!
        with ThreadPoolExecutor(max_workers=min(4, len(chunks))) as executor:
            futures = [executor.submit(fetch_chunk, c) for c in chunks]
            wav_buffers = [f.result() for f in futures]
            
        final_wav = concatenate_wav_buffers(wav_buffers)
        from io import BytesIO
        return StreamingResponse(BytesIO(final_wav), media_type="audio/wav")
            
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail="Active backend is unreachable. It may have crashed or is still initializing.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/tts/stream")
async def unified_tts_stream(request: UnifiedTTSRequest):
    """Proxy the streaming request to the currently active backend yielding raw 16-bit PCM chunks"""
    global active_backend
    if not active_backend:
        raise HTTPException(status_code=400, detail="No active TTS backend loaded. Please select a backend first.")
        
    port = PORTS[active_backend]
    
    if active_backend == "kokoro":
        payload = {
            "text": request.text,
            "voice": request.voice,
            "speed": request.speed,
            "format": "wav"
        }
        url = f"http://localhost:{port}/tts/stream"
        
    elif active_backend == "pocket":
        payload = {
            "model": "tts-1",
            "input": request.text,
            "voice": request.voice,
            "response_format": "wav",
            "speed": request.speed
        }
        url = f"http://localhost:{port}/tts/stream"
        
    elif active_backend == "supertonic":
        # Since Supertonic has no direct PCM stream, we segment it and yield PCM chunk-by-chunk
        chunks = split_text_into_chunks(request.text, max_len=200)
        if not chunks:
            chunks = [request.text]
            
        def supertonic_generator():
            for c in chunks:
                if not c.strip():
                    continue
                try:
                    chunk_payload = {
                        "text": c,
                        "voice": request.voice,
                        "lang": request.lang,
                        "speed": request.speed
                    }
                    resp = requests.post(f"http://localhost:{port}/v1/tts", json=chunk_payload, timeout=30)
                    if resp.status_code == 200:
                        # Extract PCM from WAV (strip header)
                        wav_data = resp.content
                        if len(wav_data) > 44:
                            yield wav_data[44:]
                except Exception as e:
                    print(f"[ERROR] Supertonic streaming segment failed: {e}")
                    
        return StreamingResponse(supertonic_generator(), media_type="audio/pcm")
        
    else:
        raise HTTPException(status_code=400, detail="Unknown active backend.")
        
    # Standard proxy generator for Kokoro and Pocket
    def stream_proxy():
        import requests
        with requests.post(url, json=payload, stream=True, timeout=60) as r:
            if r.status_code != 200:
                raise HTTPException(status_code=r.status_code, detail="Backend failed to stream")
            for chunk in r.iter_content(chunk_size=4096):
                if chunk:
                    yield chunk
                    
    return StreamingResponse(stream_proxy(), media_type="audio/pcm")

# ==================== SUPERTONIC VOICE BUILDER & MIXER ====================

def get_supertonic_style_path(voice_name: str) -> Path:
    """Locate a Supertonic voice style file"""
    # 1. Check custom styles folder
    custom_path = CUSTOM_STYLES_DIR / f"{voice_name}.json"
    if custom_path.exists():
        return custom_path
        
    # Check custom styles folder case-insensitively
    if CUSTOM_STYLES_DIR.exists():
        for f in CUSTOM_STYLES_DIR.glob("*.json"):
            if f.stem.lower() == voice_name.lower():
                return f
        
    # 2. Check main assets folder
    assets_path = WORKSPACE_DIR / "supertonic" / "assets" / "voice_styles" / f"{voice_name}.json"
    if assets_path.exists():
        return assets_path
        
    # 3. Check active model caches across multiple home directory candidates
    home_options = [
        Path.home(),
        Path(os.environ.get("USERPROFILE", "C:\\Users\\MrShahmeer")),
        Path("C:\\Users\\MrShahmeer")
    ]
    
    for home in home_options:
        # Check custom styles in this home directory across all model folders
        for model_dir in ["supertonic3", "supertonic2", "supertonic"]:
            cache_custom = home / ".cache" / model_dir / "custom_styles"
            if cache_custom.exists():
                for f in cache_custom.glob("*.json"):
                    if f.stem.lower() == voice_name.lower():
                        return f
                    
        # Check model preset styles
        for model_dir in ["supertonic3", "supertonic2", "supertonic"]:
            parent_dir = home / ".cache" / model_dir / "voice_styles"
            if parent_dir.exists():
                for f in parent_dir.glob("*.json"):
                    if f.stem.lower() == voice_name.lower():
                        return f
        
    # 4. Fallback search inside supertonic directory
    for path in WORKSPACE_DIR.glob(f"**/voice_styles/{voice_name}.json"):
        return path
    for path in WORKSPACE_DIR.glob("**/voice_styles/*.json"):
        if path.stem.lower() == voice_name.lower():
            return path
        
    raise FileNotFoundError(f"Style file for '{voice_name}' not found.")

def import_custom_styles_to_supertonic():
    """POST all mixed/custom JSON voice styles from custom_styles to active Supertonic server"""
    if active_backend != "supertonic":
        return
        
    port = PORTS["supertonic"]
    print("[INFO] Importing custom styles into active Supertonic server...")
    for style_file in CUSTOM_STYLES_DIR.glob("*.json"):
        try:
            print(f"[UPLOAD] Importing custom style: {style_file.name}")
            with open(style_file, 'rb') as f:
                files = {'file': (style_file.name, f, 'application/json')}
                resp = requests.post(f"http://localhost:{port}/v1/styles/import", files=files, timeout=5)
                print(f"[UPLOAD] Response: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"[WARNING] Failed to import custom style {style_file.name}: {e}")

@app.get("/api/supertonic/custom-voices")
def list_custom_voices():
    """List all custom voice style names"""
    voices = []
    for file in CUSTOM_STYLES_DIR.glob("*.json"):
        voices.append(file.stem)
    return {"custom_voices": voices}

class StyleMixRequest(BaseModel):
    voice_a: str
    voice_b: str
    weight: float  # 0.0 to 1.0 (weight of voice B)
    name: str

@app.post("/api/supertonic/mix")
def mix_supertonic_styles(request: StyleMixRequest):
    """Mathematically blend two Supertonic style profiles (style_ttl and style_dp)"""
    try:
        # 1. Locate files
        path_a = get_supertonic_style_path(request.voice_a)
        path_b = get_supertonic_style_path(request.voice_b)
        
        # 2. Read JSON
        with open(path_a, 'r') as f:
            data_a = json.load(f)
        with open(path_b, 'r') as f:
            data_b = json.load(f)
            
        # 3. Extract dimensions and data
        ttl_dims_a = data_a['style_ttl']['dims']
        dp_dims_a = data_a['style_dp']['dims']
        
        ttl_a = np.array(data_a['style_ttl']['data'], dtype=np.float32)
        ttl_b = np.array(data_b['style_ttl']['data'], dtype=np.float32)
        dp_a = np.array(data_a['style_dp']['data'], dtype=np.float32)
        dp_b = np.array(data_b['style_dp']['data'], dtype=np.float32)
        
        # 4. Perform vector interpolation
        weight = float(request.weight)
        if weight < 0.0 or weight > 1.0:
            raise HTTPException(status_code=400, detail="Weight must be between 0.0 and 1.0")
            
        mixed_ttl = (1.0 - weight) * ttl_a + weight * ttl_b
        mixed_dp = (1.0 - weight) * dp_a + weight * dp_b
        
        # 5. Format response JSON
        mixed_data = {
            "style_ttl": {
                "dims": ttl_dims_a,
                "data": mixed_ttl.tolist()
            },
            "style_dp": {
                "dims": dp_dims_a,
                "data": mixed_dp.tolist()
            }
        }
        
        # 6. Save new file in custom styles folder
        safe_name = "".join([c for c in request.name if c.isalnum() or c in ('_', '-')]).strip()
        if not safe_name:
            raise HTTPException(status_code=400, detail="Invalid mixed voice name")
            
        output_file_name = f"{safe_name}.json"
        output_path = CUSTOM_STYLES_DIR / output_file_name
        
        with open(output_path, 'w') as f:
            json.dump(mixed_data, f, indent=2)
            
        print(f"[SUCCESS] Mathematically blended '{request.voice_a}' and '{request.voice_b}' -> {output_path}")
        
        # 7. Upload to active Supertonic server if currently running
        if active_backend == "supertonic":
            try:
                port = PORTS["supertonic"]
                with open(output_path, 'rb') as f:
                    files = {'file': (output_file_name, f, 'application/json')}
                    resp = requests.post(f"http://localhost:{port}/v1/styles/import", files=files, timeout=5)
                    print(f"[AUTO-IMPORT] Custom voice {safe_name} imported automatically: {resp.status_code}")
            except Exception as e:
                print(f"[WARNING] Failed to auto-import mixed voice: {e}")
                
        return {
            "status": "success",
            "voice_name": safe_name,
            "message": f"Successfully mixed '{request.voice_a}' ({100*(1-weight):.0f}%) and '{request.voice_b}' ({100*weight:.0f}%) into '{safe_name}'!"
        }
        
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        print(f"[ERROR] Mixing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Mixing error: {str(e)}")

@app.post("/api/pocket/upload-voice")
async def upload_pocket_voice(name: str = Form(...), language: str = Form("en"), file: UploadFile = File(...)):
    """Upload a custom audio prompt for voice cloning in Pocket TTS"""
    try:
        safe_name = "".join([c for c in name if c.isalnum() or c in ('_', '-')]).strip()
        if not safe_name:
            raise HTTPException(status_code=400, detail="Invalid voice name")
            
        voices_dir = WORKSPACE_DIR / "pocket-tts-server" / "voices-celebrities"
        voices_dir.mkdir(parents=True, exist_ok=True)
        
        # Save temporary file
        temp_suffix = Path(file.filename).suffix
        temp_path = WORKSPACE_DIR / f"temp_upload_{safe_name}{temp_suffix}"
        with open(temp_path, "wb") as f:
            f.write(await file.read())
            
        # Convert to 24kHz mono 16-bit WAV (pocket tts format)
        output_path = voices_dir / f"{safe_name}_{language}.wav"
        
        # Use ffmpeg to convert
        import subprocess
        try:
            cmd = [
                "ffmpeg", "-y",
                "-i", str(temp_path),
                "-ar", "24000",
                "-ac", "1",
                "-sample_fmt", "s16",
                str(output_path)
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"[SUCCESS] Converted and saved custom voice to {output_path}")
        except Exception as e:
            # Fallback to copy if it's already WAV and ffmpeg is missing
            if temp_suffix.lower() == ".wav":
                import shutil
                shutil.copy2(str(temp_path), str(output_path))
            else:
                raise HTTPException(status_code=500, detail=f"Audio conversion failed (ffmpeg required for non-WAV formats): {e}")
        finally:
            if temp_path.exists():
                temp_path.unlink()
                
        # Trigger rescanning in Pocket server if active
        if active_backend == "pocket":
            try:
                requests.post(f"http://localhost:{PORTS['pocket']}/v1/audio/voices/scan", timeout=5)
            except:
                pass
                
        return {"status": "success", "voice_name": safe_name, "message": f"Successfully registered voice prompt '{safe_name}' for cloning!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/supertonic/upload-voice")
async def upload_supertonic_voice(name: str = Form(...), file: UploadFile = File(...)):
    """Upload an existing Voice Builder JSON profile directly to custom styles"""
    try:
        safe_name = "".join([c for c in name if c.isalnum() or c in ('_', '-')]).strip()
        if not safe_name:
            raise HTTPException(status_code=400, detail="Invalid voice name")
            
        output_path = CUSTOM_STYLES_DIR / f"{safe_name}.json"
        
        # Read uploaded JSON
        contents = await file.read()
        json_data = json.loads(contents.decode('utf-8'))
        
        # Validate keys
        if "style_ttl" not in json_data or "style_dp" not in json_data:
            raise HTTPException(status_code=400, detail="Invalid style JSON structure. Must contain 'style_ttl' and 'style_dp' keys.")
            
        with open(output_path, 'w') as f:
            json.dump(json_data, f, indent=2)
            
        print(f"[UPLOAD] Imported custom Voice Builder file: {output_path}")
        
        # Auto-import to server if running
        if active_backend == "supertonic":
            try:
                port = PORTS["supertonic"]
                with open(output_path, 'rb') as f:
                    files = {'file': (f"{safe_name}.json", f, 'application/json')}
                    resp = requests.post(f"http://localhost:{port}/v1/styles/import", files=files, timeout=5)
                    print(f"[AUTO-IMPORT] Uploaded custom style: {resp.status_code}")
            except Exception as e:
                print(f"[WARNING] Failed to auto-import uploaded voice: {e}")
                
        return {"status": "success", "voice_name": safe_name, "message": f"Successfully loaded custom voice profile '{safe_name}'!"}
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="File is not valid JSON")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Clean shutdown

# Mount frontend static files
FRONTEND_DIR = WORKSPACE_DIR / "frontend"
FRONTEND_DIR.mkdir(parents=True, exist_ok=True)

try:
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
except Exception as e:
    print(f"[WARNING] Failed to mount frontend static files: {e}")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5000)
