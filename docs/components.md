# Keeping the board's parts list useful

I built a purchasing record for the desk-node board because a part number in a schematic did not tell me what I could replace, what might disappear from sale, or which material declarations I still needed.

The list comes from the actual KiCad schematic, the circuit drawing in `hardware/desk-node.kicad_sch`. A bill of materials (BOM) is the list of parts needed to build it. This revision has 31 fitted components and 19 distinct purchasing parts. The two buttons use the same switch, so they share one purchasing record while keeping both drawing references.

## Make a package without a server

Install Python 3.11 or newer and KiCad 8's command-line tools. On macOS I use `brew install kicad`; on Ubuntu I can use the KiCad 8 Docker image as the workflow does. From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r hardware/components/requirements.txt
.venv/bin/python -m hardware.components --boards 10
```

Open `hardware/build/components/desk-node-cm.xlsx`. Change the yellow board count on its Build sheet to calculate another batch in Excel or LibreOffice. Quantities exclude spares and assembly losses. The package also contains the original exported BOM, real board placement coordinates in millimetres, a readable risk report, machine-readable records and a manifest of input checksums. A checksum identifies the exact file contents used for this package.

The [saved review report](../hardware/components/review/risk.md) and [example Excel package](../hardware/components/review/desk-node-cm.xlsx) let me inspect this revision without installing anything. I regenerate them after catalogue or circuit changes. These are engineering review files, not a released manufacturing order. I also run the [fabrication export](../hardware/README.md#build-or-order-a-board) for Gerbers, drill files, the assembler-specific placement file and electrical/layout checks. A manufacturer still needs that fabrication package and its own rotation/footprint preview.

## Try the actual parts database

InvenTree is an open-source parts manager. Docker packages it and its dependencies so I can use the same version locally and in the automated checks. With Docker and Compose installed and running:

```sh
.venv/bin/python -m hardware.components.demo --boards 10
```

The command starts an isolated InvenTree **1.6.2** container with its image digest pinned, loads the board through its REST API (the requests programs use to exchange records), reads the values back, and repeats the load. It prints the component, BOM-line, parameter and verification counts. `hardware/build/components/api-verification.json` records the result. The database is SQLite, a local file inside the container volume; a single worker and memory limit keep this small demonstration bounded. This is a single-user local sandbox rather than a production inventory deployment.

The command generates random temporary credentials in memory, publishes an automatically selected port on `127.0.0.1` only, and removes its own containers and volume on success or failure. It prints and records ownership, container PID/start time, port and cleanup information in `resources.json`. It checks Docker's container and volume metadata after cleanup. Ctrl-C also runs cleanup. A machine shutdown or forced process kill can prevent any program's cleanup, so the project name in that file identifies the exact resources to remove with `docker compose -f hardware/components/compose.yaml -p PROJECT down --volumes --remove-orphans`; supply new temporary `DESK_PARTS_PASSWORD` and `DESK_PARTS_SECRET` values if running Compose manually. Do not run this cleanup against a different project.

To choose a Docker context without changing another project's default, prefix the command with `DOCKER_CONTEXT=your-context`. The runner does not start or stop Docker Desktop or a shared virtual machine.

## What I store

- `catalog.json` preserves each schematic MPN and separately records the manufacturer and exact orderable part number, electrical specifications, datasheet, supplier SKU and candidate alternates.
- `templates.json` defines comparison rules and specification fields by component family. All ten families have fire/smoke/toxicity and shock/vibration requirement fields. Both are explicitly **not specified** for this stationary indoor prototype. That is an open qualification requirement, not a passed test or certification.
- `core.py` rejects duplicate references, quantity mismatches, ranged references, missing identities, conflicting footprints and catalogue drift. A new or removed fitted part requires a reviewed catalogue update.
- An internal part number such as `DN-RES-RES-10K` identifies my reviewed 10 kOhm resistor record. `DN` means desk node, `RES` is its family, and `RES-10K` is the permanent catalogue key. Changing a schematic reference does not change the number. Changing the purchasing specification needs a new key; I do not reuse an old number for a different part.
- `inventree.py` creates the board assembly, its native BOM lines and reference labels, family categories, primary manufacturer parts, supplier parts and individual specification/evidence parameters. It writes the complete family template alongside each baseline part. InvenTree limits parameter values to 500 characters, so longer source notes and template JSON continue as JSON string fragments in numbered fields; decoding and concatenating them restores the full value. This also preserves whitespace that the API otherwise trims. No text is truncated.

The baseline manufacturer list records the design's selected parts; it does not imply that the board has passed qualification. Alternate candidates are separate, inactive parts linked using InvenTree's native related-part records. I deliberately do not create approved BOM substitutes or supplier offers for candidates. InvenTree requires its purchaseable type flag to attach a manufacturer record, so that flag is present while the part remains inactive and explicitly unqualified. The REST client exchanges its temporary login for an in-memory API token before the load. The nine candidates have parameter screening rules and manufacturer datasheet links. The seven candidates from other manufacturers reduce the search work but do not remove a qualification hold. A second distributor selling the same manufacturer's part does not fix a single-manufacturer risk.

The loader matches records by exact identity and refuses ambiguous existing duplicates. It stores a fingerprint of the entire catalogue, family templates and BOM before loading parts. A changed catalogue or BOM is refused before mutations in an existing sandbox; I run a fresh sandbox to review a new revision. Two loads must preserve record IDs and counts. It reads every stored specification, evidence field, supplier mapping and BOM quantity back through the API. It is scoped to a fresh desk-node sandbox; it does not silently delete obsolete records from an established inventory. Unexpected old assembly lines fail verification so I can review them.

## Reading the evidence and the risk score

RoHS restricts certain hazardous substances in electrical equipment. REACH covers chemical substances and includes a changing candidate list of substances of very high concern. A supplier badge does not establish either claim for my exact part.

Every primary and candidate has a lifecycle, RoHS and REACH record, with a status, manufacturer source, document date, review date, scope and limitations. Missing or undated declarations remain `unverified`. A review date is not a declaration date. A verified historical declaration also does not establish compliance with future changes to a substance list. The Espressif record retains its lead exemption and 253-substance list scope; the Sensirion record retains its dated declaration's limits. I still need to review current applicable requirements before release.

I found dated manufacturer evidence for three primary RoHS records and two REACH records. Most declarations are still unverified. Samsung's live page reports the original 22 uF capacitor as NRND, meaning not recommended for new designs. Because that page has no fixed publication date, I retain `reported_status: nrnd` while leaving its dated lifecycle claim unverified. The risk report still raises it to the top. Its recommended Samsung replacement remains a candidate and does not create another manufacturer source. The [evidence notes](../hardware/components/evidence-notes.md) explain the source boundaries and electrical details.

The score ranks **review priority**, not the probability of failure or a predicted end-of-life date. It adds lifecycle concern (EOL 50, NRND 35, unverified 20, active 0), missing dated lifecycle evidence (10), manufacturer concentration (25 without an independent candidate, 10 with one), and unresolved RoHS/REACH evidence (5 each), capped at 100. A reported NRND/EOL warning keeps its higher weight even when the dated evidence is unverified. The report states the reasons for every part. Noncompliance is an explicit hold regardless of score. Prices, live stock, last-buy dates and lead times are not inferred.

## Update and check it

I edit the reviewed catalogue when I obtain a declaration or consider a replacement. I preserve the source's actual date and scope, record exemptions, and explain missing alternates. A candidate must match the family rules: for example, the same resistor value and package, no worse tolerance and at least the original power rating. Capacitors also need the same dielectric and adequate voltage. These checks do not prove bias capacitance, regulator stability, mechanical fit, reflow compatibility, shock resistance or sensor accuracy on my assembled board.

```sh
.venv/bin/python -m pip install pytest==8.3.5
.venv/bin/python -m pytest hardware/components/tests -q
.venv/bin/python -m hardware.components.demo --boards 10
```

The component workflow exports the actual schematic BOM and PCB placements using KiCad 8 in Docker, runs the parser, numbering, alternate, missing-evidence and workbook tests, then loads the pinned real InvenTree image twice. The package, risk report, checksums and API verification are downloadable from the `desk-node-component-package` artifact in [component CI](https://github.com/jackaI1/lifeos-desk-node/actions/workflows/components.yml). No external account or LifeOS data is required.

For a host without KiCad installed, I can supply actual CSV exports with `--bom path/to/bom.csv --placements path/to/placements.csv`, as CI does. These inputs must come from the same board revision; the runner still enforces catalogue identities and quantities. The manifest includes both design-file hashes and the exported BOM hash. The existing board, firmware, replay, capture, control and analysis checks remain separate and continue to run.
