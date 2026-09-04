# Desktop Bridge Readiness Design

## Goal

Make the React Desktop 2.0 main chat page leave its `connecting` state once
the local Desktop Bridge WebSocket is open and the Bridge has reported
readiness.

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
Bridge HTTP status and the Bridge WebSocket readiness event as the authoritative
connection signals. A successful status response followed by an open WebSocket
must transition the page state to `ready`; a closed socket must transition it
back to `connecting` and retain the existing reconnect behavior.

The source-of-truth renderer repository will be checked out outside this
repository at the recorded source commit. The regression test will exercise the
real connection-state store with a local WebSocket server, asserting that an
open Bridge connection changes the rendered state from `connecting` to `ready`.
The minimal source change will be rebuilt through that repository's normal
build process.

Only regenerated distribution files will be copied back. The current compiled
distribution verifier will be updated with the new provenance and manifest
digest, then run along with the renderer regression test and relevant desktop
Bridge tests.

## Verification

1. The new renderer test fails before the source fix because the state remains
   `connecting` after the Bridge WebSocket opens.
2. The test passes after the source fix.
3. `npm run test:dist` passes in `frontends/desktop` after importing the
   generated distribution and updating provenance.
4. The Desktop Bridge tests pass.
5. With the development launcher running, the main chat page displays the
   connected state after the local Bridge and its WebSocket are available.
