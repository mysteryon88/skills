# Renderer lock

`dependencies.lock.json` schema 2 contains one lock ID, the fixed logical `inkscape` basename, and one matching platform entry with permitted version prefixes and optional SHA-256. On Windows, PATH may resolve the official `inkscape.com` console launcher before `inkscape.exe`; both are accepted and hashed as the actual executable.

`renderer-info` reports actual version output and executable SHA-256. A prefix is a compatibility rule, not authentication. When a platform SHA-256 is present, mismatch blocks before rendering.

To prepare a lock update, supply an explicitly trusted absolute non-symlink executable to `update-renderer-lock`. The command performs no search or download, writes a new file only, refuses overwrite, and displays the exact version/hash for manual diff review. Do not replace the release lock automatically.
