import { Country, CreatedCampaign, JournalEntry } from '../core/api-types';
import { formatDateTime } from '../core/format';
import { AutocompleteOption } from '../shared/autocomplete/autocomplete';

export interface CreatorViewInput {
  countries: Country[];
  offer: AutocompleteOption | null;
  nameValid: boolean;
  countryValid: boolean;
  submitting: boolean;
  result: CreatedCampaign | null;
  error: string | null;
  journal: JournalEntry[];
  journalError: string | null;
}

export interface CreatedCampaignView {
  title: string;
  lines: { label: string; value: string }[];
  campaignUrl: string;
  editorLink: string;
}

export interface JournalRowView {
  createdAt: string;
  name: string;
  country: string;
  offerId: string;
  status: string;
  keitaroCampaignId: string;
  error: string;
  needsCleanup: boolean;
}

export interface CreatorView {
  countryOptions: { code: string; label: string }[];
  createDisabled: boolean;
  error: string | null;
  result: CreatedCampaignView | null;
  journalRows: JournalRowView[];
  journalError: string | null;
}

const EMPTY_CELL = '—';
// The backend marks a campaign it failed to roll back with this status; the owner has to remove it in Keitaro by hand.
const CLEANUP_STATUS = 'compensation_failed';

function cell(value: string | number | null): string {
  return value === null || value === '' ? EMPTY_CELL : String(value);
}

function toCreatedCampaignView(created: CreatedCampaign): CreatedCampaignView {
  return {
    title: `Кампания создана: ${created.name}`,
    lines: [
      { label: 'ID кампании', value: String(created.keitaro_campaign_id) },
      { label: 'Alias', value: created.alias },
      { label: 'Страна', value: created.country },
      { label: 'Оффер', value: String(created.offer_id) },
      { label: 'Поток страны', value: String(created.country_stream_id) },
      { label: 'Поток оффера', value: String(created.offers_stream_id) },
    ],
    campaignUrl: created.campaign_url,
    editorLink: `/editor/${created.keitaro_campaign_id}`,
  };
}

function toJournalRowView(entry: JournalEntry): JournalRowView {
  return {
    createdAt: formatDateTime(entry.created_at),
    name: cell(entry.name),
    country: cell(entry.country),
    offerId: cell(entry.offer_id),
    status: cell(entry.status),
    keitaroCampaignId: cell(entry.keitaro_campaign_id),
    error: cell(entry.error),
    needsCleanup: entry.status === CLEANUP_STATUS,
  };
}

export function toCreatorView(input: CreatorViewInput): CreatorView {
  const countryOptions: CreatorView['countryOptions'] = [];
  for (const country of input.countries) {
    countryOptions.push({ code: country.code, label: `${country.code} — ${country.name}` });
  }
  const journalRows: JournalRowView[] = [];
  for (const entry of input.journal) {
    journalRows.push(toJournalRowView(entry));
  }
  return {
    countryOptions,
    createDisabled:
      !input.nameValid || !input.countryValid || input.offer === null || input.submitting,
    error: input.error,
    result: input.result === null ? null : toCreatedCampaignView(input.result),
    journalRows,
    journalError: input.journalError,
  };
}
