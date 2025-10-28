**sydney.emom.me**

This is the codebase for sydney.emom.me website. We are building with the [11ty](https://www.11ty.dev) Static Site Generator. I have used CoPilot extensively to kick things off because I'm too impatient to read the doco, but I have no idea what I'm doing with the VSCode integration so it's all default settings and stuff but (somewhat to my surprise) it seems to be mostly working reasonably well and the only hallucinations that have been happening are by me.

However the fact remains that all good code here is mine, everything else is the LLM's fault.

To add a gallery for an event:
 - upload files to s3://sydney.emom.me/gallery/*galleryname*
 - add *gallleryname* to src/data/galleries.js


 TODO:
  - media uploads page for gallery
  - finish the TODO list