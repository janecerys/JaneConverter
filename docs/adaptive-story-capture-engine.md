# Adaptive Story Capture Engine

**Status:** Proposed design  
**Milestone:** Experimental story-capture improvement  
**Product boundary:** Supporting media ingestion; not part of the core converter reliability gate

## Goal

Story implementations change constantly: DOM structures, internal identifiers, media URLs, rendering methods, and navigation behavior can all change independently.

The story grabber should therefore not depend on one permanent selector or one story code. It should observe the page, form multiple capture hypotheses, try the safest viable strategy, validate the result, learn which strategy worked for the local site/layout, and recover when the page changes.

The internal metaphor is Mahoraga: adaptation through repeated observation and response. This is not a remote AI scraper. It is a local, deterministic strategy engine with evidence, fallbacks, and bounded memory.

## Non-goals

- Do not make story capture a requirement for ordinary conversion.
- Do not capture arbitrary page media, profile pictures, navigation thumbnails, or unrelated assets.
- Do not store cookies, passwords, tokens, signed URLs, request headers, or browser-profile data.
- Do not depend on one site's private story identifiers.
- Do not promise perfect support for every site before site-specific evidence exists.
- Do not use a remote LLM to inspect private story pages.

## Architecture overview

~~~text
Story page
    |
    v
Story surface detector
    |
    v
Candidate discovery
    |
    v
Evidence scoring and filtering
    |
    v
Capture strategy ladder
    |
    v
Media validation and fingerprinting
    |
    v
Fetched Media
    |
    v
Local adaptation memory
~~~

The existing DOM collection, network capture, page-context fetch, canvas capture, and MediaRecorder paths should become strategies behind this engine rather than independent story implementations.

## Core components

### 1. Story surface detector

Find the active story viewer before selecting media. Candidate surfaces should be scored using:

- full-screen or modal geometry
- high z-index and visible overlay state
- focus and active dialog state
- story navigation controls
- progress bars
- “next story,” “previous,” “close,” “pause,” or similar accessibility labels
- viewport-sized media containers
- shadow-root and iframe boundaries

The surface detector gives the rest of the engine a bounded region. This is the primary defence against profile pictures, sidebar thumbnails, and unrelated page media.

### 2. Candidate discovery

Discover candidates from multiple sources:

**DOM and rendering**

- video, image, picture/source, and canvas elements
- CSS background images
- shadow DOM
- story-related iframe content

**Browser media signals**

- currentSrc and source URLs
- recent resource timing entries
- media requests and approved response bodies
- recently loaded media URLs

**Story-state signals**

- currently playing media
- media that changed after navigation
- media near the active progress indicator
- media adjacent to story controls
- media whose visual fingerprint changed after advancing

No individual source is trusted on its own.

### 3. Evidence scoring

Each candidate receives positive and negative evidence rather than a simple selected/not-selected flag.

Positive evidence:

- inside the detected story surface
- currently playing
- large active rendering area
- near story navigation controls
- recently changed
- approved media host and valid MIME type
- meaningful dimensions or duration
- successful strategy in the current site/layout profile

Negative evidence:

- very small dimensions
- repeated throughout the page
- near an avatar or profile region
- outside the active story surface
- static navigation thumbnail
- duplicate URL or visual fingerprint
- no meaningful bytes
- below the media-size floor

The selected candidate should retain an explainable score, for example:

~~~text
Candidate score: 91

+ Story surface: 30
+ Currently playing: 25
+ Recent change: 15
+ Valid video response: 15
+ Large viewport area: 10
- Duplicate thumbnail: 4
~~~

### 4. Capture strategy ladder

Strategies should be attempted from least invasive and most direct to most approximate:

1. **Direct media response** — use a validated media URL or response body.
2. **Page-context fetch** — fetch from the signed-in source page for approved hosts.
3. **Network compatibility capture** — use approved media responses when DOM data is unavailable.
4. **Rendered image capture** — use canvas or the rendered image surface.
5. **Cropped visible-tab capture** — capture only the detected story rectangle as a last resort.
6. **Rendered video capture** — use captureStream and MediaRecorder when direct methods fail.

Rendered captures must be labelled as rendered because quality, overlays, captions, and file metadata may differ from the original.

Each attempt must have a timeout, a bounded size, and a reason recorded for success or failure.

### 5. Media validation

Before sending an item to JaneConverter, validate:

- non-empty bytes
- expected media kind
- MIME type and magic bytes
- dimensions for images and video
- duration where available
- maximum size
- readable file structure
- duplicate fingerprint

