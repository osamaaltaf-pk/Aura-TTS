import requests
import time
import numpy as np
import io

CENTRAL_URL = "http://127.0.0.1:5000"
BENCHMARK_TEXT = "The quick brown fox jumps over the lazy dog. Real-time speech synthesis benchmark testing."
NUM_TRIALS = 10

BACKENDS = {
    "kokoro": {
        "voice": "af_bella",
        "sample_rate": 24000
    },
    "pocket": {
        "voice": "audio1-en",
        "sample_rate": 24000
    },
    "supertonic": {
        "voice": "M5",
        "sample_rate": 16000
    }
}

def switch_backend(backend_name):
    print(f"\n[SWITCH] Activating backend: {backend_name.upper()}...")
    try:
        resp = requests.post(f"{CENTRAL_URL}/api/switch", json={"backend": backend_name}, timeout=30)
        if resp.status_code == 200:
            print(f"[SUCCESS] Backend {backend_name.upper()} loaded successfully.")
            # Wait for cold start to complete
            time.sleep(3)
            return True
        else:
            print(f"[ERROR] Failed to switch backend: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        print(f"[EXCEPTION] Failed to connect to central server: {e}")
        return False

def run_warmup(backend_name, config):
    print(f"[WARMUP] Performing warm-up request to clear cache...")
    payload = {
        "text": "Warm-up synthesis.",
        "voice": config["voice"],
        "speed": 1.0,
        "lang": "en",
        "format": "wav"
    }
    try:
        # Use streaming endpoint to force model compilation & loading in cache
        requests.post(f"{CENTRAL_URL}/api/tts/stream", json=payload, timeout=30)
    except:
        pass

def measure_trial(backend_name, config):
    payload = {
        "text": BENCHMARK_TEXT,
        "voice": config["voice"],
        "speed": 1.0,
        "lang": "en",
        "format": "wav"
    }
    
    start_time = time.perf_counter()
    ttfb = None
    total_bytes = 0
    
    try:
        # Request chunked streaming
        resp = requests.post(f"{CENTRAL_URL}/api/tts/stream", json=payload, stream=True, timeout=30)
        if resp.status_code != 200:
            print(f"  [ERROR] Trial failed with status {resp.status_code}")
            return None
            
        for chunk in resp.iter_content(chunk_size=1024):
            if chunk:
                if ttfb is None:
                    # Time to First Byte (TTFB) / First Audio Packet gen latency
                    ttfb = (time.perf_counter() - start_time) * 1000.0
                total_bytes += len(chunk)
                
        total_latency = (time.perf_counter() - start_time) * 1000.0
        
        # 16-bit PCM = 2 bytes per sample
        audio_duration = total_bytes / (config["sample_rate"] * 2.0)
        rtf = audio_duration / (total_latency / 1000.0) if total_latency > 0 else 0
        
        return {
            "ttfb_ms": ttfb or total_latency,
            "total_latency_ms": total_latency,
            "audio_duration_sec": audio_duration,
            "rtf": rtf
        }
        
    except Exception as e:
        print(f"  [EXCEPTION] Trial failed: {e}")
        return None

def print_results(results):
    print("\n" + "="*80)
    print("                TTS REAL-TIME STREAMING LATENCY BENCHMARKS")
    print("="*80)
    print(f"Benchmark sentence: \"{BENCHMARK_TEXT}\"")
    print(f"Number of trials per model: {NUM_TRIALS}")
    print("-"*80)
    print(f"{'Engine':<12} | {'TTFB p50':<10} | {'TTFB p90':<10} | {'Total p50':<10} | {'Total p90':<10} | {'Avg RTF':<8}")
    print("-"*80)
    
    for engine, data in results.items():
        if not data:
            print(f"{engine:<12} | {'FAILED':<10} | {'FAILED':<10} | {'FAILED':<10} | {'FAILED':<10} | {'FAILED':<8}")
            continue
            
        ttfbs = [r["ttfb_ms"] for r in data]
        totals = [r["total_latency_ms"] for r in data]
        rtfs = [r["rtf"] for r in data]
        
        ttfb_50 = np.percentile(ttfbs, 50)
        ttfb_90 = np.percentile(ttfbs, 90)
        total_50 = np.percentile(totals, 50)
        total_90 = np.percentile(totals, 90)
        avg_rtf = np.mean(rtfs)
        
        print(f"{engine.upper():<12} | {ttfb_50:7.1f}ms | {ttfb_90:7.1f}ms | {total_50:7.1f}ms | {total_90:7.1f}ms | {avg_rtf:7.2f}x")
    print("="*80)
    print("Note: Avg RTF > 1.0x means generation is faster than real-time playback speed.")
    print("TTFB: Time to First Byte (instant latency to first audible chunk).")
    print("="*80)

def main():
    print("Initializing speech synthesis performance benchmarks...")
    results = {}
    
    for backend, config in BACKENDS.items():
        if not switch_backend(backend):
            results[backend] = None
            continue
            
        run_warmup(backend, config)
        
        print(f"[BENCHMARK] Running {NUM_TRIALS} trials for {backend.upper()}...")
        backend_results = []
        for i in range(NUM_TRIALS):
            trial = measure_trial(backend, config)
            if trial:
                backend_results.append(trial)
            time.sleep(0.5)
            
        results[backend] = backend_results
        
    print_results(results)

if __name__ == "__main__":
    main()
