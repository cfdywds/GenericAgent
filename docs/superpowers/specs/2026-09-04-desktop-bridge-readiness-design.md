# Desktop Bridge Readiness Design

## Goal

Make the React Desktop 2.0 main chat page leave its `connecting` state once
the local Desktop Bridge reports HTTP readiness, even when its optional
WebSocket event channel is unavailable.

## Scope

- Fix the React renderer from the upstream source of truth at the commit
  recorded by `frontends/desktop/dist/build-provenance.json`.
- Add a regression test for the renderer connection state transition.
- Rebuild the renderer and import only the generated `frontends/desktop/dist`
  files and their matching provenance metadata into this repository.
- Preserve the existing Tauri shell, Bridge API, Conductor API, and legacy
  `frontends/desktop/static` implementation.

## Non-goals

- Do not commit the React source tree, its package lock, or its dependencies
  to this repository.
- Do not change ports, firewall settings, service start commands, or model
  configuration.
- Do not patch minified generated JavaScript by hand.

## Design

The generated renderer currently represents the main chat page as `connecting`
even though the local Bridge is healthy. The source renderer will treat the
successful Bridge HTTP status response with `{ ok: true, ready: true }` as
renderer readiness. The WebSocket remains an event-delivery channel and keeps
its existing reconnect behavior, but its failure or closure must not replace an
HTTP-confirmed `ready` state with `connecting`.

The source-of-truth renderer repository will be checked out outside this
repository at the recorded source commit. The regression test will exercise the
real connection-state store with a failing WebSocket constructor and a
successful mocked HTTP status response, asserting that the state changes from
`connecting` to `ready`. The minimal source change will be rebuilt through that
repository's normal build process.

Only regenerated distribution files will be copied back. The current compiled
distribution verifier will be updated with the new provenance and manifest
digest, then run along with the renderer regression test and relevant desktop
Bridge tests.

## Verification

1. The new renderer test fails before the source fix because the state remains
   `connecting` despite a healthy Bridge HTTP status response.
2. The test passes after the source fix.
3. `npm run test:dist` passes in `frontends/desktop` after importing the
   generated distribution and updating provenance.
4. The Desktop Bridge tests pass.
5. With the development launcher running, the main chat page displays the
   connected state after the local Bridge HTTP status endpoint reports ready,
   regardless of the WebSocket event channel's state.
