// Field names mirror the backend JSON one to one (snake_case), see backend/app/schemas/.

export interface ApiNotice {
  code: string;
  message: string;
}

export interface OfferBinding {
  offer_id: number;
  name: string;
  status: 'active' | 'removed';
  weight: number;
  is_pinned: boolean;
  is_published: boolean;
}

export interface EditorStream {
  keitaro_stream_id: number;
  name: string;
  position: number;
  has_offers: boolean;
  is_draft: boolean;
  can_push: boolean;
  can_cancel: boolean;
  offers: OfferBinding[];
  problems: ApiNotice[];
  warnings: ApiNotice[];
}

export interface EditorCampaign {
  keitaro_campaign_id: number;
  name: string;
  write_allowed: boolean;
  last_fetched_at: string;
  streams: EditorStream[];
}

export interface FetchResult {
  campaign: EditorCampaign;
  kept_draft_stream_ids: number[];
  notices: ApiNotice[];
}

export interface KeitaroCampaignSummary {
  id: number;
  name: string;
}

export interface OfferSummary {
  id: number;
  name: string;
}

export interface Country {
  code: string;
  name: string;
}

export interface CreatedCampaign {
  journal_id: number;
  keitaro_campaign_id: number;
  name: string;
  alias: string;
  campaign_url: string;
  country: string;
  offer_id: number;
  country_stream_id: number;
  offers_stream_id: number;
}

export interface JournalEntry {
  id: number;
  name: string;
  alias: string | null;
  country: string;
  offer_id: number;
  status: string;
  keitaro_campaign_id: number | null;
  country_stream_id: number | null;
  offers_stream_id: number | null;
  campaign_url: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}
