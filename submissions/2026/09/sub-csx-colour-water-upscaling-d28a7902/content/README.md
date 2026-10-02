# CSX colour, water, and VR reconstruction map at `d28a7902`

## Scope and evidence boundary

This contribution maps the source-visible colour, water-reflection, temporal,
reconstruction, sharpening, and presentation contracts in clean CSX source
commit `d28a790278273de6c3d8173866322a372b20440b`. It also indexes two bounded
runtime observations. Source analysis and runtime evidence remain separate:
source control flow is not represented as proof that a particular branch ran,
and a captured image is not represented as proof of a visual treatment effect.

The source commit is locally preserved but the named development branch has
moved. `source-index.md` therefore records a deterministic full-tree identity,
per-file blob identities, SHA-256 digests, byte sizes, and exact inspected line
ranges. `runtime-evidence.md` provides content-addressed indices for retained
evidence whose large or privacy-bearing source files are not published here.

## Mapped colour pipeline

`ISHDR.hlsl` exposes four distinct roles: scene/bloom input, adaptation input,
average-luminance state, and final grading. Downsample variants clamp sampled
HDR values and optionally convert them to luminance. The light-adaptation
variant compares the new downsample with its prior adaptation texture and
rate-limits the delta. The blend variant samples scene colour from `BlendTex`,
bloom from `ImageTex`, average state from `AvgTex`, and rescales the scene by
`avgValue.y / avgValue.x` when both values are non-zero.

`Param.z` selects between a hue-preserving Hejl-Burgess-Dawson path and a
luminance/Reinhard path. Both routes apply bloom. The hue-preserving route
temporarily desaturates in ICtCp before compression and restores part of the
pre-compression chroma afterward. Final grading then applies cinematic
saturation/tint/brightness, contrast, optional fade, optional linear-lighting
gamma conversion, and framebuffer sRGB conversion.

The editor joins the authored HDR, saturation, brightness, contrast, tint,
sunlight, and sky settings to their engine image-space fields. Runtime hooks
and the shader-cache catalogue separately enumerate the HDR loader identities.
An earlier accepted main-menu capture proves the compile-source join from the
observed HDR loader aliases to shared `ISHDR.hlsl`; it does not prove this
submission's clean commit ran those aliases in the later fixtures.

## Authored confounders that must be fixed in colour trials

The shared feature buffer simultaneously publishes Adaptive Brightness, Linear
Lighting, Unified Water, effective water-appearance, and bloom settings.
Adaptive Brightness composes global, active-profile, and location layers for
shared lighting, bloom, water appearance/wind, sky brightness, and several
light multipliers. Unified Water converts both the base colour and tint to a
linear domain, blends them there, and converts back to Skyrim gamma. Water
Appearance can then multiply the water result by `WaterBrightness`.

These are first-class treatment confounders. A reconstruction comparison that
does not freeze them cannot attribute a brightness, saturation, hue, bloom, or
water-only difference to DLSS, FSR, render-scale ownership, or sharpening.

## Water reflection and history path

The water shader derives dynamic-resolution-adjusted SSR coordinates, samples
blurred and raw SSR, blends them according to reflection alignment, derives an
SSR fraction, then blends SSR with the ordinary reflection in an irradiance
linear domain. LOD blending can subsequently alter reflection strength.

`ISReflectionsRayTracing.hlsl` is the source-visible screen-space raymarch and
reprojection producer. `ISApplyReflections.hlsl` conditionally applies its SSR
result against the main buffer and water mask. These two files establish source
dataflow, not an exact loaded same-frame ordering.

`ISWaterBlend.hlsl` samples source colour, water history, motion, depth, and the
water mask. It reprojects history, decodes logarithmic history, derives
coverage, unpremultiplies valid history, blends it with the source, and writes
both final colour and premultiplied logarithmic history. The engine hook clears
the second runtime render target before the original `ISWaterBlend` draw so
discarded non-water pixels cannot retain stale coverage. The stable engine enum
for that second target is not established. CSX creates `kWATER_1` and
`kWATER_2` as `R16G16B16A16_FLOAT`, while the render-scale target catalogue
also names the separate engine temporal-AA water pair. The exact live identity
relationship between those pairs remains open.

## Reconstruction and presentation ordering

The post-processing hook wraps the complete Skyrim ImageSpace call. With
vendor reconstruction selected and submit-stage render-scale inactive, it
performs the vendor reconstruction and optional DLSS sharpening before calling
Skyrim ImageSpace, while disabling engine TAA around that call after a completed
vendor dispatch. With VR render-scale submit-stage ownership active, Skyrim
ImageSpace runs on reduced physical targets with engine TAA disabled; vendor
reconstruction and any sharpening are deferred to the OpenVR submit path.

