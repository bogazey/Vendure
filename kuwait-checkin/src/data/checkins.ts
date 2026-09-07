import type { CheckIn } from './types';

const photo = (seed: string) => `https://picsum.photos/seed/${seed}/500/500`;

// Seed check-ins from other mock users, so venue feeds have content from the start.
export const seedCheckIns: CheckIn[] = [
    {
        id: 'checkin-seed-1',
        userId: 'user-mariam',
        venueId: 'venue-dose-cafe',
        photoUrl: photo('dose-1'),
        caption: 'Best flat white in Shaab ☕️',
        timestamp: '2026-08-28T09:15:00.000Z',
    },
    {
        id: 'checkin-seed-2',
        userId: 'user-yousef',
        venueId: 'venue-avenues',
        photoUrl: photo('avenues-1'),
        caption: 'Sunday mall walk 🛍️',
        timestamp: '2026-08-30T14:40:00.000Z',
    },
    {
        id: 'checkin-seed-3',
        userId: 'user-dana',
        venueId: 'venue-lulu-al-rai',
        photoUrl: photo('lulu-1'),
        caption: 'Grocery run',
        timestamp: '2026-09-01T11:05:00.000Z',
    },
    {
        id: 'checkin-seed-4',
        userId: 'user-mariam',
        venueId: 'venue-marina-mall',
        photoUrl: photo('marina-1'),
        timestamp: '2026-09-02T18:20:00.000Z',
    },
    {
        id: 'checkin-seed-5',
        userId: 'user-yousef',
        venueId: 'venue-caribou-salmiya',
        photoUrl: photo('caribou-1'),
        caption: 'Iced americano days',
        timestamp: '2026-09-03T08:00:00.000Z',
    },
    {
        id: 'checkin-seed-6',
        userId: 'user-dana',
        venueId: 'venue-360-mall',
        photoUrl: photo('360-1'),
        caption: 'New season, new fit',
        timestamp: '2026-09-04T16:30:00.000Z',
    },
    {
        id: 'checkin-seed-7',
        userId: 'user-mariam',
        venueId: 'venue-xcite-al-rai',
        photoUrl: photo('xcite-1'),
        timestamp: '2026-09-05T12:10:00.000Z',
    },
    {
        id: 'checkin-seed-8',
        userId: 'user-yousef',
        venueId: 'venue-al-kout',
        photoUrl: photo('alkout-1'),
        caption: 'Fahaheel weekend trip',
        timestamp: '2026-09-05T19:45:00.000Z',
    },
];
