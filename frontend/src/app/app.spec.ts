import { TestBed } from '@angular/core/testing';
import { App } from './app';

describe('App', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
    }).compileComponents();
  });

  it('renders the application title', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const heading = fixture.nativeElement.querySelector('h1') as HTMLHeadingElement;
    expect(heading.textContent).toContain('Adrobot');
  });
});
