import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import {
  EditorCampaign,
  EditorStream,
  FetchResult,
  KeitaroCampaignSummary,
  OfferSummary,
} from '../core/api-types';

@Injectable({ providedIn: 'root' })
export class EditorApi {
  private readonly http = inject(HttpClient);

  searchCampaigns(query: string): Observable<KeitaroCampaignSummary[]> {
    return this.http.get<KeitaroCampaignSummary[]>('/api/keitaro-campaigns', {
      params: new HttpParams().set('query', query),
    });
  }

  searchOffers(query: string): Observable<OfferSummary[]> {
    return this.http.get<OfferSummary[]>('/api/offers', {
      params: new HttpParams().set('query', query),
    });
  }

  getCampaign(campaignId: number): Observable<EditorCampaign> {
    return this.http.get<EditorCampaign>(`/api/editor/campaigns/${campaignId}`);
  }

  fetch(campaignId: number, force: boolean): Observable<FetchResult> {
    // The flag is sent only when forcing, so a plain fetch keeps the backend default.
    const params = force ? new HttpParams().set('force', 'true') : new HttpParams();
    return this.http.post<FetchResult>(`/api/editor/campaigns/${campaignId}/fetch`, null, {
      params,
    });
  }

  addOffer(streamId: number, offerId: number): Observable<EditorStream> {
    return this.http.post<EditorStream>(`/api/editor/streams/${streamId}/offers`, {
      offer_id: offerId,
    });
  }

  removeOffer(streamId: number, offerId: number): Observable<EditorStream> {
    return this.offerAction(streamId, offerId, 'remove');
  }

  bringBackOffer(streamId: number, offerId: number): Observable<EditorStream> {
    return this.offerAction(streamId, offerId, 'bring-back');
  }

  pinOffer(streamId: number, offerId: number): Observable<EditorStream> {
    return this.offerAction(streamId, offerId, 'pin');
  }

  unpinOffer(streamId: number, offerId: number): Observable<EditorStream> {
    return this.offerAction(streamId, offerId, 'unpin');
  }

  push(streamId: number): Observable<EditorStream> {
    return this.http.post<EditorStream>(`/api/editor/streams/${streamId}/push`, null);
  }

  cancel(streamId: number): Observable<EditorStream> {
    return this.http.post<EditorStream>(`/api/editor/streams/${streamId}/cancel`, null);
  }

  private offerAction(
    streamId: number,
    offerId: number,
    action: 'remove' | 'bring-back' | 'pin' | 'unpin',
  ): Observable<EditorStream> {
    return this.http.post<EditorStream>(
      `/api/editor/streams/${streamId}/offers/${offerId}/${action}`,
      null,
    );
  }
}
