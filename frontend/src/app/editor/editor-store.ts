import { Injectable, computed, inject, signal } from '@angular/core';
import { Observable, map } from 'rxjs';
import { toApiError } from '../core/api-error';
import { ApiNotice, EditorCampaign, EditorStream } from '../core/api-types';
import { toOfferOption } from '../core/format';
import { AutocompleteOption, AutocompleteSearch } from '../shared/autocomplete/autocomplete';
import { EditorApi } from './editor-api';
import { LoadStatus, parseCampaignId, toEditorView } from './editor-view';

@Injectable()
export class EditorStore {
  private readonly api = inject(EditorApi);

  private readonly campaignId = signal<number | null>(null);
  private readonly campaign = signal<EditorCampaign | null>(null);
  private readonly loadStatus = signal<LoadStatus>('idle');
  private readonly pageError = signal<string | null>(null);
  private readonly fetching = signal(false);
  private readonly fetchNotices = signal<ApiNotice[]>([]);
  private readonly keptDraftStreamIds = signal<number[]>([]);
  private readonly forceFetchConfirmOpen = signal(false);
  // The three collections below are replaced, never mutated, so computed() sees every change.
  private readonly busyStreamIds = signal<ReadonlySet<number>>(new Set());
  private readonly streamErrors = signal<ReadonlyMap<number, string>>(new Map());
  private readonly offerSelections = signal<ReadonlyMap<number, AutocompleteOption>>(new Map());

  // Bumped on every open(). Comparing it (rather than campaignId) also discards late
  // responses when the same campaign is reopened, whose state has just been reset.
  private openGeneration = 0;

  readonly searchCampaigns: AutocompleteSearch = (query): Observable<AutocompleteOption[]> =>
    this.api.searchCampaigns(query).pipe(
      map((campaigns) => {
        const options: AutocompleteOption[] = [];
        for (const campaign of campaigns) {
          options.push({ id: campaign.id, label: `${campaign.id} — ${campaign.name}` });
        }
        return options;
      }),
    );

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

  readonly view = computed(() =>
    toEditorView({
      campaignId: this.campaignId(),
      campaign: this.campaign(),
      loadStatus: this.loadStatus(),
      pageError: this.pageError(),
      fetching: this.fetching(),
      fetchNotices: this.fetchNotices(),
      keptDraftStreamIds: this.keptDraftStreamIds(),
      forceFetchConfirmOpen: this.forceFetchConfirmOpen(),
      busyStreamIds: this.busyStreamIds(),
      streamErrors: this.streamErrors(),
      offerSelections: this.offerSelections(),
    }),
  );

  open(rawId: string | undefined): void {
    const generation = ++this.openGeneration;
    this.campaign.set(null);
    this.pageError.set(null);
    this.fetching.set(false);
    this.fetchNotices.set([]);
    this.keptDraftStreamIds.set([]);
    this.forceFetchConfirmOpen.set(false);
    this.busyStreamIds.set(new Set());
    this.streamErrors.set(new Map());
    this.offerSelections.set(new Map());

    const campaignId = parseCampaignId(rawId);
    this.campaignId.set(campaignId);
    if (campaignId === null) {
      this.loadStatus.set('error');
      this.pageError.set('Некорректный id кампании');
      return;
    }

    this.loadStatus.set('loading');
    this.api.getCampaign(campaignId).subscribe({
      next: (campaign) => {
        if (generation !== this.openGeneration) {
          return;
        }
        this.campaign.set(campaign);
        this.loadStatus.set('ready');
      },
      error: (failure: unknown) => {
        if (generation !== this.openGeneration) {
          return;
        }
        const apiError = toApiError(failure);
        if (apiError.status === 404 && apiError.code === 'campaign_not_fetched') {
          this.loadStatus.set('not-fetched');
          return;
        }
        this.loadStatus.set('error');
        this.pageError.set(apiError.message);
      },
    });
  }

  fetch(): void {
    this.runFetch(false);
  }

  requestForceFetch(): void {
    this.forceFetchConfirmOpen.set(true);
  }

  confirmForceFetch(): void {
    this.runFetch(true);
  }

  dismissForceFetch(): void {
    this.forceFetchConfirmOpen.set(false);
  }

