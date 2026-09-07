export type VenueCategory = 'mall' | 'coffee_shop' | 'supermarket' | 'store';

export interface User {
    id: string;
    name: string;
    username: string;
    profilePhoto: string;
    bio: string;
}

export interface Venue {
    id: string;
    name: string;
    category: VenueCategory;
    area: string;
    lat: number;
    lng: number;
    coverPhoto: string;
}

export interface CheckIn {
    id: string;
    userId: string;
    venueId: string;
    photoUrl: string;
    caption?: string;
    timestamp: string;
}
