#!/usr/bin/env python3
"""
Aura TTS Portal - Unified Model and Voice Assets Downloader
Downloads all required model weights, config files, phonemizer dependencies, 
voice datasets, and pipelines in advance for instant, offline multi-engine loading.
"""

import os
import sys
import time
from pathlib import Path

# Add Kokoro local directory to python path
WORKSPACE_DIR = Path(__file__).parent.resolve()
sys.path.append(str(WORKSPACE_DIR / "kokoro-tts-local"))

def smart_download(file_path: str):
    """
    Checks if a Hugging Face hub asset is already cached locally.
    If cached, skips download/network verification entirely for instant offline re-runs.
    """
    if not file_path:
        return
        
    if file_path.startswith("hf://"):
        cleaned = file_path.removeprefix("hf://")
        splitted = cleaned.split("/")
        repo_id = "/".join(splitted[:2])
        filename = "/".join(splitted[2:])
        if "@" in filename:
            filename, revision = filename.split("@")
        else:
            revision = None
            
        try:
            from huggingface_hub import try_to_load_from_cache
            from huggingface_hub.utils import _CACHED_NO_EXIST
            
            cached_path = try_to_load_from_cache(repo_id, filename, revision=revision)
            if cached_path is not None and cached_path is not _CACHED_NO_EXIST:
                if os.path.exists(cached_path) and os.path.getsize(cached_path) > 0:
                    print(f"     [ALREADY CACHED] {filename} exists (skipped network check)")
                    return
        except Exception:
            pass
            
    # If not cached or not a HF asset, download using standard pocket-tts module
    from pocket_tts.utils.utils import download_if_necessary
    download_if_necessary(file_path)

def download_kokoro():
    print("\n==========================================================")
    print(" >>> PRE-DOWNLOADING KOKORO TTS MODELS & VOICES")
    print("==========================================================\n")
    try:
        from models import build_model, download_voice_files, VOICE_FILES
        
        # 1. Check if base weights exist locally before invoking build_model
        if os.path.exists("kokoro-v1_0.pth") and os.path.exists("config.json"):
            print("   [ALREADY CACHED] Kokoro base English weights and config.json exist.")
        else:
            print("[INFO] Fetching base Kokoro-82M English weights and config.json...")
            build_model(None, "cpu", lang_code='a')
            print("[SUCCESS] Base Kokoro English model and config.json ready!")
        
        # 2. Check if Chinese weights exist locally
        if os.path.exists("kokoro-v1_1-zh.pth"):
            print("   [ALREADY CACHED] Kokoro Chinese weights (kokoro-v1_1-zh.pth) exist.")
        else:
            print("[INFO] Fetching Kokoro Chinese weights (kokoro-v1_1-zh.pth)...")
            build_model(None, "cpu", lang_code='z')
            print("[SUCCESS] Chinese model weights ready!")
        
        # 3. Download all 54 voice files in parallel (already skips if they exist)
        print("[INFO] Checking high-fidelity voice files...")
        download_voice_files(VOICE_FILES)
        print("[SUCCESS] Voice assets successfully validated!")
        
        # 4. Pre-warm SpaCy
        print("[INFO] Verifying SpaCy pipelines...")
        import spacy
        if not spacy.util.is_package("en_core_web_sm"):
            print("[INFO] Downloading SpaCy English package (en_core_web_sm)...")
            spacy.cli.download("en_core_web_sm")
        print("[SUCCESS] SpaCy pipelines ready!")
        
    except Exception as e:
        print(f"[ERROR] Kokoro pre-downloader failed: {e}")
        import traceback
        traceback.print_exc()

def download_pocket():
    print("\n==========================================================")
    print(" >>> PRE-DOWNLOADING POCKET TTS MODELS")
    print("==========================================================\n")
    try:
        from pocket_tts.models.tts_model import CONFIGS_DIR, load_config
        
        # Scan all configurations in the pocket_tts library to cache everything
        print("[INFO] Scanning and caching all internal weight and tokenizer resources for Pocket TTS configs...")
        for config_file in os.listdir(CONFIGS_DIR):
            if config_file.endswith(".yaml"):
                print(f"\n  -> Scanning config: {config_file}...")
                try:
                    cfg = load_config(CONFIGS_DIR / config_file)
                    
                    # 1. Download weights_path (Voice Cloning weights!)
                    if hasattr(cfg, 'weights_path') and cfg.weights_path:
                        print(f"     * Voice Cloning weights:")
                        smart_download(cfg.weights_path)
                        
                    # 2. Download weights_path_without_voice_cloning (Fallback weights!)
                    if hasattr(cfg, 'weights_path_without_voice_cloning') and cfg.weights_path_without_voice_cloning:
                        print(f"     * Standard Fallback weights:")
                        smart_download(cfg.weights_path_without_voice_cloning)
                        
                    # 3. Download tokenizer_path (Required text tokenizer!)
                    if hasattr(cfg, 'flow_lm') and cfg.flow_lm and hasattr(cfg.flow_lm, 'tokenizer_path') and cfg.flow_lm.tokenizer_path:
                        print(f"     * Text Tokenizer model:")
                        smart_download(cfg.flow_lm.tokenizer_path)
                        
                    # 4. Download flow_lm weights if explicitly present
                    if hasattr(cfg.flow_lm, 'weights_path') and cfg.flow_lm.weights_path:
                        print(f"     * FlowLM weights:")
                        smart_download(cfg.flow_lm.weights_path)
                        
                    # 5. Download mimi weights if explicitly present
                    if hasattr(cfg, 'mimi') and cfg.mimi and hasattr(cfg.mimi, 'weights_path') and cfg.mimi.weights_path:
                        print(f"     * Mimi Codec weights:")
                        smart_download(cfg.mimi.weights_path)
                        
                except Exception as ex:
                    print(f"     [WARNING] Could not parse/download resources for {config_file}: {ex}")
                    
        print("\n[SUCCESS] Pocket TTS models fully checked!")
    except Exception as e:
        print(f"[ERROR] Pocket TTS pre-downloader failed: {e}")
        import traceback
        traceback.print_exc()

def download_supertonic():
    print("\n==========================================================")
    print(" >>> PRE-DOWNLOADING SUPERTONIC MODELS")
    print("==========================================================\n")
    try:
        from supertonic import TTS
        print("[INFO] Fetching/Verifying Supertonic base models (~260MB)...")
        start_time = time.time()
        # Initializing TTS with auto_download=True automatically loads from cache if present
        tts = TTS(auto_download=True)
        duration = time.time() - start_time
        print(f"[SUCCESS] Supertonic models verified! (took {duration:.1f}s)")
    except Exception as e:
        print(f"[ERROR] Supertonic pre-downloader failed: {e}")
        import traceback
        traceback.print_exc()

def main():
    print("==========================================================")
    print("           AURA MULTI-ENGINE OFFLINE WARM-UP TOOL")
    print("==========================================================")
    print("This script will download all model assets, weights, voice files,")
    print("and pipeline configurations for Kokoro, Pocket, and Supertonic.")
    print("Once complete, all backends will load instantly on-device.")
    print("==========================================================\n")
    
    start_total = time.time()
    
    # Run downloaders
    download_kokoro()
    download_pocket()
    download_supertonic()
    
    total_time = time.time() - start_total
    print("\n==========================================================")
    print(f" [SUCCESS] ALL MODELS AND ASSETS WARMED UP SUCCESSFULLY!")
    print(f" Total execution time: {total_time/60.0:.1f} minutes")
    print(" All portals are fully pre-cached and ready for instant offline load.")
    print("==========================================================")

if __name__ == "__main__":
    main()
