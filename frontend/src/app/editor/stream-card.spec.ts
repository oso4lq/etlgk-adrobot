import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { OfferRowView, StreamView } from './editor-view';
import { StreamCard } from './stream-card';

function makeRow(overrides: Partial<OfferRowView> = {}): OfferRowView {
  return {
    offerId: 501,
    label: '501 — Offer',
    weightLabel: '50%',
    isPinned: false,
    isUnpublished: false,
    actionsDisabled: false,
    ...overrides,
  };
}

function makeStream(overrides: Partial<StreamView> = {}): StreamView {
  return {
    id: 10,
    title: 'Stream 10',
    idLabel: '#10',
    cssClass: 'stream stream--clean',
    isDraft: false,
    hasOffers: true,
    activeOffers: [],
    archivedOffers: [],
    showArchive: false,
    showTotal: false,
    totalLabel: '',
    totalIsOff: false,
    problems: [],
    warnings: [],
    error: null,
    pushDisabled: true,
    cancelDisabled: true,
    addDisabled: true,
    hiddenOfferIds: new Set(),
    offerSelection: null,
    ...overrides,
  };
}

describe('StreamCard', () => {
  let fixture: ComponentFixture<StreamCard>;

  function render(stream: StreamView): void {
    fixture = TestBed.createComponent(StreamCard);
    fixture.componentRef.setInput('stream', stream);
    fixture.componentRef.setInput('searchOffers', () => of([]));
    fixture.detectChanges();
  }

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

  it('renders a draft stream with the draft class and enabled push', async () => {
    render(
      makeStream({
        cssClass: 'stream stream--draft',
        isDraft: true,
        pushDisabled: false,
        cancelDisabled: false,
        activeOffers: [
          makeRow({ isPinned: true }),
          makeRow({ offerId: 502, label: '502 — B', isUnpublished: true }),
        ],
        showTotal: true,
        totalLabel: 'Итого: 100%',
      }),
    );
    await fixture.whenStable();

    expect(element().querySelector('.stream--draft')).not.toBeNull();
    expect(element().textContent).toContain('черновик');
    expect(element().textContent).toContain('закреплён');
    expect(element().textContent).toContain('не опубликован');
    expect(element().textContent).toContain('Итого: 100%');
    expect(buttonByText('Push to KT')?.disabled).toBe(false);
    expect(buttonByText('Cancel')?.disabled).toBe(false);
    expect(buttonByText('Unpin')).toBeDefined();
    expect(buttonByText('Pin')).toBeDefined();
  });

  it('renders archived offers with Bring back and 0%', async () => {
    render(
      makeStream({
        showArchive: true,
        archivedOffers: [makeRow({ offerId: 503, label: '503 — Old', weightLabel: '0%' })],
      }),
    );
    await fixture.whenStable();

    expect(element().textContent).toContain('Архив');
    expect(element().textContent).toContain('503 — Old');
    expect(element().textContent).toContain('0%');
    expect(element().querySelector('.offer--archived')).not.toBeNull();
    expect(buttonByText('Bring back')).toBeDefined();
  });

  it('renders a plain stream without buttons', async () => {
    render(makeStream({ hasOffers: false, cssClass: 'stream stream--plain' }));
    await fixture.whenStable();

    expect(element().textContent).toContain('поток без офферов');
    expect(element().querySelectorAll('button').length).toBe(0);
  });

  it('emits remove with the offer id', async () => {
    render(makeStream({ activeOffers: [makeRow({ offerId: 777 })] }));
    await fixture.whenStable();
    const removed: number[] = [];
    fixture.componentInstance.remove.subscribe((offerId) => removed.push(offerId));

    buttonByText('Remove')?.click();

    expect(removed).toEqual([777]);
  });
});
