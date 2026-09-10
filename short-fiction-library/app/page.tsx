'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Download,
  Feather,
  LibraryBig,
  Search,
  SlidersHorizontal,
  X,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Skeleton } from '@/components/ui/skeleton';

type Facet = { value: string; count: number };

type Story = {
  story_id: string;
  title: string;
  subtitle: string;
  synopsis: string;
  form: string;
  form_detail: string;
  secondary_forms: string;
  author: string;
  story_translator: string;
  container_translators: string;
  translator_scope: string;
  language: string;
  word_count: number;
  notes_word_count: number;
  reading_minutes: number;
  collection_order: number;
  collection_title: string;
  collection_subtitle: string;
  collection_group: string;
  collection_first_published: string;
  collection_publisher: string;
  collection_dates: string;
  collection_rights: string;
  collection_illustrators: string;
  collection_description: string;
  era: string;
  origin: string;
  original_language: string;
  style_genre: string;
  tone: string;
  category: string;
  typical_length_estimate: string;
  content_notes: string;
  why_it_fits: string;
  us_pd_basis: string;
  book_genres: string;
  book_subjects: string;
  epub_filename: string;
  standard_ebooks_repo: string;
  source_document: string;
  source_fragment: string;
  reader_path: string;
  extraction_method: string;
  review_status: string;
  review_flags: string;
  metadata_scope: string;
};

type LibraryPayload = {
  summary: {
    stories: number;
    volumes: number;
    authors: number;
    forms: Record<string, number>;
    excluded_books: number;
  };
  facets: Record<string, Facet[]>;
  stories: Story[];
  exclusions: Array<{ title: string; reason: string }>;
};

type Filters = {
  form: string;
  author: string;
  era: string;
  origin: string;
  genre: string;
  maxMinutes: string;
};

const EMPTY_FILTERS: Filters = {
  form: '',
  author: '',
  era: '',
  origin: '',
  genre: '',
  maxMinutes: '',
};

const PAGE_SIZE = 30;
const numberFormatter = new Intl.NumberFormat('en');

function searchable(value: string) {
  return value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase();
}

function displayPeople(value: string) {
  return value.split(' | ').filter(Boolean).join(', ');
}

function FilterSelect({
  id,
  label,
  value,
  options,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  options: Facet[];
  onChange: (value: string) => void;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="text-xs font-semibold tracking-[0.12em] text-sidebar-foreground/65 uppercase">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-10 w-full rounded-md border border-sidebar-border bg-sidebar-accent px-3 text-sm text-sidebar-foreground outline-none transition focus:border-sidebar-primary focus:ring-2 focus:ring-sidebar-primary/25"
      >
        <option value="">All</option>
        {options.map((option) => (
          <option value={option.value} key={option.value}>
            {option.value} ({numberFormatter.format(option.count)})
          </option>
        ))}
      </select>
    </div>
  );
}