Submit-stage reconstruction accepts only `R8G8B8A8_UNORM` and OpenVR colour
space `Auto`, `Gamma`, or `Linear`. It copies the reconstructed result back into
the submitted allocation and copies the input OpenVR texture descriptor, thereby
preserving its format and colour-space declaration at this boundary. The
in-scene overlay path may conditionally composite after reconstruction and
before the actual compositor submit. The map ends at `IVRCompositor::Submit`;
later compositor, runtime, driver, display, and HMD transforms are unknown.

DLSS classifies R8/B8 UNORM and sRGB formats as SDR and other formats as HDR;
failure to query a texture description defaults to HDR. Its options enable
auto-exposure, use `preExposure = 1`, and set native DLSS sharpness to zero.
External DLSS sharpening is separately selectable as Off, RCAS, or Luma
Unsharp. FSR creates an HDR plus auto-exposure context, supplies no exposure
texture, uses `preExposure = 1`, and conditionally enables its integrated
sharpening according to the configured amount.

The source therefore supports two hypotheses for future controlled tests, but
does not prove either one: submit-stage FSR may receive already tone-mapped R8
input while operating under an HDR context, and moving DLSS between input
formats may change its SDR/HDR classification. Neither hypothesis is published
as a ledger assertion.

## Report attribution boundary

The report that motivated this investigation originated on a machine with an
NVIDIA GPU. That is host provenance and capability context only. The report did
not establish that DLSS was enabled, and it does not establish that the reported
phenomenon is specific to or caused by DLSS. No ledger assertion in this
submission assigns the report to DLSS or attaches it to the DLSS contract
entity.

These AMD observations establish measurable colour/luminance differences in
the recorded conditions with DLSS unavailable. Whether they reproduce the
original NVIDIA-host report, or share its mechanism, remains unresolved. The
campaign does not isolate one mechanism, close water-only causality, or
generalize its magnitudes across GPU vendors. A repaired follow-up does establish
that feature absence is not generally equivalent to loaded None.
The DLSS-specific source contracts above remain candidate mechanisms for a
future DLSS campaign, not evidence that DLSS caused the original report.

## AMD measured map update

The AMD campaign compared loaded None, loaded TAA, FSR 4 Native AA with render
scale off, and FSR 4 Quality with render scale off and on across Riverwood and
Breezehome at 15:00 and 23:00. It captured three stereo submissions per
treatment-condition pair: 120 eye images across 20 matched sets, plus 12 eye
images for the repaired boot-disabled control. Weather, time, output resolution,
source, build, DLL, and shader-cache ABI were identified.

Loaded None, loaded TAA, FSR Native AA/render-scale off, and FSR Quality/render-
scale off all retained 1,512 by 1,680 physical eye targets. Only FSR Quality
with render scale on reduced the physical target to 1,008 by 1,120 and then
reconstructed to 1,512 by 1,680. Quality/render-scale off is consequently a
vendor Quality treatment without physical target reduction, not an alias for
None or Native AA.

In aggregate linear-light comparisons, None to TAA was below sampled noise and
had no stable brightness direction. FSR Native AA was darker than None in all
four conditions (signed luma -0.002287; mean DeltaE76 1.292). FSR Quality with
render scale off was usually darker than Native AA, with a weak Riverwood-night
reversal (-0.001315; 1.079). Enabling render scale from the Quality/off state
was brighter in all four matched blocks (+0.000670; 1.036), although confidence
varied. None to Quality remained a stronger aggregate difference both with
render scale off (-0.003601; 1.592) and on (-0.002932; 1.360).

Treatments were sequential, not counterbalanced. Three repetitions support the
larger differences but do not close small or noisy effects. A separate
boot-disabled restart established `disabledAtBoot=true` and `loaded=false`.
Its first rebuild produced 46 Lighting failures—not 37—because
`CurrentFrameDepthCulling::IsOccluded` lacked its include; the broken frames are
diagnostic evidence only. An exact one-line shader repair from commit
`39399749730e601d5d3e32568f47fb1a8013c8f3` then produced a zero-failure cache
and a valid matched control while retaining the fa4 DLL/build.