JaneConverter should not report a story capture as successful until the bridge and the desktop application both accept the bytes.

### 6. Story state machine

Use explicit states instead of one long capture loop:

~~~text
Idle
  -> StorySurfaceDetected
  -> WaitingForReadableMedia
  -> CandidateSetReady
  -> CandidateSelected
  -> Capturing
  -> Validating
       -> Valid: SentToFetchedMedia
       -> Invalid: TryNextStrategy
       -> Failed: ReprobeSurface
  -> WaitingForStoryAdvance
  -> StoryChanged
~~~

This prevents a failed story item from freezing the popup, allows safe retries, and keeps story failures away from ordinary conversion.

### 7. Stable story fingerprints

Story codes and internal identifiers are unstable. They should be optional metadata, not the identity of a story.

Use a composite fingerprint:

~~~text
site + story surface + media kind
+ normalized media URL when available
+ dimensions
+ duration
+ visual hash
+ short-term sequence position
~~~

For images, use a perceptual thumbnail hash. For videos, combine URL, dimensions, duration, and a first-frame hash where available.

This allows the engine to recognize the same story loaded through different CDN URLs while still detecting a genuinely new story with no stable identifier.

### 8. Local adaptation memory

Remember which strategy worked for a site and layout fingerprint. Store only safe structural data:

- hostname
- page/layout fingerprint
- successful discovery source
- successful capture strategy
- media kind
- approximate dimensions
- failure category
- strategy success rate

Never store cookies, passwords, access tokens, signed URLs, request headers, account content, or raw private media in the adaptation profile.

Example:

~~~text
facebook.com / story-layout-7
  image:
    preferred: page-context fetch
    fallback: rendered image
    rejected: page-network thumbnail
  video:
    preferred: network response
    fallback: captureStream
~~~

Profiles must be versioned, expire or decay over time, and have a reset action.

### 9. User feedback

User actions provide useful local feedback:

- immediately discarded capture: reduce confidence in that strategy
- kept and converted: increase confidence
- duplicate discarded: strengthen duplicate detection
- capture again: try a different strategy

This is lightweight local adaptation, not a remote machine-learning system.

### 10. Diagnostics in Fetched Media

Each captured item may show:

- capture method
- media kind
- source site
- confidence
- dimensions
- duration
- original versus rendered capture
- why it was selected

Example:

> Captured as rendered image. Confidence: High. Selected because it was the active story surface and changed after navigation.

## Implementation milestones

### Milestone 1: Separate discovery from capture

Create focused modules for story surface detection, candidate discovery, evidence scoring, capture strategies, validation, fingerprints, and adaptation memory.

The existing current-media and collect-mode behavior must continue to work during this change.

### Milestone 2: Add strategy fallback

Wrap direct fetch, page-context fetch, network capture, canvas, visible-tab, and MediaRecorder methods into the strategy ladder.

Every attempt must produce a structured success or failure reason.

### Milestone 3: Add story state tracking

Track the active surface, current fingerprint, advance events, duplicate detection, bounded retries, and fast failure.

Discovery failures should return quickly. Video capture may run for the media duration, subject to a safe maximum.

### Milestone 4: Add local adaptation

Store successful strategy choices by site, layout, and media type with expiration and a reset option.

### Milestone 5: Add replay fixtures

Create structural fixtures for:

- plain image story
- edited image story
- video story
- multi-page story
- unrelated profile images
- changed story identifiers
- network-only media
- rendered-only media

## Story Engine v1 acceptance criteria

- [ ] Captures a plain story image.
- [ ] Captures a rendered or edited story image.
- [ ] Captures a playing story video.
- [ ] Processes several story pages in order.
- [ ] Avoids obvious profile pictures and sidebar thumbnails.
- [ ] Deduplicates the same story loaded through different URLs.
- [ ] Retries with a different method after failure.
- [ ] Stops quickly when no valid media is exposed.
- [ ] Does not break current-media capture or ordinary conversion.
- [ ] Keeps failures isolated from the core converter.
- [ ] Never logs cookies, tokens, signed URLs, or browser credentials.

Perfect support for every website is not the initial target. The first target is reliable adaptation across a small set of supported sites and layouts.

## Final design principle

The Mahoraga engine should not be one giant intelligent scraper. It should be:

> A self-correcting capture orchestrator that uses multiple independent strategies, validates every result, remembers what worked, and changes tactics when the page changes.

That gives JaneConverter a realistic path to improving story capture without risking the stable converter.
