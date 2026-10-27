# Style lock and neutral quality policy

## Standalone mode

A standalone icon should normally keep `iconforge.json.style_lock` as `null`. This prevents the template's example palette or geometry from becoming an accidental design system.

Null does not disable quality checks. The built-in `iconforge-default-v1` policy enforces:
- 32 canvas-unit safe margin on the 1024 canvas, rounded up at every raster size;
- optical-center tolerance of 96 canvas units;
- visual-weight range 0.18-0.86;
- transparency and transparent corners;
- no full bleed.

These are broad safety rails, not brand styling.

## Existing family or preset

For an existing family continuation, copy/adapt `style-lock.example.json`, give it a real style ID/version, measure representative family icons, and point `iconforge.json.style_lock` to it. A declared preset requires its matching style lock.

Schema version 1 records:
- style and optional preset identities/versions;
- canvas, safe margin, and optical-center tolerance;
- exact palette roles and large/small outline rules;
- radii, proportions, eyes, bounds, metaphor/forbidden zones;
- lighting, form character, visual-weight range;
- small-size simplifications, minimum element/gap, and transparency policy.

The runtime enforces structure, identity, palette membership, outline colour/width, transparent-corner/full-bleed policy, raster safe margins, visual weight, and optical center. It records but does not falsely claim arbitrary-path proof for semantic geometry, lighting, form character, minimum element/gap, or qualitative simplifications; those remain review criteria.

Any style-lock change invalidates the previous preview approval. Do not weaken the lock merely to hide a defective render.
