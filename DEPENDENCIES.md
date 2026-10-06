# External dependencies

| Dependency | Tested version | Official source |
| --- | --- | --- |
| Node.js | 26.8.1; minimum 22.19 | https://nodejs.org/ |
| Pi coding agent | 1.0.2; declared minimum 1.0.1 | https://github.com/earendil-works/pi |
| PiHerdsman | 0.21.0 | https://github.com/boadij/pi-herdsman |
| Herdr | 0.9.3 | https://github.com/herdrdev/herdr |
| GitHub CLI | Existing authenticated installation | https://cli.github.com/ |

Follow the upstream installation instructions for PiHerdsman and Herdr,
including Herdr's Pi integration. Activate the native Manager role before
using this extension. Do not combine this workflow with pi-subagents.
The extension uses public Pi APIs and model-facing staff tools, not private
Herdsman RPCs. A capability check cannot prove an internal Manager lease.

Use an isolated workspace/runtime for initial trials. No production setup or
credentials are included. The recorded native fixture used Pi 1.0.2,
PiHerdsman 0.21.0 and Herdr 0.9.3 with local Faux responses and fake GitHub;
it performed zero remote model calls and zero delegations. SSH persistence is
provided by Herdr/Herdsman; unattended restoration after reboot is not promised.

The extension is MIT. Dependencies are installed separately and retain their
upstream licenses and notices. No dependency source or binary is bundled.
