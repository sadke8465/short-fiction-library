#!/usr/bin/env python3
"""Build the private story catalog and sanitized reader files from local EPUBs."""

from __future__ import annotations

import csv
import hashlib
import html
import json
import math
import os
import posixpath
import re
import shutil
import unicodedata
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import quote, unquote, urlsplit
import xml.etree.ElementTree as ET


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT.parent
PUBLIC_ROOT = PROJECT_ROOT / "public"
DATA_DIR = PUBLIC_ROOT / "data"
READER_DIR = PUBLIC_ROOT / "reader"
CONTENT_DIR = PUBLIC_ROOT / "content"
SUPPORT_DIR = PUBLIC_ROOT / "support"
SOURCE_CSV = SOURCE_ROOT / "public_domain_short_story_sources.csv"
ROOT_CSV = PROJECT_ROOT / "stories.csv"
REPORT_FILE = PROJECT_ROOT / "library-report.json"

EPUB_NS = "http://www.idpf.org/2007/ops"
XHTML_NS = "http://www.w3.org/1999/xhtml"
OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NS = {"x": XHTML_NS, "opf": OPF_NS, "dc": DC_NS}

TYPE_ATTR = f"{{{EPUB_NS}}}type"
XML_LANG_ATTR = f"{{{XML_NS}}}lang"
WORK_TOKENS = {"se:short-story", "se:novella", "z3998:poem", "z3998:drama"}
EXTRACTION_VERSION = "1.0"
SKIP_TAGS = {"script", "style", "link", "meta", "title"}
ALLOWED_TAGS = {
    "article", "section", "div", "header", "footer", "hgroup",
    "h1", "h2", "h3", "h4", "h5", "h6", "p", "span", "br", "hr",
    "em", "i", "strong", "b", "small", "sub", "sup", "q", "cite", "abbr", "time", "a",
    "blockquote", "pre", "code", "ul", "ol", "li", "dl", "dt", "dd",
    "figure", "figcaption", "img", "picture", "source",
    "table", "caption", "thead", "tbody", "tfoot", "tr", "th", "td",
    "math", "mrow", "mi", "mn", "mo", "mfrac", "msqrt", "mroot",
    "msup", "msub", "msubsup", "munder", "mover", "munderover",
    "mtable", "mtr", "mtd", "mtext", "semantics", "annotation",
}
VOID_TAGS = {"br", "hr", "img", "source"}
WORD_RE = re.compile(r"\b[\w’'-]+\b", re.UNICODE)


@dataclass
class Document:
    rel_path: str
    zip_path: str
    root: ET.Element
    body: ET.Element
    head_title: str
    spine_index: int


def local_name(tag: str) -> str:
    return tag.split("}")[-1]


def type_tokens(element: ET.Element) -> set[str]:
    return set(element.attrib.get(TYPE_ATTR, "").split())


def clean_text(value: str | None) -> str:
    return " ".join((value or "").split())


def text_without_notes(element: ET.Element) -> str:
    parts: list[str] = []

    def visit(node: ET.Element) -> None:
        if "noteref" in type_tokens(node):
            return
        if node.text:
            parts.append(node.text)
        for child in node:
            visit(child)
            if child.tail:
                parts.append(child.tail)

    visit(element)
    return clean_text("".join(parts))


def slugify(value: str, limit: int = 70) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value).strip("-").lower()
    return (slug or "work")[:limit].rstrip("-")


def stable_story_id(book_slug: str, key: str, title: str) -> str:
    digest = hashlib.sha1(f"{book_slug}|{key}".encode()).hexdigest()[:10]
    return f"{slugify(book_slug, 38)}--{slugify(title, 54)}--{digest}"


def normalized_title(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.sub(r"[^\w]+", " ", value, flags=re.UNICODE).split())


