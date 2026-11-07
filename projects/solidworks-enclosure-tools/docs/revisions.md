# Revisions

I use `ED` for enclosure parts, `LIB` for reusable geometry and `REF` for packaging references. `ED-000` is the assembly. The final letter is the revision. Everything in A is a prototype.

`tools/release.ps1` records the revision, status, size and SHA-256 of each deliverable in `manifest.csv`. I keep the parts beside the assembly so its references resolve after download. I exclude SolidWorks lock files.

I review geometry and calculations on a branch. The PR carries the review record. A merge establishes a revision. I use a new folder and new filenames for the next revision and keep the old manifest. This is a small file workflow, not a claim that I deployed a PDM server.

Before another release, I regenerate the CAD, run the reopen inspection, export drawings, run the STL checks, inspect the PDF pages and refresh the manifest. I don't overwrite a released folder.

The print checks, bracket, revision B sensor enclosure, assembly nest, cartridge exercise and clamp exercise each have a separate hash manifest. I keep revision A unchanged. I run the new manifests with:

    python tools/manifest.py

I use the write option only after generating and inspecting a new set of prototype deliverables:

    python tools/manifest.py --write

The generation scripts refuse output folders with a release manifest. I generate into a scratch folder to change a design. The clamp readback script also uses scratch because it saves the rebuilt native references. The pure Python checks and reports do not require SolidWorks. A manifest records file integrity, not physical validation.
