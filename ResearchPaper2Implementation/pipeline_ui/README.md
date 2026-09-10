# SPIRES local workbench

This frontend wraps the existing multi-corpus pipeline. Implementation and generated
website files stay inside `pipeline_ui`; pipeline source, original corpus files,
original extractions, and the pipeline's `corpora.yaml` are not edited.

## Run locally

```powershell
.\start.ps1
```

Open [the local workbench](http://localhost:3000). The API listens on
`127.0.0.1:8765`. Use `stop.ps1` to stop the services. The existing pipeline
`.venv-testgen` must contain its documented dependencies; `.venv-ontogpt` is needed
only for new extraction. The API itself uses the standard library and invokes the
pipeline interpreter for YAML and pipeline operations. Credentials come from the
pipeline's existing environment / `.env`; they are not sent to the browser.

## Workflow

1. Select a discovered `corpus.yaml` or `corpus.*.yaml`. Schedule 1 and Part IIIC
   are included. Invalid or colliding configurations fail closed, rather than falling
   back to Schedule 1. Corpus status reports artifact files; use **Check Neo4j** for
   a live, read-only connection and provision-count check.
2. Load the provision list, which calls the official `--list-provisions` interface.
   Search identifiers, select one or several, or enter a clause manually. Each batch
   member receives a distinct output directory. All IDs are resolved before payment.
3. Preview the exact SPIRES renderer with the selected corpus and retrieval settings.
   Preview needs Neo4j, but no OpenAI key or paid model call. Generation retrieves
   again, so graph changes can change context; its saved prompt is authoritative.
4. For builds, run the free preflight first. It validates the structural profile,
   invokes `build_corpus.py --dry-run`, and exposes gates and estimates in the log.
   The official authentication gate lists models over the network without purchasing
   a completion. A successful preflight is tied to the source, config, profile, model
   and pilot selection; changed inputs require another preflight.
5. Start the build. Extraction and optional exception recovery can incur charges.
   Reused raw/cleaned/verified artifacts are not re-extracted; verification runs only
   for files missing a verified output. Estimates use upstream pricing assumptions;
   profile induction, verification and generation are separate costs. A cleaned-only
   cache can make the upstream extraction estimate overstate remaining work.
6. CSV-only is the default. Optional Neo4j loading checks ownership and endpoint
   keys first. Replacement requires typing the selected corpus prefix. Merge loading
   may leave obsolete nodes and relationships, as in the official loader.

Each setting has visible help describing its effect and tradeoffs. Production exposes
SPIRES, including optional related provision text. EDC/RP1/no-context/full-corpus arms
and their unrelated tuning controls belong to evaluation and are not exposed here.

## New corpora

Paste or upload source text and choose a unique name and graph prefix. Supply an
existing structural profile for free validation, or estimate then purchase profile
induction. The adapter invokes `induce_structure.py` with explicit UI-owned output
and config paths. Review the resulting YAML, then run a build preflight. Induction
does not extract norms or load a graph. Provision patterns are not restricted to N.M.

Original configurations are read-only. New configs live in `data/corpora/`. Build
workspaces contain copies of source, profile, configuration and reusable extractions
under `data/workspaces/`. A source fingerprint blocks reuse after source/profile/schema
changes; add a revised instrument as a new corpus with a unique prefix. Imported
pipeline artifacts have no upstream provenance hashes, so reuse alone is not proof
of semantic correctness. Identifier inconsistencies are reported during preflight
and prevent loading, without silently changing the source artifacts.

Earlier website-uploaded text/JSON files remain on disk. They can be added through
the new corpus flow with a validated structural profile. Earlier scenario runs are
imported into history on API startup.

## Adapter boundaries and known pipeline limitations

`backend/tools/workflow.py` calls the official build driver's `main()` with two
process-local adaptations: its final graph stage writes CSVs instead of automatically
loading, and exception verification runs only missing files. It also checks individual
extraction outputs because the upstream extraction command can return zero after
per-provision failures. Segmentation, cleaning, verification, reference construction,
graph building and generation remain implemented by the pipeline. These adapters
depend on the current public modules and small driver seams; integration tests cover
the cached build path.

The official Neo4j loader matches relationship endpoints by key without label
constraints. The workbench refuses loading when any new key exists under another
label family or is already ambiguous. This is a preflight guard, not a transactional
fix to the loader: do not load concurrently from another application. UI build jobs
are serialized. The original loader still owns loading and prefix-scoped wiping.
Its registry read combines original ownership with `data/registry.yaml`; registry
writes go only to that UI-owned file. External pipeline commands do not automatically
read UI-owned ownership claims.

Existing Part IIIC artifacts for `26WU(1)` and `26XC(1)` currently contain repeated
`(1)` suffixes in their stored identifiers. Preflight surfaces these mismatches;
loading through the UI is blocked until the source data is corrected separately.
CSV-only builds remain available. No original artifact is altered by this adapter.

## History and outputs

Jobs persist request/settings, timestamps, stage logs and a replay command in
`data/jobs/`. Generation preserves the existing pipeline run-record schema. The
website derives rendered context from the saved prompt instead of adding a record
field. Results show Gherkin, context, reached provisions, norm/exception counts,
estimated context tokens, actual model usage and warnings. Files can be downloaded
individually, including CSVs and the full log.

Stopping a job terminates its process tree on Windows; already-sent API calls may
still be billed. After an unexpected API restart, unfinished jobs are marked
interrupted and their outputs preserved. Check for any surviving external process
before retrying an interrupted build. Commands in **Reproduce** replay real work,
including charges or graph writes; they are not dry-run commands.

## Validation

From the pipeline directory:

```powershell
.\.venv-testgen\Scripts\python.exe -B -m unittest discover -s pipeline_ui/backend/tests -t pipeline_ui -v
```

Tests include both real provision lists and a cached official CSV build with paid
stages and Neo4j loading disabled. Other checks cover invalid configs, collisions,
artifact isolation, stale-cache rejection, batch commands and restart recovery.

From `pipeline_ui`:

```powershell
npx tsc --noEmit
npm run lint
npm run build
```
