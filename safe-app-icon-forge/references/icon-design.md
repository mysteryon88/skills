# Icon design and optical redraw

## Translate the description into a visual promise
Before sketching, reduce the service to:

`input -> action -> output`

Then identify:
- **recognition target:** the one idea that must survive at 16 px;
- **dominant noun:** the object users should recognise first;
- **action cue:** the smallest visual change that communicates what the app does;
- **forbidden associations:** nearby meanings that would mislead users.

Example for a service that finds four photos in a 2x2 scan and crops them: input is a scanned sheet, action is detect/separate/crop, output is four independent photos. A strong concept is a 2x2 photo sheet with one tile visibly separating; a weak concept is a tiny scanner window with buttons, labels, crop handles, faces, scissors, and arrows all competing.

## Concept exploration
Create exactly three materially different concepts. Vary the metaphor or silhouette, not merely colour, expression, or decoration. Good concept families might emphasize:
- the input transforming into output;
- the primary action as negative space;
- the result emerging from a compact source object.

Use one dominant metaphor and at most one supporting cue. Avoid text, initial letters, tiny interface chrome, realistic screenshots, and four equal symbols that become noise at small sizes.

The selected concept must rank first, score at least 24/30, and have no criterion below 3/5. A weak set of three is not permission to draw the winner.

## Silhouette and association tests
Before detail:
1. fill the icon as one colour; the outer shape and major negative spaces should remain distinct;
2. view it at 16, 20, 24, and 32 px without zooming;
3. ask what it resembles without revealing the product description;
4. list accidental readings such as QR code, gallery, spreadsheet, camera, medical cross, download, delete, or scissors;
5. remove any cue that is decorative but competes with the primary action.

## Large artwork
The large source may contain restrained highlights, depth, and secondary structure that remain useful at 40-1024 px. Keep the metaphor understandable without those details. Avoid embedded raster images, unnecessary transforms, external resources, clipping at the canvas edge, and detail that matters only at 256 px.

Prefer:
- a small, deliberate palette with clear roles;
- consistent corner character and line endings;
- generous negative space;
- one focal contrast;
- balanced visual mass rather than mathematical centering alone.

## Small optical redraw
The small source is not a scaled copy. At 16-32 px:
- remove highlights and secondary props;
- merge adjacent shapes that create unstable one-pixel gaps;
- enlarge the recognition anchor;
- increase outline width and negative space;
- simplify curves and reduce intersections;
- preserve the same core silhouette and action cue;
- snap critical geometry so it does not flicker between target sizes.

The geometry-hash check only detects identical artwork. Actual-size review is authoritative.

## Final visual review
Open the generated raster sheet at exactly 100% / 1:1. Do not judge a browser-scaled or fit-to-window sheet. Inspect all required sizes on light, dark, neutral, and taskbar contexts.

Final criteria are silhouette, metaphor recognition, small-size readability, visual weight, optical center, and style coherence. A pass requires at least 10/12 and no zero. Technical metrics expose drift but cannot prove that the metaphor is good.
