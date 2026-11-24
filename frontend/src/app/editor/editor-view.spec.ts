import { ApiNotice, EditorCampaign, EditorStream, OfferBinding } from '../core/api-types';
import { formatDateTime } from '../core/format';
import { EditorViewInput, parseCampaignId, toEditorView } from './editor-view';

function makeOffer(overrides: Partial<OfferBinding> = {}): OfferBinding {
  return {
    offer_id: 501,
    name: 'Offer',
    status: 'active',
    weight: 100,
    is_pinned: false,
    is_published: true,
    ...overrides,
  };
}

function makeStream(overrides: Partial<EditorStream> = {}): EditorStream {
  return {
    keitaro_stream_id: 10,
    name: 'Stream',
    position: 1,
    has_offers: true,
    is_draft: false,
    can_push: false,
    can_cancel: false,
    offers: [],
    problems: [],
    warnings: [],
    ...overrides,
  };
}

function makeCampaign(
  streams: EditorStream[],
  overrides: Partial<EditorCampaign> = {},
): EditorCampaign {
  return {
    keitaro_campaign_id: 215338,
    name: 'Campaign',
    write_allowed: true,
    last_fetched_at: '2026-11-24T10:05:00+00:00',
    streams,
    ...overrides,
  };
}

function makeInput(overrides: Partial<EditorViewInput> = {}): EditorViewInput {
  return {
    campaignId: 215338,
    campaign: null,
    loadStatus: 'ready',
    pageError: null,
    fetching: false,
    fetchNotices: [],
    keptDraftStreamIds: [],
    forceFetchConfirmOpen: false,
    busyStreamIds: new Set<number>(),
    streamErrors: new Map<number, string>(),
    offerSelections: new Map(),
    ...overrides,
  };
}

function viewOfStream(stream: EditorStream, overrides: Partial<EditorViewInput> = {}) {
  return toEditorView(makeInput({ campaign: makeCampaign([stream]), ...overrides })).streams[0];
}

describe('parseCampaignId', () => {
  it('rejects non-positive and non-integer ids', () => {
    for (const raw of ['abc', '0', '-1', '1.5', '', undefined]) {
      expect(parseCampaignId(raw)).toBeNull();
    }
    expect(parseCampaignId('215338')).toBe(215338);
  });
});