function FiltersPanel({
  facets,
  filters,
  activeCount,
  update,
  reset,
  idPrefix,
}: {
  facets: Record<string, Facet[]>;
  filters: Filters;
  activeCount: number;
  update: (key: keyof Filters, value: string) => void;
  reset: () => void;
  idPrefix: string;
}) {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-semibold tracking-[0.18em] text-sidebar-primary uppercase">Browse by</p>
          <h2 className="mt-1 font-serif text-xl text-sidebar-foreground">Collection filters</h2>
        </div>
        {activeCount > 0 && (
          <Button variant="ghost" size="sm" onClick={reset} className="text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-foreground">
            Reset
          </Button>
        )}
      </div>

      <FilterSelect id={`${idPrefix}-form`} label="Literary form" value={filters.form} options={facets.form ?? []} onChange={(value) => update('form', value)} />
      <FilterSelect id={`${idPrefix}-author`} label="Author" value={filters.author} options={facets.author ?? []} onChange={(value) => update('author', value)} />
      <FilterSelect id={`${idPrefix}-era`} label="Era · collection" value={filters.era} options={facets.era ?? []} onChange={(value) => update('era', value)} />
      <FilterSelect id={`${idPrefix}-origin`} label="Origin · collection" value={filters.origin} options={facets.origin ?? []} onChange={(value) => update('origin', value)} />
      <FilterSelect id={`${idPrefix}-genre`} label="Style / genre · collection" value={filters.genre} options={facets.style_genre ?? []} onChange={(value) => update('genre', value)} />

      <div className="space-y-1.5">
        <label htmlFor={`${idPrefix}-length`} className="text-xs font-semibold tracking-[0.12em] text-sidebar-foreground/65 uppercase">
          Maximum reading time
        </label>
        <select
          id={`${idPrefix}-length`}
          value={filters.maxMinutes}
          onChange={(event) => update('maxMinutes', event.target.value)}
          className="h-10 w-full rounded-md border border-sidebar-border bg-sidebar-accent px-3 text-sm text-sidebar-foreground outline-none transition focus:border-sidebar-primary focus:ring-2 focus:ring-sidebar-primary/25"
        >
          <option value="">Any length</option>
          {[5, 10, 20, 40, 60, 120].map((minutes) => (
            <option key={minutes} value={minutes}>Up to {minutes} minutes</option>
          ))}
        </select>
      </div>

      <div className="rounded-lg border border-sidebar-border bg-sidebar-accent/55 p-4 text-xs leading-relaxed text-sidebar-foreground/68">
        Era, origin, genre, tone, and first-publication fields are inherited from the containing collection and are labeled that way in each story record.
      </div>
    </div>
  );
}

function MetadataItem({ label, value }: { label: string; value?: string | number }) {
  if (value === '' || value === undefined || value === null) return null;
  return (
    <div>
      <dt className="text-[0.68rem] font-semibold tracking-[0.13em] text-muted-foreground uppercase">{label}</dt>
      <dd className="mt-1 text-sm leading-relaxed text-foreground">{value}</dd>
    </div>
  );
}

