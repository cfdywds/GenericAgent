# Desktop Image Support Design

Date: 2026-06-09

## Summary

GenericAgent already has partial desktop image support: the desktop UI can
paste images, preview them, send image data URLs to the bridge, and show local
user-message thumbnails. The missing part is the end-to-end capability. The
bridge currently saves pasted image data and appends `[image:path]` tags, but
it does not forward structured image payloads to the agent turn. The core agent
also accepts `put_task(images=...)` but does not consume `task["images"]`.

This design implements approach C: desktop image input and desktop image
display are both supported through a small shared image contract. The same
change also moves the project toward a unified multi-frontend attachment
protocol without forcing a broad frontend refactor.

## Goals

- Let desktop users paste an image and have a vision-capable model receive it
  as an actual multimodal content block.
- Keep the existing text fallback by preserving `[image:path]` in the user
  prompt so non-vision models and older frontend paths still have a usable file
  reference.
- Render image references in assistant replies in the desktop UI when they are
  safe local image paths or safe Markdown image URLs.
- Add focused tests for bridge normalization, core image consumption, LLM
  content-block construction, and desktop renderer safety.
- Avoid unrelated session, command, model-selection, or frontend architecture
  refactors.

## Non-goals

- No new image upload button is required. Existing paste support remains the
  first path.
- No image editing, gallery management, OCR feature, or remote image proxy is
  included.
- No broad unification of every IM/TUI attachment implementation is included in
  this change.
- No guarantee is made that every configured model can interpret images. The
  feature provides correct multimodal input where the backend supports it and a
  text/path fallback where it does not.

## Current Evidence

- `frontends/desktop/static/app.js` already stores pasted images in
  `pendingImages`, renders composer previews, persists data URLs in
  `sessionStorage`, sends `images` to the bridge, and displays user thumbnails
  from `image_ids`.
- `frontends/desktop_bridge.py` already accepts `images`, saves data URLs in a
  temp upload directory, returns `image_ids`, and appends `[image:path]` tags.
- `frontends/desktop_bridge.py` currently starts `run_agent_turn(sess, prompt,
  None)`, so structured images are dropped before reaching `agent.put_task`.
- `agentmain.py` stores `images` in queued tasks, but `GenericAgent.run()` only
  reads `query`, `source`, and `output`.
- `llmcore.py` already has conversion paths for Claude-style `image` blocks and
  OpenAI-style `image_url` blocks, including Responses API `input_image`.
- `tests/` currently contains desktop bridge security tests, but no image
  normalization or end-to-end image propagation tests.

## Image Contract

The bridge and core agent will use a simple list of image descriptors:

```json
{
  "id": "img-...",
  "path": "C:\\...\\img-....png",
  "media_type": "image/png"
}
```

Rules:

- `id` is stable for the desktop session message and is used by the UI for
  thumbnails.
- `path` is an absolute local path written by the bridge or passed from another
  trusted local frontend.
- `media_type` is one of the supported image MIME types:
  `image/png`, `image/jpeg`, `image/webp`, or `image/gif`.
- The prompt text keeps a `[image:path]` line for each image.
- The multimodal content block is generated from the same path and MIME type
  immediately before calling the LLM.

## Data Flow

1. Desktop user pastes an image.
2. `app.js` stores `{id, dataUrl}` in `pendingImages`, renders the preview, and
   sends the image list to the bridge with the prompt.
3. `desktop_bridge.normalize_prompt()` validates each data URL, saves it to the
   temp upload directory, and returns:
   - final prompt text with `[image:path]` fallback tags
   - `image_ids` for UI display
   - structured image descriptors for the agent
4. `AgentManager.submit_prompt()` stores only the display-safe user message
   metadata in `sess.messages`, then passes the structured images to
   `run_agent_turn()`.
5. `run_agent_turn()` calls `agent.put_task(prompt, images=image_payloads)`.
6. `GenericAgent.run()` reads `task["images"]`, builds `initial_user_content`,
   and calls `agent_runner_loop(..., initial_user_content=...)`.
7. `agent_runner_loop()` passes the structured user content into the client.
8. `llmcore.py` converts the content blocks according to the configured backend.
9. The desktop message list continues to show user thumbnails from
   `image_ids`.

## Core Content Construction

`agentmain.py` will add a helper that converts a text prompt and image
descriptors into Claude-style content blocks:

