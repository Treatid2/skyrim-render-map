# Source evidence index

## Source identity and method

- Repository: `Treatid2/skyrim-community-shaders`, derived from
  `ParticleTroned/skyrim-community-shaders`.
- Commit: `d28a790278273de6c3d8173866322a372b20440b`.
- Parent: `700dbb5f875a6217e7c6d4d0b7f1055443c5f3b5`.
- Git tree: `1c62041537e9ee9ea4beeec7ae7c4615050c3399`.
- Full-tree index SHA-256:
  `2F43230F5B828CF13248E23521079280A9AF053FCAAA198B6AE1928F738E4977`.
- Full-tree index method: SHA-256 of the UTF-8 bytes of `git ls-tree -r
  --full-tree` output, with one LF after every entry, for 1,163 entries.
- Source state: clean committed local preservation. The development branch has
  moved, so the commit is not claimed to be publicly reachable.

Line ranges are one-based and inclusive. File SHA-256 values cover exact Git
blob bytes, not a checkout's translated line endings.

## HDR and authored colour

| File | Git blob | Bytes | SHA-256 | Inspected lines |
|---|---|---:|---|---|
| `package/Shaders/ISHDR.hlsl` | `2fc63c40eadfccbff2a9a1ad496152fff0e7078c` | 8,515 | `2AEE42FE65E3D7EE3238B0E9050488A6DEF75C93B8D873D1E9E002ECEA83D5DF` | 7–28, 42–53, 56–129, 131–241 |
| `package/Shaders/Common/DisplayMapping.hlsli` | `f6198169cb40e69722f32ed81be0cbabb4ef08ce` | 6,697 | `A5832384E5ECF02689B81B2801B137529ADDA1DC6119F3DB2F940F650D769651` | 150–191 |
| `src/CSEditor/Weather/ImageSpaceWidget.cpp` | `338cacb4df4a52a1f29318f65553a25e1e17dc00` | 10,486 | `1BFC8342CDEC94574608620056E2DAAADAE4779D5BEEAC0B9B0EA98BBE331241` | 38–62, 131–144, 188–212 |
| `src/FrameAnnotations.cpp` | `3400c73534d93bdaa50d1a60638df9bd11d06728` | 60,817 | `88F7407E015E91078DC273A656176BD005F2D0E9263CDBD3E50655AC55D32DA2` | 563–586, 836–859 |
| `src/ShaderCache.cpp` | `d92110d39b862e85033e8aedbc7cd35bf05626e1` | 238,240 | `B0D50A80ABA47CAAE9B5CB6790688BB3E9F436B2119D5E77F6FB236E2DABEFA8` | 2772–2789 |
| `src/FeatureBuffer.cpp` | `c40079b2922f2dc5627e87897b7ad05063f4999a` | 16,926 | `D72B2DE43615151D17D3719A5E9F2F9C14AC31513A5D32D7DC98CEF35F905D2A` | 251–258 |
| `src/Features/AdaptiveBrightness.cpp` | `17f7a3e45e5318960943287760f5f750489b1a48` | 136,952 | `09D4FC33E64E134945F048C5B8649F45347AA92BAE7969FABD8D862A46C10DC7` | 3495–3586, 3639–3652 |

These ranges establish the HDR inputs, adaptation, tonemap branches, ICtCp
chroma handling, final grade order, editor-to-engine field names, loader/hook
catalogue, shared feature-buffer controls, and profile composition described in
the structured assertions.

## Water, SSR, and history

| File | Git blob | Bytes | SHA-256 | Inspected lines |
|---|---|---:|---|---|
| `package/Shaders/Water.hlsl` | `bb32a71d57644601747c39ad20f2a594359ce836` | 87,891 | `08C073AD23A57D3B21514BA23908A0E4C9332D8BBCAB134679CBC024D0A39B8C` | 1013–1050, 1090–1126 |
| `package/Shaders/ISReflectionsRayTracing.hlsl` | `4c32a1103e80d82736a838df741c901bd583a0ec` | 9,467 | `978D10F4460FE6655D1332F49EAD424940348A6CBDC31ABA3DEFA393FBFDFA14` | 20–207 |
| `package/Shaders/ISApplyReflections.hlsl` | `a66f9f0b5ae055adfff2a2a87fa76063536011e2` | 1,231 | `B144B919C7F8EE5E05C43C55B7EF657AEE66708703D115CC5EB49975E51484BF` | 12–38 |
| `package/Shaders/ISWaterBlend.hlsl` | `be2fada8f6af0ab10ffbcddb48185965c1a255e4` | 4,114 | `309450208C02947BA4421905DDA2103F132CB32F318590CF58F54C02C1D6E9B2` | 8–108 |
| `src/Hooks.cpp` | `fad2feee990085750c05589cddc8364f7251a3b4` | 98,207 | `4C963153F1E66AEA15706983A3395A273F93EB8178BA225E438D9C79322ECC35` | 1442–1462, 2626–2628 |
| `src/Deferred.cpp` | `17c3d1e5160351d358db928a3f93cb6028dd2323` | 30,716 | `2B6DDF949E882D86141B857184D0F7F3FDBFD688259EE183E1E4585F60D56D37` | 202–211 |

