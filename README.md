**sydney.emom.me**

This is the codebase for sydney.emom.me website. We are building with the [11ty](https://www.11ty.dev) Static Site Generator. I have used CoPilot extensively to kick things off because I'm too impatient to read the doco, but I have very little idea what I'm doing within VSCode so it's all default settings and stuff but (somewhat to my surprise) it seems to be mostly working reasonably well and the only hallucinations that have been happening are by me.

However the fact remains that all good code here is mine, everything else is the LLM's fault.

To build the site files, from the top level directory run
```
npx @11ty/eleventy 
```
and the site will be generated in the _site directory. (add the `--serve` flag to have it served to `localhost:8080`)

To add a gallery for an event:
 - upload files to https://media.emom.me/gallery/*galleryname* (TODO add a file uploader)
 - set *galleryname* in the `events.gallery_url` value in Postgres
 - build the site as detailed above
 - sync to the test webserver `rsync -rv --delete _site/ root@sydney.emom.me:/var/www/html/test.emom.me/`
 - sync to the live webserver `rsync -rv --delete _site/ root@sydney.emom.me:/var/www/html/sydney.emom.me/`

To add an event video embed on a gallery page:
 - set `events.youtube_embed_url` for the event row that has the matching `events.gallery_url`
 - accepted values include:
   - `https://www.youtube.com/watch?v=VIDEO_ID`
   - `https://youtu.be/VIDEO_ID`
   - `https://www.youtube.com/embed/VIDEO_ID`
   - `https://www.youtube.com/shorts/VIDEO_ID`
   - `https://www.youtube.com/live/VIDEO_ID`
   - raw `VIDEO_ID` (11 chars)
   - pasted iframe embed HTML (the `src` URL is extracted)
 - the site normalizes valid inputs to a privacy-enhanced embed URL on render:
   - `https://www.youtube-nocookie.com/embed/VIDEO_ID`
 - if a value is present but cannot be normalized, gallery pages show a fallback `Open event video` link instead of an iframe

## Postgres runtime

The site now reads its relational data from Postgres via the SSH tunnel documented in `DB_SETUP.md`.

Relevant files:

- Schema: `db/schema.sql`
- Runtime loader: `lib/data/loadEmomData.js`
- Local tunnel env template: `.pgenv-example`

To run the site:

```bash
cp .pgenv-example .pgenv
$EDITOR .pgenv

set -a
source ./.pgenv
set +a

npx @11ty/eleventy
```

`DATABASE_URL` can be used instead of the individual `PG*` variables if preferred, but the current repo workflow uses `.pgenv`.

 TODO:
  - media uploads page
  - reinstate form submission but with python (or php?) (see #thoughts) 
  - move code repo to forgejo instance git.emom.me 
  - calendar/contacts (https://sabre.io/baikal ?)
  - work out a way for 11ty to build galleries without having to be logged in to AWS :DONE
  - thumbnails for images in galleries: :DONE
  - artist profile pages: :DONE
  - set up MX an for the domain :DONE

# Thoughts
A website for a small community organisation has different resource needs compared to most social or groupware kind of sites. If you're not chasing user numbers, if the website is run by a small subset of a small group of eager volunteers, I think there's an opportunity to build something quite effective yet simple and portable. 

My theory is that an emom event will likely only ever have a handful of volunteers running it at any one time, usually out of a google spreadsheet which is basically just lists of text information anyway. So what if the backend was just a text document that anyone could understand and edit? Obviously you'd put that behind secure authentication etc but again, we don't have to neccessarily spin up an entire MFA infrastructure when everyone involved actually physically knows each other from having met at the music nights. In other words, we can base the security architecture around the idea of physical presence and contacts, which I think would open up a bunch of unique possibilities. Some scripts on a USB stick with an embedded ssh key could just about do everything we want if we set up the workflows right.

Imagine a performer arrives at the venue and gets a QR code with URL and a one-time token on a piece of wood (make it an art item they can keep) which activates their profile page on the emom website, and where they can enter their details (stage name, name of tunes they’re playing, social URLs etc) and not only do they get a free profile page right away, we can also generate images & html that OBS can use for title screens and text crawls while they’re playing. 

We had a data projector showing the artists names at the November event, but that was a static image generated before we knew the order the acts would be playing in. Have the projector instead show a web page that dynamically updates with Now Playing. Another page would allow selection of the artist name so that MC - having it open on their phone alongside the profile page and their own notes for each act - just has to tap on it to update all the signage. (I simplify, but I think it's all quite doable by putting the right pieces together in the right way)

## Resources
- [logos](https://drive.google.com/drive/u/0/mobile/folders/1oDfZQdZb9NQhx_in6vafl0fO-Ktstt2t/1EMySK_hN9GL3JIHSHvwSoSFfeiV8tKy9?usp=sharing&sort=13&direction=a)