```python
[
    {"type": "text", "text": prompt_text},
    {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": "..."
        }
    }
]
```

The helper reads image files just-in-time and skips invalid images instead of
failing the whole turn. The skipped image still remains visible as a text
fallback in the prompt if its `[image:path]` tag was already present.

This uses the existing `llmcore.py` behavior:

- Claude-compatible paths can pass `image` blocks directly.
- OpenAI-compatible paths convert `image` blocks into `image_url` data URLs.
- Responses API paths convert `image_url` blocks into `input_image`.

## Desktop Reply Rendering

Assistant replies will support safe image rendering in two forms:

- Markdown image syntax, for example `![plot](path-or-url)`.
- Plain local image references that match the existing project convention, for
  example `[image:C:\path\to\plot.png]`.

Rendering rules:

- HTTP and HTTPS image URLs can render through the existing Markdown sanitizer.
- Local file image rendering must not expose arbitrary file reads through the
  browser. The bridge will provide a local image serving endpoint that only
  serves allowed image files.
- Allowed local files are:
  - files under the bridge upload directory
  - files under the GenericAgent project root
  - files under the configured session cwd when it is already restricted under
    the GenericAgent root
- Only known image extensions are served.
- Missing or blocked images render as text links/placeholders rather than
  throwing UI errors.

The desktop UI should keep message layout stable: rendered images are capped by
CSS max width and height, with `object-fit: contain`.

## Bridge Image Endpoint

The bridge will expose a read-only image endpoint for desktop rendering:

```text
GET /image?path=<absolute-or-root-relative-path>
```

Security behavior:

- The endpoint only accepts image files after resolving the path.
- It rejects files outside the allowed roots.
- It returns `404` for missing files and `403` for disallowed paths.
- It sets an image content type based on extension or stored MIME metadata.
- It does not allow directory listing or arbitrary file download.

This keeps the browser UI away from direct `file://` paths and centralizes path
policy in the bridge.

## Error Handling

- Invalid data URL: `normalize_prompt()` raises a validation error and the HTTP
  prompt handler returns a structured `400` response. The agent turn is not
  started.
- Unsupported MIME type: same as invalid data URL.
- Oversized image: reject before writing or before agent dispatch. The initial
  decoded image limit is 10 MiB per image and must be covered by tests.
- Image read failure in `agentmain.py`: skip the image block, keep the prompt
  text fallback, and continue the turn.
- Unsupported vision backend: backend may reject the multimodal request. The
  error should surface normally through the existing agent output path. The
  text fallback remains visible for retrying with a text-only model.

## Tests

Add focused tests without introducing browser automation as a requirement:

- `tests/test_desktop_bridge_images.py`
  - valid PNG/JPEG/WebP/GIF data URL normalization
  - invalid base64 rejection
  - unsupported MIME rejection
  - returned image descriptors include `id`, `path`, and `media_type`
  - prompt text keeps `[image:path]`
  - `submit_prompt()` forwards image descriptors into `run_agent_turn()`
  - image endpoint rejects paths outside the allowed roots
- `tests/test_agentmain_images.py`
  - queued `images` are converted into content blocks
  - missing image paths are skipped without dropping prompt text
  - `agent_runner_loop()` receives `initial_user_content`
- `node --check frontends/desktop/static/app.js`
  - syntax guard for renderer changes

Existing tests that should continue passing:

- `python -m unittest tests.test_desktop_bridge_security -v`
- `python -m unittest tests.test_agentmain_llm_selection -v`

## Acceptance Criteria

- Desktop pasted images are visible before send and on the sent user message.
- Bridge saves pasted images and forwards structured descriptors to the core
  agent turn.
- Core agent converts valid image files into multimodal content blocks.
- The prompt still contains `[image:path]` fallback lines.
- Assistant replies can render safe Markdown images and safe `[image:path]`
  references in the desktop UI.
- Unsafe local paths are not rendered as images or served by the bridge.
- New tests prove the bridge, core, and renderer behavior described above.

## Implementation Notes

- Keep `llmcore.py` changes minimal. Prefer using its existing image conversion
  paths over adding another backend-specific image adapter.
- Keep desktop session message state small. Store `image_ids` and display text
  in session history, not raw base64 data.
- Avoid refactoring TUI or IM attachment paths in this change. They can adopt
  the same image descriptor contract later.
- Keep image validation and path policy in Python bridge/core code where it is
  testable with `unittest`.
