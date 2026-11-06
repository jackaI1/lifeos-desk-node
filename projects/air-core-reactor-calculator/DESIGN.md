# Calculator interface

The page is a local calculation record, intended for occasional geometry checks. I chose a quiet paper background, dark green controls and copper result rules to keep input dimensions separate from calculated values. This is an implementation choice based on the requested small Flask form, not a claimed user preference.

The two desktop columns place geometry beside a comparison table. Mobile stacks the same content in reading order. Headings use Georgia; input labels and prose use the system sans-serif. Measurements use tabular numerals. There are no remote fonts, images, scripts or tracking requests.

Tokens live in `reactor/static/style.css`: paper `#f8f7f2`, ink `#222d2a`, secondary text `#4b5e57`, green `#234f41`, copper `#904a28`, and rule `#c8d0c7`. All form inputs have visible labels and units; the error region retains submitted values. A skip link reaches the results. Circuit settings sit in a native disclosure control so the geometry stays easy to scan.

The comparison table, formula explanations, physical flags and circuit assumptions must remain visible as ordinary text. No single number should imply a tested hardware rating.
