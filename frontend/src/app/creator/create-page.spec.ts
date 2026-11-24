import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { CreatedCampaign } from '../core/api-types';
import { CreatePage } from './create-page';
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

describe('CreatePage', () => {
  let fixture: ComponentFixture<CreatePage>;
  let http: HttpTestingController;

  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(CreatePage);
    fixture.detectChanges();
    http.expectOne('/api/countries').flush([{ code: 'AU', name: 'Australia' }]);
    http.expectOne('/api/created-campaigns').flush([]);
    await fixture.whenStable();
  });

  afterEach(() => http.verify());

  function element(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function createButton(): HTMLButtonElement {
    return element().querySelector('button[type="submit"]') as HTMLButtonElement;
  }

  it('renders Name, Geo, Offer and a disabled Create button', () => {
    const text = element().textContent ?? '';
    expect(text).toContain('Name');
    expect(text).toContain('Geo');
    expect(text).toContain('Offer');
    expect(text).toContain('Выберите страну');
    expect(element().querySelector('option[value="AU"]')).not.toBeNull();
    expect(createButton().textContent).toContain('Create');
    expect(createButton().disabled).toBe(true);
  });

  it('keeps the journal table inside its own horizontally scrollable block', () => {
    expect(element().querySelector('.journal-scroll > table.journal')).not.toBeNull();
  });

  it('shows the result block with an editor link after creation', async () => {
    const input = element().querySelector('input[type="text"]') as HTMLInputElement;
    input.value = 'test_oso4lq_x';
    input.dispatchEvent(new Event('input'));
    const select = element().querySelector('select') as HTMLSelectElement;
    select.value = 'AU';
    select.dispatchEvent(new Event('input'));
    // The autocomplete is a separate component; the page forwards its selection to the store.
    const autocomplete = element().querySelector('app-autocomplete') as HTMLElement;
    expect(autocomplete).not.toBeNull();
    fixture.debugElement.injector
      .get(CreatorStore)
      .selectOffer({ id: 18813, label: '18813 — Test offer' });
    fixture.detectChanges();
    await fixture.whenStable();
    expect(createButton().disabled).toBe(false);

    createButton().click();
    http.expectOne('/api/campaigns').flush(created);
    http.expectOne('/api/created-campaigns').flush([]);
    await fixture.whenStable();

    expect(element().textContent).toContain('Кампания создана');
    const link = element().querySelector('a[href="/editor/215338"]');
    expect(link?.textContent).toContain('Открыть в редакторе');
  });
});
