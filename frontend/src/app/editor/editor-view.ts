import type { ApiNotice, EditorCampaign, EditorStream, OfferBinding } from '../core/api-types';
import { formatDateTime } from '../core/format';
import type { AutocompleteOption } from '../shared/autocomplete/autocomplete';

// Pure functions only: everything the editor screen shows is derived here from the API
// response and UI state. Weights, statuses and flags are taken from the response as-is and
// never recomputed on the client, so the screen cannot disagree with the backend.

export type LoadStatus = 'idle' | 'loading' | 'not-fetched' | 'ready' | 'error';

export interface EditorViewInput {
  campaignId: number | null;
  campaign: EditorCampaign | null;
  loadStatus: LoadStatus;
  pageError: string | null;
  fetching: boolean;
  fetchNotices: ApiNotice[];
  keptDraftStreamIds: number[];
  forceFetchConfirmOpen: boolean;
  busyStreamIds: ReadonlySet<number>;
  streamErrors: ReadonlyMap<number, string>;
  offerSelections: ReadonlyMap<number, AutocompleteOption>;
}

export interface CampaignHeaderView {
  title: string;
  details: string;
  writeForbiddenNote: string | null;
}

export interface ForceFetchView {
  offered: boolean;
  confirmOpen: boolean;
  confirmText: string;
  disabled: boolean;
}

export interface OfferRowView {
  offerId: number;
  label: string;
  weightLabel: string;
  isPinned: boolean;
  isUnpublished: boolean;
  actionsDisabled: boolean;
}

export interface StreamView {
  id: number;
  title: string;
  idLabel: string;
  cssClass: string;
  isDraft: boolean;
  hasOffers: boolean;
  activeOffers: OfferRowView[];
  archivedOffers: OfferRowView[];
  showArchive: boolean;
  showTotal: boolean;
  totalLabel: string;
  totalIsOff: boolean;
  problems: string[];
  warnings: string[];
  error: string | null;
  pushDisabled: boolean;
  cancelDisabled: boolean;
  addDisabled: boolean;
  hiddenOfferIds: ReadonlySet<number>;
  offerSelection: AutocompleteOption | null;
}

export interface EditorView {
  header: CampaignHeaderView | null;
  statusMessage: string | null;
  errorMessage: string | null;
  showFetchButton: boolean;
  fetchDisabled: boolean;
  notices: string[];
  forceFetch: ForceFetchView;
  streams: StreamView[];
}

const FULL_WEIGHT_PERCENT = 100;
const DIGITS_ONLY = /^\d+$/;

export function parseCampaignId(raw: string | undefined): number | null {
  if (raw === undefined || !DIGITS_ONLY.test(raw)) {
    return null;
  }
  const campaignId = Number(raw);
  return Number.isSafeInteger(campaignId) && campaignId > 0 ? campaignId : null;
}

export function toEditorView(input: EditorViewInput): EditorView {
  const campaign = input.campaign;
  const fetchDisabled = input.fetching || input.busyStreamIds.size > 0;
  const keptDraftNames = namesOfStillDraftStreams(campaign, input.keptDraftStreamIds);
  const keptDraftList = keptDraftNames.join(', ');
  const hasKeptDrafts = keptDraftNames.length > 0;

  const notices: string[] = [];
  for (const notice of input.fetchNotices) {
    notices.push(notice.message);
  }
  if (hasKeptDrafts) {
    notices.push(`Черновики сохранены в потоках: ${keptDraftList}`);
  }

  const streams: StreamView[] = [];
  if (campaign !== null) {
    for (const stream of campaign.streams) {
      streams.push(toStreamView(stream, input));
    }
  }

  return {
    header: campaign === null ? null : toHeaderView(campaign),
    statusMessage: toStatusMessage(input),
    errorMessage: input.pageError,
    // Fetch is the way out of both "not loaded yet" and a failed open, so it must be
    // available without a loaded campaign; only the loading state hides it.
    showFetchButton: input.campaignId !== null && input.loadStatus !== 'loading',
    fetchDisabled,
    notices,
    forceFetch: {
      offered: hasKeptDrafts,
      confirmOpen: hasKeptDrafts && input.forceFetchConfirmOpen,
      confirmText: `Неопубликованные изменения в потоках ${keptDraftList} будут потеряны`,
      disabled: fetchDisabled,
    },
    streams,
  };
}

