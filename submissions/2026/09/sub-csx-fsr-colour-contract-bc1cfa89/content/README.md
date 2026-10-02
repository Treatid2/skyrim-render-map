# CSX FSR colour-contract runtime mapping at `bc1cfa89`

## Scope

This contribution maps a new development-only control and observation surface
for FidelityFX HDR-input and auto-exposure context flags, then records one
bounded Skyrim VR campaign. The source was a precisely identified dirty working
tree at commit `c46b93b2a0e0944fbfeb8746e3ca2bc84ef276a6`; the exact dirty digest,
compiled Build ID, DLL hash, and three inspected source-file hashes are retained
below. No claim is generalized to another build.

The campaign used an unchanged shader preset. It did not isolate an ImageSpace,
water, or lighting shader. Its screenshots are SDR sRGB HMD submissions, so
they observe the submitted visible result rather than raw HDR resources or any
post-submit compositor/display transform.

## Implemented FSR colour contract

The development build exposes two independent runtime-only FSR context inputs:
`highDynamicRangeInput` and `autoExposure`. Snapshot and guarded apply actions
also expose a monotonic colour-contract revision, host/runtime context
generations and validity, pending recreation, and the latest successful FSR
dispatch.

Source locations in the identified working tree were:

- `src/Features/Upscaling/FidelityFX.h:89-116` for control and dispatch state;
- `src/Features/Upscaling/FidelityFX.cpp:1162-1214` for atomic snapshot/apply;
- `src/Features/Upscaling/FidelityFX.cpp:1609-1625` and `2738-2754` for host and
  runtime context flags;
- `src/Features/Upscaling/FidelityFX.cpp:2948-2994` for generation replacement;
- `src/Api/UpscalingDevBenchBridge.cpp:469-539` and `726-772` for the guarded
  DevBench JSON contract.

Every accepted flag change in the mirrored crossover advanced the runtime
context generation exactly once before the next successful dispatch. The
successful dispatch descriptors consistently reported path `runtime_fsr4`,
`preExposure = 1.0`, and no bound exposure resource. These settings declare the
vendor FSR context contract. They do not disable, reorder, or bypass Skyrim's
separate ImageSpace/`ISHDR` processing.

## Active input region versus physical target

With render-scale mode off, the high-level upscaling snapshot continued to
report the 1,512 by 1,680 physical per-eye target. The new successful-dispatch
descriptor separately reported the active FSR input region:

| FSR4 preset | Active input per eye | Output per eye |
|---|---:|---:|
| Native AA | 1,512×1,680 | 1,512×1,680 |
| Quality | 1,008×1,120 | 1,512×1,680 |
| Balanced | 889×988 | 1,512×1,680 |
| Performance | 756×840 | 1,512×1,680 |

This is a runtime distinction between physical target ownership and the region
consumed by the FSR dispatch. It corrects the earlier map interpretation that
Quality with render-scale mode off necessarily receives a full-resolution FSR
input.

## Campaign

The run captured an exact interior fixture and an exterior fixture with water
visible, both at 15:00 under locked `SkyrimClear_A` and timescale zero. It
produced 26 conditions and 78 analyzed three-frame stereo submissions, plus 17
bounded 180-frame profiler captures.

The initial matrix contained a four-cell Quality HDR/auto-exposure factorial
and an H1/A1 return control in each fixture. The H1/A1 preset dose covered
Native AA, Quality, Balanced, and Performance. Riverwood also received a
method-None anchor and a mirrored `A-B-D-C-A-C-D-B-A` crossover, where
A=H1/A1, B=H0/A1, C=H0/A0, and D=H1/A0. The mirrored cell acquisition ranks
are centered and therefore cancel a linear time trend in the factorial
contrasts.

The initial-to-return H1/A1 luminance drift was +0.79% in the interior and
+3.83% in Riverwood. Initial sequential factor estimates were consequently not
treated as causal. The mirrored Riverwood crossover estimated HDR +0.809%,
auto-exposure +0.758%, and interaction -1.322% of grand-mean linear luminance,
but its repeated H1/A1 anchor drifted -2.143% and cell replicate scatter
exceeded the fitted effects. The experiment proves independent flag application
and context lifecycle; it does not distinguish their direct visible contribution
from scene drift.

## Performance slice

The 180-frame runtime-dispatch averages were:

| Scene | Native AA | Quality | Balanced | Performance |
|---|---:|---:|---:|---:|
| Interior | 4.084 ms | 3.461 ms | 3.469 ms | 3.373 ms |
| Riverwood | 4.022 ms | 3.689 ms | 3.552 ms | 3.288 ms |

These are historical pilot/screening measurements of one build, machine,
shader preset and pair of scenes. Each table cell is a single bounded capture,
not a replicated timing estimate. No qualified visual-quality ordinate was
paired with these timings. They can guide later experiment selection, but
cannot establish a Pareto surface, dominance, or a preset ranking.

## Instrumentation boundary

The direct MCP catalogue advertised Depth Culling diagnostics and render-map
capture, but exact registry/snapshot calls returned `Tool not found` while
upscaling, screenshot, weather and profiler endpoints were healthy. Those two
capture surfaces are therefore not live-qualified in this build. Local
automation feedback receipt: `AUTO-20260912-231534593-93A047A4`.

## Evidence identity

Private retained evidence contains 123 content files and 746,456,086 bytes,
with deterministic tree SHA-256
`F199361219402E7122B7EA6FA20284EA5A3559A83248289DD75895D1521BD8DA`.
The publication receipt SHA-256 is
`A62A9207394ED6AFCB859E46601368465547C18F160F9ECD5FB5E821338E0A27`;
machine analysis JSON SHA-256 is
`A64BDA6F1E0B88F9B0D7CDCC8CD38F1B9DF35D77E8A60BD3F8CFCC788023B9B0`.
Absolute local paths, profile identity, session identity and raw media are not
published in this submission.

## Exact build and source identities

- Build ID: `bc1cfa895048a255a3221a7570860be5f9a007e2bc2334536b3520f54a3d558b`.
- DLL: 27,317,760 bytes, SHA-256
  `306F1E5366E827D19DEAF0BC6100A8B770FC281192CEAC9429AA132810CA6D41`.
- Shader-cache ABI:
  `e0070b1a7ce8b8bde5952a9d720f31cf1432e0f31512d233033e44246b26838e`.
- Working-tree dirty digest:
  `24dcd04c6106623f025319da026b4baf6bc15e9af6458623aafc6ae2d708acf1`.
- `FidelityFX.h` SHA-256:
  `E9A9DF11531671EA7E0893D9A739951C197A25B64750C9AFBC3F26A94D5378FE`.
- `FidelityFX.cpp` SHA-256:
  `0B20FFDAD9BF559FD0BCA759FD0D39C100E7F3CBCEF15F5D7FD0F0494B5318A0`.
- `UpscalingDevBenchBridge.cpp` SHA-256:
  `79EF2F0C43D8C14A1ED94263C6AD5647226FB9C6ADBC09FB16AE6BCFE2924907`.
- Known-working shader-cache tree: 3,606 files, 181,574,531 bytes,
  SHA-256 `6FB566E862A1733827F760A65B609447CE0139990939D452CE89DE976727A615`.

## Next discriminating examination

Use a deliberately static exposure fixture or same-frame raw-resource probes
around Skyrim ImageSpace and the FSR input/output boundary. Counterbalance at
shorter intervals, increase replication, and report water and non-water regions
separately. Extending the same sequential Riverwood image matrix would be
inefficient because its measured scene drift exceeds the fitted HDR/AE effects.
