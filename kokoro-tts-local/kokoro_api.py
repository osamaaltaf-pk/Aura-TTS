import os
import sys
from pathlib import Path
import torch
import numpy as np
import soundfile as sf
from pydub import AudioSegment
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import io
from datetime import datetime

# Add the current directory to sys.path so we can import from models.py
sys.path.append(str(Path(__file__).parent.resolve()))

from models import (
    list_available_voices, build_model, download_voice_files,
    EnhancedKPipeline, get_safe_voice_path
)

app = FastAPI(
    title="Kokoro TTS REST API",
    description="REST API wrapper for Kokoro TTS Local model",
    version="1.0.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables
device = 'cuda' if torch.cuda.is_available() else 'cpu'
model = None
pipelines = {}
SAMPLE_RATE = 24000
DEFAULT_OUTPUT_DIR = Path("outputs")
DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

LANG_MAP = {
    "af_": "a", "am_": "a",
    "bf_": "b", "bm_": "b",
    "jf_": "j", "jm_": "j",
    "zf_": "z", "zm_": "z",
    "ef_": "e", "em_": "e",
    "ff_": "f", "fm_": "f",
    "hf_": "h", "hm_": "h",
    "if_": "i", "im_": "i",
    "pf_": "p", "pm_": "p",
}

def get_pipeline_for_voice(voice_name: str) -> EnhancedKPipeline:
    """Determine the language code from the voice prefix and return the associated pipeline."""
    global model
    if model is None:
        print("[INFO] Initializing base Kokoro model...")
        model = build_model(None, device)

    prefix = voice_name[:2].lower() if len(voice_name) >= 2 else "af"
    lang_code = LANG_MAP.get(prefix, "a")
    if lang_code not in pipelines:
        print(f"[INFO] Creating pipeline for lang_code='{lang_code}'")
        pipelines[lang_code] = build_model(None, device, lang_code=lang_code)
    pipelines[lang_code].device = device
    return pipelines[lang_code]

@app.on_event("startup")
def startup_event():
    global model
    print(f"[INFO] Starting Kokoro TTS API on {device}...")
    try:
        # Build model and verify voices exist
        model = build_model(None, device)
        voices = list_available_voices()
        if not voices:
            print("[INFO] No voices found. Downloading voice files...")
            download_voice_files()
    except Exception as e:
        print(f"[ERROR] Startup failed: {e}")

class TTSRequest(BaseModel):
    text: str
    voice: str = "af_bella"
    speed: float = 1.0
    format: str = "wav" # wav, mp3, aac

@app.get("/voices")
def get_voices():
    """Get list of available voices"""
    try:
        voices = list_available_voices()
        return {"voices": voices}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tts")
def generate_tts(request: TTSRequest):
    """Generate speech from text"""
    global model
    try:
        if not request.text or not request.text.strip():
            raise HTTPException(status_code=400, detail="Text cannot be empty")
        
        # Check voice path
        voice_path = get_safe_voice_path(request.voice)
        if not voice_path.exists():
            raise HTTPException(status_code=404, detail=f"Voice '{request.voice}' not found")
        
        # Load/get pipeline
        pipeline = get_pipeline_for_voice(request.voice)
        
        # Generate speech
        print(f"[INFO] Synthesizing '{request.text[:40]}...' with voice '{request.voice}'")
        generator = pipeline(request.text, voice=str(voice_path), speed=request.speed, split_pattern=r'\n+')
        
        all_audio = []
        for gs, ps, audio in generator:
            if audio is not None:
                if isinstance(audio, np.ndarray):
                    audio = torch.from_numpy(audio).float()
                all_audio.append(audio)
        
        if not all_audio:
            raise HTTPException(status_code=500, detail="Speech generation failed")
            
        # Combine segments
        if len(all_audio) == 1:
            final_audio = all_audio[0]
        else:
            final_audio = torch.cat(all_audio, dim=0)
            
        # Detach and convert to numpy
        if isinstance(final_audio, torch.Tensor):
            final_audio = final_audio.detach().cpu().numpy()
            
        # Save as WAV in memory
        wav_buffer = io.BytesIO()
        sf.write(wav_buffer, final_audio, SAMPLE_RATE, format="WAV")
        wav_buffer.seek(0)
        audio_bytes = wav_buffer.read()
        
        # Convert to another format if requested
        if request.format.lower() in ["mp3", "aac"]:
            try:
                audio_segment = AudioSegment.from_wav(io.BytesIO(audio_bytes))
                out_buffer = io.BytesIO()
                audio_segment.export(out_buffer, format=request.format.lower(), bitrate="192k")
                out_buffer.seek(0)
                audio_bytes = out_buffer.read()
            except Exception as conv_err:
                print(f"[WARNING] Conversion to {request.format} failed: {conv_err}. Returning WAV.")
                request.format = "wav"
                
        media_type = f"audio/{request.format.lower()}"
        return StreamingResponse(
            io.BytesIO(audio_bytes),
            media_type=media_type,
            headers={"Content-Disposition": f"inline; filename=speech.{request.format.lower()}"}
        )
        
    except Exception as e:
        print(f"[ERROR] TTS Generation failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"TTS generation error: {str(e)}")

@app.get("/health")
def health():
    return {"status": "ok", "backend": "kokoro-tts-local", "device": device}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=7860)