function toStatusMessage(input: EditorViewInput): string | null {
  switch (input.loadStatus) {
    case 'loading':
      return 'Загрузка…';
    case 'not-fetched':
      return `Кампания ${input.campaignId} ещё не загружена в редактор`;
    case 'idle':
      return 'Выберите кампанию';
    case 'ready':
    case 'error':
      return null;
  }
}

function toHeaderView(campaign: EditorCampaign): CampaignHeaderView {
  return {
    title: campaign.name,
    details:
      `Keitaro id ${campaign.keitaro_campaign_id} · ` +
      `Fetch: ${formatDateTime(campaign.last_fetched_at)}`,
    writeForbiddenNote: campaign.write_allowed
      ? null
      : 'Публикация в эту кампанию запрещена (защита по префиксу)',
  };
}

// The kept ids come from the last Fetch, but the user may push or cancel such a stream
// afterwards; then nothing of it would be lost, so only streams that are still drafts count.
// Ids that are no longer in the campaign are skipped: there is no name to show for them.
function namesOfStillDraftStreams(
  campaign: EditorCampaign | null,
  streamIds: number[],
): string[] {
  const names: string[] = [];
  if (campaign === null) {
    return names;
  }
  for (const streamId of streamIds) {
    for (const stream of campaign.streams) {
      if (stream.keitaro_stream_id === streamId) {
        if (stream.is_draft) {
          names.push(stream.name);
        }
        break;
      }
    }
  }
  return names;
}

function toStreamView(stream: EditorStream, input: EditorViewInput): StreamView {
  const streamId = stream.keitaro_stream_id;
  const isBusy = input.busyStreamIds.has(streamId) || input.fetching;
  const offerSelection = input.offerSelections.get(streamId) ?? null;

  const activeOffers: OfferRowView[] = [];
  const archivedOffers: OfferRowView[] = [];
  const hiddenOfferIds = new Set<number>();
  let totalWeight = 0;
  for (const offer of stream.offers) {
    const row = toOfferRow(offer, isBusy);
    if (offer.status === 'active') {
      activeOffers.push(row);
      hiddenOfferIds.add(offer.offer_id);
      totalWeight += offer.weight;
    } else {
      archivedOffers.push(row);
    }
  }

  const problems: string[] = [];
  for (const problem of stream.problems) {
    problems.push(problem.message);
  }
  const warnings: string[] = [];
  for (const warning of stream.warnings) {
    warnings.push(warning.message);
  }

  return {
    id: streamId,
    title: stream.name,
    idLabel: `id ${streamId}`,
    cssClass: toCssClass(stream),
    isDraft: stream.is_draft,
    hasOffers: stream.has_offers,
    activeOffers,
    archivedOffers,
    showArchive: archivedOffers.length > 0,
    showTotal: activeOffers.length > 0,
    totalLabel: `Итого: ${totalWeight}%`,
    totalIsOff: totalWeight !== FULL_WEIGHT_PERCENT,
    problems,
    warnings,
    error: input.streamErrors.get(streamId) ?? null,
    pushDisabled: !stream.can_push || isBusy,
    cancelDisabled: !stream.can_cancel || isBusy,
    addDisabled: !stream.has_offers || isBusy || offerSelection === null,
    hiddenOfferIds,
    offerSelection,
  };
}

function toCssClass(stream: EditorStream): string {
  if (!stream.has_offers) {
    return 'stream stream--plain';
  }
  return stream.is_draft ? 'stream stream--draft' : 'stream stream--clean';
}

function toOfferRow(offer: OfferBinding, isBusy: boolean): OfferRowView {
  return {
    offerId: offer.offer_id,
    label: `${offer.offer_id} — ${offer.name}`,
    weightLabel: `${offer.weight}%`,
    isPinned: offer.is_pinned,
    isUnpublished: !offer.is_published,
    actionsDisabled: isBusy,
  };
}
