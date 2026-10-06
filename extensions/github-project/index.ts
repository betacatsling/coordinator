import { Type } from "@earendil-works/pi-ai";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { registerGitHubProject } from "./pi-host.mjs";

export default function (pi: ExtensionAPI) {
  registerGitHubProject(pi, Type);
}
