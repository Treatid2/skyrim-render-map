# CSX same-frame colour-pipeline probe at `74dee907`

## Scope

This contribution maps five observed colour-pipeline boundaries in one exact
development build, then records a counterbalanced Skyrim VR experiment across
five FSR 4 presets. It follows the earlier `bc1cfa89` colour-contract campaign,
which exposed independent FSR HDR-input and auto-exposure controls but could
not separate their visible contribution from scene drift.

The new instrumentation captures both eyes at each boundary in the same engine
frame. The experiment is bounded to one stationary Riverwood fixture, one
unchanged default/balanced shader preset, render-scale mode off, and the
identified dirty source tree and compiled artifact. It does not isolate an
individual shader, establish a general FSR behaviour, or describe a compositor
or physical HDR display path.

## Observed stage order

The exact observed order was:

| Order | Probe stage | Resource and format | Observation point |
|---:|---|---|---|
| 1 | `fsr_input` | Per-eye `vrIntermediateColorIn`, `R11G11B10_FLOAT` | Immediately before FSR dispatch |
| 2 | `fsr_output` | Per-eye raw FSR output, `R11G11B10_FLOAT` | After successful FSR dispatch |
| 3 | `combined_main` | `kMAIN`, `R11G11B10_FLOAT` | After the per-eye output copy-back |
| 4 | `imagespace_input` | target 114 / `kVR_FRAMEBUFFER`, `R8G8B8A8_UNORM` | Destination before the original Skyrim `Main_PostProcessing` function |
| 5 | `imagespace_output` | target 114 / `kVR_FRAMEBUFFER`, `R8G8B8A8_UNORM` | The same destination after the original function |

The API label `imagespace_input` is historical rather than semantic. It samples
the ImageSpace destination before the original function, not the source input
consumed by that function. Source inspection identifies engine target 114 as
`kVR_FRAMEBUFFER`: the target enum gives `kTOTAL` the value 114 and defines
`kVR_FRAMEBUFFER = kTOTAL`.

Every slot retains its resource identity and version, subresource, rectangle,
view/resource formats, device context, CPU frame, dispatch frame, FSR context
generation, colour-contract revision, requested and effective HDR/auto-exposure
flags, pre-exposure, and exposure-resource state. `sceneEpoch` and
`submissionEpoch` were unavailable and remain null.

## Readback contract and integrity

The seam path does not synchronously map a live render resource. It copies to a
staging resource, records an event query, and maps only after the query completes
on a later CPU frame. The captured dispatch-frame identity remains attached to
the deferred readback.

All 135 definitive captures completed with ten slots, two eyes at five stages,
and exact `cpuFrame == dispatchFrame` correlation in the emitted capture
records. No slot failures or metadata mismatches were observed.

Across all definitive captures, 78,030 sampled raw pixels were compared between
`fsr_output` and `combined_main`, with zero mismatches. This establishes sampled
identity for the observed FSR-output copy-back path; it is not a whole-resource
proof.

## Experiment design

The fixture was Riverwood exterior with water visible, at engine position
`[17224.771484375, -47204.44921875, -125.38400268554688]`, 15:00, timescale
zero, and `SkyrimClear_A`. A stationary null HMD supplied a 1,512 by 1,680
per-eye output at 90 Hz. FSR 4 ran with render-scale mode off and the
unchanged default/balanced shader preset.

The factorial cells were:

- A: HDR input on, auto exposure on;
- B: HDR input off, auto exposure on;
- C: HDR input off, auto exposure off; and
- D: HDR input on, auto exposure off.

For each preset, the acquisition order was `A-B-D-C-A-C-D-B-A` repeated three
times. This yielded A=9, B=6, C=6 and D=6 captures per preset, 27 captures per
preset and 135 definitive captures overall.

## Active regions

| FSR 4 preset | Active input per eye | Output per eye | Input pixel fraction |
|---|---:|---:|---:|
| Native AA | 1,512 x 1,680 | 1,512 x 1,680 | 1.00000 |
| Quality | 1,008 x 1,120 | 1,512 x 1,680 | 0.44444 |
| Balanced | 889 x 988 | 1,512 x 1,680 | 0.34578 |
| Performance | 756 x 840 | 1,512 x 1,680 | 0.25000 |
| Ultra Performance | 504 x 560 | 1,512 x 1,680 | 0.11111 |

## FSR transform result

The response is the sampled mean-luma ratio `fsr_output / fsr_input`. This
normalizes much of the upstream scene movement but remains approximate because
the normalized input and output grids have different resolutions. The
factorial interaction is `(A - B) - (D - C)`. The historical scripts calculated
pointwise normal-approximation 95% intervals: estimate plus or minus 1.96
times the square root of the sum of squared contrast weights times each
cell's sample variance divided by its capture count. These are not bootstrap
intervals. They treat captures as independent, do not model serial dependence
between captures/cycles, and have no adjustment for the multiple presets,
channels, metrics or contrasts examined. The numbers below are preserved,
but their uncertainty and interpretation are exploratory.

| Preset | Interaction | 95% interval |
|---|---:|---:|
| Native AA | +0.002669 | [-0.013999, +0.019337] |
| Quality | +0.022604 | [+0.000218, +0.044990] |
| Balanced | +0.017496 | [-0.009528, +0.044521] |
| Performance | +0.006786 | [-0.015561, +0.029133] |
| Ultra Performance | +0.001080 | [-0.029425, +0.031585] |

