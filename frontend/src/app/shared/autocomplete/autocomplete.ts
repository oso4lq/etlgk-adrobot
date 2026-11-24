import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  input,
  output,
  signal,
  untracked,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Observable, Subject, catchError, debounceTime, of, switchMap, tap } from 'rxjs';
import { toApiError } from '../../core/api-error';

export interface AutocompleteOption {
  id: number;
  label: string;
}

export type AutocompleteSearch = (query: string) => Observable<AutocompleteOption[]>;

interface SuggestionView {
  option: AutocompleteOption;
  isActive: boolean;
}

const SEARCH_DEBOUNCE_MILLISECONDS = 250;

let nextInstanceNumber = 0;

@Component({
  selector: 'app-autocomplete',
  templateUrl: './autocomplete.html',
  styleUrl: './autocomplete.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Autocomplete {
  readonly label = input.required<string>();
  readonly search = input.required<AutocompleteSearch>();
  readonly selection = input<AutocompleteOption | null>(null);
  readonly hiddenIds = input<ReadonlySet<number>>(new Set());
  readonly disabled = input(false);
  readonly selectionChange = output<AutocompleteOption | null>();

  protected readonly inputId = `autocomplete-input-${nextInstanceNumber++}`;
  protected readonly text = signal('');

  private readonly foundOptions = signal<AutocompleteOption[]>([]);
  private readonly isOpen = signal(false);
  private readonly activeIndex = signal(-1);
  private readonly errorText = signal<string | null>(null);
  private readonly queries = new Subject<string>();
  // The parent owns the selection but learns about edits only through the output;
  // this mirror lets the component emit null exactly once per edit without waiting for the input to update.
  private chosenOption: AutocompleteOption | null = null;

  protected readonly suggestions = computed<SuggestionView[]>(() => {
    const hiddenIds = this.hiddenIds();
    const activeIndex = this.activeIndex();
    const views: SuggestionView[] = [];
    for (const option of this.foundOptions()) {
      if (!hiddenIds.has(option.id)) {
        views.push({ option, isActive: views.length === activeIndex });
      }
    }
    return views;
  });
  protected readonly isListVisible = computed(() => this.isOpen() && this.suggestions().length > 0);
  protected readonly errorMessage = computed(() => {
    const message = this.errorText();
    return message === null ? null : `Поиск недоступен: ${message}`;
  });

  constructor() {
    this.queries
      .pipe(
        debounceTime(SEARCH_DEBOUNCE_MILLISECONDS),
        // switchMap drops the answer of an outdated request, so a slow reply can never overwrite a newer one.
        switchMap((query) =>
          this.search()(query).pipe(
            tap(() => this.errorText.set(null)),
            catchError((error: unknown) => {
              this.errorText.set(toApiError(error).message);
              return of<AutocompleteOption[]>([]);
            }),
          ),
        ),
        takeUntilDestroyed(),
      )
      .subscribe((options) => {
        this.foundOptions.set(options);
        this.activeIndex.set(-1);
        this.isOpen.set(true);
      });

    effect(() => {
      const selection = this.selection();
      untracked(() => {
        if (selection !== null) {
          this.chosenOption = selection;
          this.text.set(selection.label);
          this.isOpen.set(false);
        } else if (this.chosenOption !== null) {
          // Reset from outside; after a user edit chosenOption is already null, so typed text survives.
          this.chosenOption = null;
          this.text.set('');
        }
      });
    });
  }

  protected onInput(event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.text.set(value);
    if (this.chosenOption !== null) {
      this.chosenOption = null;
      this.selectionChange.emit(null);
    }
    this.queries.next(value);
  }

  protected onFocus(): void {
    this.queries.next(this.text());
  }

  protected onFocusOut(event: FocusEvent): void {
    const container = event.currentTarget as HTMLElement;
    if (!container.contains(event.relatedTarget as Node | null)) {
      this.isOpen.set(false);
    }
  }

  protected choose(option: AutocompleteOption): void {
    this.chosenOption = option;
    this.text.set(option.label);
    this.isOpen.set(false);
    this.selectionChange.emit(option);
  }

  protected onKeydown(event: KeyboardEvent): void {
    const suggestions = this.suggestions();
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        this.isOpen.set(true);
        this.activeIndex.set(Math.min(this.activeIndex() + 1, suggestions.length - 1));
        break;
      case 'ArrowUp':
        event.preventDefault();
        this.activeIndex.set(Math.max(this.activeIndex() - 1, 0));
        break;
      case 'Enter': {
        const active = suggestions[this.activeIndex()];
        if (this.isListVisible() && active) {
          event.preventDefault();
          this.choose(active.option);
        }
        break;
      }
      case 'Escape':
        this.isOpen.set(false);
        break;
    }
  }
}
