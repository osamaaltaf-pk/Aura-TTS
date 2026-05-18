import os
import base64
import requests
import sys

def load_gitignore_patterns(base_dir):
    """Load standard ignore rules matching our .gitignore"""
    ignored_dirs = {'venv', '.venv', 'env', '__pycache__', '.git', '.cache', 'outputs', 'output'}
    ignored_exts = {'.pth', '.pt', '.bin', '.onnx', '.log', '.wav', '.mp3', '.ogg', '.flac'}
    ignored_files = {'pocket.log', 'kokoro.log', 'supertonic.log'}
    return ignored_dirs, ignored_exts, ignored_files

def get_all_files(base_dir):
    """Walk directory and retrieve all files to be uploaded, respecting gitignore patterns"""
    ignored_dirs, ignored_exts, ignored_files = load_gitignore_patterns(base_dir)
    upload_list = []
    
    for root, dirs, files in os.walk(base_dir):
        # In-place modify dirs to avoid walking into ignored directories
        dirs[:] = [d for d in dirs if d not in ignored_dirs and not d.startswith('.')]
        
        for file in files:
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, base_dir)
            
            # Check exclusions
            _, ext = os.path.splitext(file.lower())
            if ext in ignored_exts:
                continue
            if file in ignored_files or file.startswith('temp_upload_'):
                continue
            if rel_path.startswith('.'):
                continue
                
            upload_list.append(rel_path)
            
    return upload_list

def upload_file_to_github(username, repo, token, rel_path, local_full_path):
    """Uploads a single file to GitHub via the REST API"""
    url = f"https://api.github.com/repos/{username}/{repo}/contents/{rel_path.replace(os.sep, '/')}"
    
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # Check if the file already exists on GitHub to get its SHA (if updating)
    sha = None
    get_resp = requests.get(url, headers=headers)
    if get_resp.status_code == 200:
        sha = get_resp.json().get("sha")
        
    # Read and encode file content to Base64
    with open(local_full_path, "rb") as f:
        content_bytes = f.read()
        content_b64 = base64.b64encode(content_bytes).decode("utf-8")
        
    payload = {
        "message": f"Upload {rel_path} via Aura Publisher",
        "content": content_b64
    }
    if sha:
        payload["sha"] = sha
        
    put_resp = requests.put(url, json=payload, headers=headers)
    return put_resp

def main():
    print("==========================================================")
    print("               🎙️ AURA TTS GITHUB PUBLISHER                ")
    print("==========================================================")
    print("\nThis script will upload Aura TTS directly to GitHub using the REST API.")
    print("No Git client is required! Large assets and caches are automatically ignored.\n")
    
    # 1. Ask for credentials
    username = input("Enter your GitHub Username: ").strip()
    if not username:
        print("Username cannot be empty.")
        return
        
    repo = input("Enter GitHub Repository Name (e.g. Aura-TTS): ").strip()
    if not repo:
        print("Repository name cannot be empty.")
        return
        
    print("\nTo upload, you need a GitHub Personal Access Token (PAT).")
    print("Follow these steps to create one:")
    print("1. Open your browser and log in to https://github.com")
    print("2. Go to Settings -> Developer Settings -> Personal Access Tokens -> Tokens (classic)")
    print("3. Click 'Generate new token (classic)'")
    print("4. Give it a note (e.g., 'AuraPublisher') and check the 'repo' scope checkbox.")
    print("5. Generate and copy the token.\n")
    
    token = input("Paste your GitHub Personal Access Token (PAT): ").strip()
    if not token:
        print("Token cannot be empty.")
        return
        
    base_dir = os.path.dirname(os.path.abspath(__file__))
    files_to_upload = get_all_files(base_dir)
    
    if not files_to_upload:
        print("No files found to upload.")
        return
        
    print(f"\nFound {len(files_to_upload)} files to upload (respecting .gitignore rules).")
    confirm = input("Do you want to proceed? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Upload cancelled.")
        return
        
    print("\nStarting upload...")
    success_count = 0
    
    for idx, rel_path in enumerate(files_to_upload, 1):
        local_path = os.path.join(base_dir, rel_path)
        print(f"[{idx}/{len(files_to_upload)}] Uploading {rel_path}...", end="", flush=True)
        
        try:
            resp = upload_file_to_github(username, repo, token, rel_path, local_path)
            if resp.status_code in [200, 201]:
                print(" ✅ Success")
                success_count += 1
            else:
                print(f" ❌ Failed ({resp.status_code}: {resp.json().get('message')})")
        except Exception as e:
            print(f" ❌ Error: {e}")
            
    print(f"\n==========================================================")
    print(f"Upload complete! Successfully uploaded {success_count}/{len(files_to_upload)} files.")
    print(f"Check your repository at: https://github.com/{username}/{repo}")
    print(f"==========================================================\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nPublisher stopped.")
        sys.exit(0)