  selectOffer(streamId: number, option: AutocompleteOption | null): void {
    const selections = new Map(this.offerSelections());
    if (option === null) {
      selections.delete(streamId);
    } else {
      selections.set(streamId, option);
    }
    this.offerSelections.set(selections);
  }

  addOffer(streamId: number): void {
    const option = this.offerSelections().get(streamId);
    if (option === undefined) {
      return;
    }
    this.runStreamAction(streamId, this.api.addOffer(streamId, option.id), () =>
      this.selectOffer(streamId, null),
    );
  }

  removeOffer(streamId: number, offerId: number): void {
    this.runStreamAction(streamId, this.api.removeOffer(streamId, offerId));
  }

  bringBackOffer(streamId: number, offerId: number): void {
    this.runStreamAction(streamId, this.api.bringBackOffer(streamId, offerId));
  }

  pinOffer(streamId: number, offerId: number): void {
    this.runStreamAction(streamId, this.api.pinOffer(streamId, offerId));
  }

  unpinOffer(streamId: number, offerId: number): void {
    this.runStreamAction(streamId, this.api.unpinOffer(streamId, offerId));
  }

  push(streamId: number): void {
    this.runStreamAction(streamId, this.api.push(streamId));
  }

  cancel(streamId: number): void {
    this.runStreamAction(streamId, this.api.cancel(streamId));
  }

  private runFetch(force: boolean): void {
    const campaignId = this.campaignId();
    if (campaignId === null || this.fetching() || this.busyStreamIds().size > 0) {
      return;
    }
    const generation = this.openGeneration;
    this.fetching.set(true);
    this.api.fetch(campaignId, force).subscribe({
      next: (result) => {
        if (generation !== this.openGeneration) {
          return;
        }
        this.campaign.set(result.campaign);
        this.loadStatus.set('ready');
        this.pageError.set(null);
        this.fetchNotices.set(result.notices);
        this.keptDraftStreamIds.set(result.kept_draft_stream_ids);
        this.streamErrors.set(new Map());
        this.forceFetchConfirmOpen.set(false);
        this.fetching.set(false);
      },
      error: (failure: unknown) => {
        if (generation !== this.openGeneration) {
          return;
        }
        this.pageError.set(toApiError(failure).message);
        this.fetching.set(false);
      },
    });
  }

  private runStreamAction(
    streamId: number,
    request: Observable<EditorStream>,
    onSuccess?: () => void,
  ): void {
    if (this.fetching() || this.busyStreamIds().has(streamId)) {
      return;
    }
    const generation = this.openGeneration;
    this.setBusy(streamId, true);
    request.subscribe({
      next: (stream) => {
        if (generation !== this.openGeneration) {
          return;
        }
        this.replaceStream(stream);
        this.setStreamError(streamId, null);
        onSuccess?.();
        // Kept ids live until the next fetch; a stale confirmation would reappear unasked when
        // the same stream becomes a draft again.
        this.forceFetchConfirmOpen.set(false);
        this.setBusy(streamId, false);
      },
      error: (failure: unknown) => {
        if (generation !== this.openGeneration) {
          return;
        }
        this.setStreamError(streamId, toApiError(failure).message);
        this.setBusy(streamId, false);
      },
    });
  }

  // The response is the backend's truth for the stream: weights, flags and statuses are
  // taken as-is, nothing is recomputed here.
  private replaceStream(updated: EditorStream): void {
    const campaign = this.campaign();
    if (campaign === null) {
      return;
    }
    const streams: EditorStream[] = [];
    for (const stream of campaign.streams) {
      streams.push(stream.keitaro_stream_id === updated.keitaro_stream_id ? updated : stream);
    }
    this.campaign.set({ ...campaign, streams });
  }

  private setBusy(streamId: number, busy: boolean): void {
    const busyIds = new Set(this.busyStreamIds());
    if (busy) {
      busyIds.add(streamId);
    } else {
      busyIds.delete(streamId);
    }
    this.busyStreamIds.set(busyIds);
  }

  private setStreamError(streamId: number, message: string | null): void {
    const errors = new Map(this.streamErrors());
    if (message === null) {
      errors.delete(streamId);
    } else {
      errors.set(streamId, message);
    }
    this.streamErrors.set(errors);
  }
}
