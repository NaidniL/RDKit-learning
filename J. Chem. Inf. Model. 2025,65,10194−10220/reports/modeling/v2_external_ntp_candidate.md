# v2 NTP candidate external

状态：`CANDIDATE BUILT — NOT AUTHORIZED FOR EXTERNAL EVALUATION`。

NTP/NICEATM 的 NTP Cancer Bioassay Chemicals 表是新的候选来源。按冻结规则只保留 P 且无 NE 的阳性、以及至少一个 NE 且其余仅 NE/NT 的阴性；随后剔除与 current formal development 的 exact、connectivity 和 tautomer 重叠。脚本不读取或复用 v1 CCRIS external。

## Locked source

- URL: `https://ntp.niehs.nih.gov/iccvam/refsubs/ntp-cancer-bioassay-july2020.txt`
- raw SHA-256: `b5313e9abf36c1d60bb589f9c734c7992ddaacff17016cb651be29579538fbba`
- source encoding: `cp1252`
- raw rows: `571`
- release: `20260711_194149_961442_UTC_formal_e20e3008`

## Candidate result

- candidates: `49`
- carcinogen: `15`
- noncarcinogen: `34`

## Exclusions

- NTP_uncertain_or_conflicting: `364`
- development_connectivity_overlap: `11`
- development_exact_overlap: `104`
- development_tautomer_overlap: `5`
- invalid_qsar_ready_smiles: `32`
- within_ntp_structure_label_conflict: `4`

该集合仍只是候选 external。必须在后续独立授权中绑定其 manifest，并完成与 v1 external 的非复用审计后，才可进入一次性 v2 external evaluation。
