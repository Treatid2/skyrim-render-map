# Historical August preset feature screen

This generic observation preserves the 2026-08-30 physical Pico 4 Ultra,
OCU/VDXR, RX 7900 XT Whiterun pilot. `observation.json` contains exact
API-reported feature deltas, uncertainty, significance flags, and four separate
profiler control windows. The canonical compiler indexes its entity and
submission; it does not interpret this private observation schema as typed
performance samples or derive a Pareto surface.

The feature trials used three-second current/comparison/restored-current
A-B-A phases. The requested 120 frames belong to the adjacent profiler control
windows. Timer history counts may be lower for conditionally executed timers.
No raw feature samples are reconstructed from averages or standard errors.
`gameGpuMs` is preserved as an invalid historical field because it reported
zero or epsilon. API significance flags are reported without independent
statistical revalidation. Signs and costs are specific to this scene/build.

The two initial controls had progressing game time and remain confounded.
The later controls set TimeScale to zero; their exact recorded GameHour is
retained. The final B2 payload completed 120 frames, although the wrapper
failed during profiler restoration with HTTP 503. The source session report
records explicit recovery and restoration; capture completion and wrapper
success are separate fields.

Source identities are retained by SHA256. The original scripts, invocation
records, settings and profiler JSON are archived privately with exact byte
round-trip verification. Compiled shader cache and binary payloads are outside
this bounded import. Cache identity is a historical claim from the preserved
receipt; it was not requalified against today's runtime.

The source documentation is pinned at commit
`0a805ab9cc29ac895da6d168f18dd13446945975`; the observed dirty runtime baseline
was `c46b93b2a0e0944fbfeb8746e3ca2bc84ef276a6`. These are distinct identities.
The original evidence directory contained no screenshot files. Visual quality,
stereo correctness, cross-vendor/runtime comparability, preset qualification,
and typed performance admission remain unresolved.
