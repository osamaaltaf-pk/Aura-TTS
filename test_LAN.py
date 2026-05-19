import os
import sys
import time
import requests

def get_base_url():
    # Attempt to query the local orchestrator to find its current state and local LAN IP
    local_url = "http://127.0.0.1:5000"
    try:
        resp = requests.get(f"{local_url}/api/status", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            lan_ip = data.get("system", {}).get("local_ip", "127.0.0.1")
            print(f"[INFO] Discovered central server online.")
            print(f"[INFO] Local LAN URL: http://{lan_ip}:5000")
            print(f"[INFO] Loopback URL: {local_url}")
            return local_url
    except Exception as e:
        print(f"[WARNING] Local connection to {local_url} failed: {e}")
    
    # Default to localhost loopback
    return local_url

def switch_and_wait(base_url, backend):
    print(f"\n--- Testing Backend: {backend.upper()} ---")
    print(f"[INFO] Requesting switch to {backend} (timeout up to 180s)...")
    try:
        # FastAPI's /api/switch internally waits up to 180s for the backend port to open,
        # so we set our client timeout to 180s to accommodate heavy model loads.
        resp = requests.post(f"{base_url}/api/switch", json={"backend": backend}, timeout=180)
        if resp.status_code == 200:
            print(f"[SUCCESS] {backend.upper()} model loaded and active backend set successfully!")
            return True
        else:
            print(f"[ERROR] Failed to switch: {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        print(f"[ERROR] Switch request connection failed: {e}")
        return False

def test_synthesis(base_url, backend):
    # Fetch available voices
    print(f"[INFO] Querying available voices for {backend}...")
    voice_name = None
    try:
        resp = requests.get(f"{base_url}/api/voices", timeout=10)
        if resp.status_code == 200:
            voices = resp.json().get("voices", [])
            if voices:
                voice_name = voices[0].get("name")
                print(f"[INFO] Found {len(voices)} available voices. Selected: '{voice_name}'")
            else:
                print(f"[WARNING] No voices returned by {backend} API.")
    except Exception as e:
        print(f"[WARNING] Failed to fetch voices list: {e}")

    # Fallback default voices if none discovered
    if not voice_name:
        defaults = {
            "kokoro": "af_sarah",
            "pocket": "ljspeech",
            "supertonic": "standard"
        }
        voice_name = defaults.get(backend, "default")
        print(f"[INFO] Falling back to default voice for {backend}: '{voice_name}'")

    # Synthesize
    payload = {
        "text": f"Hello! This speech is being generated locally offline via the Aura TTS {backend.upper()} engine.",
        "voice": voice_name,
        "speed": 1.0,
        "lang": "en"
    }
    
    url = f"{base_url}/api/tts"
    print(f"[INFO] Synthesizing audio via {url}...")
    start_time = time.time()
    try:
        response = requests.post(url, json=payload, timeout=60)
        if response.status_code == 200:
            filename = f"output_{backend}.wav"
            with open(filename, "wb") as f:
                f.write(response.content)
            duration = time.time() - start_time
            print(f"[SUCCESS] Speech synthesized in {duration:.2f}s and saved to '{filename}'!")
            return True
        else:
            print(f"[ERROR] Synthesis failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"[ERROR] Synthesis request failed: {e}")
        return False

def main():
    print("==========================================================")
    print("           Aura TTS LAN API Integrator & Test             ")
    print("==========================================================")
    
    base_url = get_base_url()
    
    # We will test all three engines sequentially: kokoro, pocket, supertonic
    backends = ["kokoro", "pocket", "supertonic"]
    results = {}
    
    for backend in backends:
        if switch_and_wait(base_url, backend):
            # Add small delay to let backend stabilize post port-binding
            time.sleep(2)
            success = test_synthesis(base_url, backend)
            results[backend] = "PASSED" if success else "SYNTHESIS_FAILED"
        else:
            results[backend] = "LOADING_FAILED"
            
    print("\n==========================================================")
    print("                      TEST RESULTS                        ")
    print("==========================================================")
    for backend, status in results.items():
        print(f"{backend.upper():<12} : {status}")
    print("==========================================================")

if __name__ == "__main__":
    main()
