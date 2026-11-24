import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { App } from './app';

describe('App', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [provideRouter([])],
    }).compileComponents();
  });

  it('renders the application title', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const heading = fixture.nativeElement.querySelector('h1') as HTMLHeadingElement;
    expect(heading.textContent).toContain('Adrobot');
  });

  it('renders navigation links', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const links = fixture.nativeElement.querySelectorAll('nav a') as NodeListOf<HTMLAnchorElement>;
    expect(links[0].textContent?.trim()).toBe('Create');
    expect(links[0].getAttribute('href')).toBe('/create');
    expect(links[1].textContent?.trim()).toBe('Editor');
    expect(links[1].getAttribute('href')).toBe('/editor');
  });
});
