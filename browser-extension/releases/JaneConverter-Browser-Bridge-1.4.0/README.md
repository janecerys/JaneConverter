# JaneConverter Browser Capture

This optional local extension sends media that you explicitly select in an open
browser page to JaneConverter over the local loopback connection. It does not
read, export, upload, or save browser cookies, cache databases, passwords, or
session files.

## Install in Vivaldi or another Chromium browser

1. Open the browser's extensions page (\`vivaldi://extensions\`,
   \`chrome://extensions\`, or the equivalent).
2. Enable **Developer mode**.
3. Choose **Load unpacked**.
4. Select this \`browser-extension\` folder.

## Use

1. In JaneConverter, choose **Create access link**. A source URL is optional.
2. Open the source in the browser where you are already signed in.
3. Return to the access page and confirm access.
4. Open this extension from the browser toolbar.
5. Choose **Capture current media** for the visible video, audio, or image. The
   bridge can read direct media URLs and browser-created blob media. If a site
   only exposes the video while it is playing, the bridge records that visible
   playback into a temporary WebM instead.
6. **Experimental:** Choose **Capture story sequence** when the story pages are presented
   in one open story viewer. Story viewers change their media codes frequently, so
   this mode may miss pages or capture duplicates.
7. Approve the browser's permission prompt for the source or its media delivery
   host when asked.
8. Return to JaneConverter and click **Convert**.

## Story sequence status

Story sequence capture remains experimental. It is intentionally kept available for testing, but it is not the reliability path yet; use **Capture current media**, **Collect mode**, or **Network Compatibility Mode** when you need repeatable captures.

## Story sequence status

Story sequence capture remains experimental. It is intentionally kept available for testing, but it is not the reliability path yet; use **Capture current media**, **Collect mode**, or **Network Compatibility Mode** when you need repeatable captures.

## Collect mode

Use **Enable collect mode** when the browser story viewer pauses or changes as soon
as the extension popup closes:

1. Confirm access once in JaneConverter.
2. Open the story page and open the extension popup.
3. Click **Enable collect mode**, then close the popup.
4. Play or advance stories normally. JaneConverter watches the active page and
   sends the primary rendered story surface to **Fetched Media**.
5. Open **Fetched Media** in JaneConverter to preview, discard, or convert each
   captured item. Click **Disable collect mode** from the extension popup when
   finished.

Collect mode does not read cookies or browser storage. It captures rendered image
surfaces and currently playing video frames, ignores small page thumbnails when
possible, and keeps the same confirmed access session for every item. A browser
may still refuse protected, DRM-backed, paused, or cross-origin media; collect
mode does not bypass those restrictions.

## Network Compatibility Mode

Use **Enable Network Compatibility Mode** when a site plays media but the page
does not expose readable media bytes to the normal capture path:

1. Confirm access once in JaneConverter and leave the access page open.
2. Open the signed-in media page in the same browser tab.
3. Open the extension and choose **Enable Network Compatibility Mode**.
4. Play or advance the media normally. JaneConverter listens only to approved
   media responses from that tab and places accepted files in **Fetched Media**.
5. Disable the mode when finished.

This mode uses Chrome's tab-scoped debugger/network API, so the browser shows a
high-privilege debugger permission warning. That warning is expected. The mode
is disabled by default and is enabled only by the user's click for one selected
tab. The extension does not read or export cookies, authorization headers,
request bodies, page text, or browser databases. The Console shows only redacted
host, media type, response status, size, and accepted/discarded reason.

Adaptive manifests, tiny assets such as avatars, unapproved hosts, failed
responses, DRM-protected playback, and media bodies that the browser does not
make available are discarded. The mode improves reliability for ordinary
authenticated media responses, but it cannot defeat browser or site DRM.
On the first capture click, JaneConverter inspects only the selected source tab.
The extension checks the page's media elements (including shadow DOM and canvas
renderers), observes media URLs created by that page's fetch/XHR activity, and
then reads only the item you selected. Direct media is streamed to the local
bridge; blob or rendered media uses the browser's playback capture fallback.
The extension never reads cookies, browser databases, request bodies, or
unrelated tabs.

JaneConverter receives a temporary media file for the current app session. The
file is removed when the access session is cleared or the app exits. Captures
are still subject to the source site's access rules and the browser's ability
to expose or render the selected media; the extension does not bypass DRM,
private API restrictions, or protected media. Keep the selected video open and
playing while using the capture button.

## Supported sites

There is no hard-coded social-media list. The extension can capture any
HTTP/HTTPS page whose visible media can be fetched by the current browser
session, including common Facebook, Instagram, X/Twitter, YouTube, TikTok,
Reddit, Twitch, Vimeo, Dailymotion, Rumble, Kick, SoundCloud, Spotify,
Bandcamp, Mixcloud, Discord, Telegram, Pinterest, LinkedIn, Snapchat, Tumblr,
Flickr, Imgur, Bilibili, VK, WhatsApp, and Streamable pages. Actual results
depend on the page and the site's media delivery behavior.

## Troubleshooting capture errors

- **JaneConverter bridge request failed** means the confirmed localhost access
  page is stale, closed, or the local app is not running. Reopen a fresh access
  link and confirm it.
- **Media read failed** means the browser exposed a media URL but did not allow
  the extension or the signed-in page to read its bytes. Keep the media playing,
  approve the host permission, and retry.
- An adaptive playlist (.m3u8 or .mpd) alone is not a downloadable file. The
  extension will wait for a direct rendition or use the visible playback
  fallback; it does not bypass DRM.
