# Project and output format

## Project schema version 2

`iconforge.json` has exactly these top-level keys: `schema_version`, `project`, `sources`, `style_lock`, `provenance`, `visual_review`, `preset`, `exports`, `preview`, and `renderer`. It must be canonical JSON. Unknown keys, duplicate keys, noncanonical formatting, or unsafe paths are errors.

The release profile requires PNG sizes 16, 20, 24, 32, 40, 48, 64, 128, 256, 512, and 1024; ICO sizes 16, 20, 24, 32, 40, 48, 64, 128, and 256. Small and large arrays are disjoint and exactly cover PNG sizes. 16-32 are small; 48 and above are large; 40 defaults to large.

All paths are canonical project-relative paths. A project cannot select an executable or Python renderer module; it names only a renderer lock ID.

## Visual review schema version 2

A newly initialized review is `draft: true` and `final: null`. Preview refuses the draft until starter content is replaced and `draft` becomes false.

The file contains exactly three concepts. The selected concept follows the documented ranking and, when non-draft, must score at least 24/30 with no criterion below 3/5.

A final pass records:
- exactly the required nine reviewed sizes and four contexts;
- six 0-2 scores, total at least 10/12, with no zero;
- reviewer and `view_scale_percent: 100`;
- `review_source_sha256`, `review_input_sha256`, and `review_output_sha256` from one preview.

## Preview evidence schema version 1

`review/review-evidence.json` is canonical and generated, not handwritten. It records:
- hashes of canonical `iconforge.json`, sanitized large/small SVG, and optional style lock;
- renderer name/version/lock/executable SHA-256;
- platform, machine architecture, and Python version;
- hashes of every exported PNG at 16/20/24/32/40/48/64/128/256/512/1024; the first nine are the actual-size review set;
- hashes of editable and raster review sheets;
- the derived source, input, and output binding hashes.

A preview directory is disposable evidence. It contains sanitized sources, rendered assets, review files, and evidence but no manifest, `SHA256SUMS`, release ZIP, or sidecar.

## Manifest schema version 3

The canonical release manifest records:
- skill, project, preset, and optional style identities;
- the effective neutral or style-lock quality policy;
- renderer version/hash plus platform, machine, and Python;
- exact export sizes and source-tier routing;
- provenance, visual-review, and evidence summaries;
- exact per-file records and an exact sorted package-member allowlist;
- deterministic build format version 2.

The package includes canonical `source/iconforge.json` so the independent verifier can recompute source binding. Standalone packages omit `source/style-lock.json`; family/preset packages include it.

`SHA256SUMS` covers every package file plus `manifest.json`. The versioned project ZIP contains exactly the allowlisted package members and has a separate outer SHA-256 sidecar. The verifier re-sanitizes SVG, re-parses PNG/ICO, regenerates the review SVG, checks evidence against exact bytes, and rejects self-consistent semantic mutations.
