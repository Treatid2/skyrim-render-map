# Candidate contrast-identity correction (2026-10-02)

The original unadmitted candidate is preserved at render-map research commit
`64bb49dd20c83ec5c24b28b77c1ec2ccead5af5a`. This correction creates four ordered
experimental-contrast entities linked to the existing AMD campaign. Each
contrast has the same four matched fixture/time blocks as its original result;
the campaign itself is no longer the single-valued subject of four different
comparisons. No values, assertion IDs, evidence, applicability, source identity
or runtime observations change.

| Assertion ID | Corrected contrast entity suffix | Ordered comparison |
|---|---|---|
| `amd-none-to-taa-colour-result` | `amd-none-to-taa-four-block-contrast` | loaded None to loaded TAA |
| `amd-none-to-fsr-native-colour-result` | `amd-none-to-fsr-native-four-block-contrast` | loaded None to FSR 4 Native AA, render-scale mode off |
| `amd-fsr-native-to-quality-colour-result` | `amd-fsr-native-to-quality-four-block-contrast` | FSR 4 Native AA to Quality, both render-scale mode off |
| `amd-quality-render-scale-colour-result` | `amd-quality-render-scale-four-block-contrast` | FSR 4 Quality, render-scale mode off to on |

This removes six false pairwise conflicts between distinct comparisons.
Contradictory values for the same contrast, predicate and applicability remain
detectable; a synthetic negative-control compilation verifies that property.

Substantive-review follow-up: narrowed the README's original "The phenomenon
therefore is not DLSS-specific" wording. The AMD results show differences with
DLSS unavailable, but their identity or mechanism relative to the original
NVIDIA-host report remains unresolved. No assertion or measured value changes.
