# Runtime evidence index

## Breezehome four-frame structural capture

This retained evidence is private/offline because the event stream and derived
graph are very large and may contain installation-specific metadata. The
published index exposes only content identities, bounded counts, positive
results, and limitations.

- Summary capture time: `2026-09-12T16:40:23.461Z`.
- CSX source commit: `d28a790278273de6c3d8173866322a372b20440b`.
- Scenario: Skyrim VR, Breezehome, four frames.
- Capture ID: `capture-live-0001004a587c28e4-2`.
- Completion: complete `frame-limit`; not truncated.
- Events: 449,360; dropped events: 0; catalogue drops: 0.
- Event stream: 623,501,145 bytes,
  SHA-256 `C04755F14BB5A46F8BEEDBC7ACD047691EFE64DDB1611530CB9576A51D093B86`.
- Capture manifest SHA-256:
  `27AA47812EB6573F1916680B04C9DCD12A3A397DACED3EB09E7C397017C6F0A2`.
- Derived graph: schema `csx.derived-render-graph/1.12`, producer
  `static-semantic-resource-graph-10`, 388,002 nodes, 1,008,244 edges, one
  non-blocking gap, acyclic.
- Derived graph: 1,074,161,891 bytes,
  SHA-256 `5CE4CF9488871B3A5974FBFD44BCA508688FB8FDBCA76E31FEF637CF8BB3A0AE`.
- Evidence summary: 2,418 bytes,
  SHA-256 `3A6C988C134DAEE15A1A0BF4FD47FC239DBA6D00F2D450068C817ED815E1E4CB`.
- Catalogue counts: 17 shaders, 130 stage shaders, 787 resources, 767 target
  views, 26 target bindings, 282 scene objects, 820 geometries, and 796
  material states.
- Validation counters: ten of ten shader compilation tasks passed; 49,629
  effective-state queries covered 156,453 state slots with zero mismatches;
  12,292 material-input execution matches; 3,184 prepared-geometry draw
  matches; 152,821 CPU-access operations.

Only positive relationships present in the capture are usable evidence.
Unobserved event kinds, passes, shader aliases, and resource identities remain
unknown. The single graph gap records an Unmap just after the capture boundary
whose preceding Map was outside the interval; it is not evidence of missing
render topology.

The embedded capture manifest does not establish a complete deployed DLL hash,
build manifest, runtime route, profile/load order, settings digest, shader-cache
identity, GPU identity, physical render dimensions, or treatment state. This
capture therefore supports structural instrumentation and graph-completeness
claims only. It supplies no profiler result and no water/upscaling image-quality
comparison.

## Riverwood water-visible stereo observation

This bounded observation is retained offline because its source JSON contains
absolute paths and process/session identifiers. Those fields are deliberately
not copied into this contribution.

- Observation time: `2026-09-08T02:20:46.5396786Z`.
- Scenario: loaded Skyrim VR scene at Riverwood with visible water.
- DevBench version: `1.16.0`.
- Capture source: accepted HMD submission; fallback policy `reject`.
- Output contract: left and right eye PNG, each 1,512 by 1,680,
  `sdr_srgb`.
- Left image: 4,655,025 bytes,
  SHA-256 `DA6DEE56D3FCD4E4E926F628424DA1743C7D1C3539A9E5537A2C877328FACB65`.
- Right image: 4,655,214 bytes,
  SHA-256 `D0B4677C906B07209F7F6C19F713971F17E95851ACC57C9376AA1C1C5D3F8A96`.
- Sanitized source index identity: the original 10,223-byte observation JSON
  has SHA-256 `DF9881B191E7BEB392C3D9A52155B641335B754ED741DE11EDC0C56E0788872B`.
- Runtime device: AMD Radeon RX 7900 XT; DLSS was unavailable.

This is a fixture and capture-provenance record only. It does not form an A/B
pair, does not establish the reconstruction or render-scale treatment, and
does not prove a water, brightness, saturation, hue, exposure, temporal, or
performance effect. The retained runtime descriptor and DLL identities are not
reproduced here because the reviewed observation file does not contain their
complete values.

## Original report provenance boundary

Contributor clarification establishes only that the original report came from
an NVIDIA-host machine. The enabled reconstruction method and render-scale
state were not established. NVIDIA hardware makes DLSS available in principle;
it does not show that DLSS was active, and it is not causal evidence for the
reported phenomenon. The report is not represented by a ledger assertion and
is not attached to the DLSS contract entity. Its causal scope remains open
across reconstruction method, render-scale ownership, shared image-space and
water stages, sharpening, mip-bias, GPU-vendor, and downstream display domains.

## AMD five-treatment colour/render-path campaign

This controlled campaign was captured on an AMD system where the runtime
capability mask was `7`: None, TAA, and FSR were available, while DLSS was not.
It therefore demonstrates that the measured colour/luminance differences do
not require DLSS. It does not establish one exclusive mechanism or generalize
the magnitudes to other GPUs.

