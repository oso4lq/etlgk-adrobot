import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { CreatedCampaign } from '../core/api-types';
import { CreatorStore } from './creator-store';

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

describe('CreatorStore', () => {
  let store: CreatorStore;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [CreatorStore, provideHttpClient(), provideHttpClientTesting()],
    });
    store = TestBed.inject(CreatorStore);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  function fillForm(): void {
    store.model.set({ name: '  test_oso4lq_x  ', country: 'AU' });
    store.selectOffer({ id: 18813, label: '18813 — Test offer' });
  }

  it('loads countries and journal', () => {
    store.load();
    http.expectOne('/api/countries').flush([{ code: 'AU', name: 'Australia' }]);
    http.expectOne('/api/created-campaigns').flush([]);

    expect(store.view().countryOptions).toEqual([{ code: 'AU', label: 'AU — Australia' }]);
    expect(store.view().journalRows).toEqual([]);
  });

  it('posts trimmed name and clears the form on success', () => {
    fillForm();
    store.submit();
    const request = http.expectOne('/api/campaigns');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({ name: 'test_oso4lq_x', country: 'AU', offer_id: 18813 });
    request.flush(created);

    expect(store.view().result?.editorLink).toBe('/editor/215338');
    expect(store.model().name).toBe('');
    expect(store.offer()).toBeNull();
    http.expectOne('/api/created-campaigns').flush([]);
  });

  it('keeps the input and shows the API message on failure', () => {
    fillForm();
    store.submit();
    http
      .expectOne('/api/campaigns')
      .flush(
        { code: 'name_prefix_required', message: 'Имя должно начинаться с префикса' },
        { status: 422, statusText: 'Unprocessable Entity' },
      );

    expect(store.view().error).toBe('Имя должно начинаться с префикса');
    expect(store.model().name).toBe('  test_oso4lq_x  ');
    expect(store.offer()?.id).toBe(18813);
    http.expectOne('/api/created-campaigns').flush([]);
  });

  it('ignores a second submit while creating', () => {
    fillForm();
    store.submit();
    store.submit();

    const requests = http.match('/api/campaigns');
    expect(requests.length).toBe(1);
    requests[0].flush(created);
    http.expectOne('/api/created-campaigns').flush([]);
  });

  it('drops the previous result and error when a new submit starts or fails', () => {
    fillForm();
    store.submit();
    http.expectOne('/api/campaigns').flush(created);
    http.expectOne('/api/created-campaigns').flush([]);
    expect(store.view().result).not.toBeNull();

    fillForm();
    store.submit();
    expect(store.view().result).toBeNull();
    http
      .expectOne('/api/campaigns')
      .flush(
        { code: 'keitaro_error', message: 'Keitaro недоступен' },
        { status: 502, statusText: 'Bad Gateway' },
      );

    expect(store.view().result).toBeNull();
    expect(store.view().error).toBe('Keitaro недоступен');
    http.expectOne('/api/created-campaigns').flush([]);

    store.submit();
    expect(store.view().error).toBeNull();
    http.expectOne('/api/campaigns').flush(created);
    http.expectOne('/api/created-campaigns').flush([]);
  });

  it('does not send a request for a whitespace-only name', () => {
    store.model.set({ name: '   ', country: 'AU' });
    store.selectOffer({ id: 18813, label: '18813 — Test offer' });
    store.submit();

    http.expectNone('/api/campaigns');
  });

  describe('create error is tied to the submitted values', () => {
    const otherOffer = { id: 999, label: '999 — Other offer' };

    function failSubmit(): void {
      fillForm();
      store.submit();
      http
        .expectOne('/api/campaigns')
        .flush(
          { code: 'name_prefix_required', message: 'Название кампании должно начинаться с «test_oso4lq_»' },
          { status: 422, statusText: 'Unprocessable Entity' },
        );
      http.expectOne('/api/created-campaigns').flush([]);
    }

    it('hides the error once the name is edited', () => {
      failSubmit();
      expect(store.view().error).not.toBeNull();

      store.model.set({ name: 'test_oso4lq_y', country: 'AU' });

      expect(store.view().error).toBeNull();
    });

    it('hides the error once the country is changed', () => {
      failSubmit();

      store.model.set({ name: '  test_oso4lq_x  ', country: 'DE' });

      expect(store.view().error).toBeNull();
    });

    it('hides the error once another offer is selected', () => {
      failSubmit();

      store.selectOffer(otherOffer);

      expect(store.view().error).toBeNull();
    });

    it('shows the error again when the failed values are restored', () => {
      failSubmit();
      store.model.set({ name: 'test_oso4lq_y', country: 'AU' });
      expect(store.view().error).toBeNull();

      store.model.set({ name: 'test_oso4lq_x', country: 'AU' });

      expect(store.view().error).toBe('Название кампании должно начинаться с «test_oso4lq_»');
    });

    it('keeps the countries load error visible after the name is edited', () => {
      store.load();
      http
        .expectOne('/api/countries')
        .flush({ code: 'keitaro_error', message: 'Keitaro недоступен' }, { status: 502, statusText: 'Bad Gateway' });
      http.expectOne('/api/created-campaigns').flush([]);

      store.model.set({ name: 'test_oso4lq_y', country: '' });

      expect(store.view().error).toBe('Keitaro недоступен');
    });
  });
});
