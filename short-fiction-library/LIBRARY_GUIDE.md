# Short Fiction Library

This is a directory of the individual works inside your EPUB collection. It includes short stories as well as clearly labeled novellas, frame tales, prose poems, dramatic works, literary sketches, and children’s novellas.

## Read online

Open **https://sadke8465.github.io/short-fiction-library/** on your phone or any other device. The published website and all included story texts are public.

## Open the library

Double-click **Open Short Fiction Library.command**. Your browser will open automatically. Keep the small Terminal window open while using the library; closing it stops the local site.

The launcher opens the local copy on this Mac. The GitHub Pages copy is published separately whenever changes are pushed to the repository.

## What is included

- Searchable and filterable metadata for every extracted work
- The full readable text, including available illustrations, tables, formulas, and story notes
- A downloadable CSV with both story-level and inherited collection metadata
- Clear labels for metadata inherited from the containing collection
- Provenance, extraction method, source location, and content/source hashes for auditing

The original EPUBs are never edited. `Cranford` is deliberately excluded because its files are chapters of one novel rather than individual stories.

## Refresh after changing the source library

Keep the EPUB files and `public_domain_short_story_sources.csv` in the folder immediately above this project. Double-click **Refresh Story Catalog.command**, then reopen or refresh the site.

Each EPUB currently matches a Standard Ebooks repository URL in the source CSV. A newly added EPUB needs a matching repository URL in that CSV before it can be included.

## Metadata scope

Story titles, forms, word counts, reading times, and source locations come from the individual work in the EPUB. Publication era, origin, style/genre, tone, content notes, and public-domain rationale come from the matched collection row in the supplied CSV and are labeled as inherited. Translator credits come from the EPUB’s collection-level metadata; where a collection has several translators, no unsupported story-level assignment is made.