The raymarch and apply shaders are mapped as source dataflow only. No retained
loaded-water trace joins their exact execution order to the water and HDR
stages in the same frame.

## Reconstruction and presentation

| File | Git blob | Bytes | SHA-256 | Inspected lines |
|---|---|---:|---|---|
| `src/Features/Upscaling.cpp` | `1a29f88b894097770028c4ae0e9a51e8e62795e6` | 2,301,910 | `4527834FE30ABB3A9BDB2FA5AD7FA9A612D13656B36D97AE1477E4E2327C0A71` | 2177–2208, 2326–2372, 4378–4414, 11232–11253, 18109–18136, 20330–20361, 43986–43999, 48463–48537, 50326–50369, 56419–56436, 56706–56930, 57283–57456 |
| `src/Features/Upscaling/Streamline.cpp` | `d86da86cb47b276acdfad84ab2922b123b1d5459` | 138,571 | `AFA6C18C4D30F035BEF7C8CDEC8E71DA4256A6CAAD50784D317004FF27A71832` | 129–141, 337–344, 2112–2162 |
| `src/Features/Upscaling/FidelityFX.cpp` | `f5b97de4ab797c950a8782e3cbbc0d97ed6f31d8` | 163,926 | `6EAAE44A3D16E0B6A4AE648FA95571B678916424BF4487579ACAA899F24A7EDC` | 60–68, 3115–3120, 3645–3671 |
| `src/Features/VR/InSceneOverlay.cpp` | `e95d6bbbf42f12c6be8ae530c21e3994981d67d5` | 121,416 | `67C6701B93D4DE5E22B5BA9428D7658557A80C6E62181576F0C4127F9004B173` | 1697–1763 |

These ranges establish target ownership, post-processing order, temporal
fallback, colour and format admission, output-descriptor preservation, DLSS and
FSR colour/exposure contracts, sharpening, mip bias, foveated alternatives,
and the accepted compositor-submit boundary.

The AMD campaign report names source commit
`fa4aac8d0b6772d3d75374fdbd2ad71604608ead`. Its `Upscaling.cpp` is the same
exact Git blob indexed above. Several report line references had drifted from
that blob, so the lifecycle, activity, full-resolution mask-repair, and
post-processing ranges were re-normalized against the content identity rather
than copied as stale offsets. In the normalized source, `DataLoaded` installs
the VR bridge and disables engine `bUseTAA` plus the dynamic-resolution clamp;
vendor activity requires an actual downscale, while the VR full-resolution mask
path can still refresh depth and underwater mask resources when colour
upscaling is inactive.

## Boot-disabled external-shader repair

The first boot-disabled cache rebuild exposed a compile-topology defect in the
deployed shader source, not a valid colour treatment. Relative to source commit
`fa4aac8d0b6772d3d75374fdbd2ad71604608ead`, repair commit
`39399749730e601d5d3e32568f47fb1a8013c8f3` adds exactly one line to
`package/Shaders/Lighting.hlsl`:
`#include "Common/CurrentFrameDepthCulling.hlsli"`.

| File | Repair Git blob | Bytes | SHA-256 | Inspected lines |
|---|---|---:|---|---|
| `package/Shaders/Lighting.hlsl` | `1c870579503c9ea6b38b6c7f959785fed55a9f93` | 182,931 | `2782553C80473F0CFF7287048F1BEF0882CC4394A9E6BE1FB0DCC855FDDABF84` | 1–8 |

The valid boot-disabled control combines the unchanged fa4 DLL/build with this
exact repaired external-shader blob. The original 46 failed Lighting variants
and their broken frames are diagnostic evidence only; all visual assertions use
the subsequent zero-failure rebuild.

## Bounded negative searches

At the identified commit, a case-insensitive Git search for `DLSS`, `FSR`,
`FidelityFX`, or `Streamline` returned no match in exactly these three files:

- `package/Shaders/Water.hlsl`;
- `package/Shaders/ISWaterBlend.hlsl`; and
- `package/Shaders/ISHDR.hlsl`.

The result is bounded to those file blobs and tokens. It does not establish an
absence elsewhere in CSX, in generated permutations, in vendor libraries, or
at runtime. An inspected search of the upscaling path found no explicit normal-
frame vendor saturation, cinematic-grade, or tint control. False substring
matches such as `interior` were excluded. Exposure, format interpretation,
sharpening, overlays, and downstream compositor transforms remain possible
colour-affecting mechanisms.
