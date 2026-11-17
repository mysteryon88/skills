---
name: mutation-environment
description: Prepare and diagnose a project-local environment for a smart-contract mutation campaign, including compiler/test-runner dependencies, cache isolation and reproducible installation receipts.
---

# Mutation environment

Work only in the campaign's assigned worktree and `.mutation/` environment. Consume the scout's exact compiler/test requirements; produce version/help output, verified source URLs, downloaded checksums, commands, dependency lockfiles and a nonempty baseline receipt. Existing tools may be read; new tools/dependencies/caches must stay inside the project. No global config, admin components, connector activation or automatic WSL installation.

Try native Windows first; use already installed WSL2 for Linux-only tools. Run the **whole Python controller within WSL** for Linux tools so its process group owns descendants; a Windows `wsl.exe` PID is insufficient. Record which filesystem/runtime produced evidence. Test paths with spaces and actual executable wrappers; prefer argv arrays over shell strings.

Use [catalog installation sources](../mutation-campaign/references/tool-catalog.md), project venv/npm prefix/local extracted binaries and exact versions. Record SHA-256 before extraction. Keep downloaded ZIPs in a dedicated private project location with a non-release extension if the hosting repository forbids ZIPs outside its publish directory. Do not run remote installer pipelines that write into the home directory.

Set HOME/USERPROFILE, APPDATA, XDG, TEMP/TMP/TMPDIR, npm/pip/compiler/fuzz/fork caches to the lane's project environment. Verify actual tool behavior; some Windows applications use known-folder APIs instead of HOME. Record any unavoidable external read and block routes that create external artifacts. Never copy credentials into source fixtures or publish payloads; runtime authentication uses ignored private storage with preserved permissions.

On baseline failure retain logs and diagnose before repairs. Change configuration/tests only when evidence establishes the defect; preserve expected behavior. Contract defects go back to the coordinator with a reproducer and separate proposed patch. Track every owned process PID plus start identity and stop its tree after tests, including failures. Never stop unrelated processes.
