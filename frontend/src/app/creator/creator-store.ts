import { Injectable, computed, inject, signal } from '@angular/core';
import { form, maxLength, required } from '@angular/forms/signals';
import { Observable, map } from 'rxjs';
import { toApiError } from '../core/api-error';
import { Country, CreatedCampaign, JournalEntry } from '../core/api-types';
import { toOfferOption } from '../core/format';
import { AutocompleteOption, AutocompleteSearch } from '../shared/autocomplete/autocomplete';
import { CreatorApi } from './creator-api';
import { toCreatorView } from './creator-view';

interface CreateAttempt {
  name: string;
  country: string;
  offerId: number;
}

interface SubmitFailure {
  message: string;
  attempt: CreateAttempt;
}

@Injectable()
export class CreatorStore {
  private readonly api = inject(CreatorApi);

  readonly model = signal({ name: '', country: '' });
  readonly createForm = form(this.model, (path) => {
    required(path.name);
    maxLength(path.name, 255);
    required(path.country);
  });
  readonly offer = signal<AutocompleteOption | null>(null);

  private readonly countries = signal<Country[]>([]);
  private readonly submitting = signal(false);
  private readonly result = signal<CreatedCampaign | null>(null);
  private readonly loadError = signal<string | null>(null);
  private readonly submitFailure = signal<SubmitFailure | null>(null);
  private readonly journal = signal<JournalEntry[]>([]);
  private readonly journalError = signal<string | null>(null);

  readonly searchOffers: AutocompleteSearch = (query): Observable<AutocompleteOption[]> =>
    this.api.searchOffers(query).pipe(
      map((offers) => {
        const options: AutocompleteOption[] = [];
        for (const offer of offers) {
          options.push(toOfferOption(offer));
        }
        return options;
      }),
    );

  // A create error describes the values that were sent. Once the form differs from that attempt the
  // message is stale, and it returns if the user restores the same values. Derived rather than cleared
  // in an effect because signal forms give the store no explicit change events.
  private readonly visibleError = computed(() => {
    const failure = this.submitFailure();
    if (failure === null) {
      return null;
    }
    const model = this.model();
    const offer = this.offer();
    const sameAttempt =
      model.name.trim() === failure.attempt.name &&
      model.country === failure.attempt.country &&
      offer?.id === failure.attempt.offerId;
    return sameAttempt ? failure.message : null;
  });

  readonly view = computed(() =>
    toCreatorView({
      countries: this.countries(),
      offer: this.offer(),
      // A whitespace-only name passes `required`, but Keitaro would get an empty campaign name.
      nameValid: this.createForm.name().valid() && this.model().name.trim() !== '',
      countryValid: this.createForm.country().valid(),
      submitting: this.submitting(),
      result: this.result(),
      error: this.loadError() ?? this.visibleError(),
      journal: this.journal(),
      journalError: this.journalError(),
    }),
  );

  load(): void {
    this.api.countries().subscribe({
      next: (countries) => this.countries.set(countries),
      error: (failure: unknown) => this.loadError.set(toApiError(failure).message),
    });
    this.loadJournal();
  }

  selectOffer(option: AutocompleteOption | null): void {
    this.offer.set(option);
  }

  submit(): void {
    const offer = this.offer();
    if (this.view().createDisabled || offer === null) {
      return;
    }
    this.submitting.set(true);
    // The previous attempt's outcome must not stay on screen next to the new one.
    this.result.set(null);
    this.submitFailure.set(null);
    const attempt: CreateAttempt = {
      name: this.model().name.trim(),
      country: this.model().country,
      offerId: offer.id,
    };
    this.api
      .createCampaign({
        name: attempt.name,
        country: attempt.country,
        offer_id: attempt.offerId,
      })
      .subscribe({
        next: (created) => {
          this.result.set(created);
          this.model.set({ name: '', country: '' });
          this.offer.set(null);
          this.submitting.set(false);
          this.loadJournal();
        },
        error: (failure: unknown) => {
          this.submitFailure.set({ message: toApiError(failure).message, attempt });
          this.submitting.set(false);
          // The backend journals a failed attempt too, so the table must show it.
          this.loadJournal();
        },
      });
  }

  private loadJournal(): void {
    this.api.journal().subscribe({
      next: (entries) => {
        this.journal.set(entries);
        this.journalError.set(null);
      },
      error: (failure: unknown) => this.journalError.set(toApiError(failure).message),
    });
  }
}
