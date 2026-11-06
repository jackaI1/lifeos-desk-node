# Revisions

I use `ED` for enclosure parts, `LIB` for reusable geometry and `REF` for packaging references. `ED-000` is the assembly. The final letter is the revision. Everything in A is a prototype.

`tools/release.ps1` records the revision, status, size and SHA-256 of each deliverable in `manifest.csv`. I keep the parts beside the assembly so its references resolve after download. I exclude SolidWorks lock files.

I review geometry and calculations on a branch. The PR carries the review record. A merge establishes a revision. I use a new folder and new filenames for the next revision and keep the old manifest. This is a small file workflow, not a claim that I deployed a PDM server.

Before another release, I regenerate the CAD, run the reopen inspection, export drawings, run the STL checks, inspect the PDF pages and refresh the manifest. I don't overwrite a released folder.
