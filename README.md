**sydney.emom.me**

This is the codebase for sydney.emom.me website. We are building with the [11ty](https://www.11ty.dev) Static Site Generator. I have used CoPilot extensively to kick things off because I'm too impatient to read the doco, but I have no idea what I'm doing with the VSCode integration so it's all default settings and stuff but (somewhat to my surprise) it seems to be mostly working reasonably well and the only hallucinations that have been happening are by me.

However the fact remains that all good code here is mine, everything else is the LLM's fault.

To build the site files, from the top level directory run
```
npx @11ty/eleventy 
```
and the site will be generated in the _site directory. (add the `--serve` flag to have it served to `localhost:8080`)

To add a gallery for an event:
 - upload files to s3://sydney.emom.me/gallery/*galleryname*
 - add *gallleryname* to src/data/galleries.js

 TODO:
  - media uploads page for gallery
  - work out a way for 11ty to build galleries without having to be logged in to AWS (without just making the s3 bucket public)
  - reinstate form submission but with python &sqlite (or even .csv?!) for db (see #thoughts) 
  - move code repo to forgejo @ git.emom.me 
  - finish the TODO list

# Thoughts
A website for a small community organisation has different resource needs compared to most social and/or groupware kind of sites. If you're not chasing user numbers, if the website is run by a small subset of a small group of eager volunteers, I think there's an opportunity to build something quite effective yet simple and transferable. 

My theory is that an emom event will likely only ever have a handful of volunteers running it at any one time, usually out of a google spreadsheet which is basically just lists of text information anyway. So what if the backend was just a text document that anyone could understand and edit? Obviously you'd put that behind secure authentication etc but again, we don't have to neccessarily spin up an entire MFA infrastructure when everyone involved actually physically knows each other from having met at the music nights. Does that make sense? 