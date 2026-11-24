import { HttpErrorResponse } from '@angular/common/http';
import { Component, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Subject } from 'rxjs';
import { Autocomplete, AutocompleteOption } from './autocomplete';

@Component({
  imports: [Autocomplete],
  template: `
    <app-autocomplete
      label="Offer"
      [search]="search"
      [selection]="selection()"
      [hiddenIds]="hiddenIds()"
      (selectionChange)="changes.push($event)"
    />
  `,
})
class HostComponent {
  readonly selection = signal<AutocompleteOption | null>(null);
  readonly hiddenIds = signal<ReadonlySet<number>>(new Set());
  readonly changes: (AutocompleteOption | null)[] = [];
  readonly requests: { query: string; response: Subject<AutocompleteOption[]> }[] = [];

  readonly search = (query: string) => {
    const response = new Subject<AutocompleteOption[]>();
    this.requests.push({ query, response });
    return response;
  };
}

describe('Autocomplete', () => {
  let fixture: ComponentFixture<HostComponent>;
  let host: HostComponent;
  let root: HTMLElement;

  const alpha: AutocompleteOption = { id: 1, label: 'Alpha' };
  const beta: AutocompleteOption = { id: 2, label: 'Beta' };

  function inputElement(): HTMLInputElement {
    return root.querySelector('input') as HTMLInputElement;
  }

  function type(text: string): void {
    const input = inputElement();
    input.value = text;
    input.dispatchEvent(new Event('input'));
  }

  async function pause(): Promise<void> {
    await vi.advanceTimersByTimeAsync(250);
    fixture.detectChanges();
    await fixture.whenStable();
  }

  function suggestionLabels(): string[] {
    const labels: string[] = [];
    for (const button of Array.from(root.querySelectorAll('li button'))) {
      labels.push((button.textContent ?? '').trim());
    }
    return labels;
  }

  beforeEach(() => {
    vi.useFakeTimers();
    fixture = TestBed.createComponent(HostComponent);
    host = fixture.componentInstance;
    root = fixture.nativeElement;
    fixture.detectChanges();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('searches after a 250 ms pause', async () => {
    type('50');
    await vi.advanceTimersByTimeAsync(249);
    expect(host.requests).toHaveLength(0);

    await vi.advanceTimersByTimeAsync(1);
    expect(host.requests).toHaveLength(1);
    expect(host.requests[0].query).toBe('50');
  });

  it('shows suggestions only for the latest query', async () => {
    type('1');
    await pause();
    type('12');
    await pause();
    expect(host.requests.map((request) => request.query)).toEqual(['1', '12']);

    host.requests[1].response.next([beta]);
    host.requests[0].response.next([alpha]);
    fixture.detectChanges();

    expect(suggestionLabels()).toEqual(['Beta']);
  });

  it('hides options listed in hiddenIds', async () => {
    host.hiddenIds.set(new Set([1]));
    fixture.detectChanges();
    type('a');
    await pause();
    host.requests[0].response.next([alpha, beta]);
    fixture.detectChanges();

    expect(suggestionLabels()).toEqual(['Beta']);
  });

  it('emits the chosen option and closes the list', async () => {
    type('a');
    await pause();
    host.requests[0].response.next([alpha, beta]);
    fixture.detectChanges();

    (root.querySelectorAll('li button')[1] as HTMLButtonElement).click();
    fixture.detectChanges();

    expect(host.changes).toEqual([beta]);
    expect(inputElement().value).toBe('Beta');
    expect(suggestionLabels()).toEqual([]);
  });

  it('emits null once when the text is edited after a choice', async () => {
    type('a');
    await pause();
    host.requests[0].response.next([alpha]);
    fixture.detectChanges();
    (root.querySelector('li button') as HTMLButtonElement).click();
    host.selection.set(alpha);
    fixture.detectChanges();

    type('Alph');
    type('Alp');
    host.selection.set(null);
    fixture.detectChanges();

    expect(host.changes).toEqual([alpha, null]);
    expect(inputElement().value).toBe('Alp');
  });

  it('clears the text when selection becomes null', async () => {
    host.selection.set(alpha);
    fixture.detectChanges();
    expect(inputElement().value).toBe('Alpha');

    host.selection.set(null);
    fixture.detectChanges();

    expect(inputElement().value).toBe('');
    expect(host.changes).toEqual([]);
  });

  it('shows a search error message', async () => {
    type('a');
    await pause();
    host.requests[0].response.error(
      new HttpErrorResponse({
        status: 503,
        error: { code: 'keitaro_unavailable', message: 'Keitaro недоступен' },
      }),
    );
    fixture.detectChanges();

    expect(root.textContent).toContain('Поиск недоступен: Keitaro недоступен');
  });

  it('does not reopen the list when a choice overtakes a pending search', async () => {
    type('a');
    await pause();
    host.requests[0].response.next([alpha]);
    fixture.detectChanges();

    type('b');
    (root.querySelector('li button') as HTMLButtonElement).click();
    await pause();
    expect(host.requests).toHaveLength(2);
    host.requests[1].response.next([beta]);
    fixture.detectChanges();

    expect(suggestionLabels()).toEqual([]);
    expect(inputElement().value).toBe('Alpha');
  });

  it('prevents mousedown on the list so the input keeps focus', async () => {
    type('a');
    await pause();
    host.requests[0].response.next([alpha]);
    fixture.detectChanges();

    const event = new MouseEvent('mousedown', { cancelable: true, bubbles: true });
    root.querySelector('ul')!.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(true);
  });

  it('does not open the list when a search finishes after the field lost focus', async () => {
    type('Al');
    await pause();
    inputElement().dispatchEvent(new FocusEvent('focusout', { bubbles: true, relatedTarget: null }));
    host.requests[0].response.next([alpha]);
    fixture.detectChanges();

    expect(suggestionLabels()).toEqual([]);
  });
});
