import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { EditorCampaign, EditorStream } from '../core/api-types';
import { EditorStore } from './editor-store';

function makeStream(
  id: number,
  overrides: Partial<EditorStream> = {},
): EditorStream {
  return {
    keitaro_stream_id: id,
    name: `Stream ${id}`,
    position: id,
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

function makeCampaign(id: number, streams: EditorStream[]): EditorCampaign {
  return {
    keitaro_campaign_id: id,
    name: `Campaign ${id}`,
    write_allowed: true,
    last_fetched_at: '2026-11-24T10:00:00Z',
    streams,
  };
}

describe('EditorStore', () => {
  let store: EditorStore;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [EditorStore, provideHttpClient(), provideHttpClientTesting()],
    });
    store = TestBed.inject(EditorStore);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  function openReady(streams: EditorStream[] = [makeStream(1), makeStream(2)]): void {
    store.open('1');
    http.expectOne('/api/editor/campaigns/1').flush(makeCampaign(1, streams));
  }

  function titles(): string[] {
    const result: string[] = [];
    for (const stream of store.view().streams) {
      result.push(stream.title);
    }
    return result;
  }

  it('open with invalid id shows error without request', () => {
    store.open('abc');

    expect(store.view().errorMessage).toBe('Некорректный id кампании');
    expect(store.view().showFetchButton).toBe(false);
  });

  it('opens a fetched campaign', () => {
    openReady();

    expect(store.view().header?.title).toBe('Campaign 1');
    expect(titles()).toEqual(['Stream 1', 'Stream 2']);
    expect(store.view().errorMessage).toBeNull();
  });

  it('reports a campaign that was not fetched yet', () => {
    store.open('1');
    http
      .expectOne('/api/editor/campaigns/1')
      .flush(
        { code: 'campaign_not_fetched', message: 'Кампания не загружена' },
        { status: 404, statusText: 'Not Found' },
      );

    expect(store.view().statusMessage).toBe('Кампания 1 ещё не загружена в редактор');
    expect(store.view().errorMessage).toBeNull();
    expect(store.view().showFetchButton).toBe(true);
  });

  it('shows other open errors', () => {
    store.open('1');
    http
      .expectOne('/api/editor/campaigns/1')
      .flush(
        { code: 'keitaro_unavailable', message: 'Keitaro недоступен' },
        { status: 502, statusText: 'Bad Gateway' },
      );

    expect(store.view().errorMessage).toBe('Keitaro недоступен');
  });

  it('fetch stores notices and offers a forced fetch for kept drafts', () => {
    openReady();

    store.fetch();
    const plain = http.expectOne('/api/editor/campaigns/1/fetch');
    expect(plain.request.method).toBe('POST');
    expect(plain.request.params.has('force')).toBe(false);
    plain.flush({
      campaign: makeCampaign(1, [makeStream(1), makeStream(2, { is_draft: true })]),
      kept_draft_stream_ids: [2],
      notices: [{ code: 'x', message: 'Что-то произошло' }],
    });

    expect(store.view().notices).toContain('Что-то произошло');
    expect(store.view().forceFetch.offered).toBe(true);

    store.requestForceFetch();
    expect(store.view().forceFetch.confirmOpen).toBe(true);
    store.confirmForceFetch();
    const forced = http.expectOne('/api/editor/campaigns/1/fetch?force=true');
    forced.flush({
      campaign: makeCampaign(1, [makeStream(1), makeStream(2)]),
      kept_draft_stream_ids: [],
      notices: [],
    });

    expect(store.view().forceFetch.offered).toBe(false);
    expect(store.view().forceFetch.confirmOpen).toBe(false);
  });

  it('fetch failure keeps the loaded campaign and shows the message', () => {
    openReady();

    store.fetch();
    http
      .expectOne('/api/editor/campaigns/1/fetch')
      .flush(
        { code: 'keitaro_unavailable', message: 'Keitaro недоступен' },
        { status: 502, statusText: 'Bad Gateway' },
      );

    expect(store.view().errorMessage).toBe('Keitaro недоступен');
    expect(titles()).toEqual(['Stream 1', 'Stream 2']);
    expect(store.view().fetchDisabled).toBe(false);
  });

  it('replaces only the changed stream with the action response', () => {
    openReady();

    store.push(2);
    http
      .expectOne('/api/editor/streams/2/push')
      .flush(makeStream(2, { name: 'Pushed stream' }));

    expect(titles()).toEqual(['Stream 1', 'Pushed stream']);
  });

  it('sends each offer action to its own endpoint', () => {
    openReady();
    const expectedUrls = [
      '/api/editor/streams/1/offers/7/remove',
      '/api/editor/streams/1/offers/7/bring-back',
      '/api/editor/streams/1/offers/7/pin',
      '/api/editor/streams/1/offers/7/unpin',
      '/api/editor/streams/1/cancel',
    ];
    const actions = [
      () => store.removeOffer(1, 7),
      () => store.bringBackOffer(1, 7),
      () => store.pinOffer(1, 7),
      () => store.unpinOffer(1, 7),
      () => store.cancel(1),
    ];

    for (let index = 0; index < actions.length; index++) {
      actions[index]();
      const request = http.expectOne(expectedUrls[index]);
      expect(request.request.method).toBe('POST');
      request.flush(makeStream(1));
    }
  });

  it('clears the offer selection after a successful add', () => {
    openReady();
    store.selectOffer(1, { id: 18813, label: '18813 — Offer' });
    expect(store.view().streams[0].offerSelection?.id).toBe(18813);

    store.addOffer(1);
    const request = http.expectOne('/api/editor/streams/1/offers');
    expect(request.request.body).toEqual({ offer_id: 18813 });
    request.flush(makeStream(1));

    expect(store.view().streams[0].offerSelection).toBeNull();
  });

  it('keeps the offer selection when the add fails', () => {
    openReady();
    store.selectOffer(1, { id: 18813, label: '18813 — Offer' });

    store.addOffer(1);
    http
      .expectOne('/api/editor/streams/1/offers')
      .flush(
        { code: 'offer_not_found', message: 'Оффер не найден' },
        { status: 404, statusText: 'Not Found' },
      );

    expect(store.view().streams[0].offerSelection?.id).toBe(18813);
    expect(store.view().streams[0].error).toBe('Оффер не найден');
  });

  it('records an action error on the stream and frees it', () => {
    openReady([makeStream(1), makeStream(2, { can_push: true })]);

    store.push(2);
    expect(store.view().streams[1].pushDisabled).toBe(true);
    http
      .expectOne('/api/editor/streams/2/push')
      .flush(
        { code: 'keitaro_stream_changed', message: 'Поток изменён в Keitaro' },
        { status: 409, statusText: 'Conflict' },
      );

    expect(store.view().streams[1].error).toBe('Поток изменён в Keitaro');
    expect(store.view().streams[1].pushDisabled).toBe(false);
    expect(store.view().streams[0].error).toBeNull();
  });

  it('ignores a second action on a busy stream', () => {
    openReady([makeStream(1), makeStream(2, { can_push: true })]);

    store.push(2);
    store.push(2);

    http.expectOne('/api/editor/streams/2/push').flush(makeStream(2));
  });

  it('ignores stream actions while fetching', () => {
    openReady();

    store.fetch();
    store.push(1);
    store.removeOffer(1, 7);

    http.expectOne('/api/editor/campaigns/1/fetch').flush({
      campaign: makeCampaign(1, [makeStream(1)]),
      kept_draft_stream_ids: [],
      notices: [],
    });
  });

  it('ignores fetch while a stream action is in progress', () => {
    openReady();

    store.push(1);
    store.fetch();

    http.expectOne('/api/editor/streams/1/push').flush(makeStream(1));
  });

  it('drops late responses for a previously opened campaign', () => {
    store.open('1');
    const firstRequest = http.expectOne('/api/editor/campaigns/1');
    store.open('2');
    const secondRequest = http.expectOne('/api/editor/campaigns/2');

    secondRequest.flush(makeCampaign(2, [makeStream(5)]));
    firstRequest.flush(makeCampaign(1, [makeStream(1)]));

    expect(store.view().header?.title).toBe('Campaign 2');
    expect(titles()).toEqual(['Stream 5']);
  });

  it('drops a late open error for a previously opened campaign', () => {
    store.open('1');
    const firstRequest = http.expectOne('/api/editor/campaigns/1');
    store.open('2');
    http.expectOne('/api/editor/campaigns/2').flush(makeCampaign(2, [makeStream(5)]));

    firstRequest.flush(
      { code: 'boom', message: 'Старая ошибка' },
      { status: 500, statusText: 'Server Error' },
    );

    expect(store.view().errorMessage).toBeNull();
    expect(titles()).toEqual(['Stream 5']);
  });

  it('drops a late action response started before the campaign changed', () => {
    openReady();
    store.push(1);
    const pushRequest = http.expectOne('/api/editor/streams/1/push');

    store.open('2');
    http.expectOne('/api/editor/campaigns/2').flush(makeCampaign(2, [makeStream(1)]));
    pushRequest.flush(makeStream(1, { name: 'Stale stream' }));

    expect(titles()).toEqual(['Stream 1']);
    expect(store.view().streams[0].pushDisabled).toBe(true);
    expect(store.view().fetchDisabled).toBe(false);
  });

  it('drops a late action error and a late fetch response after the campaign changed', () => {
    openReady();
    store.push(1);
    const pushRequest = http.expectOne('/api/editor/streams/1/push');
    store.open('2');
    http.expectOne('/api/editor/campaigns/2').flush(makeCampaign(2, [makeStream(1)]));

    pushRequest.error(new ProgressEvent('error'));

    expect(store.view().streams[0].error).toBeNull();

    store.fetch();
    const fetchRequest = http.expectOne('/api/editor/campaigns/2/fetch');
    store.open('3');
    http.expectOne('/api/editor/campaigns/3').flush(makeCampaign(3, [makeStream(9)]));
    fetchRequest.flush({
      campaign: makeCampaign(2, [makeStream(1)]),
      kept_draft_stream_ids: [],
      notices: [],
    });

    expect(store.view().header?.title).toBe('Campaign 3');
    expect(store.view().fetchDisabled).toBe(false);
  });

  it('maps campaign and offer search results to options', () => {
    let campaignOptions: unknown;
    let offerOptions: unknown;
    store.searchCampaigns('te').subscribe((options) => (campaignOptions = options));
    http
      .expectOne('/api/keitaro-campaigns?query=te')
      .flush([{ id: 5, name: 'test_oso4lq_a' }]);
    store.searchOffers('18').subscribe((options) => (offerOptions = options));
    http.expectOne('/api/offers?query=18').flush([{ id: 18813, name: 'Offer' }]);

    expect(campaignOptions).toEqual([{ id: 5, label: '5 — test_oso4lq_a' }]);
    expect(offerOptions).toEqual([{ id: 18813, label: '18813 — Offer' }]);
  });

  it('dismissing the force fetch confirmation closes it', () => {
    openReady();
    store.requestForceFetch();
    store.dismissForceFetch();

    expect(store.view().forceFetch.confirmOpen).toBe(false);
  });
});
