# MicroRhodoDB v1.5.0 build container.
#
# NOT BUILT in the agent sandbox (no Docker daemon available there) - the conda lock
# (workflow/envs/mrdb.lock.yml) is the tested, verified reproducibility path for this release.
# This Dockerfile is provided so a user with Docker can build and run the identical pinned
# environment; please build and smoke-test it (`docker build . && docker run <image> snakemake -n`)
# before relying on it, since it has not been executed end-to-end here.
#
# Build:  docker build -f workflow/Dockerfile -t microrhododb:1.5.0 .
# Run:    docker run --rm -v $(pwd):/work -w /work microrhododb:1.5.0 \
#            snakemake -c 16 -s workflow/Snakefile --configfile workflow/config.yaml <target>

FROM condaforge/miniforge3:24.9.2-0

LABEL org.opencontainers.image.title="MicroRhodoDB v1.5.0 build environment"
LABEL org.opencontainers.image.description="Pinned conda environment (IQ-TREE 2.3.6, HMMER 3.4, MAFFT 7.526, MMseqs2, EPA-ng, gappa, DIAMOND 2.1.10, ClipKIT, Snakemake 8.30) for reproducing the MicroRhodoDB v1.5.0 release."
LABEL org.opencontainers.image.source="https://github.com/<owner>/MicroRhodoDB"

WORKDIR /work
COPY workflow/envs/mrdb.lock.yml /tmp/mrdb.lock.yml

# Mamba resolves this pinned environment far faster than conda; falls back to conda if mamba
# is unavailable in the base image.
RUN (mamba env create -f /tmp/mrdb.lock.yml || conda env create -f /tmp/mrdb.lock.yml) \
    && conda clean -afy

SHELL ["conda", "run", "-n", "mrdb", "/bin/bash", "-c"]
ENV PATH="/opt/conda/envs/mrdb/bin:${PATH}"

# Repository code (Snakefile, pipeline/, tests/, curation/) is bind-mounted at /work via
# `docker run -v $(pwd):/work`, not copied into the image, so release edits never require a
# rebuild. Large release databases and the refpkg stay out of the image entirely (Zenodo /
# release assets), keeping this image small and purely a toolchain container.

ENTRYPOINT ["conda", "run", "--no-capture-output", "-n", "mrdb"]
CMD ["snakemake", "--help"]
