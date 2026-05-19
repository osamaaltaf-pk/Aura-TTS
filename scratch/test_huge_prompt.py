import requests
import os

text = """This is flow inpected via inspect methdo on chrom, i need playwright automation extension to automate image generation on flow , i want to upload , list of prompts, select aspect ratio, model slection from list , number of generation, this extension must use broser by playwright and control broswer even if i maximize or shorten the broswer width to fit two or more chrom profiles on a laptop screen , and sleects these buttons on ui and perform automation image and video generation attaching you the ui ss of the flow website ,it must rename generated images in a specific folder wihch can be edits manually in setting, cache clear system, retry failed images, all features like this , it must select , Clear prompt on submit, within setting icon on the upper right tabs and click to make this prompt clearing automatically,a nd then click below nanao banana button and upload button to upload images and there is another function to reuse already uploaded images , for image to image genartion, two mode, story mode, in edit mode new image will be uploaded each time from computer - this mode must eb slow very much so delay in action must be configureable on settng tab, story mode, one image will be uploaded and it must select from already uploaded image the first uploaded image autocailly to resue for indivdual scene generation on original character sheet or environent shaett image and apply prompts from list one by one, in edit mode one image one prompt will be uplaoded."""

# Use the currently active voice or standard test voice
payload = {
    "text": text,
    "voice": "test",
    "lang": "en",
    "format": "wav"
}

# Make sure scratch directory exists
os.makedirs("scratch", exist_ok=True)

print("[PROBE] Sending massive prompt to local TTS backend...")
r = requests.post("http://127.0.0.1:5000/api/tts", json=payload)
print(f"[PROBE] Status code: {r.status_code}")
if r.status_code == 200:
    out_path = "scratch/huge_prompt_synthesis_test.wav"
    with open(out_path, "wb") as f:
        f.write(r.content)
    print(f"[SUCCESS] Audio successfully generated and saved to: {out_path}")
    print(f"[INFO] Total generated audio size: {len(r.content)} bytes")
else:
    print(f"[FAILED] Error detail: {r.text}")
