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
});