At Breezehome 15:00, boot-disabled was measurably brighter and different from
loaded None (RGB MAE 0.014911, signed luma +0.006914, DeltaE76 1.969,
RGB/noise 2.29, luma/noise 2.10) and loaded TAA (0.014853, +0.006233, 1.963,
2.15, 1.98). Separation from every FSR path was stronger. At 23:00, the
boot-disabled-to-None comparison had weak RGB-only separation and luma below
noise; loaded TAA was the nearest sampled path and indistinguishable at sampled
repeatability. Thus feature absence is neither generally loaded None nor simply
loaded TAA; the distinction is strongly lighting/condition dependent.

## Temporal, mip, and foveation controls

True `None` preserves Skyrim's TAA and water-stabilization state. Vendor routes
disable engine TAA around ImageSpace only after vendor output is available; a
gated fixed-resolution vendor frame retains Skyrim's temporal fallback. DLSS
uses zero native sharpness and an optional separate sharpener, whereas FSR's
sharpening is part of its dispatch contract. Sharpening mode and amount must
therefore be controlled independently from reconstruction method.

Material mip bias is `log2(renderWidth / outputWidth) + methodOffset`, with a
DLSS offset of `-1` and an FSR offset of `0`. Render-scale mode obtains the
physical engine and final sizes from its resolution plan; non-render-scale mode
uses the dynamic screen size and screen size. An active OpenComposite
Unleashed external upscaler overrides this calculation with its own published
mip bias.

Both SSR and vendor reconstruction contain foveated branches. Source proves
those branches and their fallbacks exist, not that foveation caused a measured
image difference in either retained observation.

## Required next experiment

A primary within-host campaign should collect seven treatments on one NVIDIA
machine and one water-visible, weather-stable fixture:

1. true None;
2. DLSS Native AA at 1:1;
3. FSR Native AA at 1:1;
4. matched reduced-resolution DLSS with render scale off;
5. the same DLSS dimensions with render scale on;
6. matched reduced-resolution FSR with render scale off; and
7. the same FSR dimensions with render scale on.

Use three repetitions per treatment and sixteen correlated stereo captures per
repetition. Freeze ImageSpace, Adaptive Brightness, Linear Lighting, Unified
Water, Water Appearance, bloom, sharpening, mip-bias ownership, foveation,
weather, pose, and exposure-related configuration. Record actual input/output
formats, OpenVR colour enum, render and output dimensions, vendor exposure
domain, stable water-history target identities, foveated route, and the final
submit descriptor for every treatment.

Where practical, repeat matched true None and FSR treatments on a second,
non-NVIDIA GPU while holding scene, dimensions, render-scale state, and all
available configuration fixed. This cross-GPU replication is experiment design
only. Its purpose is to distinguish a GPU-vendor interaction from a
reconstruction-method effect; it implies neither one before results exist.

The AMD campaign now supplies one bounded non-NVIDIA FSR slice, but it does not
replace the planned matrix: treatment order should be counterbalanced, capture
count increased for small effects, and the feature-absence control repeated
with higher replication using the repaired cache. Targeted water and non-water
regions should be reported separately. Equivalent matched treatments
on NVIDIA remain necessary to estimate a cross-GPU interaction rather than
merely observing that the phenomenon exists without DLSS.

Primary analysis should operate in linear light: luminance and RGB/chroma/hue
deltas, fitted exposure/gain residual, water-to-control-region ratios, temporal
drift, and stereo deltas. Gamma-space HSV is not an adequate primary measure.

## Explicit open boundaries

- Same-frame loaded-water join from SSR/history through `kMAIN`, `ISHDR`, the
  vendor path, and accepted eye submission.
- Actual resource formats and OpenVR colour enums for every treatment.
- Vendor exposure and output domains at runtime.
- Stable enum identity of the `ISWaterBlend` second render target.
- Relationship between `kWATER_1/2` and temporal-AA water targets.
- Runtime ordering of the foveated branches.
- Compositor and HMD transforms after accepted submit.
- Complete configuration, build, module, cache, GPU, and render-size identity
  for the earlier clean-commit four-frame Breezehome structural capture.
- Live dimensions, producers, and consumers of `kWATER_REFLECTIONS`.
- Enabled reconstruction method and render-scale state for the original
  NVIDIA-host report.
- Counterbalanced replication and water-versus-control-region decomposition of
  the AMD treatment effects.

The bounded absence of vendor tokens in the inspected water/history/HDR shader
files does not prove that no vendor-dependent effect exists elsewhere. It only
shows that those three source files contain no direct DLSS/FSR branch at the
identified commit. Likewise, render-scale differences are mapped as stage,
resource, and domain ownership changes—not as separate water shader
permutations.
