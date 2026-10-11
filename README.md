# instagram-automation

Hands-off pipeline for the Instagram page **@kambam.capcutclips**. It runs on GitHub Actions; nothing needs to stay switched on at home.

```
sources.txt ──▶ Make clips (daily) ──▶ clip storage ──▶ Post reel (3× a day) ──▶ Instagram
  your links     OpenShorts finds the     GitHub release     official Instagram API
                 funniest moments, crops  + state/clips/
                 to 9:16, adds captions,
                 hook text and a caption
```

Clipping is done by [OpenShorts](https://github.com/mutonby/openshorts) (MIT), pinned to a fixed version in `make-clips.yml`. Posting uses Meta's official content publishing API, so there is no password sharing and no bot behaviour that could get the page banned.

## No regular job

List the channels to clip from once, in `channels.txt`:

```
https://www.youtube.com/@creatorhandle | @creatorhandle
```

Whenever the pipeline is about to run out of clips it pulls the newest long videos from those channels by itself (Shorts are skipped). To clip one specific video, add its link to `sources.txt`; those are always used first.

Only list channels you are allowed to clip (your own, clipping campaigns, creators who gave permission); reposting other people's content without permission gets reels removed and pages restricted.

## One-time setup

1. **Gemini key** (free): create one at <https://aistudio.google.com/apikey>.
2. **Meta app**: at <https://developers.facebook.com/apps> create an app of type *Business* and add the *Instagram* product. Leave it in development mode.
3. **Token**: in the Graph API Explorer pick your app, generate a user token with `instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement` and `business_management`, then on your computer run

   ```
   pip install requests
   python scripts/get_token.py <app id> <app secret> <that token>
   ```

   It prints `IG_USER_ID` and a long-lived `IG_ACCESS_TOKEN`.
4. **Secrets**: in this repo go to Settings → Secrets and variables → Actions and add

   | Secret | Value |
   | --- | --- |
   | `GEMINI_API_KEY` | from step 1 |
   | `IG_USER_ID` | from step 3 |
   | `IG_ACCESS_TOKEN` | from step 3 |
   | `YOUTUBE_COOKIES` | optional, see Troubleshooting |

5. **Test**: Actions → *Check setup* → Run workflow. It should print `Connected to @kambam.capcutclips`.
6. Add your channels to `channels.txt`, run *Make clips* once by hand, then run *Post reel* with "Rehearse without posting" ticked to preview the first caption.

## Schedule and settings

| What | When (IST) | Change it in |
| --- | --- | --- |
| Make clips | 07:47 daily, only when fewer than 6 clips are waiting | `.github/workflows/make-clips.yml` |
| Post reel | 12:22, 18:22, 21:22 | `.github/workflows/post-reel.yml` |

GitHub can start scheduled runs several minutes late. Hashtags, credit line, clips per video and the 30-minute source limit are in `config.yml`.

`state/clips/` has one small file per clip showing whether it is `ready`, `posted` (with the reel link) or `failed` (with Instagram's error). To drop a clip before it goes out, delete its file.

## Troubleshooting

- **"Sign in to confirm you're not a bot" in Make clips**: YouTube often blocks downloads from GitHub's servers. Export your YouTube cookies in Netscape format with a browser extension and save the text as the `YOUTUBE_COOKIES` secret.
- **Token errors (code 190)**: repeat step 3 and update `IG_ACCESS_TOKEN`.
- **A clip keeps failing**: after 3 attempts it is marked `failed` and the next one is used.
- **Private repo**: works, but Make clips uses about 30–60 Actions minutes per video against the 2,000 free minutes a month. Public repos are not metered.

## Tests

```
pip install -r requirements.txt pytest
pytest tests
```