def safe_generated_dir(path: Path) -> None:
    resolved = path.resolve()
    public = PUBLIC_ROOT.resolve()
    if public not in resolved.parents:
        raise RuntimeError(f"Refusing to replace unexpected directory: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True, exist_ok=True)


def parse_source_catalog() -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    with SOURCE_CSV.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    by_slug: dict[str, dict[str, str]] = {}
    pattern = re.compile(r"https://github\.com/standardebooks/([^\s|,]+)")
    for row in rows:
        for match in pattern.finditer(row.get("standard_ebooks_repo_verified", "")):
            by_slug[match.group(1).rstrip("/")] = row
    return rows, by_slug


def find_rootfile(archive: zipfile.ZipFile) -> str:
    container = ET.fromstring(archive.read("META-INF/container.xml"))
    rootfile = container.find(".//{*}rootfile")
    if rootfile is None or not rootfile.attrib.get("full-path"):
        raise ValueError("EPUB container has no package path")
    return rootfile.attrib["full-path"]


def metadata_texts(opf: ET.Element, qname: str) -> list[str]:
    return [clean_text(element.text) for element in opf.findall(f".//{qname}", NS) if clean_text(element.text)]


def parse_opf(archive: zipfile.ZipFile, rootfile: str) -> dict:
    opf = ET.fromstring(archive.read(rootfile))
    base = posixpath.dirname(rootfile)
    metadata = opf.find("opf:metadata", NS)
    if metadata is None:
        raise ValueError("EPUB package has no metadata")

    titles = {element.attrib.get("id", ""): clean_text(element.text) for element in metadata.findall("dc:title", NS)}
    title = titles.get("title") or next(iter(titles.values()), "Untitled")
    subtitle = titles.get("subtitle", "")
    creators = metadata_texts(metadata, "dc:creator")
    language = next(iter(metadata_texts(metadata, "dc:language")), "")
    identifier = next(iter(metadata_texts(metadata, "dc:identifier")), "")
    publisher = next(iter(metadata_texts(metadata, "dc:publisher")), "")
    dates = metadata_texts(metadata, "dc:date")
    rights = metadata_texts(metadata, "dc:rights")
    sources = metadata_texts(metadata, "dc:source")
    subjects = metadata_texts(metadata, "dc:subject")
    description = next(iter(metadata_texts(metadata, "dc:description")), "")

    contributors = {
        element.attrib.get("id", ""): clean_text(element.text)
        for element in metadata.findall("dc:contributor", NS)
        if clean_text(element.text)
    }
    roles: dict[str, list[str]] = defaultdict(list)
    props: dict[str, list[str]] = defaultdict(list)
    for meta in metadata.findall("opf:meta", NS):
        prop = meta.attrib.get("property", "")
        value = clean_text("".join(meta.itertext()))
        if prop == "role":
            person = contributors.get(meta.attrib.get("refines", "").lstrip("#"), "")
            if person and value and person not in roles[value]:
                roles[value].append(person)
        elif prop and value:
            props[prop].append(value)

    repo_url = ""
    for link in metadata.findall("opf:link", NS):
        if link.attrib.get("rel") == "schema:codeRepository":
            repo_url = link.attrib.get("href", "")
            break

    manifest: dict[str, dict[str, str]] = {}
    nav_href = ""
    for item in opf.findall("opf:manifest/opf:item", NS):
        item_id = item.attrib.get("id", "")
        manifest[item_id] = dict(item.attrib)
        if "nav" in item.attrib.get("properties", "").split():
            nav_href = item.attrib.get("href", "")

    spine: list[str] = []
    for itemref in opf.findall("opf:spine/opf:itemref", NS):
        item = manifest.get(itemref.attrib.get("idref", ""), {})
        href = item.get("href", "")
        if href and item.get("media-type") in {"application/xhtml+xml", "text/html"}:
            spine.append(posixpath.normpath(href))

    return {
        "root": opf,
        "base": base,
        "title": title,
        "subtitle": subtitle,
        "creators": creators,
        "language": language,
        "identifier": identifier,
        "publisher": publisher,
        "dates": dates,
        "rights": rights,
        "sources": sources,
        "subjects": subjects,
        "description": description,
        "abstract": next(iter(props.get("schema:abstract", [])), ""),
        "word_count": next(iter(props.get("schema:wordCount", [])), ""),
        "genres": props.get("schema:genre", []),
        "modified": next(iter(props.get("dcterms:modified", [])), ""),
        "translators": roles.get("trl", []),
        "illustrators": roles.get("ill", []) + roles.get("art", []),
        "repo_url": repo_url,
        "manifest": manifest,
        "spine": spine,
        "nav_href": nav_href,
    }


def parse_documents(archive: zipfile.ZipFile, package: dict) -> dict[str, Document]:
    documents: dict[str, Document] = {}
    names = set(archive.namelist())
    for index, rel_path in enumerate(package["spine"]):
        zip_path = posixpath.normpath(posixpath.join(package["base"], rel_path))
        if zip_path not in names:
            continue
        root = ET.fromstring(archive.read(zip_path))
        body = root.find(".//x:body", NS)
        if body is None:
            continue
        head_title = clean_text(root.findtext(".//x:head/x:title", default="", namespaces=NS))
        documents[rel_path] = Document(rel_path, zip_path, root, body, head_title, index)
    return documents


def parse_toc(archive: zipfile.ZipFile, package: dict) -> tuple[dict[str, dict], list[dict]]:
    href = package.get("nav_href", "")
    if not href:
        return {}, []
    zip_path = posixpath.normpath(posixpath.join(package["base"], href))
    toc = ET.fromstring(archive.read(zip_path))
    nav = next((n for n in toc.findall(".//x:nav", NS) if "toc" in type_tokens(n)), None)
    if nav is None:
        return {}, []
    root_ol = nav.find("x:ol", NS)
    if root_ol is None:
        return {}, []

    lookup: dict[str, dict] = {}
    ordered: list[dict] = []
    nav_dir = posixpath.dirname(href)

    def walk(ol: ET.Element, ancestors: list[str]) -> None:
        for li in ol.findall("x:li", NS):
            anchor = li.find("x:a", NS)
            label_node = anchor if anchor is not None else li.find("x:span", NS)
            label = text_without_notes(label_node) if label_node is not None else ""
            next_ancestors = ancestors + ([label] if label else [])
            if anchor is not None and anchor.attrib.get("href"):
                raw = unquote(anchor.attrib["href"])
                parts = urlsplit(raw)
                rel = posixpath.normpath(posixpath.join(nav_dir, parts.path)) if parts.path else ""
                key = rel + (f"#{parts.fragment}" if parts.fragment else "")
                entry = {"href": key, "path": next_ancestors, "label": label, "order": len(ordered) + 1}
                lookup[key] = entry
                ordered.append(entry)
            child = li.find("x:ol", NS)
            if child is not None:
                walk(child, next_ancestors)

    walk(root_ol, [])
    return lookup, ordered


def find_by_id(document: Document, element_id: str) -> ET.Element | None:
    return next((element for element in document.root.iter() if element.attrib.get("id") == element_id), None)


def main_content_element(document: Document) -> ET.Element:
    for child in document.body:
        if local_name(child.tag) in {"article", "section", "div"}:
            return child
    return document.body


def own_scope_nodes(element: ET.Element) -> Iterable[ET.Element]:
    """Yield a work's own descendants without crossing into nested work sections."""
    yield element

    def walk(node: ET.Element) -> Iterable[ET.Element]:
        for child in node:
            if local_name(child.tag) in {"article", "section"}:
                continue
            yield child
            yield from walk(child)

    yield from walk(element)


def title_for_element(element: ET.Element) -> str:
    preferred: list[ET.Element] = []
    fallback: list[ET.Element] = []
    for node in own_scope_nodes(element):
        tag = local_name(node.tag)
        tokens = type_tokens(node)
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6", "p"} and "title" in tokens:
            preferred.append(node)
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            fallback.append(node)
    for node in preferred + fallback:
        value = text_without_notes(node)
        if value:
            return value
    return ""


def subtitle_for_element(element: ET.Element) -> str:
    for node in own_scope_nodes(element):
        if "subtitle" in type_tokens(node):
            value = text_without_notes(node)
            if value:
                return value
    return ""


def synopsis_for_element(element: ET.Element) -> str:
    for node in element.iter():
        if "se:bridgehead" in type_tokens(node):
            value = text_without_notes(node)
            if value:
                return value
    return ""


def toc_entry_for(rel_path: str, element_id: str, toc_lookup: dict[str, dict]) -> dict:
    exact = f"{rel_path}#{element_id}" if element_id else rel_path
    if exact in toc_lookup:
        return toc_lookup[exact]
    if rel_path in toc_lookup:
        return toc_lookup[rel_path]
    matches = [entry for key, entry in toc_lookup.items() if key.split("#", 1)[0] == rel_path]
    return matches[0] if matches else {"path": [], "label": "", "order": 10**9}


def semantic_form(tokens: set[str], catalog_row: dict[str, str], element: ET.Element) -> tuple[str, str]:
    if "se:novella" in tokens:
        return "Novella", ""
    if "se:short-story" in tokens:
        return "Short story", ""
    if "z3998:drama" in tokens:
        return "Drama", ""
    if "z3998:poem" in tokens:
        has_verse = any("z3998:verse" in type_tokens(node) for node in element.iter())
        return ("Poem", "") if has_verse else ("Prose poem", "")
    return "Short story", ""


def make_candidate(
    book_slug: str,
    documents: dict[str, Document],
    parts: list[tuple[str, ET.Element]],
    toc_lookup: dict[str, dict],
    catalog_row: dict[str, str],
    *,
    title: str = "",
    form: str = "",
    form_detail: str = "",
    synopsis: str = "",
    method: str = "semantic markup",
    manual_key: str = "",
) -> dict:
    first_rel, first_element = parts[0]
    first_document = documents[first_rel]
    element_id = first_element.attrib.get("id", "")
    toc = toc_entry_for(first_rel, element_id, toc_lookup)
    actual_title = title or title_for_element(first_element) or toc.get("label", "") or first_document.head_title or "Untitled"
    tokens = type_tokens(first_element)
    if not form:
        form, inferred_detail = semantic_form(tokens, catalog_row, first_element)
        form_detail = form_detail or inferred_detail
    if not form_detail and catalog_row.get("category") == "Folklore & myth":
        form_detail = "Folktale / myth · inherited collection label"
    key = manual_key or "+".join(f"{rel}#{element.attrib.get('id', '')}" for rel, element in parts)
    candidate_id = stable_story_id(book_slug, key, actual_title)
    return {
        "id": candidate_id,
        "title": actual_title,
        "subtitle": subtitle_for_element(first_element),
        "synopsis": synopsis or synopsis_for_element(first_element),
        "form": form,
        "form_detail": form_detail,
        "parts": parts,
        "first_rel": first_rel,
        "element_id": element_id,
        "toc_path": toc.get("path", []),
        "toc_order": toc.get("order", 10**9),
        "spine_order": first_document.spine_index,
        "method": method,
    }


def secondary_forms_for(element: ET.Element, primary_form: str) -> str:
    tokens = type_tokens(element)
    labels: list[str] = []
    mapping = {
        "z3998:drama": "Drama",
        "z3998:scene": "Scene",
        "z3998:poem": "Poem",
        "z3998:letter": "Letter",
        "z3998:diary": "Diary",
    }
    for token, label in mapping.items():
        if token in tokens and label.casefold() not in primary_form.casefold():
            labels.append(label)
    return " | ".join(labels)


def explicit_candidates(
    book_slug: str,
    documents: dict[str, Document],
    toc_lookup: dict[str, dict],
    catalog_row: dict[str, str],
) -> list[dict]:
    candidates: list[dict] = []
    for rel_path, document in documents.items():
        parent = {child: node for node in document.root.iter() for child in node}
        for element in document.root.iter():
            if local_name(element.tag) not in {"article", "section"}:
                continue
            tokens = type_tokens(element)
            if not tokens.intersection(WORK_TOKENS):
                continue
            ancestor = parent.get(element)
            nested_in_work = False
            while ancestor is not None:
                if local_name(ancestor.tag) in {"article", "section"} and type_tokens(ancestor).intersection(WORK_TOKENS):
                    nested_in_work = True
                    break
                ancestor = parent.get(ancestor)
            if nested_in_work:
                continue
            candidates.append(make_candidate(book_slug, documents, [(rel_path, element)], toc_lookup, catalog_row))
    return candidates


def supplemental_candidates(
    book_slug: str,
    documents: dict[str, Document],
    toc_lookup: dict[str, dict],
    catalog_row: dict[str, str],
) -> list[dict]:
    """Known source-markup omissions that should not broaden the global rules."""
    works: list[dict] = []
    if book_slug == "dashiell-hammett_continental-op-stories":
        rel = "text/the-tenth-clue.xhtml"
        element = find_by_id(documents[rel], "the-tenth-clue")
        if element is None:
            raise ValueError("Missing the supplemental work The Tenth Clue")
        works.append(make_candidate(
            book_slug, documents, [(rel, element)], toc_lookup, catalog_row,
            title="The Tenth Clue", form="Short story", form_detail="Continental Op",
            method="curated markup correction", manual_key="the-tenth-clue",
        ))
    elif book_slug == "gustave-flaubert_short-fiction_m-walter-dunne":
        rel = "text/the-dance-of-death.xhtml"
        element = find_by_id(documents[rel], "the-dance-of-death")
        if element is None:
            raise ValueError("Missing the supplemental work The Dance of Death")
        works.append(make_candidate(
            book_slug, documents, [(rel, element)], toc_lookup, catalog_row,
            title="The Dance of Death", form="Dramatic scene", form_detail="Prose drama",
            method="curated markup correction", manual_key="the-dance-of-death",
        ))
    return works


def document_by_number(documents: dict[str, Document], number: int) -> tuple[str, ET.Element]:
    rel = f"text/chapter-{number}.xhtml"
    document = documents[rel]
    return rel, main_content_element(document)


def bodymatter_documents(documents: dict[str, Document]) -> list[tuple[str, Document]]:
    result = []
    for rel, document in documents.items():
        if "bodymatter" in type_tokens(document.body):
            result.append((rel, document))
    return sorted(result, key=lambda item: item[1].spine_index)


def manual_candidates(
    book_slug: str,
    documents: dict[str, Document],
    toc_lookup: dict[str, dict],
    catalog_row: dict[str, str],
) -> tuple[list[dict], list[dict]]:
    works: list[dict] = []
    exclusions: list[dict] = []

    def add(parts: list[tuple[str, ET.Element]], **kwargs) -> None:
        works.append(make_candidate(book_slug, documents, parts, toc_lookup, catalog_row, method="curated structural rule", **kwargs))

    if book_slug == "baroness-orczy_the-old-man-in-the-corner":
        groups = [
            (1, 3, "The Fenchurch Street Mystery"),
            (4, 6, "The Robbery in Phillimore Terrace"),
            (7, 9, "The York Mystery"),
            (10, 11, "The Mysterious Death on the Underground Railway"),
            (12, 13, "The Liverpool Mystery"),
            (14, 17, "The Edinburgh Mystery"),
            (18, 20, "The Theft at the English Provident Bank"),
            (21, 23, "The Dublin Mystery"),
            (24, 27, "An Unparalleled Outrage"),
            (28, 30, "The Regent’s Park Murder"),
            (31, 33, "The de Genneville Peerage"),
            (34, 36, "The Mysterious Death in Percy Street"),
        ]
        for start, end, title in groups:
            add([document_by_number(documents, n) for n in range(start, end + 1)], title=title, form="Short story", form_detail="Linked mystery", manual_key=f"chapters-{start}-{end}")

    elif book_slug == "elizabeth-gaskell_cranford":
        exclusions.append({
            "book_slug": book_slug,
            "title": "Cranford",
            "reason": "A single novel presented in chapters; chapters were not promoted to stories.",
            "word_count": 70911,
        })

    elif book_slug == "ernest-bramah_kai-lungs-golden-hours":
        for chapter in [2, 3, 4, 5, 6, 7, 8, 9, 10, 12]:
            rel = f"text/chapter-{chapter}.xhtml"
            element = find_by_id(documents[rel], f"chapter-{chapter}-1")
            if element is None:
                raise ValueError(f"Missing embedded tale chapter-{chapter}-1")
            add([(rel, element)], form="Frame tale", form_detail="Kai Lung tale", manual_key=f"chapter-{chapter}-1")

    elif book_slug == "gertrude-stein_three-lives":
        anna_parts = []
        for rel in ["text/the-good-anna.xhtml", "text/the-good-anna-1.xhtml", "text/the-good-anna-2.xhtml", "text/the-good-anna-3.xhtml"]:
            anna_parts.append((rel, main_content_element(documents[rel])))
        add(anna_parts, title="The Good Anna", form="Novella", form_detail="Portrait", manual_key="the-good-anna-complete")
        for rel, title in [("text/melanctha.xhtml", "Melanctha"), ("text/the-gentle-lena.xhtml", "The Gentle Lena")]:
            add([(rel, main_content_element(documents[rel]))], title=title, form="Novella", form_detail="Portrait", manual_key=title)

    elif book_slug == "giovanni-boccaccio_the-decameron_john-payne":
        for day in range(1, 11):
            for number in range(1, 11):
                rel = f"text/day-{day}-{number}.xhtml"
                element = main_content_element(documents[rel])
                add([(rel, element)], title=f"Day {day}, Story {number}", form="Frame tale", form_detail=f"Day {day}", synopsis=synopsis_for_element(element), manual_key=f"day-{day}-{number}")

    elif book_slug == "lord-dunsany_the-gods-of-pegana":
        for rel, document in bodymatter_documents(documents):
            element = main_content_element(document)
            if "chapter" in type_tokens(element):
                add([(rel, element)], form="Prose poem", form_detail="Mythic vignette", manual_key=rel)

    elif book_slug == "rudyard-kipling_the-jungle-book":
        mowgli = {"mowglis-brothers.xhtml", "kaas-hunting.xhtml", "tiger-tiger.xhtml"}
        for rel, document in bodymatter_documents(documents):
            detail = "Animal tale · Mowgli" if posixpath.basename(rel) in mowgli else "Animal tale"
            add([(rel, main_content_element(document))], form="Short story", form_detail=detail, manual_key=rel)

    elif book_slug == "sarah-orne-jewett_the-country-of-the-pointed-firs":
        parts = [document_by_number(documents, number) for number in range(1, 22)]
        add(parts, title="The Country of the Pointed Firs", form="Novella", form_detail="Linked-story sequence", manual_key="complete-novella")

    elif book_slug == "stephen-leacock_sunshine-sketches-of-a-little-town":
        for number in range(1, 13):
            rel, element = document_by_number(documents, number)
            add([(rel, element)], form="Literary sketch", form_detail="Mariposa cycle", manual_key=f"chapter-{number}")

    elif book_slug in {"thornton-w-burgess_green-forest-stories", "thornton-w-burgess_green-meadow-stories"}:
        for rel, document in bodymatter_documents(documents):
            element = main_content_element(document)
            if "division" in type_tokens(element):
                add([(rel, element)], form="Children’s novella", form_detail="Animal tale", manual_key=rel)

    elif book_slug == "w-somerset-maugham_ashenden":
        chapters = bodymatter_documents(documents)
        groups = [
            (1, 3, "Miss King"),
            (4, 6, "The Hairless Mexican"),
            (7, 8, "Giulia Lazzari"),
            (9, 10, "The Traitor"),
            (11, 13, "His Excellency"),
            (14, 16, "Mr. Harrington’s Washing"),
        ]
        for start, end, title in groups:
            parts = [(rel, main_content_element(document)) for rel, document in chapters[start - 1:end]]
            add(parts, title=title, form="Short story", form_detail="Ashenden cycle", manual_key=f"chapters-{start}-{end}")

    return works, exclusions


def readable_text(element: ET.Element) -> str:
    parts: list[str] = []

    def visit(node: ET.Element) -> None:
        tokens = type_tokens(node)
        if tokens.intersection({"noteref", "title", "subtitle"}):
            return
        if node.text:
            parts.append(node.text)
        for child in node:
            visit(child)
            if child.tail:
                parts.append(child.tail)

    visit(element)
    value = "".join(parts).replace("\u2060", "").replace("\u00ad", "")
    return clean_text(value)


def element_word_count(parts: list[tuple[str, ET.Element]]) -> int:
    return sum(len(WORD_RE.findall(readable_text(element))) for _, element in parts)


def element_content_hash(parts: list[tuple[str, ET.Element]]) -> str:
    text = "\n".join(readable_text(element) for _, element in parts)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def referenced_note_elements(parts: list[tuple[str, ET.Element]], notes_by_id: dict[str, tuple[str, ET.Element]]) -> list[ET.Element]:
    queue: list[str] = []
    seen: set[str] = set()
    for _, element in parts:
        for anchor in element.iter():
            if local_name(anchor.tag) != "a":
                continue
            fragment = urlsplit(anchor.attrib.get("href", "")).fragment
            if fragment in notes_by_id and fragment not in seen:
                queue.append(fragment)
                seen.add(fragment)
    result: list[ET.Element] = []
    while queue:
        note_id = queue.pop(0)
        _, note = notes_by_id[note_id]
        result.append(note)
        for anchor in note.iter():
            if local_name(anchor.tag) != "a":
                continue
            fragment = urlsplit(anchor.attrib.get("href", "")).fragment
            if fragment in notes_by_id and fragment not in seen:
                queue.append(fragment)
                seen.add(fragment)
    return result


def normalize_zip_target(current_rel: str, raw_path: str) -> str:
    decoded = unquote(raw_path)
    target = posixpath.normpath(posixpath.join(posixpath.dirname(current_rel), decoded))
    if target.startswith("../") or target.startswith("/"):
        return ""
    return target


def sanitize_svg(data: bytes) -> bytes:
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return b""
    parent_map = {child: parent for parent in root.iter() for child in parent}
    for element in list(root.iter()):
        if local_name(element.tag).lower() in {"script", "foreignobject"}:
            parent = parent_map.get(element)
            if parent is not None:
                parent.remove(element)
            continue
        for attr in list(element.attrib):
            name = local_name(attr).lower()
            value = element.attrib[attr].strip().lower()
            if name.startswith("on") or (name in {"href", "xlink:href"} and value.startswith(("javascript:", "data:text/html"))):
                del element.attrib[attr]
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def copy_asset(archive: zipfile.ZipFile, package: dict, book_slug: str, rel_path: str, copied: set[str]) -> str:
    if not rel_path or rel_path in copied:
        return f"/content/{quote(book_slug)}/{quote(rel_path, safe='/')}" if rel_path else ""
    zip_path = posixpath.normpath(posixpath.join(package["base"], rel_path))
    if zip_path not in set(archive.namelist()):
        return ""
    destination = CONTENT_DIR / book_slug / Path(rel_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = archive.read(zip_path)
    if destination.suffix.lower() == ".svg":
        data = sanitize_svg(data)
        if not data:
            return ""
    destination.write_bytes(data)
    copied.add(rel_path)
    return f"/content/{quote(book_slug)}/{quote(rel_path, safe='/')}"


def note_map_for(documents: dict[str, Document]) -> dict[str, tuple[str, ET.Element]]:
    notes: dict[str, tuple[str, ET.Element]] = {}
    for rel, document in documents.items():
        for element in document.root.iter():
            element_id = element.attrib.get("id", "")
            tokens = type_tokens(element)
            if element_id and (element_id.startswith(("note-", "footnote-")) or tokens.intersection({"footnote", "endnote", "rearnote"})):
                notes[element_id] = (rel, element)
    return notes


def build_target_index(book_slug: str, candidates: list[dict]) -> dict[tuple[str, str], str]:
    targets: dict[tuple[str, str], str] = {}
    by_document: dict[str, set[str]] = defaultdict(set)
    for candidate in candidates:
        for rel, element in candidate["parts"]:
            element_id = element.attrib.get("id", "")
            if element_id:
                targets[(rel, element_id)] = candidate["id"]
            by_document[rel].add(candidate["id"])
    for rel, ids in by_document.items():
        if len(ids) == 1:
            targets[(rel, "")] = next(iter(ids))
    return targets


def render_reader_html(
    archive: zipfile.ZipFile,
    package: dict,
    book_slug: str,
    candidate: dict,
    documents: dict[str, Document],
    target_index: dict[tuple[str, str], str],
    notes_by_id: dict[str, tuple[str, ET.Element]],
    copied_assets: set[str],
    written_support: set[str],
) -> str:
    referenced_notes: list[str] = []
    seen_notes: set[str] = set()
    candidate_part_rels = {rel for rel, _ in candidate["parts"]}

    def render(element: ET.Element, current_rel: str, *, include_tail: bool = False, in_note: bool = False) -> str:
        tag = local_name(element.tag).lower()
        if tag in SKIP_TAGS:
            return html.escape(element.tail or "") if include_tail else ""

        text = html.escape(element.text or "")
        children = "".join(render(child, current_rel, include_tail=True, in_note=in_note) for child in element)
        tail = html.escape(element.tail or "") if include_tail else ""
        inner = text + children

        if tag not in ALLOWED_TAGS:
            return inner + tail

        attrs: list[str] = []
        element_id = element.attrib.get("id", "")
        if element_id:
            attrs.append(f'id="{html.escape(element_id, quote=True)}"')
        lang = element.attrib.get(XML_LANG_ATTR) or element.attrib.get("lang")
        if lang:
            attrs.append(f'lang="{html.escape(lang, quote=True)}"')

        classes: list[str] = []
        for token in type_tokens(element):
            classes.append("epub-" + re.sub(r"[^a-zA-Z0-9_-]+", "-", token).strip("-").lower())
        for token in element.attrib.get("class", "").split():
            safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", token).strip("-").lower()
            if safe:
                classes.append("source-" + safe)

        if tag == "a":
            raw_href = element.attrib.get("href", "")
            if raw_href:
                split = urlsplit(raw_href)
                if split.scheme in {"http", "https"}:
                    attrs.extend([f'href="{html.escape(raw_href, quote=True)}"', 'target="_blank"', 'rel="noopener noreferrer"'])
                    classes.append("external-link")
                elif split.path:
                    target_rel = normalize_zip_target(current_rel, split.path)
                    if split.fragment in notes_by_id:
                        attrs.append(f'href="#{html.escape(split.fragment, quote=True)}"')
                        classes.append("note-ref")
                        if split.fragment not in seen_notes:
                            referenced_notes.append(split.fragment)
                            seen_notes.add(split.fragment)
                    elif target_rel in candidate_part_rels and split.fragment:
                        attrs.append(f'href="#{html.escape(split.fragment, quote=True)}"')
                        if "backlink" in type_tokens(element) or "backlink" in element.attrib.get("class", "").split():
                            classes.append("note-backlink")
                    elif (target_rel, split.fragment) in target_index:
                        attrs.extend(['href="#"', f'data-story-id="{target_index[(target_rel, split.fragment)]}"'])
                        if split.fragment:
                            attrs.append(f'data-story-fragment="{html.escape(split.fragment, quote=True)}"')
                        classes.append("cross-story-link")
                    elif (target_rel, "") in target_index:
                        target_story_id = target_index[(target_rel, "")]
                        attrs.extend(['href="#"', f'data-story-id="{target_story_id}"'])
                        if split.fragment:
                            attrs.append(f'data-story-fragment="{html.escape(split.fragment, quote=True)}"')
                        classes.append("cross-story-link")
                    elif target_rel in documents:
                        support_name = slugify(target_rel, 100)
                        support_key = f"{book_slug}/{support_name}"
                        support_url = f"/support/{quote(book_slug)}/{quote(support_name)}.html"
                        if support_key not in written_support:
                            written_support.add(support_key)
                            support_body = render(main_content_element(documents[target_rel]), target_rel)
                            support_file = SUPPORT_DIR / book_slug / f"{support_name}.html"
                            support_file.parent.mkdir(parents=True, exist_ok=True)
                            support_file.write_text(
                                '<!doctype html><html><head><meta charset="utf-8">'
                                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                                '<title>Supporting material</title><style>'
                                'body{max-width:46rem;margin:3rem auto;padding:0 1.5rem;color:#29241f;background:#fbf7ef;font:18px/1.7 Georgia,serif}'
                                'img{max-width:100%;height:auto}a{color:#7a2835}table{max-width:100%;border-collapse:collapse}'
                                'td,th{padding:.35rem;border:1px solid #aaa}'
                                '</style></head><body>' + support_body + '</body></html>',
                                encoding="utf-8",
                            )
                        attrs.extend([f'href="{html.escape(support_url, quote=True)}"', 'target="_blank"', 'rel="noopener noreferrer"'])
                        classes.append("support-link")
                elif split.fragment:
                    if split.fragment in notes_by_id:
                        attrs.append(f'href="#{html.escape(split.fragment, quote=True)}"')
                        classes.append("note-ref")
                        if split.fragment not in seen_notes:
                            referenced_notes.append(split.fragment)
                            seen_notes.add(split.fragment)
                    elif (current_rel, split.fragment) in target_index:
                        target_story_id = target_index[(current_rel, split.fragment)]
                        attrs.extend(['href="#"', f'data-story-id="{target_story_id}"'])
                        attrs.append(f'data-story-fragment="{html.escape(split.fragment, quote=True)}"')
                        classes.append("cross-story-link")
                    else:
                        attrs.append(f'href="#{html.escape(split.fragment, quote=True)}"')
            if "noteref" in type_tokens(element):
                classes.append("note-ref")

        elif tag in {"img", "source"}:
            wrote_source = False
            raw_src = element.attrib.get("src", "")
            if raw_src:
                target_rel = normalize_zip_target(current_rel, raw_src)
                url = copy_asset(archive, package, book_slug, target_rel, copied_assets)
                if url:
                    attrs.append(f'src="{html.escape(url, quote=True)}"')
                    wrote_source = True
            raw_srcset = element.attrib.get("srcset", "")
            if raw_srcset:
                rewritten: list[str] = []
                for candidate_src in raw_srcset.split(","):
                    pieces = candidate_src.strip().split()
                    if not pieces:
                        continue
                    target_rel = normalize_zip_target(current_rel, pieces[0])
                    url = copy_asset(archive, package, book_slug, target_rel, copied_assets)
                    if url:
                        rewritten.append(" ".join([url, *pieces[1:]]))
                if rewritten:
                    attrs.append(f'srcset="{html.escape(", ".join(rewritten), quote=True)}"')
                    wrote_source = True
            if not wrote_source:
                return tail
            if tag == "img":
                attrs.append(f'alt="{html.escape(element.attrib.get("alt", ""), quote=True)}"')
                attrs.append('loading="lazy"')
            classes.append("reader-image")

        elif tag in {"th", "td"}:
            for name in ("colspan", "rowspan"):
                value = element.attrib.get(name, "")
                if value.isdigit():
                    attrs.append(f'{name}="{value}"')

        if tag == "abbr" and element.attrib.get("title"):
            attrs.append(f'title="{html.escape(element.attrib["title"], quote=True)}"')
        if tag == "time" and element.attrib.get("datetime"):
            attrs.append(f'datetime="{html.escape(element.attrib["datetime"], quote=True)}"')
        if classes:
            attrs.append(f'class="{html.escape(" ".join(dict.fromkeys(classes)), quote=True)}"')

        attr_text = (" " + " ".join(attrs)) if attrs else ""
        if tag in VOID_TAGS:
            return f"<{tag}{attr_text}>" + tail
        return f"<{tag}{attr_text}>{inner}</{tag}>" + tail

    sections: list[str] = []
    composite = len(candidate["parts"]) > 1
    for part_index, (rel, element) in enumerate(candidate["parts"]):
        rendered = render(element, rel)
        if composite:
            sections.append(f'<div class="reader-part" data-part="{part_index + 1}">{rendered}</div>')
        else:
            sections.append(rendered)

    notes_html: list[str] = []
    for note_id in referenced_notes:
        note = notes_by_id.get(note_id)
        if not note:
            continue
        rel, element = note
        notes_html.append(render(element, rel, in_note=True))
    if notes_html:
        sections.append('<section class="reader-notes"><h2>Notes</h2><ol>' + "".join(notes_html) + "</ol></section>")

    return '<div class="reader-prose">' + "".join(sections) + "</div>"


def inherited_metadata(catalog_row: dict[str, str]) -> dict[str, str]:
    return {
        "catalog_row_id": catalog_row.get("id", ""),
        "category": catalog_row.get("category", ""),
        "collection_first_published": catalog_row.get("first_published", ""),
        "era": catalog_row.get("era", ""),
        "origin": catalog_row.get("origin", ""),
        "original_language": catalog_row.get("original_language", ""),
        "style_genre": catalog_row.get("style_genre", ""),
        "tone": catalog_row.get("tone", ""),
        "typical_length_estimate": catalog_row.get("typical_length_estimate", ""),
        "source_type": catalog_row.get("source_type", ""),
        "us_pd_basis": catalog_row.get("us_pd_basis", ""),
        "content_notes": catalog_row.get("content_notes", ""),
        "blind_mode_fit": catalog_row.get("blind_mode_fit", ""),
        "test_priority": catalog_row.get("test_priority", ""),
        "why_it_fits": catalog_row.get("why_it_fits", ""),
    }


def build() -> None:
    source_rows, source_by_slug = parse_source_catalog()
    safe_generated_dir(DATA_DIR)
    safe_generated_dir(READER_DIR)
    safe_generated_dir(CONTENT_DIR)
    safe_generated_dir(SUPPORT_DIR)

    all_records: list[dict] = []
    all_exclusions: list[dict] = []
    audit_books: list[dict] = []
    missing_catalog: list[str] = []
    errors: list[dict] = []

    epub_paths = sorted(SOURCE_ROOT.glob("*.epub"))
    for epub_path in epub_paths:
        book_slug = epub_path.stem
        catalog_row = source_by_slug.get(book_slug, {})
        if not catalog_row:
            missing_catalog.append(book_slug)
        try:
            with zipfile.ZipFile(epub_path) as archive:
                rootfile = find_rootfile(archive)
                package = parse_opf(archive, rootfile)
                documents = parse_documents(archive, package)
                toc_lookup, _ = parse_toc(archive, package)
                candidates = explicit_candidates(book_slug, documents, toc_lookup, catalog_row)
                exclusions: list[dict] = []
                if not candidates:
                    candidates, exclusions = manual_candidates(book_slug, documents, toc_lookup, catalog_row)
                supplements = supplemental_candidates(book_slug, documents, toc_lookup, catalog_row)
                existing_locations = {
                    (candidate["first_rel"], candidate["element_id"])
                    for candidate in candidates
                }
                candidates.extend(
                    candidate for candidate in supplements
                    if (candidate["first_rel"], candidate["element_id"]) not in existing_locations
                )
                all_exclusions.extend(exclusions)
                candidates.sort(key=lambda item: (item["spine_order"], item["toc_order"], item["id"]))

                target_index = build_target_index(book_slug, candidates)
                notes_by_id = note_map_for(documents)
                copied_assets: set[str] = set()
                written_support: set[str] = set()
                inherited = inherited_metadata(catalog_row)
                epub_sha256 = hashlib.sha256(epub_path.read_bytes()).hexdigest()

                for collection_order, candidate in enumerate(candidates, start=1):
                    words = element_word_count(candidate["parts"])
                    notes_word_count = sum(
                        len(WORD_RE.findall(readable_text(note)))
                        for note in referenced_note_elements(candidate["parts"], notes_by_id)
                    )
                    reading_minutes = max(1, math.ceil(words / 240))
                    reader_html = render_reader_html(
                        archive, package, book_slug, candidate, documents, target_index,
                        notes_by_id, copied_assets, written_support,
                    )
                    reader_rel = f"/reader/{candidate['id']}.html"
                    (READER_DIR / f"{candidate['id']}.html").write_text(reader_html, encoding="utf-8")

                    translators = package["translators"]
                    if not translators and catalog_row.get("translator"):
                        translators = [catalog_row["translator"]]

                    review_flags: list[str] = []
                    if len(translators) > 1:
                        review_flags.append("Multiple collection translators; story-level attribution unresolved")
                    if (
                        book_slug == "ernest-hemingway_short-fiction"
                        and candidate["title"] in {"Big Two-Hearted River Part I", "Big Two-Hearted River Part II"}
                    ):
                        review_flags.append("Multipart story boundary; source marks Parts I and II separately")

                    toc_path = candidate["toc_path"]
                    grouping = " › ".join(toc_path[:-1]) if len(toc_path) > 1 else ""
                    first_element = candidate["parts"][0][1]
                    record = {
                        "story_id": candidate["id"],
                        "title": candidate["title"],
                        "title_normalized": normalized_title(candidate["title"]),
                        "subtitle": candidate["subtitle"],
                        "synopsis": candidate["synopsis"],
                        "form": candidate["form"],
                        "form_detail": candidate["form_detail"],
                        "secondary_forms": secondary_forms_for(first_element, candidate["form"]),
                        "author": " | ".join(package["creators"]),
                        "story_translator": "",
                        "container_translators": " | ".join(translators),
                        "translator_scope": (
                            "Collection-level OPF attribution; story assignment unresolved"
                            if len(translators) > 1 else
                            "Collection-level OPF attribution"
                            if translators else
                            "No translator listed"
                        ),
                        "language": package["language"],
                        "word_count": words,
                        "notes_word_count": notes_word_count,
                        "reading_minutes": reading_minutes,
                        "content_sha256": element_content_hash(candidate["parts"]),
                        "collection_order": collection_order,
                        "collection_title": package["title"],
                        "collection_subtitle": package["subtitle"],
                        "collection_group": grouping,
                        "collection_publisher": package["publisher"],
                        "collection_dates": " | ".join(package["dates"]),
                        "collection_rights": " | ".join(package["rights"]),
                        "collection_illustrators": " | ".join(package["illustrators"]),
                        "collection_description": package["description"],
                        "book_word_count": int(package["word_count"]) if str(package["word_count"]).isdigit() else "",
                        "book_genres": " | ".join(package["genres"]),
                        "book_subjects": " | ".join(package["subjects"]),
                        "book_abstract": package["abstract"],
                        "epub_filename": epub_path.name,
                        "epub_sha256": epub_sha256,
                        "epub_identifier": package["identifier"],
                        "standard_ebooks_repo": package["repo_url"],
                        "source_urls": " | ".join(package["sources"]),
                        "source_document": candidate["first_rel"],
                        "source_fragment": candidate["element_id"],
                        "reader_path": reader_rel,
                        "extraction_method": candidate["method"],
                        "extraction_version": EXTRACTION_VERSION,
                        "review_status": "Curated boundary rule" if candidate["method"].startswith("curated") else "Source semantic markup",
                        "review_flags": " | ".join(review_flags),
                        "field_provenance": "Story fields: EPUB structure/text; collection fields: EPUB metadata; descriptive fields: matched source CSV row.",
                        "metadata_scope": "Story title, form, length, and location are story-level; descriptive catalog fields are inherited from the containing collection.",
                        **inherited,
                    }
                    all_records.append(record)

                audit_books.append({
                    "book_slug": book_slug,
                    "title": package["title"],
                    "story_count": len(candidates),
                    "methods": dict(Counter(candidate["method"] for candidate in candidates)),
                    "assets_copied": len(copied_assets),
                    "catalog_row_id": catalog_row.get("id", ""),
                })
        except Exception as exc:
            errors.append({"epub": epub_path.name, "error": str(exc)})

    collision_groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for record in all_records:
        collision_groups[(record["author"].casefold(), record["title_normalized"])].append(record)
    for group in collision_groups.values():
        if len(group) > 1:
            for record in group:
                collision_flag = "Same-author title collision; retained as a distinct source work"
                record["review_flags"] = " | ".join(filter(None, [record["review_flags"], collision_flag]))

    all_records.sort(key=lambda row: (row["title"].casefold(), row["author"].casefold(), row["story_id"]))

    fieldnames = [
        "story_id", "title", "title_normalized", "subtitle", "synopsis", "form", "form_detail", "secondary_forms",
        "author", "story_translator", "container_translators", "translator_scope", "language", "word_count", "notes_word_count", "reading_minutes", "content_sha256",
        "collection_order", "collection_title", "collection_subtitle", "collection_group",
        "collection_publisher", "collection_dates", "collection_rights", "collection_illustrators", "collection_description",
        "collection_first_published", "era", "origin", "original_language",
        "style_genre", "tone", "typical_length_estimate", "source_type",
        "content_notes", "blind_mode_fit", "test_priority", "why_it_fits",
        "us_pd_basis", "category", "book_word_count", "book_genres", "book_subjects",
        "book_abstract", "epub_filename", "epub_sha256", "epub_identifier", "standard_ebooks_repo",
        "source_urls", "source_document", "source_fragment", "reader_path",
        "extraction_method", "extraction_version", "review_status", "review_flags",
        "field_provenance", "metadata_scope", "catalog_row_id",
    ]
    for destination in [ROOT_CSV, DATA_DIR / "stories.csv"]:
        with destination.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(all_records)

    facets = {}
    for key in ["form", "author", "era", "origin", "original_language", "style_genre", "tone", "collection_title"]:
        counts = Counter(record[key] for record in all_records if record.get(key))
        facets[key] = [{"value": value, "count": count} for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold()))]

    payload = {
        "summary": {
            "stories": len(all_records),
            "volumes": len(epub_paths),
            "authors": len({record["author"] for record in all_records if record["author"]}),
            "forms": dict(Counter(record["form"] for record in all_records)),
            "excluded_books": len(all_exclusions),
        },
        "facets": facets,
        "stories": all_records,
        "exclusions": all_exclusions,
    }
    (DATA_DIR / "stories.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    report = {
        "source_epubs": len(epub_paths),
        "source_catalog_rows": len(source_rows),
        "catalog_slugs": len(source_by_slug),
        "records": len(all_records),
        "forms": dict(Counter(record["form"] for record in all_records)),
        "semantic_records": sum(record["extraction_method"] == "semantic markup" for record in all_records),
        "curated_rule_records": sum(record["extraction_method"] == "curated structural rule" for record in all_records),
        "curated_correction_records": sum(record["extraction_method"] == "curated markup correction" for record in all_records),
        "excluded": all_exclusions,
        "missing_catalog": missing_catalog,
        "errors": errors,
        "books": audit_books,
        "unique_story_ids": len({record["story_id"] for record in all_records}),
        "reader_files": len(list(READER_DIR.glob("*.html"))),
        "support_files": len(list(SUPPORT_DIR.rglob("*.html"))),
    }
    REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if errors:
        raise RuntimeError(f"Library build completed with {len(errors)} EPUB errors; see {REPORT_FILE}")
    if missing_catalog:
        raise RuntimeError(f"Missing catalog matches for {len(missing_catalog)} EPUBs")
    if report["unique_story_ids"] != len(all_records) or report["reader_files"] != len(all_records):
        raise RuntimeError("Story IDs or reader files are not one-to-one")

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    build()