There is no monotonic scaling with decreasing input resolution. Quality is the
only tested preset whose interval narrowly excludes zero. This is a
Quality-specific lead for replication, not a general upscaling-strength law.

At Quality, condition means were A=0.918479, B=0.918282, C=0.941477 and
D=0.919070. The HDR main effect was -0.011105 with interval
[-0.022298, +0.000088], the auto-exposure main effect was -0.011893 with
interval [-0.023086, -0.000701], and their interaction was +0.022604 with
interval [+0.000218, +0.044990]. Quality channel interactions were R=+0.017365
with an interval including zero, G=+0.023222 with interval
[+0.000644, +0.045800], and B=+0.032871 with interval
[+0.005437, +0.060305]. P10, P50 and P90 interaction intervals each included
zero.

The Quality FSR input-to-output interaction is an exploratory replication
lead, not a confirmed earliest causal boundary. A narrowly zero-excluding,
unadjusted pointwise interval selected from several tested endpoints does not
establish causal onset, absence of upstream effects, or shader attribution.
The different normalized sample grids are a further limitation.

## ImageSpace result and format boundary

Destination-before to destination-after ImageSpace effects were generally small
and unresolved. Performance produced one isolated HDR main effect of -0.000873
with interval [-0.001485, -0.000261]. It is retained as an observation requiring
replication and multiple-comparison treatment, not promoted to a pipeline rule.

`combined_main` is `R11G11B10_FLOAT`, while the probed ImageSpace destination is
`R8G8B8A8_UNORM`. The capture path performs no transfer-function conversion, so
their numeric summaries are not directly colour-comparable. The exact transfer
or shader path between these resources remains unobserved.

## Evidence identity

Private retained evidence contains 180 files and 265,443,076 bytes. Its
deterministic relative-path tree SHA-256 is
`8CA79F5EDF1E69E7CE33071834668F899FB5221543B6F615D0F8AD0F4A3D90BC`.
The human-readable report SHA-256 is
`C9F9AB33B4F373E9CF0376C53715E47C89099CCDC8B60EEEA47E80A2091C4415`;
the full ladder analysis SHA-256 is
`0996A00B39BAEA8FD9877CB8FB9E512375B00807400FF283B001DBE59C61ED53`;
the Quality analysis SHA-256 is
`6D55EAFE01D973AFA1E8BFCCA1129E15325F6B39B30BC6904A1B83FC2D1995D0`;
and the promotion verification SHA-256 is
`09FB9AA80952FBC179D8E9447963F593EC1C503E45A56E59961E39B274688DDE`.
Absolute paths, task/session/profile identifiers, and raw media are not
published in this submission.

## Exact build and source identities

- Build ID: `74dee907c708e4bee3ed01041a00f6d8e0da25a215376d3da535dd42680b1f8e`.
- DLL: 27,417,600 bytes, SHA-256
  `72FED649FC70123B86E6E967B9E428A065546F87CA1185F797D0B6595FA1CDBD`.
- Build manifest SHA-256:
  `F65D65E6FD70ED9EC0E1C6F061A19945F8F7E15A2787D125B8AAD46D4074218D`.
- Shader-cache ABI:
  `e0070b1a7ce8b8bde5952a9d720f31cf1432e0f31512d233033e44246b26838e`.
- Working-tree dirty digest:
  `aba24c96d1c4818b43cbdf1cbf3b6c312402d34ab74e2753d6692ac803252ffd`.
- `ColourPipelineProbe.h` SHA-256:
  `5F72D333F429F1CA2F31EDB292DA41E0646EE82BA3D690DD0A196BFA6C4169A4`.
- `ColourPipelineProbe.cpp` SHA-256:
  `1EA24DE6678CA958895E4B2BDC9D4A4943726E8C7DFEB349D4B57BBF97F3775D`.
- `FidelityFX.cpp` SHA-256:
  `E9830C7EFA342DD70E61CB8A059648B8D2E167866A54B1643E47ADEE355E8098`.
- `Upscaling.cpp` SHA-256:
  `EDCAF65D35A024D5657CFD4EE5906D1AA6B1EEB7844E1C266A40481B5372C8E2`.
- `UpscalingDevBenchBridge.cpp` SHA-256:
  `ED68CF498325DF7C6776401E04EB34AB2941506F726B4B7EB96FB4C2A8202B30`.

The runtime build manifest reports `manifestVerified=false` because artifact
verification is delegated to the deployment harness. The deployment-side DLL
and manifest hashes were independently verified.

## Instrumentation availability

The DevBench catalogue advertised `communityshaders.render_map`, but the live
call returned `Tool not found`. Colour-probe, upscaling, screenshot and related
services remained callable. This is a catalogue/dispatch consistency finding;
it does not invalidate the independent colour-probe captures.

## Next discriminating examination

Replicate the Quality factorial in a controlled interior fixture. If the
interaction survives scene change, add an internal ImageSpace seam that observes
the actual source and intermediate resources responsible for the
`R11G11B10_FLOAT` `kMAIN` to `R8G8B8A8_UNORM` framebuffer transition. Return to
render-scale mode on/off only after that attribution step. FSR sharpness is
a separate setting whose value was not established by this capture metadata.

