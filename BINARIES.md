# Binary files not committed to git

The SQLite databases are too large for the git repository. The current database is attached to the GitHub Release
`v1.6.0`; it is all the CLI, the API, the browser and the website need. Download it to the path below (relative to
the repository root) and check the SHA-256:

```bash
python web/scripts/fetch_release_db.py          # downloads and verifies against the table below
# or: gh release download v1.6.0 -R CongjianL/MicroRhodoDB --pattern microrhododb_v1.6.0.sqlite -D releases/v1.6.0/db
```

| Path | Bytes | SHA-256 |
|---|---|---|
| `releases/v1.6.0/db/microrhododb_v1.6.0.sqlite` | 33464320 | `379a254356c6489a2b9e0600d501d76d22bc8e3ced4cfbdd5160fb00c3dce17f` |

## Prior-release databases (not on the GitHub Release)

These are not currently published. They are needed only to rebuild v1.6.0 with the Snakemake workflow (from
v1.5.0) and for the tests that compare v1.6.0 with earlier releases; those tests skip when the databases are absent.
If you have a copy, place it at the path shown and check it against the SHA-256 below.

<!-- Column order differs from the table above on purpose: web/scripts/release_gate.py (RA-1) and
     web/scripts/fetch_release_db.py read `path | bytes | sha256` rows as GitHub Release assets. -->
| Path | SHA-256 | Bytes |
|---|---|---|
| `releases/v1.5.0/db/microrhododb_v1.5.0.sqlite` | `d715baf8af951cb5a78aa2f5db042c03b8fff788d2627fc6df2d97b67e88e33a` | 30932992 |
| `releases/v1.5.0/db/microrhododb_v1.5.0_env_pilot.sqlite` | `2fd572a8e7990da36215f939e7f61409ffef8a4a2889e8d9960536a37051852b` | 1400832 |
| `releases/v1.4.0/db/microrhododb_v1.4.0.sqlite` | `21342d94b207b6e0b9e8f313d3689ea962fc59c89503c287ee59de46061f6854` | 18759680 |
| `releases/v1.3.0/db/microrhododb_v1.3.0.sqlite` | `09ce39204f350e79df58ea0efc0512a24876d4e486e92ce156182a0207248e41` | 18034688 |
| `releases/v1.0/db/microrhododb_v1.0.sqlite` | `f15033ca5f5166cb0f09a57cb012a91e275ab498654ef6a66c58159c0daf7879` | 8667136 |

```bash
sha256sum -c <<'EOF'
379a254356c6489a2b9e0600d501d76d22bc8e3ced4cfbdd5160fb00c3dce17f  releases/v1.6.0/db/microrhododb_v1.6.0.sqlite
d715baf8af951cb5a78aa2f5db042c03b8fff788d2627fc6df2d97b67e88e33a  releases/v1.5.0/db/microrhododb_v1.5.0.sqlite
2fd572a8e7990da36215f939e7f61409ffef8a4a2889e8d9960536a37051852b  releases/v1.5.0/db/microrhododb_v1.5.0_env_pilot.sqlite
21342d94b207b6e0b9e8f313d3689ea962fc59c89503c287ee59de46061f6854  releases/v1.4.0/db/microrhododb_v1.4.0.sqlite
09ce39204f350e79df58ea0efc0512a24876d4e486e92ce156182a0207248e41  releases/v1.3.0/db/microrhododb_v1.3.0.sqlite
f15033ca5f5166cb0f09a57cb012a91e275ab498654ef6a66c58159c0daf7879  releases/v1.0/db/microrhododb_v1.0.sqlite
EOF
```

The v1.3.0 and v1.0 databases are needed only by the historical v1.4.0 test suite. v1.1 and v1.2.0 are not needed.
