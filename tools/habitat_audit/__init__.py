"""PR-7c.1 habitat metadata availability audit (MicroRhodoDB v1.6.0).

Evidence-availability audit only: reads the frozen release database read-only,
retrieves public accession-chain metadata through a content-addressed cache and
classifies, per source record, what habitat evidence is (or is not) available.
Nothing here writes to the release database, releases/, refpkg/, pipeline/,
site/ or the production web export.
"""

AUDIT_ID = "PR-7c.1"
AUDIT_VERSION = "1.0.0"
