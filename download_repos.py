import urllib.request
import zipfile
import io
import os
import shutil

repos = {
    "kokoro-tts-local": "https://github.com/PierrunoYT/Kokoro-TTS-Local/archive/refs/heads/main.zip",
    "pocket-tts-server": "https://github.com/ai-joe-git/pocket-tts-server/archive/refs/heads/main.zip",
    "supertonic": "https://github.com/supertone-inc/supertonic/archive/refs/heads/main.zip"
}

def download_and_extract(name, url):
    print(f"Downloading {name} from {url}...")
    headers = {'User-Agent': 'Mozilla/5.0'}
    req = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(req) as response:
            zip_data = response.read()
        print(f"Downloaded {name} successfully. Extracting...")
        
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zip_ref:
            # Get the top level directory name inside the zip
            top_dir = zip_ref.namelist()[0].split('/')[0]
            zip_ref.extractall(".")
            
        print(f"Extracted {name}. Renaming {top_dir} to {name}...")
        if os.path.exists(name):
            shutil.rmtree(name)
        os.rename(top_dir, name)
        print(f"Finished setting up {name}!\n")
    except Exception as e:
        print(f"Error processing {name} with URL {url}: {e}")
        # Try master.zip if main.zip fails
        if "main.zip" in url:
            alternative_url = url.replace("main.zip", "master.zip")
            print(f"Retrying with master branch URL: {alternative_url}")
            download_and_extract(name, alternative_url)

if __name__ == "__main__":
    for name, url in repos.items():
        download_and_extract(name, url)
