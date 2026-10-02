# Candidate correction provenance (2026-10-02)

This is a correction of an unadmitted candidate, not a rewrite of accepted
evidence. The original research version remains preserved at render-map commit
`64bb49dd20c83ec5c24b28b77c1ec2ccead5af5a`. Assertion IDs, measured numbers,
runtime applicability, original source state, capture hashes and dates remain
historical. This correction does not represent a new game run.

## Render-scale mode is not sharpening

The definitive raw metadata records `renderScaleMode: false`. The original
report and candidate called this `renderScaleSharpening: false` / "render-scale
sharpening off". That spelling is preserved here as an erroneous historical
interpretation, not an observed setting. The corrected value is
`renderScaleMode: false`; FSR sharpness remains unknown.

Two exact source blobs were recovered in preserved CSX snapshot
`0f3d849f66d1c5cb176b41006aa836ce79c9aa5e` and independently hash-matched to
the original capture's recorded source identities:

- `src/Api/UpscalingDevBenchBridge.cpp`, SHA-256
  `ED68CF498325DF7C6776401E04EB34AB2941506F726B4B7EB96FB4C2A8202B30`:
  lines 270-274 parse the JSON `renderScaleMode` into the profile flag;
  lines 283-287 serialize that same flag.
- `src/Features/Upscaling.cpp`, SHA-256
  `EDCAF65D35A024D5657CFD4EE5906D1AA6B1EEB7844E1C266A40481B5372C8E2`:
  render-scale mode and `sharpnessFSR` are separate settings; lines 16215
  onward apply the profile mode, while lines 15812 onward expose FSR sharpness
  separately.

The recovered snapshot is evidence for those exact blob contents, not a new
claim that the historical dirty build was clean or publicly reachable.

## Interval method and inferential limits

The original task-owned `analyze_quality_ladder.py` SHA-256 is
`441A6DEC5C87C4F46DA5366066B2BCE824D8C4A6556B7159209576E78616394E`;
`analyze_colour_pipeline.py` SHA-256 is
`4D624BE7899232FA221F973E6056D1F16271CB61DFF65DD32E3B541DAA945689`.
Both calculate `estimate +/- 1.96 * sqrt(sum(w^2 * sampleVariance / n))`.
There is no bootstrap procedure, multiplicity adjustment or serial-dependence
model. Original report/manifest "bootstrap" wording was incorrect. Original
interval numbers remain unchanged; re-analysis reproduced the ladder output.

The stable assertion ID `earliest-resolved-colour-boundary-74d` is retained,
but its original predicate `experiment.colour.earliest-resolved-boundary` is
corrected to `experiment.colour.exploratory-boundary-lead`. Neither that legacy
ID nor the corrected result establishes earliest causal onset, upstream
absence, shader attribution or a general upscaling-strength law.
