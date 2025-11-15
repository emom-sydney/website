**sydney.emom.me**

This is the codebase for sydney.emom.me website. We are building with the [11ty](https://www.11ty.dev) Static Site Generator. I have used CoPilot extensively to kick things off because I'm too impatient to read the doco, but I have very little idea what I'm doing within VSCode so it's all default settings and stuff but (somewhat to my surprise) it seems to be mostly working reasonably well and the only hallucinations that have been happening are by me.

However the fact remains that all good code here is mine, everything else is the LLM's fault.

To build the site files, from the top level directory run
```
npx @11ty/eleventy 
```
and the site will be generated in the _site directory. (add the `--serve` flag to have it served to `localhost:8080`)

To add a gallery for an event:
 - upload files to s3://sydney.emom.me/gallery/*galleryname*
 - add *gallleryname* to src/data/galleries.js
 - build the site as detailed above
 - sync to the live webserver `rsync -rv --delete _site/ root@sydney.emom.me:/var/www/html/sydney.emom.me/`

 TODO:
  - media uploads page
  - USB stick with .ssh key and executable script to import media
  - work out a way for 11ty to build galleries without having to be logged in to AWS (?without just making the s3 bucket public?)
  - reinstate form submission but with python &sqlite (or even .csv?!) for db (see #thoughts) 
  - move code repo to forgejo @ git.emom.me 
  - finish the TODO list

# Thoughts
A website for a small community organisation has different resource needs compared to most social and/or groupware kind of sites. If you're not chasing user numbers, if the website is run by a small subset of a small group of eager volunteers, I think there's an opportunity to build something quite effective yet simple and transferable. 

My theory is that an emom event will likely only ever have a handful of volunteers running it at any one time, usually out of a google spreadsheet which is basically just lists of text information anyway. So what if the backend was just a text document that anyone could understand and edit? Obviously you'd put that behind secure authentication etc but again, we don't have to neccessarily spin up an entire MFA infrastructure when everyone involved actually physically knows each other from having met at the music nights. Does that make sense? 

Imagine the artist arrives at venue and gets a QR code with URL and a one-time token (make it an art item they can keep) which activates their profile page on the emom website, and where they can enter their details (stage name, name of tunes they’re playing, social URLs etc) and not only do they get a free profile page right away, we can also generate images & html that OBS can use for title screens and text crawls while they’re playing. 

We had a data projector showing the artists names at the November event, but that was a static image generated before we knew the order the acts would be playing in. Have the projector instead show a web page that dynamically updates with Now Playing. Another page would allow selection of the artist name so that MC - having it open on their phone alongside the profile page and their own notes for each act - just has to tap on it to update all the signage. (I simplify, but I think it's all quite doable by putting the right pieces together in the right way)