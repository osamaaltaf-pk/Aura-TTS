import sys
sys.path.append(".")
from central_server import split_text_into_chunks

text = """This is flow inpected via inspect methdo on chrom, i need playwright automation extension to automate image generation on flow , i want to upload , list of prompts, select aspect ratio, model slection from list , number of generation, this extension must use broser by playwright and control broswer even if i maximize or shorten the broswer width to fit two or more chrom profiles on a laptop screen , and sleects these buttons on ui and perform automation image and video generation attaching you the ui ss of the flow website ,it must rename generated images in a specific folder wihch can be edits manually in setting, cache clear system, retry failed images, all features like this , it must select , Clear prompt on submit, within setting icon on the upper right tabs and click to make this prompt clearing automatically,a nd then click below nanao banana button and upload button to upload images and there is another function to reuse already uploaded images , for image to image genartion, two mode, story mode, in edit mode new image will be uploaded each time from computer - this mode must eb slow very much so delay in action must be configureable on settng tab, story mode, one image will be uploaded and it must select from already uploaded image the first uploaded image autocailly to resue for indivdual scene generation on original character sheet or environent shaett image and apply prompts from list one by one, in edit mode one image one prompt will be uplaoded."""

chunks = split_text_into_chunks(text, max_len=200)
print(f"Generated {len(chunks)} chunks.")
for i, chunk in enumerate(chunks):
    print(f"Chunk {i+1} (len={len(chunk)}): {chunk}")
