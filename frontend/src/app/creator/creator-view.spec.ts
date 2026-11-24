import { CreatedCampaign, JournalEntry } from '../core/api-types';
import { formatDateTime } from '../core/format';
import { CreatorViewInput, toCreatorView } from './creator-view';

const created: CreatedCampaign = {
  journal_id: 1,
  keitaro_campaign_id: 215338,
  name: 'test_oso4lq_x',
  alias: 'abc123',
  campaign_url: 'https://tracker.example/abc123',
  country: 'AU',
  offer_id: 18813,
  country_stream_id: 111,
  offers_stream_id: 222,
};

function input(overrides: Partial<CreatorViewInput> = {}): CreatorViewInput {
  return {
    countries: [],
    offer: { id: 18813, label: '18813 — Test offer' },
    nameValid: true,
    countryValid: true,
    submitting: false,
    result: null,
    error: null,
    journal: [],
    journalError: null,
    ...overrides,
  };
}

describe('toCreatorView', () => {
  it('labels countries as code and name', () => {
    const view = toCreatorView(
      input({
        countries: [
          { code: 'AU', name: 'Australia' },
          { code: 'DE', name: 'Germany' },
        ],
      }),
    );

    expect(view.countryOptions).toEqual([
      { code: 'AU', label: 'AU — Australia' },
      { code: 'DE', label: 'DE — Germany' },
    ]);
  });

  it('disables Create until name, country and offer are set', () => {
    expect(toCreatorView(input()).createDisabled).toBe(false);
    expect(toCreatorView(input({ nameValid: false })).createDisabled).toBe(true);
    expect(toCreatorView(input({ countryValid: false })).createDisabled).toBe(true);
    expect(toCreatorView(input({ offer: null })).createDisabled).toBe(true);
  });

  it('disables Create while submitting', () => {
    expect(toCreatorView(input({ submitting: true })).createDisabled).toBe(true);
  });

  it('describes the created campaign with an editor link', () => {
    const view = toCreatorView(input({ result: created }));

    expect(view.result?.editorLink).toBe('/editor/215338');
    expect(view.result?.campaignUrl).toBe('https://tracker.example/abc123');
    const values = new Set<string>();
    for (const line of view.result?.lines ?? []) {
      values.add(line.value);
    }
    for (const expected of ['abc123', 'AU', '18813', '111', '222']) {
      expect(values.has(expected)).toBe(true);
    }
  });

  it('marks compensation_failed journal rows for cleanup and fills empty cells with a dash', () => {
    const failed: JournalEntry = {
      id: 2,
      name: 'test_oso4lq_y',
      alias: null,
      country: 'AU',
      offer_id: 18813,
      status: 'compensation_failed',
      keitaro_campaign_id: null,
      country_stream_id: null,
      offers_stream_id: null,
      campaign_url: null,
      error: null,
      created_at: '2026-11-24T10:05:00+00:00',
      updated_at: '2026-11-24T10:05:00+00:00',
    };
    const view = toCreatorView(input({ journal: [failed] }));

    expect(view.journalRows).toEqual([
      {
        createdAt: formatDateTime(failed.created_at),
        name: 'test_oso4lq_y',
        country: 'AU',
        offerId: '18813',
        status: 'compensation_failed',
        keitaroCampaignId: '—',
        error: '—',
        needsCleanup: true,
      },
    ]);
  });
});
