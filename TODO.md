# TODO

## Open

### Bugs

- [ ] Gallery lightbox is fixed to top of page instead of scrolling with content

- [x] User reported error "Unexpected token '<', "<html><h"...is not valid JSON" when "send registration link" is clicked at start of performer registration workflow. [It was an http/https mismatch]
 
### Enhancements

- [ ] Templates for email notifications (styled html with multipart text/plain alternatives)
- [x] opt-in toggle on performer registration page for "add to alumni mailing list"

- [ ] email admin details when toast alert triggered by error (if that's even possible given toast notifications happen client-side?)

- [x] Thumbnail generation on media server instead of during 11ty build
- [ ] Tag system for media so we can pull gallery pics into performer profiles, among other things. 

- [ ] New db table for profile options, containing:
    - [ ] image_url from profile_images
    - [ ] Tribuo link
    - [ ] Fun question/answers on profile pages, eg Favourite TV show? Cat or dog person? Roland or Korg? They can pick one or two from (say) a dozen or so choices
    - [ ] Content usage / copyright release consent flag
    - [ ] "Notify when new event dates added" flag
    - [ ] "always use bcc when emailing me" flag

- [ ] Migrate static .json values in _data to Global/app settings in a db table (among other things this allows us to have separate settings for dev/test & prod server)
- [ ] Tabbed admin interface, with tabs for performer profiles, event calender, other planned features. Speaking of which:
    - [ ] Blog
    - [ ] Classifieds 

- [ ] Stage Manager / MC page for use during event. Read performer bios, arrange running order. Use simple tile interface suitable for mobile phone screen.
- [ ] Tied to the above, an api (maybe) to allow real-time display of current performer name and a QR code directed at performer profile.

### Later:

- [ ] move code repo to self-hosted forgejo instance 
- [ ] calendar/contacts (https://sabre.io/baikal ?)
- [ ] An SMS gateway so we can send & receive performer confirmation messages in a more immediate way than email currently does.