describe('toEditorView', () => {
  it('shows a plain stream without offers or buttons', () => {
    const view = viewOfStream(
      makeStream({ keitaro_stream_id: 7, name: 'Plain', has_offers: false, can_push: false }),
    );

    expect(view.cssClass).toBe('stream stream--plain');
    expect(view.title).toBe('Plain');
    expect(view.idLabel).toBe('id 7');
    expect(view.hasOffers).toBe(false);
    expect(view.activeOffers).toEqual([]);
    expect(view.archivedOffers).toEqual([]);
    expect(view.showArchive).toBe(false);
    expect(view.showTotal).toBe(false);
    expect(view.pushDisabled).toBe(true);
    expect(view.cancelDisabled).toBe(true);
    expect(view.addDisabled).toBe(true);
  });

  it('colors a draft stream yellow and a clean stream white', () => {
    const draft = viewOfStream(makeStream({ is_draft: true }));
    const clean = viewOfStream(makeStream({ is_draft: false }));

    expect(draft.cssClass).toBe('stream stream--draft');
    expect(draft.isDraft).toBe(true);
    expect(clean.cssClass).toBe('stream stream--clean');
    expect(clean.isDraft).toBe(false);
  });

  it('splits active offers and archive, labels weights and the total', () => {
    const view = viewOfStream(
      makeStream({
        offers: [
          makeOffer({ offer_id: 501, name: 'A', weight: 25 }),
          makeOffer({ offer_id: 502, name: 'B', weight: 25, is_pinned: true }),
          makeOffer({ offer_id: 503, name: 'C', weight: 0, status: 'removed' }),
        ],
      }),
    );

    const activeWeights: string[] = [];
    const activePins: boolean[] = [];
    for (const row of view.activeOffers) {
      activeWeights.push(row.weightLabel);
      activePins.push(row.isPinned);
    }
    expect(activeWeights).toEqual(['25%', '25%']);
    expect(activePins).toEqual([false, true]);
    expect(view.activeOffers[0].label).toBe('501 — A');
    expect(view.archivedOffers.length).toBe(1);
    expect(view.archivedOffers[0].label).toBe('503 — C');
    expect(view.archivedOffers[0].weightLabel).toBe('0%');
    expect(view.showArchive).toBe(true);
    expect(view.showTotal).toBe(true);
    expect(view.totalLabel).toBe('Итого: 50%');
    expect(view.totalIsOff).toBe(true);
  });

  it('shows a total of exactly 100 as in order', () => {
    const view = viewOfStream(
      makeStream({
        offers: [makeOffer({ offer_id: 1, weight: 50 }), makeOffer({ offer_id: 2, weight: 50 })],
      }),
    );

    expect(view.totalLabel).toBe('Итого: 100%');
    expect(view.totalIsOff).toBe(false);
  });

  it('hides the total when only archived offers remain', () => {
    const view = viewOfStream(
      makeStream({ offers: [makeOffer({ status: 'removed', weight: 0 })] }),
    );

    expect(view.showTotal).toBe(false);
    expect(view.showArchive).toBe(true);
    expect(view.activeOffers).toEqual([]);
  });

  it('marks unpublished offers', () => {
    const view = viewOfStream(
      makeStream({
        offers: [
          makeOffer({ offer_id: 1, is_published: true }),
          makeOffer({ offer_id: 2, is_published: false }),
        ],
      }),
    );

    expect(view.activeOffers[0].isUnpublished).toBe(false);
    expect(view.activeOffers[1].isUnpublished).toBe(true);
  });

  it('disables push and cancel from the API flags and while busy or fetching', () => {
    const stream = makeStream({ keitaro_stream_id: 10, can_push: true, can_cancel: true });
    const idle = viewOfStream(stream);
    const forbidden = viewOfStream(makeStream({ can_push: false, can_cancel: false }));
    const busy = viewOfStream(stream, { busyStreamIds: new Set([10]) });
    const otherBusy = viewOfStream(stream, { busyStreamIds: new Set([99]) });
    const fetching = viewOfStream(
      makeStream({ can_push: true, can_cancel: true, offers: [makeOffer()] }),
      { fetching: true },
    );

    expect(idle.pushDisabled).toBe(false);
    expect(idle.cancelDisabled).toBe(false);
    expect(forbidden.pushDisabled).toBe(true);
    expect(forbidden.cancelDisabled).toBe(true);
    expect(busy.pushDisabled).toBe(true);
    expect(busy.cancelDisabled).toBe(true);
    expect(otherBusy.pushDisabled).toBe(false);
    expect(fetching.pushDisabled).toBe(true);
    expect(fetching.cancelDisabled).toBe(true);
    expect(fetching.activeOffers[0].actionsDisabled).toBe(true);
  });

  it('disables offer actions only while the stream is busy', () => {
    const stream = makeStream({ keitaro_stream_id: 10, offers: [makeOffer()] });

    expect(viewOfStream(stream).activeOffers[0].actionsDisabled).toBe(false);
    expect(
      viewOfStream(stream, { busyStreamIds: new Set([10]) }).activeOffers[0].actionsDisabled,
    ).toBe(true);
  });

  it('disables Add until an offer is chosen and hides active offers from suggestions', () => {
    const stream = makeStream({
      keitaro_stream_id: 10,
      offers: [
        makeOffer({ offer_id: 501 }),
        makeOffer({ offer_id: 502 }),
        makeOffer({ offer_id: 503, status: 'removed', weight: 0 }),
      ],
    });
    const chosen = { id: 900, label: '900 — New' };

    const withoutChoice = viewOfStream(stream);
    const withChoice = viewOfStream(stream, { offerSelections: new Map([[10, chosen]]) });
    const busyWithChoice = viewOfStream(stream, {
      offerSelections: new Map([[10, chosen]]),
      busyStreamIds: new Set([10]),
    });

    expect(withoutChoice.addDisabled).toBe(true);
    expect(withoutChoice.offerSelection).toBeNull();
    expect(withChoice.addDisabled).toBe(false);
    expect(withChoice.offerSelection).toEqual(chosen);
    expect(busyWithChoice.addDisabled).toBe(true);
    expect([...withChoice.hiddenOfferIds]).toEqual([501, 502]);
  });

  it('passes problems, warnings and the stream error through', () => {
    const problems: ApiNotice[] = [{ code: 'sum', message: 'Сумма не 100' }];
    const warnings: ApiNotice[] = [{ code: 'pin', message: 'Закреплены все' }];
    const view = viewOfStream(makeStream({ keitaro_stream_id: 10, problems, warnings }), {
      streamErrors: new Map([[10, 'Не удалось']]),
    });
    const quiet = viewOfStream(makeStream());

    expect(view.problems).toEqual(['Сумма не 100']);
    expect(view.warnings).toEqual(['Закреплены все']);
    expect(view.error).toBe('Не удалось');
    expect(quiet.error).toBeNull();
  });

  it('shows only the fetch error, not the not-fetched status, for a missing campaign', () => {
    const view = toEditorView(
      makeInput({ loadStatus: 'not-fetched', pageError: 'Кампания 99999 не найдена в Keitaro' }),
    );

    expect(view.statusMessage).toBeNull();
    expect(view.errorMessage).toBe('Кампания 99999 не найдена в Keitaro');
    expect(view.showFetchButton).toBe(true);
  });

  it('describes not-fetched, loading, error and idle states', () => {
    const notFetched = toEditorView(makeInput({ loadStatus: 'not-fetched' }));
    const loading = toEditorView(makeInput({ loadStatus: 'loading' }));
    const failed = toEditorView(makeInput({ loadStatus: 'error', pageError: 'Сбой' }));
    const idle = toEditorView(makeInput({ loadStatus: 'idle', campaignId: null }));
    const ready = toEditorView(makeInput({ campaign: makeCampaign([]) }));

    expect(notFetched.statusMessage).toBe('Кампания 215338 ещё не загружена в редактор');
    expect(notFetched.showFetchButton).toBe(true);
    expect(notFetched.header).toBeNull();
    expect(loading.statusMessage).toBe('Загрузка…');
    expect(loading.showFetchButton).toBe(false);
    expect(failed.statusMessage).toBeNull();
    expect(failed.errorMessage).toBe('Сбой');
    expect(failed.showFetchButton).toBe(true);
    expect(idle.statusMessage).toBe('Выберите кампанию');
    expect(idle.showFetchButton).toBe(false);
    expect(ready.statusMessage).toBeNull();
    expect(ready.errorMessage).toBeNull();
    expect(ready.showFetchButton).toBe(true);
  });

  it('disables Fetch while fetching or while any stream is busy', () => {
    const campaign = makeCampaign([makeStream()]);

    expect(toEditorView(makeInput({ campaign })).fetchDisabled).toBe(false);
    expect(toEditorView(makeInput({ campaign, fetching: true })).fetchDisabled).toBe(true);
    expect(
      toEditorView(makeInput({ campaign, busyStreamIds: new Set([10]) })).fetchDisabled,
    ).toBe(true);
  });

  it('describes the loaded campaign in the header', () => {
    const view = toEditorView(makeInput({ campaign: makeCampaign([]) }));

    expect(view.header?.title).toBe('Campaign');
    expect(view.header?.details).toBe(
      `Keitaro id 215338 · Fetch: ${formatDateTime('2026-11-24T10:05:00+00:00')}`,
    );
    expect(view.header?.writeForbiddenNote).toBeNull();
  });

  it('offers a forced fetch naming the streams with kept drafts', () => {
    const campaign = makeCampaign([
      makeStream({ keitaro_stream_id: 10, name: 'First', is_draft: true }),
      makeStream({ keitaro_stream_id: 11, name: 'Second', is_draft: true }),
      makeStream({ keitaro_stream_id: 12, name: 'Third', is_draft: true }),
    ]);
    const notice: ApiNotice = { code: 'x', message: 'Сообщение сервера' };

    const view = toEditorView(
      makeInput({
        campaign,
        keptDraftStreamIds: [10, 12, 999],
        fetchNotices: [notice],
        forceFetchConfirmOpen: true,
      }),
    );
    const without = toEditorView(makeInput({ campaign }));

    expect(view.notices).toEqual(['Сообщение сервера']);
    expect(view.forceFetch).toEqual({
      offered: true,
      confirmOpen: true,
      confirmText: 'Неопубликованные изменения в потоках First, Third будут потеряны',
      disabled: false,
    });
    expect(without.notices).toEqual([]);
    expect(without.forceFetch.offered).toBe(false);
    expect(without.forceFetch.confirmOpen).toBe(false);
  });

  it('names only kept streams that are still drafts', () => {
    // Stream 11 was pushed after the fetch kept its draft: nothing of it can be lost any more.
    const campaign = makeCampaign([
      makeStream({ keitaro_stream_id: 10, name: 'First', is_draft: true }),
      makeStream({ keitaro_stream_id: 11, name: 'Second', is_draft: false }),
      makeStream({ keitaro_stream_id: 12, name: 'Third', is_draft: true }),
    ]);

    const view = toEditorView(makeInput({ campaign, keptDraftStreamIds: [10, 11, 12] }));

    expect(view.notices).toEqual([]);
    expect(view.forceFetch.offered).toBe(true);
    expect(view.forceFetch.confirmText).toBe(
      'Неопубликованные изменения в потоках First, Third будут потеряны',
    );
  });

  it('drops the kept-draft notice and the forced fetch once no kept stream is a draft', () => {
    // The fetch kept the draft of stream 10, then the user pushed or cancelled it.
    const campaign = makeCampaign([
      makeStream({ keitaro_stream_id: 10, name: 'First', is_draft: false }),
    ]);

    const view = toEditorView(
      makeInput({ campaign, keptDraftStreamIds: [10], forceFetchConfirmOpen: true }),
    );

    expect(view.notices).toEqual([]);
    expect(view.forceFetch.offered).toBe(false);
    expect(view.forceFetch.confirmOpen).toBe(false);
  });

  it("hides the server's kept-draft notice once no kept stream is a draft", () => {
    const keptNotice: ApiNotice = {
      code: 'draft_streams_kept',
      message: 'Не обновлены потоки с неопубликованными изменениями: «First»',
    };
    const deletedNotice: ApiNotice = {
      code: 'streams_deleted_in_keitaro',
      message: 'Потоков больше нет в Keitaro',
    };
    const input = {
      keptDraftStreamIds: [10],
      fetchNotices: [keptNotice, deletedNotice],
    };
    const stillDraft = toEditorView(
      makeInput({
        ...input,
        campaign: makeCampaign([
          makeStream({ keitaro_stream_id: 10, name: 'First', is_draft: true }),
        ]),
      }),
    );
    const publishedSince = toEditorView(
      makeInput({
        ...input,
        campaign: makeCampaign([
          makeStream({ keitaro_stream_id: 10, name: 'First', is_draft: false }),
        ]),
      }),
    );

    expect(stillDraft.notices).toEqual([
      keptNotice.message,
      deletedNotice.message,
    ]);
    expect(publishedSince.notices).toEqual([deletedNotice.message]);
  });

  it('disables the forced fetch like Fetch', () => {
    const view = toEditorView(
      makeInput({
        campaign: makeCampaign([makeStream({ is_draft: true })]),
        keptDraftStreamIds: [10],
        fetching: true,
      }),
    );

    expect(view.forceFetch.disabled).toBe(true);
  });

  it('notes when writing to the campaign is forbidden', () => {
    const view = toEditorView(
      makeInput({ campaign: makeCampaign([], { write_allowed: false }) }),
    );

    expect(view.header?.writeForbiddenNote).toBe(
      'Публикация в эту кампанию запрещена (защита по префиксу)',
    );
  });
});
