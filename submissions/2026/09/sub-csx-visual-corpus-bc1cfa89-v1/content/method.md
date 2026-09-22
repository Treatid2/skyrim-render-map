# Historical screenshot comparison corpus

This generic observation indexes 26 bc1cfa89 capture sequences from Breezehome
and Riverwood. Exact source hashes reconcile 78 side-by-side stereo frames
(156 eye views) plus six separate eye PNGs, for 84 source PNG files. The two
derived analysis PNGs are excluded from this source-image count. The extra
eye PNGs equal the corresponding SBS halves pixel for pixel, but their hashes
were not individually attested by original sequence children. The distinction
is retained in `corpus-index.json`.

Original PNGs and sequence manifests are stored byte-for-byte inside local,
content-addressed DEFLATE ZIP archives. Every member was independently read
back and hash-verified; PNGs were decoded and geometry/pixel hashes verified.
Fixed archive metadata makes packaging deterministic for the recorded Python
and zlib versions. Compression is an outer lossless storage transformation;
no image resizing, colour conversion, quantisation or re-encoding occurred.
The archive digest and original PNG digest identify different byte objects.

The original campaign's 123-file inventory (excluding its publication receipt)
and SHA256 were independently reconciled before packaging. All 124 original
files, including the publication receipt and separate runtime/analysis evidence,
remain in the private corpus. No game assets or captured images are in this PR.

Preserved sequence manifests declare HMD submission, reject fallback, and SDR
sRGB. They do not independently record per-frame effective source, engine frame,
timestamp, pose or complete configuration identity. These fields remain unknown.
Sequence updated time is not a frame timestamp. Treatment digests cover only
the enumerated historical fields; they are not full configuration identities.
Profiler IDs link same-campaign metadata only and do not imply simultaneous
capture or matched performance eligibility. None, disabled and unloaded paths
must remain distinct.

Measured exposure/scene drift exceeds the fitted HDR/AE effects. Descriptive
image reanalysis is supported; quality ranking, preset qualification, causal
shader attribution and automatic Pareto use are prohibited for these historical
comparisons. Three frames per treatment do not establish temporal stability.
Future reference comparisons require independently qualified camera, scene,
exposure, runtime, build, resolution, capture-stage and treatment provenance.
Keep metrics, technical correctness, rendering effects and aesthetic preference
as separate versioned evaluation records linked to exact source hashes.

This uses canonical main's generic observation lane. It is not a specialised
visual-capture record: that contract is still on the unmerged PR stack and the
current adapter does not support these SBS manifests. Public media hosting and
rights are unresolved. `mediaLicence: null` and the empty retrieval list are
explicit; the metadata licence does not grant rights to captured game imagery.
The canonical compiler indexes the entity/submission without interpreting this
observation as valid comparison stimuli or a quality score.
