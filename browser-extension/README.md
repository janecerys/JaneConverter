# JaneConverter Browser Bridge

This optional local extension lets JaneConverter use a browser session while Vivaldi, Chrome, Edge, Brave, or another Chromium browser remains open.

It does not export a cookie file, upload session data, or send anything to a remote service. When the user clicks **Connect**, the extension requests permission for the current source origin, reads only cookies applicable to that source URL, and sends them to the one-time JaneConverter loopback access link. JaneConverter validates the payload and keeps it in memory for the current app process.

## Install in Vivaldi

1. Open `vivaldi://extensions`.
2. Enable **Developer mode**.
3. Choose **Load unpacked**.
4. Select this `browser-extension` folder.

## Use

1. In JaneConverter, paste the online source and click **Create access link**.
2. Sign in or open the source in the browser.
3. Return to the access page and click **I am signed in — confirm access**.
4. Open the JaneConverter Browser Bridge extension and click **Connect to JaneConverter**.
5. Approve the permission for that source origin, then return to JaneConverter and convert.

The existing browser-database path remains available as a fallback when the bridge is not installed or not selected.

## Site coverage and permissions

The extension does not maintain a hard-coded list of social or media platforms.
It supports any HTTP or HTTPS source that the browser exposes through its cookies
API. When the Connect button is clicked, the browser asks for permission for the
current source origin only. This keeps the install narrow while still supporting
Facebook, Instagram, X/Twitter, YouTube, TikTok, Reddit, Twitch, Vimeo,
Dailymotion, Rumble, Kick, SoundCloud, Spotify, Apple Music, Bandcamp, Mixcloud,
Discord, Telegram, Pinterest, LinkedIn, Snapchat, Tumblr, Flickr, Imgur, Bilibili,
VK, WhatsApp, Streamable, and other supported yt-dlp sites without editing the
manifest.

The extension reads only cookies applicable to the confirmed source URL and sends
them only to JaneConverter's one-time loopback bridge.