- Campaign date: `2026-09-12` (`Europe/London`).
- CSX source commit: `fa4aac8d0b6772d3d75374fdbd2ad71604608ead`, clean.
- Build ID: `259e7a39aee83172a0f6ad47ab4f67535debe6f560fc5dfab92e3365c11362c0`.
- Deployed DLL SHA-256:
  `1499BFADA1CC3C17C1A9CB3A7DB7E16E9E376725402D1A8050F98BA0DAEC1BD2`.
- Shader-cache ABI:
  `267215B3932D4EED65F01397180D535C0B36CF71F15880303E84A240EED0AAF9`.
- Runtime: Skyrim VR under SteamVR null-HMD, 1,512 by 1,680 per eye at
  90 Hz output resolution.
- Fixtures: Riverwood exterior and Breezehome interior at 15:00 and 23:00.
  Weather was forced and locked to `SkyrimClear_A`
  (`0x10E1F2~Skyrim.esm`), and `timescale` was zero. Breezehome remains
  weather/time-sensitive and is not treated as a weather-independent control.
- Treatments: loaded None; loaded TAA; FSR 4 Native AA with render scale off;
  FSR 4 Quality with render scale off; and FSR 4 Quality with render scale on.
- Replication: three stereo submissions for each loaded treatment-condition
  pair, producing 120 eye images across 20 matched sets, plus three stereo
  submissions at each Breezehome time for the repaired boot-disabled control
  (12 additional eye images).

Physical target ownership differed from the output contract. Loaded None,
loaded TAA, FSR Native AA/render-scale off, and FSR Quality/render-scale off all
used 1,512 by 1,680 physical eye targets. FSR Quality/render-scale on used
1,008 by 1,120 physical eye targets and reconstructed them to 1,512 by 1,680.
In this build, selecting the Quality vendor profile with render scale off did
not physically reduce the engine target. It is nevertheless a vendor Quality
route and is not equivalent to loaded None or vendor Native AA.

Aggregate matched-set measurements were calculated in linear light. Signed
luminance is second treatment minus first treatment. `RGB/noise` is the
reported signal-to-sampled-noise ratio.

| Comparison | Signed linear luma | Mean DeltaE76 | RGB/noise | Bounded interpretation |
|---|---:|---:|---:|---|
| None to TAA | -0.000038 | 0.936 | 0.68 | Below sampled noise; no stable brightness direction. |
| None to FSR Native AA, RS off | -0.002287 | 1.292 | 1.15 | FSR was darker in all four conditions. |
| FSR Native AA to FSR Quality, RS off | -0.001315 | 1.079 | 1.34 | Quality was usually darker; Riverwood night weakly reversed. |
| FSR Quality RS off to RS on | +0.000670 | 1.036 | 1.18 | RS on was brighter in all four matched blocks; confidence varied. |
| None to FSR Quality, RS off | -0.003601 | 1.592 | 1.45 | Stronger aggregate separation. |
| None to FSR Quality, RS on | -0.002932 | 1.360 | 1.21 | Strong aggregate separation. |

Percent changes are intentionally omitted because the 23:00 baseline luma is
very low. Treatments were applied sequentially rather than counterbalanced.
Three repetitions support the larger aggregate differences, but they do not
provide causal closure for small/noisy effects, especially water-only effects.

A separate restart tested feature absence. The feature API reported
`disabledAtBoot=true` and `loaded=false`; 37 of 40 features loaded, with
HorizonFix, Upscaling, and WetnessEffects absent. The task profile had
`bUseTAA=0` and automatic dynamic resolution disabled. Changing feature
presence caused the shader cache to be rejected. The first rebuild recorded
46—not 37—Lighting shader failures at `Lighting.hlsl(182)` because
`CurrentFrameDepthCulling::IsOccluded` was undeclared. Its nearly white/broken
frames are invalid diagnostic evidence only.

The failure was an omitted external-shader include. Commit
`39399749730e601d5d3e32568f47fb1a8013c8f3` adds exactly
`Common/CurrentFrameDepthCulling.hlsli` to `package/Shaders/Lighting.hlsl`.
The repaired deployed file was Git blob
`1c870579503c9ea6b38b6c7f959785fed55a9f93`, 182,931 bytes, SHA-256
`2782553C80473F0CFF7287048F1BEF0882CC4394A9E6BE1FB0DCC855FDDABF84`.
The valid control retained the fa4 DLL/build and used only this exact external-
shader repair. Its rebuild produced zero `Failed to compile` entries and a
3,607-file, 181,619,864-byte known-working cache with tree SHA-256
`0CC010BD4F858D1C961881DA774411661E1D53314D97C4A4C3028A7BDADF20D7`.

The repaired control used the exact Breezehome cell and position
`[-384.46826171875, -656.160888671875, 66.83744049072266]`, locked
`SkyrimClear_A`, `timescale 0`, and exact 15:00 and 23:00 observations. Values
below are left/right-eye means. Signed luminance is boot-disabled minus loaded
reference.