export default function Home() {
  const [library, setLibrary] = useState<LibraryPayload | null>(null);
  const [loadError, setLoadError] = useState('');
  const [query, setQuery] = useState('');
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [sort, setSort] = useState('title');
  const [page, setPage] = useState(1);
  const [filterSheetOpen, setFilterSheetOpen] = useState(false);
  const [selectedStory, setSelectedStory] = useState<Story | null>(null);
  const [readerHtml, setReaderHtml] = useState('');
  const [readerError, setReaderError] = useState('');
  const readerRequest = useRef<AbortController | null>(null);
  const readerContainer = useRef<HTMLDivElement | null>(null);
  const pendingReaderFragment = useRef('');

  useEffect(() => {
    const controller = new AbortController();
    fetch('/data/stories.json', { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`Catalog request failed (${response.status})`);
        return response.json() as Promise<LibraryPayload>;
      })
      .then(setLibrary)
      .catch((error: Error) => {
        if (error.name !== 'AbortError') setLoadError(error.message);
      });
    return () => controller.abort();
  }, []);

  const openStory = useCallback((story: Story, fragment = '') => {
    readerRequest.current?.abort();
    const controller = new AbortController();
    readerRequest.current = controller;
    pendingReaderFragment.current = fragment;
    setSelectedStory(story);
    setReaderHtml('');
    setReaderError('');
    fetch(story.reader_path, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`Story request failed (${response.status})`);
        return response.text();
      })
      .then(setReaderHtml)
      .catch((error: Error) => {
        if (error.name !== 'AbortError') setReaderError(error.message);
      });
  }, []);

  useEffect(() => () => readerRequest.current?.abort(), []);

  const activeFilterCount = Object.values(filters).filter(Boolean).length;

  const updateFilter = useCallback((key: keyof Filters, value: string) => {
    setFilters((current) => ({ ...current, [key]: value }));
    setPage(1);
  }, []);

  const resetFilters = useCallback(() => {
    setFilters(EMPTY_FILTERS);
    setPage(1);
  }, []);

  const filteredStories = useMemo(() => {
    if (!library) return [];
    const needle = searchable(query.trim());
    const maxMinutes = Number(filters.maxMinutes || 0);
    const result = library.stories.filter((story) => {
      if (filters.form && story.form !== filters.form) return false;
      if (filters.author && story.author !== filters.author) return false;
      if (filters.era && story.era !== filters.era) return false;
      if (filters.origin && story.origin !== filters.origin) return false;
      if (filters.genre && story.style_genre !== filters.genre) return false;
      if (maxMinutes && story.reading_minutes > maxMinutes) return false;
      if (!needle) return true;
      return searchable([
        story.title,
        story.subtitle,
        story.author,
        story.collection_title,
        story.collection_group,
        story.form,
        story.form_detail,
        story.secondary_forms,
        story.synopsis,
        story.style_genre,
        story.category,
        story.tone,
        story.origin,
      ].filter(Boolean).join(' ')).includes(needle);
    });

    result.sort((a, b) => {
      if (sort === 'author') return a.author.localeCompare(b.author) || a.title.localeCompare(b.title);
      if (sort === 'shortest') return a.reading_minutes - b.reading_minutes || a.title.localeCompare(b.title);
      if (sort === 'longest') return b.reading_minutes - a.reading_minutes || a.title.localeCompare(b.title);
      if (sort === 'collection') return a.collection_title.localeCompare(b.collection_title) || a.collection_order - b.collection_order;
      return a.title.localeCompare(b.title) || a.author.localeCompare(b.author);
    });
    return result;
  }, [library, query, filters, sort]);

  const pageCount = Math.max(1, Math.ceil(filteredStories.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount);
  const pageStories = filteredStories.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  const resultStart = filteredStories.length ? (currentPage - 1) * PAGE_SIZE + 1 : 0;
  const resultEnd = Math.min(currentPage * PAGE_SIZE, filteredStories.length);
  const selectedIndex = selectedStory ? filteredStories.findIndex((story) => story.story_id === selectedStory.story_id) : -1;

  const openStoryById = useCallback((storyId: string, fragment = '') => {
    const story = library?.stories.find((item) => item.story_id === storyId);
    if (story) openStory(story, fragment);
  }, [library, openStory]);

  useEffect(() => {
    const container = readerContainer.current;
    if (!container) return;
    const handleClick = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      const link = target.closest<HTMLAnchorElement>('a');
      if (!link) return;
      const storyId = link.dataset.storyId;
      if (storyId) {
        event.preventDefault();
        openStoryById(storyId, link.dataset.storyFragment ?? '');
        return;
      }
      const href = link.getAttribute('href');
      if (href?.startsWith('#') && href.length > 1) {
        event.preventDefault();
        const destination = document.getElementById(decodeURIComponent(href.slice(1)));
        destination?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    };
    container.addEventListener('click', handleClick);
    return () => container.removeEventListener('click', handleClick);
  }, [readerHtml, openStoryById]);

  useEffect(() => {
    const fragment = pendingReaderFragment.current;
    if (!readerHtml || !fragment) return;
    const frame = window.requestAnimationFrame(() => {
      const destination = readerContainer.current?.querySelector<HTMLElement>(`#${CSS.escape(fragment)}`);
      destination?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      pendingReaderFragment.current = '';
    });
    return () => window.cancelAnimationFrame(frame);
  }, [readerHtml]);

  function goToPage(nextPage: number) {
    setPage(Math.max(1, Math.min(pageCount, nextPage)));
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  return (
    <main className="min-h-screen bg-background">
      <header className="border-b border-border bg-card">
        <div className="mx-auto max-w-[96rem] px-4 py-5 sm:px-6 lg:px-8">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
            <div className="flex items-start gap-3">
              <div className="mt-0.5 flex size-11 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
                <Feather className="size-5" aria-hidden="true" />
              </div>
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h1 className="font-serif text-3xl tracking-tight text-foreground sm:text-4xl">Short Fiction Library</h1>
                  <Badge variant="outline" className="border-accent/25 text-accent">Private · local</Badge>
                </div>
                <p className="mt-1 text-sm text-muted-foreground">Individual works, liberated from their containing volumes.</p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
              {library && (
                <>
                  <span><b className="text-foreground">{numberFormatter.format(library.summary.stories)}</b> works</span>
                  <span aria-hidden="true">·</span>
                  <span><b className="text-foreground">{library.summary.authors}</b> authors</span>
                  <span aria-hidden="true">·</span>
                  <span><b className="text-foreground">{library.summary.volumes}</b> EPUBs</span>
                </>
              )}
              <a href="/data/stories.csv" download className={buttonVariants({ variant: 'outline', className: 'ml-1' })}>
                <Download aria-hidden="true" />
                Download CSV
              </a>
            </div>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-[96rem] lg:grid-cols-[17rem_minmax(0,1fr)]">
        <aside className="hidden min-h-[calc(100vh-6.8rem)] bg-sidebar p-6 lg:block">
          <div className="sticky top-6">
            <FiltersPanel idPrefix="desktop-filter" facets={library?.facets ?? {}} filters={filters} activeCount={activeFilterCount} update={updateFilter} reset={resetFilters} />
          </div>
        </aside>

        <section className="min-w-0 px-4 py-6 sm:px-6 lg:px-8 lg:py-8" aria-label="Story catalog">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-center">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
              <Input
                type="search"
                value={query}
                onChange={(event) => { setQuery(event.target.value); setPage(1); }}
                placeholder="Search title, author, collection, form, genre…"
                aria-label="Search stories"
                className="h-11 bg-card pl-10 shadow-xs"
              />
              {query && (
                <button type="button" onClick={() => { setQuery(''); setPage(1); }} aria-label="Clear search" className="absolute top-1/2 right-3 -translate-y-1/2 rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground">
                  <X className="size-4" />
                </button>
              )}
            </div>

            <div className="flex gap-2">
              <Button variant="outline" className="h-11 flex-1 bg-card lg:hidden" onClick={() => setFilterSheetOpen(true)}>
                <SlidersHorizontal aria-hidden="true" />
                Filters {activeFilterCount ? `(${activeFilterCount})` : ''}
              </Button>
              <label className="sr-only" htmlFor="sort-stories">Sort stories</label>
              <select
                id="sort-stories"
                value={sort}
                onChange={(event) => { setSort(event.target.value); setPage(1); }}
                className="h-11 min-w-40 rounded-lg border border-input bg-card px-3 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/25"
              >
                <option value="title">Title A–Z</option>
                <option value="author">Author A–Z</option>
                <option value="shortest">Shortest first</option>
                <option value="longest">Longest first</option>
                <option value="collection">Collection order</option>
              </select>
            </div>
          </div>

          {activeFilterCount > 0 && (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {Object.entries(filters).filter(([, value]) => value).map(([key, value]) => (
                <Badge key={key} variant="secondary" className="h-7 gap-1.5 px-2.5">
                  {key === 'maxMinutes' ? `≤ ${value} min` : value}
                  <button type="button" onClick={() => updateFilter(key as keyof Filters, '')} aria-label={`Remove ${value} filter`} className="rounded-full hover:bg-black/10">
                    <X className="size-3" />
                  </button>
                </Badge>
              ))}
            </div>
          )}

          <div className="mt-6 flex items-end justify-between gap-4">
            <div>
              <p className="text-xs font-semibold tracking-[0.16em] text-accent uppercase">The index</p>
              <h2 className="mt-1 font-serif text-2xl text-foreground">
                {loadError ? 'Catalog unavailable' : library ? `${numberFormatter.format(filteredStories.length)} works` : 'Opening the catalog…'}
              </h2>
            </div>
            {library && filteredStories.length > 0 && (
              <p className="hidden text-sm text-muted-foreground sm:block" aria-live="polite">
                Showing {numberFormatter.format(resultStart)}–{numberFormatter.format(resultEnd)}
              </p>
            )}
          </div>

          {loadError ? (
            <div className="mt-6 rounded-xl border border-destructive/20 bg-card p-8 text-center">
              <LibraryBig className="mx-auto size-8 text-destructive" />
              <h3 className="mt-3 font-serif text-xl">The catalog could not be opened</h3>
              <p className="mt-2 text-sm text-muted-foreground">Refresh the story catalog, then reload this page. {loadError}</p>
            </div>
          ) : !library ? (
            <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 9 }).map((_, index) => <Skeleton key={index} className="h-56 rounded-xl bg-card" />)}
            </div>
          ) : pageStories.length === 0 ? (
            <div className="mt-6 rounded-xl border border-dashed border-border bg-card p-10 text-center">
              <BookOpen className="mx-auto size-8 text-muted-foreground" />
              <h3 className="mt-3 font-serif text-xl">No stories match</h3>
              <p className="mt-2 text-sm text-muted-foreground">Try a broader search or reset the filters.</p>
              <Button className="mt-5" onClick={() => { setQuery(''); resetFilters(); }}>Clear search and filters</Button>
            </div>
          ) : (
            <div className="mt-5 grid gap-4 sm:grid-cols-2 2xl:grid-cols-3">
              {pageStories.map((story) => (
                <article key={story.story_id} className="group relative overflow-hidden rounded-xl border border-border bg-card shadow-xs transition hover:-translate-y-0.5 hover:border-accent/35 hover:shadow-md">
                  <button type="button" onClick={() => openStory(story)} className="flex h-full w-full flex-col p-5 text-left focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/40">
                    <div className="flex w-full items-start justify-between gap-3">
                      <div className="flex flex-wrap gap-1.5">
                        <Badge variant="secondary">{story.form}</Badge>
                        {story.form_detail && <Badge variant="outline" className="max-w-full truncate">{story.form_detail}</Badge>}
                      </div>
                      <span className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground"><Clock3 className="size-3.5" />{story.reading_minutes} min</span>
                    </div>
                    <h3 className="mt-5 font-serif text-[1.35rem] leading-tight text-foreground transition group-hover:text-accent">{story.title}</h3>
                    {story.subtitle && <p className="mt-1 line-clamp-2 font-serif text-sm italic text-muted-foreground">{story.subtitle}</p>}
                    <p className="mt-2 text-sm font-medium text-foreground/80">{displayPeople(story.author)}</p>
                    {story.synopsis && <p className="mt-3 line-clamp-3 text-sm leading-relaxed text-muted-foreground">{story.synopsis}</p>}
                    <div className="mt-auto pt-5 text-xs leading-relaxed text-muted-foreground">
                      <p className="line-clamp-1">From <i>{story.collection_title}</i></p>
                      <p className="mt-1">{numberFormatter.format(story.word_count)} words</p>
                    </div>
                  </button>
                </article>
              ))}
            </div>
          )}

          {library && filteredStories.length > PAGE_SIZE && (
            <nav className="mt-8 flex items-center justify-between border-t border-border pt-5" aria-label="Catalog pages">
              <Button variant="outline" disabled={currentPage === 1} onClick={() => goToPage(currentPage - 1)}>
                <ChevronLeft aria-hidden="true" /> Previous
              </Button>
              <p className="text-sm text-muted-foreground">Page <b className="text-foreground">{currentPage}</b> of {pageCount}</p>
              <Button variant="outline" disabled={currentPage === pageCount} onClick={() => goToPage(currentPage + 1)}>
                Next <ChevronRight aria-hidden="true" />
              </Button>
            </nav>
          )}
        </section>
      </div>

      <Sheet open={filterSheetOpen} onOpenChange={setFilterSheetOpen}>
        <SheetContent side="left" className="w-[min(92vw,22rem)]! bg-sidebar text-sidebar-foreground sm:max-w-[22rem]!">
          <SheetHeader className="border-b border-sidebar-border">
            <SheetTitle className="font-serif text-sidebar-foreground">Filter the collection</SheetTitle>
            <SheetDescription className="text-sidebar-foreground/65">Narrow the individual works in the catalog.</SheetDescription>
          </SheetHeader>
          <div className="overflow-y-auto px-4 pb-8">
            <FiltersPanel idPrefix="mobile-filter" facets={library?.facets ?? {}} filters={filters} activeCount={activeFilterCount} update={updateFilter} reset={resetFilters} />
          </div>
        </SheetContent>
      </Sheet>

      <Sheet open={Boolean(selectedStory)} onOpenChange={(open) => { if (!open) setSelectedStory(null); }}>
        <SheetContent className="w-full! gap-0 bg-card p-0 sm:max-w-[min(100vw,76rem)]!">
          {selectedStory && (
            <>
              <SheetHeader className="reader-surface shrink-0 border-b border-border px-5 py-5 pr-14 sm:px-8 sm:py-6 sm:pr-16">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="secondary">{selectedStory.form}</Badge>
                  {selectedStory.form_detail && <Badge variant="outline">{selectedStory.form_detail}</Badge>}
                  {selectedStory.secondary_forms && <Badge variant="outline">Also: {selectedStory.secondary_forms.replaceAll(' | ', ', ')}</Badge>}
                </div>
                <SheetTitle className="mt-3 max-w-4xl font-serif text-2xl leading-tight sm:text-3xl">{selectedStory.title}</SheetTitle>
                <SheetDescription className="mt-1 text-sm">
                  {selectedStory.subtitle && <span className="mr-2 italic">{selectedStory.subtitle}</span>}
                  by <span className="font-medium text-foreground">{displayPeople(selectedStory.author)}</span>
                  <span className="mx-2" aria-hidden="true">·</span>
                  {numberFormatter.format(selectedStory.word_count)} words
                  <span className="mx-2" aria-hidden="true">·</span>
                  {selectedStory.reading_minutes} min
                </SheetDescription>
              </SheetHeader>

              <div className="grid min-h-0 flex-1 overflow-hidden lg:grid-cols-[18rem_minmax(0,1fr)]">
                <aside className="hidden overflow-y-auto border-r border-border bg-muted/45 p-5 lg:block">
                  <h3 className="text-xs font-semibold tracking-[0.15em] text-accent uppercase">Story metadata</h3>
                  <dl className="mt-4 space-y-4">
                    <MetadataItem label="Collection" value={selectedStory.collection_title} />
                    <MetadataItem label="Section" value={selectedStory.collection_group} />
                    <MetadataItem label="Order in collection" value={selectedStory.collection_order} />
                    <MetadataItem label="Language" value={selectedStory.language} />
                    <MetadataItem label="Story translator" value={selectedStory.story_translator} />
                    <MetadataItem label="Collection translator(s)" value={displayPeople(selectedStory.container_translators)} />
                    <MetadataItem label="Collection illustrator(s)" value={displayPeople(selectedStory.collection_illustrators)} />
                    <MetadataItem label="Source EPUB" value={selectedStory.epub_filename} />
                  </dl>

                  <div className="mt-7 border-t border-border pt-5">
                    <p className="text-[0.68rem] font-semibold tracking-[0.13em] text-muted-foreground uppercase">Inherited from collection</p>
                    <dl className="mt-4 space-y-4">
                      <MetadataItem label="First published" value={selectedStory.collection_first_published} />
                      <MetadataItem label="Era" value={selectedStory.era} />
                      <MetadataItem label="Origin" value={selectedStory.origin} />
                      <MetadataItem label="Style / genre" value={selectedStory.style_genre} />
                      <MetadataItem label="Tone" value={selectedStory.tone} />
                      <MetadataItem label="Category" value={selectedStory.category} />
                      <MetadataItem label="Content notes" value={selectedStory.content_notes} />
                    </dl>
                  </div>

                  <details className="mt-6 rounded-lg border border-border bg-card p-3 text-xs text-muted-foreground">
                    <summary className="cursor-pointer font-semibold text-foreground">Provenance & review</summary>
                    <p className="mt-3 leading-relaxed">{selectedStory.metadata_scope}</p>
                    <p className="mt-2"><b>Boundary:</b> {selectedStory.review_status}</p>
                    {selectedStory.review_flags && <p className="mt-2"><b>Review flag:</b> {selectedStory.review_flags}</p>}
                    <p className="mt-2 break-all"><b>Location:</b> {selectedStory.source_document}{selectedStory.source_fragment ? `#${selectedStory.source_fragment}` : ''}</p>
                  </details>
                </aside>

                <div className="min-h-0 overflow-y-auto reader-surface" id="story-reader-scroll">
                  <div className="mx-auto max-w-3xl px-5 pt-6 sm:px-10 sm:pt-10">
                    <details className="mb-6 rounded-lg border border-border bg-card/90 p-4 lg:hidden">
                      <summary className="cursor-pointer text-sm font-semibold text-foreground">Story metadata and provenance</summary>
                      <dl className="mt-4 grid gap-4 sm:grid-cols-2">
                        <MetadataItem label="Collection" value={selectedStory.collection_title} />
                        <MetadataItem label="Section" value={selectedStory.collection_group} />
                        <MetadataItem label="Language" value={selectedStory.language} />
                        <MetadataItem label="Collection translator(s)" value={displayPeople(selectedStory.container_translators)} />
                        <MetadataItem label="First published · inherited" value={selectedStory.collection_first_published} />
                        <MetadataItem label="Era · inherited" value={selectedStory.era} />
                        <MetadataItem label="Origin · inherited" value={selectedStory.origin} />
                        <MetadataItem label="Style / genre · inherited" value={selectedStory.style_genre} />
                        <MetadataItem label="Tone · inherited" value={selectedStory.tone} />
                        <MetadataItem label="Content notes · inherited" value={selectedStory.content_notes} />
                      </dl>
                      <p className="mt-4 border-t border-border pt-3 text-xs leading-relaxed text-muted-foreground">{selectedStory.metadata_scope}</p>
                    </details>
                    {selectedStory.synopsis && (
                      <div className="mb-8 rounded-lg border border-accent/15 bg-card/80 p-4 font-serif text-sm italic leading-relaxed text-muted-foreground">
                        {selectedStory.synopsis}
                      </div>
                    )}
                    {readerError ? (
                      <div className="rounded-lg border border-destructive/20 bg-card p-6 text-center text-sm text-muted-foreground">This story could not be opened. {readerError}</div>
                    ) : !readerHtml ? (
                      <div className="space-y-4 py-8">
                        <Skeleton className="mx-auto h-7 w-2/3" />
                        {Array.from({ length: 12 }).map((_, index) => <Skeleton key={index} className="h-4 w-full" />)}
                      </div>
                    ) : (
                      <div ref={readerContainer} dangerouslySetInnerHTML={{ __html: readerHtml }} />
                    )}
                  </div>
                </div>
              </div>

              <div className="flex shrink-0 items-center justify-between border-t border-border bg-card px-4 py-3 sm:px-6">
                <Button variant="outline" size="sm" disabled={selectedIndex <= 0} onClick={() => openStory(filteredStories[selectedIndex - 1])}>
                  <ChevronLeft aria-hidden="true" /> Previous
                </Button>
                <span className="max-w-[45%] truncate text-xs text-muted-foreground">
                  {selectedIndex >= 0 ? `${numberFormatter.format(selectedIndex + 1)} of ${numberFormatter.format(filteredStories.length)} filtered works` : 'Linked story'}
                </span>
                <Button variant="outline" size="sm" disabled={selectedIndex < 0 || selectedIndex >= filteredStories.length - 1} onClick={() => openStory(filteredStories[selectedIndex + 1])}>
                  Next <ChevronRight aria-hidden="true" />
                </Button>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </main>
  );
}
