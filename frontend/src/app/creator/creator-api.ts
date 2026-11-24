import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { Country, CreatedCampaign, JournalEntry, OfferSummary } from '../core/api-types';

export interface CreateCampaignBody {
  name: string;
  country: string;
  offer_id: number;
}

@Injectable({ providedIn: 'root' })
export class CreatorApi {
  private readonly http = inject(HttpClient);

  countries(): Observable<Country[]> {
    return this.http.get<Country[]>('/api/countries');
  }

  searchOffers(query: string): Observable<OfferSummary[]> {
    return this.http.get<OfferSummary[]>('/api/offers', { params: new HttpParams().set('query', query) });
  }

  createCampaign(body: CreateCampaignBody): Observable<CreatedCampaign> {
    return this.http.post<CreatedCampaign>('/api/campaigns', body);
  }

  journal(): Observable<JournalEntry[]> {
    return this.http.get<JournalEntry[]>('/api/created-campaigns');
  }
}