| Loaded reference | Time | RGB MAE | Signed linear luma | DeltaE76 | RGB/noise | Luma/noise | Bounded interpretation |
|---|---:|---:|---:|---:|---:|---:|---|
| None | 15:00 | 0.014911 | +0.006914 | 1.969 | 2.29 | 2.10 | Boot-disabled was measurably brighter and different. |
| TAA | 15:00 | 0.014853 | +0.006233 | 1.963 | 2.15 | 1.98 | Also clearly separated. |
| FSR Native AA, RS off | 15:00 | 0.017662 | +0.011005 | 2.177 | 6.06 | 4.93 | Strong separation. |
| FSR Quality, RS off | 15:00 | 0.021088 | +0.013461 | 2.555 | 7.00 | 5.55 | Strongest daytime separation. |
| FSR Quality, RS on | 15:00 | 0.019093 | +0.012649 | 2.363 | 5.31 | 4.54 | Strong separation. |
| None | 23:00 | 0.004618 | -0.000887 | 0.885 | 1.17 | 0.86 | Weak RGB-only separation; luma below noise. |
| TAA | 23:00 | 0.003928 | -0.000273 | 0.740 | 0.73 | 0.55 | Nearest sampled path; indistinguishable at sampled repeatability. |
| FSR Native AA, RS off | 23:00 | 0.004419 | +0.000418 | 0.801 | 1.13 | 0.69 | Weak RGB-only separation. |
| FSR Quality, RS off | 23:00 | 0.005703 | +0.000932 | 0.894 | 1.45 | 0.87 | RGB separation; luma below noise. |
| FSR Quality, RS on | 23:00 | 0.004825 | +0.000466 | 0.834 | 1.23 | 0.79 | RGB separation; luma below noise. |

The daytime result disproves general visual equivalence between feature absence
and loaded None. The distinction is strongly lighting/condition dependent and
mostly falls below the sampled luma noise floor at night. Feature absence is
not simply loaded TAA either: TAA is the nearest sampled night path but remains
clearly separated during daytime.

The retained report and machine analysis are indexed by content identity only;
their absolute working paths and identifying fixture strings are excluded:

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| Campaign report | 13,324 | `ABE35970BFD4A8C7F249B35173627708887E5F106E0A888732A1DA4F55DE0475` |
| `analysis.json` | 101,807 | `D645D7960286171346E5749A08CDB12609B0DA49F55D5911819B2C795DC24C7A` |
| `analysis.md` | 3,957 | `9B1EB701A987CD1155E883C49EDDBFD2A54BC6C4734343EB31E2D27F86EECB37` |
| `comparisons-vs-loaded-none.csv` | 11,269 | `C712A512970DE3200F77C7CC3A6FC078A7C0D5A9F276FD742766EFA3CE8947BB` |
| `pairwise-comparisons.csv` | 27,919 | `EEF41DB4033192AAF99083706C21710EE2075FAD27370078925A5CB19A86F2E5` |
| `per-image-metrics.csv` | 56,373 | `615053BC2DD60E3F120D732C3EF8B959992EE1332B4BB64A40E173B1D8157446` |
| `per-set-metrics.csv` | 18,861 | `FEAC83835144095887C27A2C7F518E3E0D2E095174399D070B1E93D3EAA5014D` |
| Boot-disabled comparisons | 71,994 | `D0EB1F57E8079E91115FD8BC8BF32A98E4DE040D9C4F444F0FCA30E722F916F7` |
| Promoted capture corpus tree | 1,749,078,108 | `9809EE6F94D11C17F1F761A17778D5C0AD13D43234552446B9374BFEC81B86F9` |
| Repaired boot-disabled cache tree | 181,619,864 | `0CC010BD4F858D1C961881DA774411661E1D53314D97C4A4C3028A7BDADF20D7` |

The capture corpus contains 514 files. The repaired cache contains 3,607 files
and was catalogued as
`20260912T201332810Z-fa4-DLL-plus-exact-393997-Lighting-include-hotfix-Upscaling-unlo-0cc010bd4f85`.
The campaign closes neither the dominant water-only contributor nor cross-
vendor magnitude or downstream compositor/display effects.

## Earlier accepted runtime joins

The accepted submission
`sub-csx-full-render-exploration-9935c5210` contains two relevant, independently
bounded records:

- `imagespace-compile-source-main-menu-capture-2026-08-29.md` joins observed
  main-menu HDR loader aliases to shared `ISHDR.hlsl`. Numeric compile ordinals
  disagreed between historical artifacts, so normalized path plus content hash
  is the usable identity.
- `eye-submission-live-capture-2026-08-29.md` proves a main-menu producer-to-eye
  submission boundary for its own build and fixture.

Neither record is a water-loaded render-scale trial, and neither is projected
as proof of visual equivalence or difference here.
