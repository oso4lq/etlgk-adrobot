import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { EditorPage } from './editor-page';

describe('EditorPage', () => {
  let fixture: ComponentFixture<EditorPage>;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(EditorPage);
  });

  afterEach(() => http.verify());

  function element(): HTMLElement {
    return fixture.nativeElement as HTMLElement;
  }

  function buttonByText(text: string): HTMLButtonElement | undefined {
    for (const button of Array.from(element().querySelectorAll('button'))) {
      if ((button.textContent ?? '').trim() === text) {
        return button;
      }
    }
    return undefined;
  }

  const notFetchedBody = { code: 'campaign_not_fetched', message: 'Кампания не загружена' };

  function emptyCampaign(): object {
    return {
      keitaro_campaign_id: 7,
      name: 'C7',
      write_allowed: true,
      last_fetched_at: '2026-11-24T10:00:00Z',
      streams: [],
    };
  }

  it('shows Fetch Streams for a campaign that was not fetched', async () => {
    fixture.componentRef.setInput('campaignId', '7');
    fixture.detectChanges();
    http
      .expectOne('/api/editor/campaigns/7')
      .flush(notFetchedBody, { status: 404, statusText: 'Not Found' });
    await fixture.whenStable();

    expect(element().textContent).toContain('Кампания 7 ещё не загружена в редактор');
    expect(buttonByText('Fetch Streams')).toBeDefined();
  });

  it('asks for confirmation before a forced fetch', async () => {
    fixture.componentRef.setInput('campaignId', '7');
    fixture.detectChanges();
    http
      .expectOne('/api/editor/campaigns/7')
      .flush(notFetchedBody, { status: 404, statusText: 'Not Found' });
    await fixture.whenStable();

    buttonByText('Fetch Streams')?.click();
    http
      .expectOne('/api/editor/campaigns/7/fetch')
      .flush({ campaign: emptyCampaign(), kept_draft_stream_ids: [3], notices: [] });
    await fixture.whenStable();

    buttonByText('Fetch Streams с отбросом черновиков')?.click();
    await fixture.whenStable();
    expect(element().textContent).toContain('Отбросить и загрузить');
    http.expectNone('/api/editor/campaigns/7/fetch?force=true');

    buttonByText('Отбросить и загрузить')?.click();
    http
      .expectOne('/api/editor/campaigns/7/fetch?force=true')
      .flush({ campaign: emptyCampaign(), kept_draft_stream_ids: [], notices: [] });
  });
});
